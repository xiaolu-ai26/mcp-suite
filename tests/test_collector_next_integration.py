"""collector-next integration tests.

Covers the two behaviors this branch adds on top of its four merged branches:

1. Platform-adapter companies reach the daily chain. The default ``--companies``
   set is the hardcoded priority list plus every company in
   ``p1_platform_companies.json`` (deduplicated, stable order), and the output
   directory ordinal comes from this run's company list, not ``COMPANIES``.
2. A checkpoint whose company set is a pure subset of the request (a platform
   company was added) resumes without repeating finished work, and a removed or
   otherwise different selection restarts instead of aborts.
"""
import json
from pathlib import Path
from unittest.mock import patch

from qiuzhao.collector import p1_pipeline as p
from qiuzhao.collector import p1_platform_beisen as beisen
from qiuzhao.collector import p1_platform_moka as moka


PLATFORM_ONLY = ('中信建投', '中金公司', '国信证券', '浙江民泰商业银行',
                 '安踏集团', '小天才', '信也科技')
OVERLAP = ('三七互娱', '金山办公', '鹰角网络')
BANK_ONLY = ('中国工商银行', '中国农业银行', '交通银行', '招商银行', '中信银行')
# Append-only foreign-company block (Workday + SuccessFactors), registered after
# the banks block so it never reorders the blocks that already shipped.
FOREIGN_ONLY = ('英伟达', '花旗银行', '强生', '壳牌', '英国石油', '美敦力',
                '奥纬咨询', '美满电子', '史密夫斐尔',
                '思爱普', '采埃孚', '勃林格殷格翰')
# Public-API batch appended last (20260918i): both companies already own a legacy
# id namespace in production, so their adapters publish coverage['stable_id_prefix'].
PUBLIC_API_ONLY = ('字节跳动', '美的集团')
# Foreign batch 2 (20260918j): Dayee hotjob.cn tenants + the 51job micro-site.
DAYEE_MODULE = 'qiuzhao.collector.p1_foreign_01'
JOB51_MODULE = 'qiuzhao.collector.p1_platform_51job'
DAYEE_ONLY = ('德勤', '康师傅', 'ZARA', '广汽集团', '益海嘉里', '迪卡侬', 'ZURU')
JOB51_ONLY = ('百事',)
# 20260918h shipped 924 companies; this cumulative branch adds 字节跳动/美的集团
# (20260918i) plus 22 new foreign-batch names (20260918j). 毕马威 was already
# registered through an older moka tenant, so the batch's second kpmg tenant adds
# no company — that is exactly the duplicate-name risk this file guards.
# 948 (20260918k) + foreign-discovery 20260919d: +1 beisen, +4 moka, +3 dayee,
# +6 51job, +2 workday = 964.
EXPECTED_DEFAULT_COMPANIES = 964
CONFIG_SECTION_MODULES = {
    'beisen': 'qiuzhao.collector.p1_platform_beisen',
    'moka': 'qiuzhao.collector.p1_platform_moka',
    'feishu': 'qiuzhao.collector.p1_feishu_public',
    'workday': 'qiuzhao.collector.p1_platform_workday',
    'successfactors': 'qiuzhao.collector.p1_platform_successfactors',
    'dayee': DAYEE_MODULE,
    'job51': JOB51_MODULE,
}


def validated(company, scope='campus'):
    payload = {'jobs': [dict(source_record_id='1', job_title='软件工程师',
                             description_raw='负责软件开发。',
                             recruitment_unit=company + '有限公司',
                             recruitment_type=p.SCOPES[scope],
                             detail_url='https://official.example.com/jobs/' + company)],
               'coverage': {'status': 'success', 'complete': True, 'detail_complete': True,
                            'expected_total': 1, 'collected_jobs': 1, 'pages_scanned': 1,
                            'errors': [], 'source_url': 'https://official.example.com/jobs',
                            'evidence': ['listing.json'],
                            'scope_evidence': 'official employment type field'}}
    return p.validate_result(payload, company, scope)


# --- 1. default company set contains the platform adapters --------------------

def test_default_companies_append_platform_in_config_order_without_duplicates():
    # Hardcoded companies keep their approved order and are never moved by platform.
    assert p.DEFAULT_COMPANIES[:len(p.COMPANIES)] == p.COMPANIES
    assert len(p.DEFAULT_COMPANIES) == len(set(p.DEFAULT_COMPANIES))
    for name in PLATFORM_ONLY:
        assert name in p.DEFAULT_COMPANIES
        assert name not in p.COMPANIES
        assert p.REGISTRY[name] in ('qiuzhao.collector.p1_platform_beisen',
                                    'qiuzhao.collector.p1_platform_moka')
    # Platform entries that overlap the hardcoded list stay in their hardcoded slot.
    for name in OVERLAP:
        assert name in p.COMPANIES
        assert p.DEFAULT_COMPANIES.count(name) == 1


