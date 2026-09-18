"""Bounded per-company/per-scope public recruitment refresh in the existing daily chain.

Adapter contract: collect(company, scope, output_dir) -> {jobs: [...], coverage: {...}}.
Each invocation runs in an isolated process. Only validated complete snapshots may
remove previously P1-owned records; partial sources retain old records.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import copy
import datetime as dt
from .portable_runtime import fcntl, stop_tree
import hashlib
import gzip
import importlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import urlsplit
from . import p1_pending_index as N

from qiuzhao.normalize import normalize_records
from qiuzhao.v4_fields import graduation_of, graduation_constraints_of, iter_json_file

COMPANIES = [
    '拼多多', '大疆', '华为', '小红书', '快手', 'OPPO', 'vivo', '荣耀', '比亚迪', '宁德时代',
    '米哈游', '哔哩哔哩', '蚂蚁集团', '百度', '滴滴', '携程', '联想', '海康威视', '安克创新', '影石Insta360',
    '鹰角网络', '叠纸游戏', '莉莉丝游戏', '完美世界', '三七互娱', '巨人网络', '金山办公', '用友网络', '金蝶', '科大讯飞',
    '商汤科技', '中兴通讯', '大华股份', '汇川技术', 'TP-LINK普联', '石头科技', '科沃斯', '理想汽车', '小鹏汽车', '蔚来汽车',
    '吉利汽车', '长城汽车', '迈瑞医疗', '恒瑞医药', '药明康德', '小米', '京东', '美团', '网易', '得物',
]
SCOPES = {'campus': '校园招聘', 'intern': '实习招聘', 'social': '社会招聘'}
# Stable order is the user-approved priority list. Missing modules are blocked,
# never interpreted as an empty successful source.
REGISTRY = {name: f'qiuzhao.collector.p1_sources_{(i // 10) * 10 + 1:02d}_{(i // 10 + 1) * 10:02d}'
            for i, name in enumerate(COMPANIES)}

# Platform-level adapters (Beisen zhiye.com / Moka) register every company
# declared in p1_platform_companies.json without another REGISTRY edit.
try:
    from .p1_platform_beisen import merged_registry as _platform_registry
    REGISTRY.update(_platform_registry())
except Exception:  # optional platform config may be absent in a minimal checkout
    pass

# Bank-specific adapters (batch 1) register their companies the same way, so the
# hardcoded 50 ordinals never change.
try:
    from .p1_banks_01 import merged_registry as _banks_registry
    REGISTRY.update(_banks_registry())
except Exception:  # optional bank adapters may be absent in a minimal checkout
    pass

# Ali/Tencent gap adapters (batch 2, 20260918e) register their companies the same
# way and are appended here so the hardcoded 50 ordinals and the batch-1 block
# above stay untouched.
try:
    from .alibaba_headless import merged_registry as _alibaba_registry
    REGISTRY.update(_alibaba_registry())
except Exception:  # optional Ali adapters may be absent in a minimal checkout
    pass

try:
    from .tencent_music import merged_registry as _tencent_music_registry
    REGISTRY.update(_tencent_music_registry())
except Exception:  # optional Tencent Music adapter may be absent in a minimal checkout
    pass

# Foreign-company platform adapters (Workday CXS / SAP SuccessFactors). This is an
# append-only block independent of the platform/bank blocks above, so it never touches
# the hardcoded 50-ordinal list and merges cleanly with the other executors' blocks.
try:
    from .p1_platform_workday import merged_registry as _workday_registry
    REGISTRY.update(_workday_registry())
except Exception:  # optional platform config may be absent in a minimal checkout
    pass
try:
    from .p1_platform_successfactors import merged_registry as _sf_registry
    REGISTRY.update(_sf_registry())
except Exception:  # optional platform config may be absent in a minimal checkout
    pass

# Feishu platform adapter (config-driven, appended as an independent registration
# block). setdefault keeps the hardcoded 50 and the beisen/moka entries winning, so
# migrating 小鹏/蔚来/影石/莉莉丝/商汤 into the feishu config cannot replace their
# dedicated p1_sources_* adapters; only new feishu tenants from the JSON are added.
try:
    from .p1_feishu_public import merged_registry as _feishu_registry
    for _feishu_name, _feishu_module in _feishu_registry().items():
        REGISTRY.setdefault(_feishu_name, _feishu_module)
except Exception:  # optional platform config may be absent in a minimal checkout
    pass

# ByteDance public-API adapter (batch 3, 20260918i). 字节跳动 is not one of the
# hardcoded 50, so this appends it as one more platform-style company with all
# three scopes; it publishes the historical 'bytedance-<job post id>' identity via
# coverage['stable_id_prefix'] so the 4171 existing rows are updated in place
# instead of being duplicated under a fresh hash namespace.
try:
    from .p1_bytedance_public import merged_registry as _bytedance_registry
    REGISTRY.update(_bytedance_registry())
except Exception:  # optional ByteDance adapter may be absent in a minimal checkout
    pass

# Midea public school-recruitment adapter (same batch). 美的集团 also keeps its
# historical 'midea-<positionId>' identity through the same opt-in prefix, so the
# 146 live rows are refreshed instead of replaced.  Its social scope is blocked by
# design: the public school API does not expose experienced postings.
try:
    from .p1_midea_public import merged_registry as _midea_registry
    REGISTRY.update(_midea_registry())
except Exception:  # optional Midea adapter may be absent in a minimal checkout
    pass

# Foreign-company dedicated adapters, batch 2 (Dayee hotjob.cn — Deloitte and the
# other foreign employers on that multi-tenant portal). Append-only independent
# registration block: it only adds names to REGISTRY, so the hardcoded 50 ordinals
# and every earlier block stay byte-identical and merge cleanly.
try:
    from .p1_foreign_01 import merged_registry as _foreign01_registry
    REGISTRY.update(_foreign01_registry())
except Exception:  # optional foreign adapters may be absent in a minimal checkout
    pass

# 51job corporate campus micro-sites (public server-rendered pages, no account).
# Append-only independent registration block, same contract as the blocks above.
try:
    from .p1_platform_51job import merged_registry as _job51_registry
    REGISTRY.update(_job51_registry())
except Exception:  # optional micro-site adapters may be absent in a minimal checkout
    pass

# Foreign-company ATS adapters, batch A (20260919b). Eightfold AI public careers
# tenants (惠普/微软/高通/应用材料/泛林) and Phenom People public careers tenants
# (宝洁/玛氏/罗氏/波士顿咨询/ABB/飞利浦/默沙东/思科). Both read the JSON the
# public careers page itself asks for; neither logs in, signs or solves anything.
# Append-only independent registration block: it only adds names to REGISTRY, so
# the hardcoded 50 ordinals and every earlier block stay byte-identical.
try:
    from .p1_platform_eightfold import merged_registry as _eightfold_registry
    REGISTRY.update(_eightfold_registry())
except Exception:  # optional Eightfold adapters may be absent in a minimal checkout
    pass

try:
    from .p1_platform_phenom import merged_registry as _phenom_registry
    REGISTRY.update(_phenom_registry())
except Exception:  # optional Phenom adapters may be absent in a minimal checkout
    pass

# Foreign batch 3 (20260919c): Avature portals, iCIMS Career Portal and Oracle
# Recruiting Cloud candidate-experience sites. Three more append-only registration
# blocks placed after every existing block, so the hardcoded 50 ordinals and all
# earlier registrations stay byte-identical and the merge stays conflict-free.
try:
    from .p1_platform_avature import merged_registry as _avature_registry
    REGISTRY.update(_avature_registry())
except Exception:  # optional platform adapters may be absent in a minimal checkout
    pass
try:
    from .p1_platform_icims import merged_registry as _icims_registry
    REGISTRY.update(_icims_registry())
except Exception:  # optional platform adapters may be absent in a minimal checkout
    pass
try:
    from .p1_platform_orc import merged_registry as _orc_registry
    REGISTRY.update(_orc_registry())
except Exception:  # optional platform adapters may be absent in a minimal checkout
    pass

# tupu360 (foreign batch C, 20260919f): multi-tenant recruitment sites used by
# 雀巢 / 路易威登 / 强生 / 礼来 / 舍弗勒 / 宝马 / Google / IQVIA and others.
# Append-only independent registration block, same contract as the blocks above.
# setdefault, not update: 强生 already has an approved Workday entry (jj/wd5/JJ)
# and an append-only block must never displace a company another adapter owns.
try:
    from .p1_platform_tupu360 import merged_registry as _tupu360_registry
    for _tupu360_name, _tupu360_module in _tupu360_registry().items():
        REGISTRY.setdefault(_tupu360_name, _tupu360_module)
except Exception:  # optional tupu360 adapters may be absent in a minimal checkout
    pass

# The daily chain is invoked without --companies, so the default set must contain
# every extra adapter company, not only the hardcoded 50. Hardcoded companies
# keep their approved priority order; platform companies follow in config order
# (beisen then moka, deduplicated against the hardcoded names because
# 三七互娱 / 金山办公 / 鹰角网络 appear in both lists), then the bank block, then
# the Ali/Tencent gap block, then the foreign Workday/SuccessFactors block, then
# config-driven Feishu tenants (setdefault, so they never displace an earlier
# adapter), then the 20260918i public-API daily adapters (字节跳动/美的集团), then
# the 20260918j foreign batch-2 blocks (Dayee hotjob.cn, then the 51job
# micro-sites), then the 20260919b foreign batch-A blocks (Eightfold AI, then
# Phenom People), then the 20260919c foreign batch-3 platform blocks (Avature,
# iCIMS, Oracle Recruiting Cloud), and finally the 20260919f tupu360 block
# (setdefault, so the parked/duplicate names never displace an earlier adapter).
# Every append-only block is kept verbatim, so no earlier company changes slot.
PLATFORM_COMPANIES = [name for name in REGISTRY if name not in COMPANIES]
DEFAULT_COMPANIES = [*COMPANIES, *PLATFORM_COMPANIES]

# --- 905+ company scheduling safety ------------------------------------------
# 站长 2026-09-18 最终口径：每家公司每天全跑、社招也跑。Platform-host adapters
# default to all three scopes (campus + intern + social); a config entry can still
# narrow one company with an explicit "scopes" list. The hardcoded 50 and the
# Ali/Tencent gap adapters keep all three scopes as before.
PLATFORM_MODULES = frozenset({
    'qiuzhao.collector.p1_platform_beisen',
    'qiuzhao.collector.p1_platform_moka',
    'qiuzhao.collector.p1_feishu_public',
    'qiuzhao.collector.p1_platform_workday',
    'qiuzhao.collector.p1_platform_successfactors',
    'qiuzhao.collector.p1_banks_01',
    # Foreign batch 2 (20260918j): Dayee multi-tenant portal and 51job campus
    # micro-sites are shared upstream hosts, so they belong to the platform gate
    # (same-host concurrency <= PLATFORM_WORKERS, >= PLATFORM_MIN_INTERVAL apart).
    'qiuzhao.collector.p1_foreign_01',
    'qiuzhao.collector.p1_platform_51job',
    # Foreign batch A (20260919b): Eightfold AI and Phenom People are shared
    # upstream platforms, so every tenant of each belongs to the platform gate
    # (same-platform concurrency <= PLATFORM_WORKERS, >= PLATFORM_MIN_INTERVAL apart).
    'qiuzhao.collector.p1_platform_eightfold',
    'qiuzhao.collector.p1_platform_phenom',
    # Foreign batch 3 (20260919c): Avature portals (shared *.avature.net / branded
    # Avature hosts), iCIMS Career Portal and Oracle Recruiting Cloud all live on
    # shared upstream hosts, so they belong to the platform gate as well.
    'qiuzhao.collector.p1_platform_avature',
    'qiuzhao.collector.p1_platform_icims',
    'qiuzhao.collector.p1_platform_orc',
    # Foreign batch C (20260919f): tupu360 is one shared upstream platform
    # (careersite.tupu360.com + customer-hosted tenants), so it belongs to the
    # platform gate (same-host concurrency <= PLATFORM_WORKERS, >=
    # PLATFORM_MIN_INTERVAL apart).
    'qiuzhao.collector.p1_platform_tupu360',
})
PLATFORM_DEFAULT_SCOPES = ('campus', 'intern', 'social')
# Per-platform concurrency cap and minimum spacing between same-host unit launches.
PLATFORM_WORKERS = 2
PLATFORM_MIN_INTERVAL = 1.0
# Day rotation is kept as an operational lever but is OFF by default (1 = run the
# full set every day). Set --platform-rotation N>1 only if a full day cannot fit.
ROTATING_MODULES = frozenset({
    'qiuzhao.collector.p1_platform_beisen',
    'qiuzhao.collector.p1_platform_moka',
    'qiuzhao.collector.p1_feishu_public',
})
PLATFORM_ROTATION_DEFAULT = 1
PLATFORM_HOST_GROUPS = {
    'qiuzhao.collector.p1_platform_beisen': 'zhiye.com',
    'qiuzhao.collector.p1_platform_moka': 'app.mokahr.com',
    'qiuzhao.collector.p1_feishu_public': 'jobs.feishu.cn',
    'qiuzhao.collector.p1_platform_workday': 'myworkdayjobs.com',
    'qiuzhao.collector.p1_platform_successfactors': 'successfactors',
    'qiuzhao.collector.p1_banks_01': 'banks',
    'qiuzhao.collector.alibaba_headless': 'alibaba',
    'qiuzhao.collector.tencent_music': 'tencent_music',
    'qiuzhao.collector.p1_foreign_01': 'hotjob.cn',
    'qiuzhao.collector.p1_platform_51job': '51job.com',
    'qiuzhao.collector.p1_platform_eightfold': 'eightfold',
    'qiuzhao.collector.p1_platform_phenom': 'phenom',
    # Foreign batch 3 (20260919c). Avature portals share the *.avature.net front end;
    # iCIMS portals share the iCIMS Career Portal; ORC tenants share Oracle Cloud HCM.
    'qiuzhao.collector.p1_platform_avature': 'avature',
    'qiuzhao.collector.p1_platform_icims': 'icims',
    'qiuzhao.collector.p1_platform_orc': 'oraclecloud',
    'qiuzhao.collector.p1_platform_tupu360': 'tupu360.com',
}


def _load_scope_opt_ins():
    """Per-company scope override from object entries in the platform config.

    A platform company now defaults to all three scopes (campus+intern+social).
    An object entry may carry ``"scopes": ["campus","intern"]`` (a bare string also
    works) to narrow that company explicitly. Missing/invalid config yields no
    overrides, so the full default set applies.
    """
    opt_ins = {}
    try:
        from .p1_platform_beisen import CONFIG_PATH
        data = json.loads(Path(CONFIG_PATH).read_text(encoding='utf-8'))
    except Exception:  # optional platform config may be absent in a minimal checkout
        return opt_ins
    for section in ('beisen', 'moka', 'feishu', 'workday', 'successfactors',
                    'dayee', 'job51', 'eightfold', 'phenom', 'avature', 'icims',
                    'orc', 'tupu360'):
        entries = data.get(section)
        if not isinstance(entries, dict):
            continue
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            name = str(entry.get('name') or '').strip()
            raw = entry.get('scopes')
            if not name or raw is None:
                continue
            if isinstance(raw, str):
                raw = [raw]
            if not isinstance(raw, list):
                continue
            enabled = {str(scope) for scope in raw if str(scope) in SCOPES}
            if enabled:
                opt_ins[name] = enabled
    return opt_ins


PLATFORM_SCOPE_OPT_INS = _load_scope_opt_ins()


def _load_platform_slugs():
    """``company name -> config slug`` for deterministic rotation hashing."""
    mapping = {}
    for module_name in ('p1_platform_beisen', 'p1_platform_moka', 'p1_feishu_public'):
        try:
            module = importlib.import_module('qiuzhao.collector.' + module_name)
        except Exception:  # optional module may be absent in a minimal checkout
            continue
        mapping.update(getattr(module, 'NAME_TO_SLUG', {}) or {})
    return mapping


PLATFORM_SLUGS = _load_platform_slugs()


def company_scopes(company, scopes=None):
    """Effective scopes for one company, restricted to the requested list.

    Since the 2026-09-18 final policy every scope family defaults to all three
    scopes and ``social`` is no longer skipped. A platform config entry can still
    narrow a company through an explicit ``scopes`` override.
    """
    requested = list(scopes) if scopes is not None else list(SCOPES)
    if company in COMPANIES:
        # The hardcoded 50 keep all three scopes even when a platform config line
        # shadows their REGISTRY entry (三七互娱 / 金山办公 / 鹰角网络).
        allowed = tuple(SCOPES)
    elif REGISTRY.get(company) in PLATFORM_MODULES:
        enabled = PLATFORM_SCOPE_OPT_INS.get(company)
        allowed = (tuple(scope for scope in SCOPES if scope in enabled)
                   if enabled else PLATFORM_DEFAULT_SCOPES)
    else:
        allowed = tuple(SCOPES)
    return [scope for scope in requested if scope in allowed]


def platform_group(company):
    """Upstream host family used for the per-platform concurrency gate."""
    module = REGISTRY.get(company)
    return PLATFORM_HOST_GROUPS.get(module) or 'company:' + str(company)


def platform_rotation_group(company, groups):
    """Deterministic day bucket (0..groups-1) for a rotating platform company."""
    groups = max(1, int(groups))
    slug = PLATFORM_SLUGS.get(company, company)
    digest = hashlib.sha256(str(slug).encode('utf-8')).digest()
    return int.from_bytes(digest[:8], 'big') % groups


def companies_for_day(companies, groups, day=None):
    """Drop rotating platform companies outside today's bucket.

    Every non-rotating company (hardcoded 50, banks, Ali/Tencent, Workday/SF) is
    kept, so the daily chain always covers them.
    """
    groups = max(1, int(groups))
    if groups == 1:
        return list(companies)
    day = day or dt.datetime.now(dt.timezone.utc).date()
    bucket = day.toordinal() % groups
    def rotating(company):
        return company not in COMPANIES and REGISTRY.get(company) in ROTATING_MODULES
    return [company for company in companies
            if not rotating(company)
            or platform_rotation_group(company, groups) == bucket]


class PlatformGate:
    """Per-platform concurrency cap plus spacing between same-host unit launches.

    The pipeline cannot observe individual adapter HTTP calls, so the throttle
    bounds what it does control: at most ``workers_per_platform`` units of one
    upstream host run concurrently, and consecutive launches on that host are
    spaced at least ``min_interval`` seconds apart. Adapters keep their own request
    pacing; ``collect_process`` additionally injects
    ``QIUZHAO_PLATFORM_REQUEST_INTERVAL`` for adapters that honour it.
    """

    def __init__(self, workers_per_platform=PLATFORM_WORKERS,
                 min_interval=PLATFORM_MIN_INTERVAL):
        self.workers_per_platform = max(1, int(workers_per_platform))
        self.min_interval = max(0.0, float(min_interval))
        self._guard = threading.Lock()
        self._semaphores = {}
        self._next_start = {}

    def _semaphore(self, platform):
        with self._guard:
            semaphore = self._semaphores.get(platform)
            if semaphore is None:
                semaphore = threading.Semaphore(self.workers_per_platform)
                self._semaphores[platform] = semaphore
            return semaphore

    def acquire(self, platform):
        semaphore = self._semaphore(platform)
        semaphore.acquire()
        if self.min_interval <= 0:
            return semaphore
        while True:
            with self._guard:
                current = time.monotonic()
                target = self._next_start.get(platform, 0.0)
                if current >= target:
                    self._next_start[platform] = current + self.min_interval
                    return semaphore
                wait = target - current
            time.sleep(min(wait, 0.25))

    def release(self, platform):
        self._semaphore(platform).release()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def stream_sha(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1 << 20), b''):
        digest.update(chunk)
    return digest.hexdigest()


def sha(path):
    with path.open('rb') as stream:
        return stream_sha(stream)


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            st = path.stat()
            os.chmod(temporary, st.st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def blocked(reason, status='blocked'):
    return {'jobs': [], 'coverage': {'status': status, 'complete': False,
            'detail_complete': False, 'expected_total': None, 'collected_jobs': 0,
            'pages_scanned': 0, 'errors': [reason], 'checked_at': now()}}


def validate_result(payload, company, scope, evidence_dir=None):
    """Reject malformed evidence instead of letting a source corrupt the shared store."""
    if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
        raise ValueError('adapter result must contain jobs list')
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or coverage.get('status') not in {'success', 'partial', 'blocked'}:
        raise ValueError('invalid coverage status')
    result = copy.deepcopy(payload)
    coverage = result['coverage']
    rows = result['jobs']
    if coverage.get('collected_jobs') != len(rows):
        raise ValueError('coverage count differs from returned jobs')
    if coverage.get('status') == 'blocked' and rows:
        raise ValueError('blocked result cannot publish rows')
    pending=N.normalize_pending_index(result.get('pending_index',[]),company,scope,SCOPES[scope])
    result['pending_index']=pending
    if (rows or pending or coverage.get('complete') is True) and not coverage.get('scope_evidence'):
        raise ValueError('missing official scope evidence')
    identities = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('job must be an object')
        for key in ('source_record_id', 'job_title', 'description_raw', 'recruitment_unit'):
            if not str(row.get(key) or '').strip():
                raise ValueError(f'job missing {key}')
        url = row.get('detail_url') or row.get('source_url')
        if not isinstance(url, str) or urlsplit(url).scheme not in {'http', 'https'} or not urlsplit(url).netloc:
            raise ValueError('missing official detail URL')
        source_id = str(row['source_record_id'])
        if source_id in identities:
            raise ValueError('duplicate source_record_id within scope')
        identities.add(source_id)
        row['source_record_id'] = source_id
        row['detail_url'] = url
        row['source_url'] = row.get('source_url') or url
        row['application_url'] = row.get('application_url') or url
        row['p1_company'] = company
        row['p1_scope'] = scope
        if row.get('recruitment_type') != SCOPES[scope]:
            raise ValueError('job recruitment_type conflicts with requested scope')
        row['canonical_company'] = company
        # Search company aliases without replacing the true hiring/legal unit.
        row['parent_unit_raw'] = ' / '.join(dict.fromkeys([company, str(row.get('parent_unit_raw') or company)]))
        row['recruiting_unit_raw'] = row.get('recruiting_unit_raw') or row['recruitment_unit']
        row['reviewed_at'] = row.get('reviewed_at') or now()
        # Identity is normally a fresh company|scope|source hash.  An adapter that
        # already owns a historical id namespace (ByteDance: 4171 live rows under
        # 'bytedance-<job post id>') may declare coverage['stable_id_prefix']; its
        # own ids are then kept so the merge updates those rows instead of adding a
        # duplicate company under a new hash namespace.  The prefix is opt-in and
        # must match the adapter-supplied id, so no other adapter changes identity.
        prefix = str(coverage.get('stable_id_prefix') or '')
        supplied = str(row.get('id') or '')
        if prefix and supplied.startswith(prefix) and len(supplied) > len(prefix):
            row['id'] = supplied
        else:
            row['id'] = 'p1-' + hashlib.sha256(f'{company}|{scope}|{source_id}'.encode()).hexdigest()[:24]
        row['p1_identity'] = row['id']
        row['status'] = row.get('status') if row.get('status') in {'open', 'unverified', 'expired'} else 'unverified'
        years = graduation_of(row)[0]
        if scope != 'social' and years and not graduation_constraints_of(row) and max(int(y[:4]) for y in years) < dt.datetime.now(dt.timezone.utc).year - 1:
            if row['status'] != 'expired':
                row['status'] = 'unverified'
            note = '官方列表仍公开，但明确届别较旧；请核验当前是否接受申请。'
            if note not in str(row.get('status_note') or ''):
                row['status_note'] = str(row.get('status_note') or '') + note
    for row in pending:
        if row['source_record_id'] in identities:raise ValueError('same source ID appears in jobs and pending_index')
        identities.add(row['source_record_id'])
        row.update(recruitment_unit=row.get('recruitment_unit') or company,canonical_company=company,
                   parent_unit_raw=company,source_url=row.get('source_url') or row['detail_url'],
                   application_url=row.get('application_url') or row['detail_url'])
        row['last_attempt_at']=row.get('last_attempt_at') or coverage.get('checked_at')
        if row['pending_reason']=='fetch_failed':row['reviewed_at']=None
        else:row['reviewed_at']=row.get('reviewed_at') or row['last_attempt_at']
        row['pending_note']=('本次详情请求未成功取得，岗位存在已由官方列表确认；详情仍待核验。' if row['pending_reason']=='fetch_failed'
                             else '官方详情已取得，但未披露有效岗位职责和任职要求；保留真实岗位索引。')
        if row.get('source_is_active') is False and {row.get('source_status_raw'),row.get('source_list_status_raw'),row.get('source_detail_status_raw')} & {'pause','closed','expired_jd_redirect'}:
            if 'expired_jd_redirect' in {row.get('source_status_raw'),row.get('source_list_status_raw'),row.get('source_detail_status_raw')} and (not isinstance(row.get('source_status_evidence'),dict) or not row['source_status_evidence']):
                raise ValueError('expired redirect requires official URL evidence')
            row['status']='expired'
        if evidence_dir is None:raise ValueError('pending index requires saved official evidence directory')
        root=Path(evidence_dir).resolve()
        references=[row[k] for k in ('listing_evidence_path','detail_evidence_path') if row.get(k)]
        for ref in references:
            path=Path(ref);path=(root/path).resolve() if not path.is_absolute() else path.resolve()
            if not (path.is_relative_to(root) or path.is_relative_to(root.parent/'shared')) or not path.is_file() or not path.stat().st_size:
                raise ValueError('pending index evidence must be a real current scope file')
    coverage['available_job_count']=len(rows);coverage['pending_count']=len(pending)
    complete = coverage.get('complete') is True
    if complete and any(row['detail_request_status']!='success' for row in pending):
        raise ValueError('failed detail request cannot have complete coverage')
    if complete:
        if (coverage.get('status') != 'success' or coverage.get('detail_complete') is not True
                or coverage.get('errors')
                or not coverage.get('source_url') or not coverage.get('evidence')):
            raise ValueError('complete requires successful full listing/details and evidence')
        if evidence_dir is not None:
            root = Path(evidence_dir).resolve()
            shared = root.parent / 'shared'
            request = coverage.get('scope_request')
            if (not isinstance(request, dict) or request.get('company') != company
                    or request.get('scope') != scope or not request.get('source_url')
                    or not isinstance(request.get('params'), dict)):
                raise ValueError('complete requires company/scope-bound official request metadata')
            evidence = coverage.get('evidence_files')
            if not isinstance(evidence, list) or not evidence:
                raise ValueError('complete requires saved response evidence_files')
            for reference in evidence:
                if not isinstance(reference, str):
                    raise ValueError('evidence file reference must be a string')
                path = Path(reference)
                path = (root / path).resolve() if not path.is_absolute() else path.resolve()
                allowed = path.is_relative_to(root) or path.is_relative_to(shared)
                if not allowed or not path.is_file() or not path.stat().st_size:
                    raise ValueError('evidence must be a nonempty current scope or company shared file')
        expected = coverage.get('expected_total')
        if expected is not None:
            if type(expected) is not int or expected != len(rows)+len(pending):
                raise ValueError('expected total differs from unique returned jobs')
        elif not (coverage.get('pagination_exhausted') is True
                  and coverage.get('unique_source_ids') == len(rows)+len(pending)
                  and coverage.get('last_page_evidence')):
            raise ValueError('no total requires unique count and proven pagination exhaustion')
    elif coverage.get('status') == 'success':
        # An adapter may finish its available subset, but that is not full coverage.
        coverage['status'] = 'partial'
    coverage['checked_at'] = now()
    return result


def collect_process(company, scope, output_dir, timeout=3600):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / 'result.json'
    # Do not permit stale result reuse after a killed/interrupted previous attempt.
    if result_path.exists():
        result_path.unlink()
    command = [sys.executable, '-m', 'qiuzhao.collector.p1_pipeline', '--adapter', REGISTRY[company],
               '--company', company, '--scope', scope, '--output-dir', str(output_dir)]
    with open(output_dir / 'adapter.log', 'w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, cwd=Path(__file__).resolve().parents[2])
        cleanup = None
        try:
            rc = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                cleanup = stop_tree(process, strict=False)
            except Exception as error:
                # An adapter writes its own scope directory, never the shared jobs file.
                # Retain the timeout as a failure but do not abort every later scope.
                cleanup = {'pid': process.pid, 'cleanup_error': type(error).__name__+': '+str(error)[-1500:],
                           'process_terminated': process.poll() is not None}
            atomic_json(output_dir / 'timeout-cleanup.json', cleanup)
            rc = 'timeout'
    if rc:
        if result_path.exists() and not (cleanup and not cleanup.get('tree_termination_confirmed')):
            try:
                checkpoint = json.loads(result_path.read_text(encoding='utf-8'))
                if checkpoint.get('jobs') or checkpoint.get('pending_index'):
                    coverage = checkpoint['coverage']
                    coverage.update(status='partial', complete=False, detail_complete=False)
                    coverage.setdefault('errors', []).append(f'adapter interrupted: {rc}; scope timeout={timeout}s')
                    if cleanup is not None:coverage['timeout_cleanup'] = cleanup
                    return validate_result(checkpoint, company, scope, output_dir)
            except (ValueError, TypeError, KeyError):
                pass
        failed=blocked(f'adapter exit={rc}; inspect {output_dir / "adapter.log"}')
        if cleanup is not None:failed['coverage']['timeout_cleanup']=cleanup
        return failed
    if not result_path.exists():
        return blocked(f'adapter result missing; inspect {output_dir / "adapter.log"}')
    try:
        return validate_result(json.loads(result_path.read_text(encoding='utf-8')), company, scope, output_dir)
    except (ValueError, TypeError, KeyError) as error:
        return blocked(f'adapter contract rejected: {error}')


def official_uuid(row):
    """Only UUID source identities can bridge verified legacy URL changes."""
    value = str(row.get('source_record_id') or '')
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def merge_records(previous, results):
    """Update stable identities, retain failed-source rows, remove only proven absences."""
    merged = list(previous)
    changes = {'added': 0, 'updated': 0, 'removed': 0}
    for company, scope, result in results:
        rows, coverage = result['jobs'], result['coverage']
        pending=result.get('pending_index',[])
        if coverage['status'] == 'blocked' and not pending:
            continue
        rows=[*rows,*pending]
        by_id = {str(row.get('p1_identity') or row.get('id')): index for index, row in enumerate(merged) if row.get('id')}
        twin_indices = {}
        for index, row in enumerate(merged):
            if row.get('id'):twin_indices.setdefault(row['id'], []).append(index)
        # Exact detail URL + recruitment type can safely adopt a legacy record.
        by_url = {}
        for index, row in enumerate(merged):
            url = row.get('detail_url') or row.get('source_url')
            if url and row.get('id'):
                by_url.setdefault((url, row.get('recruitment_type')), []).append(index)
        by_source_uuid = {}
        for index, row in enumerate(merged):
            identity = official_uuid(row)
            owner = row.get('canonical_company') or row.get('p1_company') or row.get('recruitment_unit')
            if identity and owner == company and row.get('recruitment_type') == SCOPES[scope]:
                by_source_uuid.setdefault(identity, []).append(index)
        seen = N.presence_keys(result)
        adopted_indices = set()
        incoming_url_counts = {}
        for row in rows:
            incoming_url_counts[row['detail_url']] = incoming_url_counts.get(row['detail_url'], 0) + 1
        for incoming in rows:
            incoming = copy.deepcopy(incoming)
            canonical = incoming['p1_identity']
            normalize_records([incoming])
            index = by_id.get(canonical)
            if index is None and official_uuid(incoming):
                candidates = by_source_uuid.get(official_uuid(incoming), [])
                if len(candidates) == 1 and candidates[0] not in adopted_indices:
                    index = candidates[0]
            if index is None:
                matches = by_url.get((incoming['detail_url'], incoming['recruitment_type']), [])
                if (len(matches) == 1 and matches[0] not in adopted_indices
                        and incoming_url_counts[incoming['detail_url']] == 1):
                    candidate = merged[matches[0]]
                    if (not candidate.get('p1_company') or candidate.get('p1_company') == company) and (
                            not candidate.get('p1_scope') or candidate.get('p1_scope') == scope):
                        index = matches[0]
            if index is None:
                merged.append(incoming)
                by_id[canonical] = len(merged) - 1
                changes['added'] += 1
            else:
                old = merged[index]
                # Incoming evidence is authoritative; retaining old raw fields
                # could silently carry a stale cohort/campaign into new rows.
                incoming['id'] = old['id']
                if incoming.get('index_only') and old.get('description_raw'):
                    # A failed/empty current detail never destroys earlier verified prose.
                    retained=copy.deepcopy(old)
                    for field in ('p1_identity','p1_company','p1_scope','canonical_company','parent_unit_raw',
                                  'pending_reason','pending_note','detail_request_status','last_attempt_at'):
                        retained[field]=incoming.get(field)
                    if incoming.get('status')=='expired':
                        for field in ('status','status_note','source_is_active','source_status_raw','source_list_status_raw',
                                      'source_detail_status_raw','source_status_evidence','source_status_dates','source_status_conflict'):
                            if field in incoming:retained[field]=incoming[field]
                    incoming=retained
                # Preserve existing identical-ID multiplicity without leaving stale twin rows.
                for twin in twin_indices.get(old['id'], [index]):
                    prior = merged[twin]
                    if prior == old:
                        merged[twin] = copy.deepcopy(incoming)
                adopted_indices.add(index)
                by_id[canonical] = index
                from qiuzhao.normalize import business_value
                changes['updated'] += int(business_value(old) != business_value(incoming))
            seen.add(canonical)
        if coverage.get('complete') is True and coverage.get('status') == 'success' and result['jobs']:
            reviewed = coverage.get('checked_at') or now()
            for index, row in enumerate(merged):
                if row.get('p1_company') == company and row.get('p1_scope') == scope and (row.get('p1_identity') or row.get('id')) not in seen:
                    if row.get('status') != 'removed':
                        changes['removed'] += 1
                    row = dict(row)
                    merged[index] = row
                    row.update(status='removed', reviewed_at=reviewed,
                               removal_reason='Absent from complete current company/scope official listing',
                               source_is_active=False, source_status_raw='closed',
                               source_status_evidence={'list_status':'closed', 'reason':'complete_snapshot_absence',
                                   'company':company, 'scope':scope, 'complete':True,
                                   'source_url':coverage.get('source_url'),
                                   'checked_at':reviewed})
    return merged, changes


def publish(data_dir, results, run_dir):
    """Use current bytes, true pre-write backup, CAS recheck and atomic replacement."""
    data_dir, run_dir = Path(data_dir), Path(run_dir)
    jobs_path = data_dir / 'jobs.json'
    with open(data_dir / 'p1-publish.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before_hash = sha(jobs_path)
        previous = list(iter_json_file(jobs_path,strict=True))
        if not isinstance(previous, list):
            raise ValueError('production jobs must be a list')
        merged, changes = merge_records(previous, results)
        # One true pre-write snapshot per locked execution batch, not 150
        # complete database copies. Per-scope candidate snapshots and hashes
        # remain in the checkpoint for inspection/replay.
        run_dir.mkdir(parents=True, exist_ok=True)
        backup = run_dir / 'jobs.before.json.gz'
        manifest = run_dir / 'backup.json'
        if not backup.exists():
            with jobs_path.open('rb') as source, gzip.open(backup, 'wb', compresslevel=3) as stream:
                shutil.copyfileobj(source, stream, length=1 << 20)
            with gzip.open(backup, 'rb') as stream:
                backup_hash = stream_sha(stream)
            if backup_hash != before_hash:
                raise RuntimeError('pre-write backup hash mismatch')
            atomic_json(manifest, {'uncompressed_sha256': backup_hash, 'created_at': now()})
        else:
            backup_hash = json.loads(manifest.read_text(encoding='utf-8'))['uncompressed_sha256']
            with gzip.open(backup, 'rb') as stream:
                if stream_sha(stream) != backup_hash:
                    raise RuntimeError('existing batch backup hash mismatch; refusing publish')
        if sha(jobs_path) != before_hash:
            raise RuntimeError('jobs changed concurrently; refusing overwrite')
        atomic_json(jobs_path, merged)
        return dict(changes, before_sha256=before_hash, after_sha256=sha(jobs_path),
                    backup=str(backup), backup_sha256=backup_hash, total_jobs=len(merged), published_at=now())


def checkpoint_path(data_dir, companies, scopes):
    selection = json.dumps([companies, scopes], ensure_ascii=False).encode()
    key = hashlib.sha256(selection).hexdigest()[:20]
    return Path(data_dir) / 'p1-checkpoints' / (key + '.json')


def resume_compatible(checkpoint, companies, scopes):
    """Can this checkpoint continue into the requested selection?

    A checkpoint resumes when the scopes match and its company set is a subset of
    the request. Platform companies are appended to the default set as one line is
    added to ``p1_platform_companies.json``; those additions must not look like a
    broken resume. Existing validated results are reused and only the added
    companies run. A removed or otherwise different selection is a genuine
    mismatch: callers must start a new run instead of reusing stale results.
    """
    if list(checkpoint.get('scopes') or []) != list(scopes):
        return False
    return set(checkpoint.get('companies') or []).issubset(set(companies))


def any_validated(status):
    """A scope counts as trustworthy output only when its validated coverage
    actually reached the shared store: success (complete snapshot, may add,
    update or remove rows) or a partial that still carried rows. Empty
    partials and blocked scopes merged nothing and do not count."""
    for entry in status.get('results', {}).values():
        coverage = entry.get('coverage', {})
        if coverage.get('status') == 'success':
            return True
        if (coverage.get('status') == 'partial'
                and (coverage.get('available_job_count') or coverage.get('pending_count'))):
            return True
    return False


def retry_queue_path(data_dir):
    return Path(data_dir) / 'p1-retry-queue.json'


def load_retry_queue(data_dir):
    """Read the previous day's failed-unit queue; tolerate a missing/corrupt file."""
    try:
        payload = json.loads(retry_queue_path(data_dir).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    entries = payload.get('entries') if isinstance(payload, dict) else None
    if not isinstance(entries, dict):
        return {}
    return {str(key): dict(value) for key, value in entries.items()
            if isinstance(value, dict) and value.get('company') and value.get('scope')}


def save_retry_queue(data_dir, queue):
    """Best-effort atomic write; a read-only data dir must never abort collection."""
    try:
        atomic_json(retry_queue_path(data_dir), {'updated_at': now(), 'entries': queue})
    except OSError:
        pass


def last_attempt_path(data_dir):
    return Path(data_dir) / 'p1-last-attempt.json'


def load_last_attempt(data_dir):
    """Read each unit's most recent real attempt time (epoch seconds).

    A missing/corrupt file means "nothing attempted yet"; every unit is then treated
    as stale and keeps its natural order. Only real attempts are recorded, never
    resumed/skipped units.
    """
    try:
        payload = json.loads(last_attempt_path(data_dir).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    entries = payload.get('entries') if isinstance(payload, dict) else None
    if not isinstance(entries, dict):
        return {}
    result = {}
    for key, value in entries.items():
        try:
            stamp = float(value)
        except (TypeError, ValueError):
            continue
        if stamp > 0:
            result[str(key)] = stamp
    return result


def save_last_attempt(data_dir, attempts):
    """Best-effort atomic write; a read-only data dir must never abort collection."""
    try:
        atomic_json(last_attempt_path(data_dir), {'updated_at': now(), 'entries': attempts})
    except OSError:
        pass


def stale_key(last_attempt, company, effective_scopes):
    """Fairness key for one company's chain.

    ``0.0`` means at least one of the company's scopes was never attempted (the unit
    was cut off by ``--max-run-seconds``), so the company must lead the next run. A
    positive value is the oldest real attempt time across the company's scopes;
    smaller means staler and is served first.
    """
    values = [last_attempt.get(f'{company}/{scope}') for scope in effective_scopes]
    if not values or any(not value for value in values):
        return 0.0
    return min(values)


def failure_reason(coverage):
    errors = ' | '.join(str(error) for error in (coverage.get('errors') or []))
    if coverage.get('timeout_cleanup') is not None or 'timeout' in errors.lower():
        return 'timeout'
    if 'ssl' in errors.lower():
        return 'ssl'
    if coverage.get('status') == 'blocked':
        return 'blocked'
    return 'incomplete'


def is_full_success(coverage):
    return coverage.get('status') == 'success' and coverage.get('complete') is True


def next_consecutive_days(previous, today):
    last = previous.get('last_failed_date')
    try:
        last_date = dt.date.fromisoformat(str(last))
    except (TypeError, ValueError):
        return 1
    if last_date == today:
        return max(1, int(previous.get('consecutive_days') or 1))
    if last_date == today - dt.timedelta(days=1):
        return max(1, int(previous.get('consecutive_days') or 1)) + 1
    return 1


def record_retry_failure(queue, company, scope, coverage):
    key = f'{company}/{scope}'
    previous = queue.get(key) or {}
    today = dt.datetime.now(dt.timezone.utc).date()
    entry = dict(previous)
    entry.update(company=company, scope=scope, reason=failure_reason(coverage),
                 count=int(previous.get('count') or 0) + 1, last_failed_at=now(),
                 last_failed_date=today.isoformat(),
                 consecutive_days=next_consecutive_days(previous, today),
                 first_failed_at=previous.get('first_failed_at') or now())
    dates = [str(day) for day in (previous.get('fail_dates') or [])]
    if today.isoformat() not in dates:
        dates.append(today.isoformat())
    entry['fail_dates'] = dates[-10:]
    queue[key] = entry
    return entry


def record_retry_success(queue, company, scope):
    queue.pop(f'{company}/{scope}', None)


def retry_tier(entry):
    """-1 = failed yesterday, run first; 0 = normal; 1 = three-day failure, run last."""
    if not entry:
        return 0
    try:
        days = int(entry.get('consecutive_days') or 1)
    except (TypeError, ValueError):
        days = 1
    return -1 if days < 3 else 1


def plan_chains(companies, scopes, queue, scopes_by_company=None, last_attempt=None):
    """Company chains keep same-company scopes serial while companies run concurrently.

    Ordering (2026-09-18 fairness fallback for the 5h hard cap):
      1. companies with any never-attempted scope lead (these are the units
         ``--max-run-seconds`` cut off), then the rest by their oldest attempt time
         ascending (stalest first);
      2. retry-queue failures are served before never-failed companies at the same
         attempt state;
      3. units that failed three consecutive days are demoted to the very end
         without dropping any company.

    Inside a company, retry-tier scopes still lead and the rest keep their natural
    scope order. ``scopes_by_company`` carries the per-company effective scopes (all
    three by default); when omitted it is derived here.
    """
    if scopes_by_company is None:
        scopes_by_company = {company: company_scopes(company, scopes) for company in companies}
    if last_attempt is None:
        last_attempt = {}
    position = {company: index for index, company in enumerate(companies)}
    chains = {}
    for company in companies:
        effective = scopes_by_company.get(company, [])
        scope_position = {scope: index for index, scope in enumerate(effective)}
        chains[company] = sorted(effective, key=lambda scope: (
            retry_tier(queue.get(f'{company}/{scope}')), scope_position[scope]))
    def company_key(company):
        effective = scopes_by_company.get(company, [])
        tiers = [retry_tier(queue.get(f'{company}/{scope}')) for scope in effective]
        demoted = 1 if tiers and min(tiers) > 0 else 0
        stale = stale_key(last_attempt, company, effective)
        never_attempted = 0 if stale <= 0 else 1
        failed = 0 if any(tier < 0 for tier in tiers) else 1
        return (demoted, never_attempted, failed, stale, position[company])
    return [{'company': company, 'scopes': chains[company]}
            for company in sorted(companies, key=company_key)]


def retry_summary(queue, companies, scopes, scopes_by_company=None):
    if scopes_by_company is None:
        scopes_by_company = {company: list(scopes) for company in companies}
    priority, demoted = [], []
    for company in companies:
        for scope in scopes_by_company.get(company, []):
            entry = queue.get(f'{company}/{scope}')
            if entry:
                (demoted if retry_tier(entry) > 0 else priority).append(f'{company}/{scope}')
    return priority, demoted


def run(data_dir, run_dir, companies, scopes, timeout=600, apply=False, resume=False,
        max_run_seconds=21600, workers=4, platform_workers=PLATFORM_WORKERS,
        platform_min_interval=PLATFORM_MIN_INTERVAL):
    data_dir, run_dir = Path(data_dir), Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    status_path = run_dir / 'status.json'
    if status_path.exists() and not resume:
        raise ValueError('run directory already exists; use --resume or a new directory')
    # Effective scopes: platform companies skip social unless their config opts in.
    scopes_by_company = {company: company_scopes(company, scopes) for company in companies}
    fresh = {'started_at': now(), 'run_dir': str(run_dir), 'companies': list(companies),
             'scopes': list(scopes), 'results': {}, 'publications': []}
    if resume and status_path.exists():
        status = json.loads(status_path.read_text(encoding='utf-8'))
        if resume_compatible(status, companies, scopes):
            # Pure addition (platform companies appended to the default set): reuse
            # every validated result and run only the new companies.
            status['companies'] = list(companies)
        else:
            # A removed/different selection is a new run, not a fatal resume
            # mismatch: restart in place instead of failing the whole day.
            status = fresh
    else:
        status = fresh
    retry_queue = load_retry_queue(data_dir)
    last_attempt = load_last_attempt(data_dir)
    state_lock = threading.Lock()

    def save_status():
        atomic_json(status_path, status)
        atomic_json(data_dir / 'p1-status.json', status)
        atomic_json(checkpoint_path(data_dir, companies, scopes), status)

    def publish_retry_summary():
        priority, demoted = retry_summary(retry_queue, companies, scopes, scopes_by_company)
        status['retry'] = {'priority': priority, 'demoted': demoted,
                           'queue_path': str(retry_queue_path(data_dir))}

    publish_retry_summary()
    status.update(run_finished=False, success=False)
    save_status()
    publication_dir = run_dir / 'batches' / str(time.time_ns())
    deadline = time.monotonic() + max_run_seconds
    workers = max(1, int(workers))
    gate = PlatformGate(platform_workers, platform_min_interval)
    # Politely space same-host requests for adapters that honour this env hook; an
    # explicit caller value (e.g. the offline >=2s probe) is never lowered.
    os.environ.setdefault('QIUZHAO_PLATFORM_REQUEST_INTERVAL',
                          str(max(1.0, float(platform_min_interval))))

    def run_unit(company, scope):
        key = f'{company}/{scope}'
        # Position in this run's company list, not the hardcoded COMPANIES, so
        # platform-adapter companies get a directory instead of an index error.
        # Hardcoded companies stay first, so their ordinals (and any resume of the
        # same selection) are unchanged.
        ordinal = companies.index(company) + 1
        output = run_dir / f'{ordinal:02d}' / scope
        with state_lock:
            saved = status['results'].get(key)
        if saved and saved.get('attempted', True) and (not apply or saved.get('published')):
            return 'skipped'
        if time.monotonic() >= deadline:
            return 'deadline'
        if saved and Path(saved['result_path']).exists():
            result = validate_result(json.loads(Path(saved['result_path']).read_text(encoding='utf-8')), company, scope, output)
            attempted_now = False
        else:
            # Same-host platform units are capped and spaced; adapters keep their
            # own internal request pacing.
            platform = platform_group(company)
            gate.acquire(platform)
            try:
                result = collect_process(company, scope, output, min(timeout, max(1, deadline - time.monotonic())))
            finally:
                gate.release(platform)
            atomic_json(output / 'validated.json', result)
            attempted_now = True
        # publish() serializes on the p1-publish.lock file lock; the status append is
        # protected below so concurrent company chains cannot lose a checkpoint entry.
        publication = None
        if apply and (result['jobs'] or result.get('pending_index') or result['coverage'].get('complete')):
            publication = publish(data_dir, [(company, scope, result)], publication_dir)
        with state_lock:
            status['results'][key] = {'coverage': result['coverage'],
                                      'result_path': str(output / 'validated.json'),
                                      'published': bool(apply), 'attempted': True}
            if publication is not None:
                status['publications'].append(dict(company=company, scope=scope, **publication))
            if is_full_success(result['coverage']):
                record_retry_success(retry_queue, company, scope)
            else:
                record_retry_failure(retry_queue, company, scope, result['coverage'])
            if attempted_now:
                # Real attempt (success or failure) feeds the next-day fairness
                # ordering; resumed/skipped units deliberately keep their old stamp.
                last_attempt[key] = time.time()
                save_last_attempt(data_dir, last_attempt)
            save_status()
            save_retry_queue(data_dir, retry_queue)
        print(json.dumps({'company': company, 'scope': scope, **result['coverage']}, ensure_ascii=False), flush=True)
        return 'ok'

    def run_chain(chain):
        for scope in chain['scopes']:
            if run_unit(chain['company'], scope) == 'deadline':
                return 'deadline'
        return 'ok'

    # One chain per company: same-company scopes stay serial, workers limit how many
    # companies (and therefore units) run at once. last_attempt drives the next-day
    # fairness ordering for units the hard cap cut off.
    chains = plan_chains(companies, scopes, retry_queue, scopes_by_company, last_attempt)
    interrupted = False
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {}
        queue_of_chains = list(chains)
        stop_submitting = False

        def submit_next():
            if stop_submitting or not queue_of_chains or time.monotonic() >= deadline:
                return
            chain = queue_of_chains.pop(0)
            futures[executor.submit(run_chain, chain)] = chain

        for _ in range(min(workers, len(queue_of_chains))):
            submit_next()
        while futures:
            done, _ = concurrent.futures.wait(list(futures), return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                futures.pop(future, None)
                try:
                    outcome = future.result()
                except BaseException:
                    interrupted = True
                    raise
                if outcome == 'deadline':
                    stop_submitting = True
                submit_next()
    finally:
        executor.shutdown(wait=not interrupted, cancel_futures=True)

    with state_lock:
        remaining = [f'{company}/{scope}' for company in companies
                     for scope in scopes_by_company.get(company, [])
                     if f'{company}/{scope}' not in status['results']]
        publish_retry_summary()
        status['pending'] = remaining
        if remaining:
            # Scopes already validated are trustworthy partial output; resume later.
            status['run_finished'] = False
            status['success'] = False
            status['paused_at'] = now()
        else:
            status['run_finished'] = True
            status['pending'] = []
            status['completed_at'] = now()
            status['success'] = all(is_full_success(e['coverage']) for e in status['results'].values())
        save_status()
    # Exit contract: 0 = every scope success+complete; 2 = at least one scope passed
    # validation and was merged while another did not (keep partial output);
    # 1 = no scope produced trustworthy output (callers must roll back).
    if status['success']:
        return 0
    return 2 if any_validated(status) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--adapter')
    parser.add_argument('--company')
    parser.add_argument('--scope', choices=list(SCOPES))
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--data-dir', type=Path, default=Path('/var/lib/mcp-suite'))
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--companies', help='comma-separated exact company names; '
                        'default all hardcoded + platform-adapter companies')
    parser.add_argument('--scopes', default=','.join(SCOPES))
    parser.add_argument('--timeout', type=int, default=None,
                        help='legacy per-scope timeout in seconds; --scope-timeout takes precedence')
    parser.add_argument('--scope-timeout', type=int, default=None,
                        help='per-scope subprocess timeout in seconds (default 600)')
    parser.add_argument('--workers', type=int, default=4,
                        help='max concurrent units/companies, 1-64 (default 4; the '
                             'jingling daily chain passes 8)')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--resume-latest', action='store_true')
    parser.add_argument('--max-run-seconds', type=int, default=21600)
    parser.add_argument('--platform-rotation', type=int, default=PLATFORM_ROTATION_DEFAULT,
                        help='split the config-driven platform companies (beisen/moka/feishu) '
                             'across N days and run one bucket per day; 1=off, the '
                             'default, so every company runs every day. Ignored when '
                             '--companies is given.')
    parser.add_argument('--platform-workers', type=int, default=PLATFORM_WORKERS,
                        help='max concurrent units per platform host, before the global '
                             '--workers cap (default %d)' % PLATFORM_WORKERS)
    parser.add_argument('--platform-interval', type=float, default=PLATFORM_MIN_INTERVAL,
                        help='minimum seconds between same-host unit launches (default %.1f)'
                             % PLATFORM_MIN_INTERVAL)
    args = parser.parse_args()
    if args.adapter:
        try:
            module = importlib.import_module(args.adapter)
            result = module.collect(args.company, args.scope, args.output_dir)
        except Exception as error:
            result = blocked(f'{type(error).__name__}: {error}')
        atomic_json(args.output_dir / 'result.json', result)
        return 0
    if not 1 <= args.workers <= 64:
        parser.error('--workers must be between 1 and 64')
    scope_timeout = args.scope_timeout if args.scope_timeout is not None else (
        args.timeout if args.timeout is not None else 600)
    if args.companies:
        companies = args.companies.split(',')
    else:
        # Day rotation only applies to the default daily set; an explicit
        # --companies selection is always run in full.
        companies = companies_for_day(DEFAULT_COMPANIES, args.platform_rotation)
    scopes = args.scopes.split(',')
    if any(c not in REGISTRY for c in companies) or any(s not in SCOPES for s in scopes):
        parser.error('unknown company or scope')
    if len(set(companies)) != len(companies) or len(set(scopes)) != len(scopes):
        parser.error('duplicate company or scope')
    run_dir = args.run_dir or args.data_dir / 'p1-runs' / dt.datetime.now().strftime('%Y%m%dT%H%M%S')
    def select_checkpoint():
        nonlocal run_dir
        latest = checkpoint_path(args.data_dir, companies, scopes)
        if not latest.exists():
            latest = args.data_dir / 'p1-status.json'
        if args.resume_latest and latest.exists():
            checkpoint = json.loads(latest.read_text(encoding='utf-8'))
            if checkpoint.get('run_dir'):
                saved_path = Path(checkpoint['run_dir']) / 'status.json'
                if saved_path.exists():
                    checkpoint = json.loads(saved_path.read_text(encoding='utf-8'))
            if (checkpoint.get('companies') == companies and checkpoint.get('scopes') == scopes
                    and not checkpoint.get('run_finished', True) and checkpoint.get('run_dir')):
                run_dir, args.resume = Path(checkpoint['run_dir']), True
    os.environ.setdefault('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(args.data_dir / 'p1-detail-cache'))
    if args.apply:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        lock_path = args.data_dir / 'collector.lock'
        # Reuse the shell wrapper's inherited lock description when present.
        try:
            st = os.fstat(9)
            target = lock_path.stat()
            inherited = st.st_dev == target.st_dev and st.st_ino == target.st_ino
        except OSError:
            inherited = False
        lock = os.fdopen(os.dup(9), 'a') if inherited else open(lock_path, 'a')
        with lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            select_checkpoint()
            return run(args.data_dir, run_dir, companies, scopes, scope_timeout,
                       args.apply, args.resume, args.max_run_seconds, args.workers,
                       platform_workers=args.platform_workers,
                       platform_min_interval=args.platform_interval)
    select_checkpoint()
    return run(args.data_dir, run_dir, companies, scopes, scope_timeout,
               args.apply, args.resume, args.max_run_seconds, args.workers,
               platform_workers=args.platform_workers,
               platform_min_interval=args.platform_interval)


if __name__ == '__main__':
    raise SystemExit(main())
