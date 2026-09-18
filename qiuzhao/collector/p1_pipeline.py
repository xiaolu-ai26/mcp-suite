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

# The daily chain is invoked without --companies, so the default set must contain
# every platform-adapter company, not only the hardcoded 50. Hardcoded companies
# keep their approved priority order; platform companies follow in config order
# (beisen then moka) and are deduplicated against the hardcoded names, because
# 三七互娱 / 金山办公 / 鹰角网络 appear in both lists.
PLATFORM_COMPANIES = [name for name in REGISTRY if name not in COMPANIES]
DEFAULT_COMPANIES = [*COMPANIES, *PLATFORM_COMPANIES]


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


def plan_chains(companies, scopes, queue):
    """Company chains keep same-company scopes serial while companies run concurrently.

    Retry-queue units lead their company and the global order; units that failed three
    consecutive days are demoted to the very end without dropping any company.
    """
    position = {company: index for index, company in enumerate(companies)}
    scope_position = {scope: index for index, scope in enumerate(scopes)}
    chains = {}
    for company in companies:
        chains[company] = sorted(scopes, key=lambda scope: (
            retry_tier(queue.get(f'{company}/{scope}')), scope_position[scope]))
    def company_key(company):
        tiers = [retry_tier(queue.get(f'{company}/{scope}')) for scope in scopes]
        return (min(tiers) if tiers else 0, position[company])
    return [{'company': company, 'scopes': chains[company]}
            for company in sorted(companies, key=company_key)]


def retry_summary(queue, companies, scopes):
    priority, demoted = [], []
    for company in companies:
        for scope in scopes:
            entry = queue.get(f'{company}/{scope}')
            if entry:
                (demoted if retry_tier(entry) > 0 else priority).append(f'{company}/{scope}')
    return priority, demoted


def run(data_dir, run_dir, companies, scopes, timeout=600, apply=False, resume=False, max_run_seconds=21600, workers=4):
    data_dir, run_dir = Path(data_dir), Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    status_path = run_dir / 'status.json'
    if status_path.exists() and not resume:
        raise ValueError('run directory already exists; use --resume or a new directory')
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
    state_lock = threading.Lock()

    def save_status():
        atomic_json(status_path, status)
        atomic_json(data_dir / 'p1-status.json', status)
        atomic_json(checkpoint_path(data_dir, companies, scopes), status)

    def publish_retry_summary():
        priority, demoted = retry_summary(retry_queue, companies, scopes)
        status['retry'] = {'priority': priority, 'demoted': demoted,
                           'queue_path': str(retry_queue_path(data_dir))}

    publish_retry_summary()
    status.update(run_finished=False, success=False)
    save_status()
    publication_dir = run_dir / 'batches' / str(time.time_ns())
    deadline = time.monotonic() + max_run_seconds
    workers = max(1, int(workers))

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
        else:
            result = collect_process(company, scope, output, min(timeout, max(1, deadline - time.monotonic())))
            atomic_json(output / 'validated.json', result)
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
    # companies (and therefore units) run at once.
    chains = plan_chains(companies, scopes, retry_queue)
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
        remaining = [f'{company}/{scope}' for company in companies for scope in scopes
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
                        help='max concurrent units/companies, 1-6 (default 4)')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--resume-latest', action='store_true')
    parser.add_argument('--max-run-seconds', type=int, default=21600)
    args = parser.parse_args()
    if args.adapter:
        try:
            module = importlib.import_module(args.adapter)
            result = module.collect(args.company, args.scope, args.output_dir)
        except Exception as error:
            result = blocked(f'{type(error).__name__}: {error}')
        atomic_json(args.output_dir / 'result.json', result)
        return 0
    if not 1 <= args.workers <= 6:
        parser.error('--workers must be between 1 and 6')
    scope_timeout = args.scope_timeout if args.scope_timeout is not None else (
        args.timeout if args.timeout is not None else 600)
    companies = args.companies.split(',') if args.companies else DEFAULT_COMPANIES
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
                       args.apply, args.resume, args.max_run_seconds, args.workers)
    select_checkpoint()
    return run(args.data_dir, run_dir, companies, scopes, scope_timeout,
               args.apply, args.resume, args.max_run_seconds, args.workers)


if __name__ == '__main__':
    raise SystemExit(main())