def test_platform_companies_are_appended_after_hardcoded_in_config_order():
    extra = [name for name in p.DEFAULT_COMPANIES if name not in p.COMPANIES]
    def module_of(name):
        return p.REGISTRY[name]

    beisen_names = [n for n in extra if module_of(n) == 'qiuzhao.collector.p1_platform_beisen']
    moka_names = [n for n in extra if module_of(n) == 'qiuzhao.collector.p1_platform_moka']
    bank_names = [n for n in extra if module_of(n) == 'qiuzhao.collector.p1_banks_01']
    ali_names = [n for n in extra if module_of(n) == 'qiuzhao.collector.alibaba_headless']
    tme_names = [n for n in extra if module_of(n) == 'qiuzhao.collector.tencent_music']
    foreign_names = [n for n in extra
                     if module_of(n) in ('qiuzhao.collector.p1_platform_workday',
                                         'qiuzhao.collector.p1_platform_successfactors')]
    feishu_names = [n for n in extra if module_of(n) == 'qiuzhao.collector.p1_feishu_public']
    # Append-only public-API block shipped after the Feishu block (20260918i):
    # 字节跳动 and 美的集团 each keep a historical id namespace in production.
    public_api_names = [n for n in extra
                        if module_of(n) in ('qiuzhao.collector.p1_bytedance_public',
                                            'qiuzhao.collector.p1_midea_public')]
    # Foreign batch-2 blocks (20260918j) appended after the public-API block.
    dayee_names = [n for n in extra if module_of(n) == 'qiuzhao.collector.p1_foreign_01']
    job51_names = [n for n in extra if module_of(n) == 'qiuzhao.collector.p1_platform_51job']

    assert set(PLATFORM_ONLY) <= set(beisen_names) | set(moka_names)
    assert set(BANK_ONLY) <= set(bank_names)
    assert set(FOREIGN_ONLY) <= set(foreign_names)
    assert set(PUBLIC_API_ONLY) <= set(public_api_names)
    coverage_blocks = (set(beisen_names) | set(moka_names) | set(bank_names) | set(ali_names)
                       | set(tme_names) | set(foreign_names) | set(feishu_names)
                       | set(public_api_names) | set(dayee_names) | set(job51_names))
    assert set(extra) == coverage_blocks

    # Approved append order: beisen then moka, banks, Ali/Tencent gap, foreign
    # Workday/SuccessFactors, config-driven Feishu, the 20260918i public-API batch
    # (字节跳动/美的集团), then the 20260918j foreign batch-2 blocks (Dayee
    # hotjob.cn, then 51job micro-sites). Every block stays contiguous and no
    # block is interleaved with another.
    block_order = [
        ('beisen', beisen_names),
        ('moka', moka_names),
        ('banks', bank_names),
        ('ali', ali_names),
        ('tencent_music', tme_names),
        ('workday/successfactors', foreign_names),
        ('feishu', feishu_names),
        ('public_api', public_api_names),
        ('dayee', dayee_names),
        ('51job', job51_names),
    ]
    cursor = 0
    for label, names in block_order:
        assert extra[cursor:cursor + len(names)] == names, label
        cursor += len(names)
    assert cursor == len(extra)
    assert extra.index('中信建投') < extra.index('安踏集团')
    for name in BANK_ONLY:
        assert p.REGISTRY[name] == 'qiuzhao.collector.p1_banks_01'
    assert p.REGISTRY['英伟达'] == 'qiuzhao.collector.p1_platform_workday'
    assert p.REGISTRY['思爱普'] == 'qiuzhao.collector.p1_platform_successfactors'


def test_every_registry_module_exposes_the_collect_contract():
    # p1_feishu_public shipped without a `collect` alias, so the daily chain would
    # block every Feishu tenant. Guard the subprocess contract for every module.
    import importlib

    for module_path in sorted(set(p.REGISTRY.values())):
        module = importlib.import_module(module_path)
        assert callable(getattr(module, 'collect', None)), module_path


def test_platform_company_runs_without_index_error_and_gets_unique_dir(tmp_path):
    companies = ['大疆', '小天才']
    outputs = {}

    def fake(company, scope, output, timeout):
        outputs[company] = output
        return validated(company, scope)

    with patch.object(p, 'collect_process', side_effect=fake):
        assert p.run(tmp_path, tmp_path / 'run', companies, ['campus'], workers=2) == 0
    # Ordinals come from this run's list; 小天才 is not in the hardcoded COMPANIES.
    assert outputs['大疆'].parent.name == '01'
    assert outputs['小天才'].parent.name == '02'
    assert outputs['大疆'].name == outputs['小天才'].name == 'campus'


def test_cli_default_company_set_reaches_run(tmp_path):
    captured = {}

    def fake_run(data_dir, run_dir, companies, scopes, timeout=600, apply=False,
                 resume=False, max_run_seconds=21600, workers=4,
                 platform_workers=2, platform_min_interval=1.0):
        captured['companies'] = list(companies)
        return 0

    with patch.object(p, 'run', side_effect=fake_run):
        with patch('sys.argv', ['p1', '--data-dir', str(tmp_path), '--scopes', 'campus']):
            assert p.main() == 0
    # Default is no rotation (站长 2026-09-18): every hardcoded and platform company
    # reaches the run.
    assert captured['companies'] == p.DEFAULT_COMPANIES
    # --platform-rotation 2 stays available and buckets only config platforms.
    with patch.object(p, 'run', side_effect=fake_run):
        with patch('sys.argv', ['p1', '--data-dir', str(tmp_path), '--platform-rotation', '2']):
            assert p.main() == 0
    companies = set(captured['companies'])
    assert set(p.COMPANIES) <= companies
    daily = {name for name in p.DEFAULT_COMPANIES
             if name not in p.COMPANIES and p.REGISTRY[name] not in p.ROTATING_MODULES}
    assert daily <= companies <= set(p.DEFAULT_COMPANIES)
    assert len(captured['companies']) < len(p.DEFAULT_COMPANIES)


# --- 2. resume accepts added platform companies, never aborts -----------------

def test_resume_accepts_newly_added_platform_company(tmp_path):
    root, run = tmp_path, tmp_path / 'run'
    with patch.object(p, 'collect_process',
                      side_effect=lambda c, s, o, t: validated(c, s)):
        assert p.run(root, run, ['大疆'], ['campus']) == 0
    calls = []

    def fake(company, scope, output, timeout):
        calls.append(company)
        return validated(company, scope)

    with patch.object(p, 'collect_process', side_effect=fake):
        assert p.run(root, run, ['大疆', '小天才'], ['campus'], resume=True) == 0
    assert calls == ['小天才']  # 大疆 is reused from the checkpoint
    status = json.loads((run / 'status.json').read_text(encoding='utf-8'))
    assert status['companies'] == ['大疆', '小天才']
    assert set(status['results']) == {'大疆/campus', '小天才/campus'}
    assert status['success'] is True


def test_resume_with_removed_company_restarts_instead_of_raising(tmp_path):
    root, run = tmp_path, tmp_path / 'run'
    assert p.run(root, run, ['大疆', '小天才'], ['campus'], max_run_seconds=0) == 1
    calls = []

    def fake(company, scope, output, timeout):
        calls.append(company)
        return validated(company, scope)

    with patch.object(p, 'collect_process', side_effect=fake):
        assert p.run(root, run, ['大疆'], ['campus'], resume=True) == 0
    assert calls == ['大疆']  # the stale two-company checkpoint is not reused
    status = json.loads((run / 'status.json').read_text(encoding='utf-8'))
    assert status['companies'] == ['大疆']
    assert set(status['results']) == {'大疆/campus'}


def test_resume_compatible_only_for_scopes_and_company_subsets():
    checkpoint = {'companies': ['大疆'], 'scopes': ['campus']}
    assert p.resume_compatible(checkpoint, ['大疆', '小天才'], ['campus']) is True
    assert p.resume_compatible(checkpoint, ['大疆'], ['campus']) is True
    assert p.resume_compatible(checkpoint, ['拼多多'], ['campus']) is False
    assert p.resume_compatible(checkpoint, ['大疆', '小天才'], ['intern']) is False


# --- 3. production request budget is uncapped --------------------------------

def test_platform_request_budget_defaults_to_unlimited(monkeypatch):
    monkeypatch.delenv('QIUZHAO_PLATFORM_REQUEST_BUDGET', raising=False)
    assert beisen.DEFAULT_REQUEST_BUDGET is None
    assert moka.DEFAULT_REQUEST_BUDGET is None
    assert beisen._budget_limit(None) is None
    assert moka._budget_limit(None) is None
    # The verification-only cap still applies when explicitly requested.
    monkeypatch.setenv('QIUZHAO_PLATFORM_REQUEST_BUDGET', '20')
    assert beisen._budget_limit(None) == 20
    assert moka._budget_limit(None) == 20
    assert beisen._budget_limit(5) == 5
    assert moka._budget_limit(5) == 5


# --- 4. the deployable jingling collector passes the new p1 step args ---------

def test_deployable_windows_collector_uses_scope_timeout_and_workers():
    from deploy import windows_collector as W
    source = Path(W.__file__).read_text(encoding='utf-8')
    assert "'--scope-timeout','600'" in source
    assert "'--workers','8'" in source
    assert "'--platform-workers','3'" in source
    assert "'--max-run-seconds','18000'" in source
    assert "'--timeout','1200'" not in source
    # The ported production tail (base-sync via lark_sync_daemon) must be intact.
    assert "state['stage']='base-sync'" in source
    assert 'lark_sync_daemon' in source
    assert 'lark_sync_index' not in source


# --- 5. merged 20260918i + 20260918j registry guards --------------------------

def test_default_set_is_h_baseline_plus_i_and_j_additions():
    # 站长口径的 924 家 (20260918h) + 字节跳动/美的集团 + 外企第二批新增 = 948,
    # + 外企发现批 20260919d 净增 16 家 = 964.
    assert len(p.DEFAULT_COMPANIES) == EXPECTED_DEFAULT_COMPANIES
    for name in (*PUBLIC_API_ONLY, *DAYEE_ONLY, *JOB51_ONLY):
        assert name in p.DEFAULT_COMPANIES, name
    assert p.REGISTRY['字节跳动'] == 'qiuzhao.collector.p1_bytedance_public'
    assert p.REGISTRY['美的集团'] == 'qiuzhao.collector.p1_midea_public'
    for name in DAYEE_ONLY:
        assert p.REGISTRY[name] == DAYEE_MODULE, name
    for name in JOB51_ONLY:
        assert p.REGISTRY[name] == JOB51_MODULE, name
    # Earlier blocks keep their owners after the merge.
    assert p.REGISTRY['中信建投'] == 'qiuzhao.collector.p1_platform_beisen'
    assert p.REGISTRY['英伟达'] == 'qiuzhao.collector.p1_platform_workday'
    assert p.REGISTRY['思爱普'] == 'qiuzhao.collector.p1_platform_successfactors'
    assert p.REGISTRY['中国工商银行'] == 'qiuzhao.collector.p1_banks_01'
    assert p.REGISTRY['阿里巴巴'] == 'qiuzhao.collector.alibaba_headless'
    assert p.REGISTRY['腾讯音乐'] == 'qiuzhao.collector.tencent_music'


def _declared_config_names(section):
    path = Path(p.__file__).with_name('p1_platform_companies.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    names = []
    for entry in (data.get(section) or {}).values():
        name = entry if isinstance(entry, str) else str((entry or {}).get('name') or '')
        if name:
            names.append(name)
    return names


def test_registry_names_are_unique_and_config_sections_never_hijack_a_module():
    # A duplicate canonical name would silently merge two adapters into one daily
    # unit and drop one of them from the run plan. 高露洁 (beisen) and 高露洁棕榄
    # (moka) are two distinct official names on purpose.
    assert len(p.DEFAULT_COMPANIES) == len(set(p.DEFAULT_COMPANIES))
    assert len(p.REGISTRY) == len(p.DEFAULT_COMPANIES)
    assert set(p.REGISTRY) == set(p.DEFAULT_COMPANIES)
    assert p.REGISTRY['高露洁'] == 'qiuzhao.collector.p1_platform_beisen'
    assert p.REGISTRY['高露洁棕榄'] == 'qiuzhao.collector.p1_platform_moka'

    declared = {section: _declared_config_names(section)
                for section in CONFIG_SECTION_MODULES}
    # No name may be declared by two different sections: the later block would
    # silently replace the earlier block's adapter through REGISTRY.update().
    owners = {}
    for section, names in declared.items():
        for name in set(names):
            assert name not in owners, (name, owners.get(name), section)
            owners[name] = section
    # Every declared name resolves to its own section's module. A setdefault
    # section (feishu) is allowed to leave an earlier dedicated adapter in place;
    # anything else means the section hijacked a company it does not own.
    for section, names in declared.items():
        for name in names:
            owner = p.REGISTRY[name]
            if name in p.COMPANIES:
                if owner == CONFIG_SECTION_MODULES[section]:
                    # beisen/moka deliberately adopt the overlapping hardcoded
                    # 三七互娱/金山办公/鹰角网络 moka tenants.
                    assert section in ('beisen', 'moka'), (section, name, owner)
                else:
                    # feishu's setdefault must keep the hardcoded p1_sources_* slot.
                    assert section == 'feishu' and owner.startswith('qiuzhao.collector.p1_sources_'), \
                        (section, name, owner)
                continue
            if owner == CONFIG_SECTION_MODULES[section] or section == 'feishu':
                continue
            raise AssertionError((section, name, owner))
