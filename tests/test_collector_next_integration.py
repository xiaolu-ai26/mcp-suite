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
import importlib
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
# Foreign batch A (20260919b): Eightfold AI and Phenom People public careers.
EIGHTFOLD_MODULE = 'qiuzhao.collector.p1_platform_eightfold'
PHENOM_MODULE = 'qiuzhao.collector.p1_platform_phenom'
EIGHTFOLD_ONLY = ('惠普', '微软', '高通', '应用材料', '泛林')
PHENOM_ONLY = ('宝洁', '玛氏', '罗氏', '波士顿咨询', 'ABB', '飞利浦', '默沙东', '思科')
DAYEE_ONLY = ('德勤', '康师傅', 'ZARA', '广汽集团', '益海嘉里', '迪卡侬', 'ZURU')
JOB51_ONLY = ('百事',)
# Foreign batch 3 (20260919c): Avature portals, the iCIMS Career Portal and Oracle
# Recruiting Cloud candidate-experience sites, plus the three Workday tenants and
# one SuccessFactors tenant whose earlier "China -> 0" reading was a scope/parser
# artefact. The iCIMS section deliberately registers no company (every
# China-relevant tenant publishes "Disallow: /"); the module still ships.
AVATURE_MODULE = 'qiuzhao.collector.p1_platform_avature'
ICIMS_MODULE = 'qiuzhao.collector.p1_platform_icims'
ORC_MODULE = 'qiuzhao.collector.p1_platform_orc'
AVATURE_ONLY = ('西门子', '欧莱雅', '艺电', '贝恩')
ORC_ONLY = ('霍尼韦尔', '摩根大通', '康明斯', '艾默生', '洲际酒店', '万豪', '宣伟',
            '阿卡迈', '百胜餐饮')
WORKDAY_FIXED = ('可口可乐', '耐克', 'GSK')
SF_FIXED = ('巴斯夫',)
# Foreign batch C (20260919f) + the 20260919g full-site batch: the tupu360
# multi-tenant platform. collector-next-6 imported the full-site batch's
# configuration (60 careersite tenants, 68 declared rows) with every row parked.
# 站长 decided on 2026-09-20 ("接回来的60家都开") to enable the 60 careersite rows
# even though the platform robots.txt is a site-wide "Disallow: /"; the 8 rows whose
# anonymous side has no public route stay parked. 5 of the 60 names already belong to
# an earlier-registered adapter (ABB/康明斯/强生/斯堪尼亚/药明康德), so the daily set
# grows by 55, not 60.
TUPU360_MODULE = 'qiuzhao.collector.p1_platform_tupu360'
TUPU360_ENABLED = ('IQVIA 艾昆纬', '礼来', '舍弗勒', '宝马', '茵梦达')
TUPU360_ENABLED_NET_NEW = 55
TUPU360_SETDEFAULT_OWNERS = {
    'ABB': 'qiuzhao.collector.p1_platform_phenom',
    '康明斯': 'qiuzhao.collector.p1_platform_orc',
    '强生': 'qiuzhao.collector.p1_platform_workday',
    '斯堪尼亚': 'qiuzhao.collector.p1_platform_moka',
    '药明康德': 'qiuzhao.collector.p1_sources_41_50',
}
# Same-name conflicts resolved by measurement (see RECEIPT-collector-next-4):
# 惠普/应用材料 -> Eightfold, 飞利浦 -> Phenom (more measured China postings than
# the discovery Workday rows, which are parked); 强生 stays on the pre-existing
# Workday tenant because tupu360 is off; 毕马威 keeps the shipped moka tenant.
PARKED_WORKDAY = ('惠普', '应用材料', '飞利浦')
SAME_NAME_OWNERS = {
    '惠普': EIGHTFOLD_MODULE,
    '应用材料': EIGHTFOLD_MODULE,
    '飞利浦': PHENOM_MODULE,
    '强生': 'qiuzhao.collector.p1_platform_workday',
    '毕马威': 'qiuzhao.collector.p1_platform_moka',
}
# 20260918h shipped 924 companies; this cumulative branch adds 字节跳动/美的集团
# (20260918i), 22 foreign-batch names (20260918j), 13 foreign ATS tenants from
# batch A (20260919b: Eightfold 5 + Phenom 8), 17 names from the 20260919c platform
# blocks, 5 net-new tupu360 tenants (20260919f) and the 82 foreign-discovery names
# (20260919d/round 2: +10 moka, +5 dayee, +8 job51, +1 beisen, +58 workday, of
# which 惠普/应用材料/飞利浦/可口可乐 duplicate batch A/B rows), i.e.
# 948 + 13 + 17 + 5 + 82 - 4 = 1061 names before the same-company conflict
# handling. Parking the whole tupu360 section (5 names, 强生 was already blocked by
# setdefault) removes exactly those 5: 1061 - 5 = **1056**. 惠普/应用材料/飞利浦 and
# 毕马威 keep their names through the winning adapter, so they are not subtracted.
# multi-entrance recheck (2026-09-19): 雀巢/博西家电/北京环球度假区/昂际航电 (moka),
# 上汽大众/光束汽车 (beisen), 杜邦/友邦保险/丹纳赫 (workday) and
# 阿克苏诺贝尔/汇丰/阿迪达斯 (successfactors) were added after being wrongly parked;
# 1056 + 13 = **1069** (12 + 通用磨坊 Workday).
# gap-report (feat/gap-report, 2026-09-20): 站长 enabled the 60 tupu360 careersite
# tenants; 5 names keep an earlier adapter (TUPU360_SETDEFAULT_OWNERS), so
# 1069 + (60 - 5) = **1124**.
EXPECTED_DEFAULT_COMPANIES = 1124
CONFIG_SECTION_MODULES = {
    'beisen': 'qiuzhao.collector.p1_platform_beisen',
    'moka': 'qiuzhao.collector.p1_platform_moka',
    'feishu': 'qiuzhao.collector.p1_feishu_public',
    'workday': 'qiuzhao.collector.p1_platform_workday',
    'successfactors': 'qiuzhao.collector.p1_platform_successfactors',
    'dayee': DAYEE_MODULE,
    'job51': JOB51_MODULE,
    'eightfold': EIGHTFOLD_MODULE,
    'phenom': PHENOM_MODULE,
    'avature': AVATURE_MODULE,
    'icims': ICIMS_MODULE,
    'orc': ORC_MODULE,
    'tupu360': TUPU360_MODULE,
}
# Sections whose registration block uses REGISTRY.setdefault, so a name they
# declare may legitimately keep an earlier adapter (feishu portals and the
# tupu360 tenant that duplicates 强生's approved Workday entry).
SETDEFAULT_SECTIONS = ('feishu', 'tupu360')


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
    # Foreign batch A (20260919b) appended after the 51job block.
    eightfold_names = [n for n in extra if module_of(n) == EIGHTFOLD_MODULE]
    phenom_names = [n for n in extra if module_of(n) == PHENOM_MODULE]
    # Foreign batch-3 blocks (20260919c) appended after the batch-A blocks.
    avature_names = [n for n in extra if module_of(n) == AVATURE_MODULE]
    icims_names = [n for n in extra if module_of(n) == ICIMS_MODULE]
    orc_names = [n for n in extra if module_of(n) == ORC_MODULE]
    # Foreign batch C (20260919f) appended last.
    tupu360_names = [n for n in extra if module_of(n) == TUPU360_MODULE]

    assert set(AVATURE_ONLY) <= set(avature_names)
    assert set(ORC_ONLY) <= set(orc_names)
    assert icims_names == [], 'no iCIMS tenant may be registered while robots disallows'
    assert set(PLATFORM_ONLY) <= set(beisen_names) | set(moka_names)
    assert set(BANK_ONLY) <= set(bank_names)
    assert set(FOREIGN_ONLY) <= set(foreign_names)
    assert set(PUBLIC_API_ONLY) <= set(public_api_names)
    # 站长 enabled the 60 tupu360 careersite tenants on 2026-09-20 (platform robots is
    # a site-wide Disallow, accepted knowingly). 5 names keep an earlier adapter, so
    # the block contributes 55 net-new companies and stays the last contiguous block.
    assert len(tupu360_names) == TUPU360_ENABLED_NET_NEW
    assert set(TUPU360_ENABLED) <= set(tupu360_names)
    for name, module in TUPU360_SETDEFAULT_OWNERS.items():
        assert name not in tupu360_names, name
        assert p.REGISTRY[name] == module, (name, p.REGISTRY[name])
    assert TUPU360_MODULE in p.PLATFORM_MODULES
    coverage_blocks = (set(beisen_names) | set(moka_names) | set(bank_names) | set(ali_names)
                       | set(tme_names) | set(foreign_names) | set(feishu_names)
                       | set(public_api_names) | set(dayee_names) | set(job51_names)
                       | set(eightfold_names) | set(phenom_names)
                       | set(avature_names) | set(icims_names) | set(orc_names)
                       | set(tupu360_names))
    assert set(extra) == coverage_blocks
    assert set(EIGHTFOLD_ONLY) <= set(eightfold_names)
    assert set(PHENOM_ONLY) <= set(phenom_names)

    # Approved append order: beisen then moka, banks, Ali/Tencent gap, foreign
    # Workday/SuccessFactors, config-driven Feishu, the 20260918i public-API batch
    # (字节跳动/美的集团), the 20260918j foreign batch-2 blocks (Dayee hotjob.cn,
    # then 51job micro-sites), then the 20260919b foreign batch-A blocks
    # (Eightfold AI, then Phenom People). Every block stays contiguous and no
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
        ('eightfold', eightfold_names),
        ('phenom', phenom_names),
        ('avature', avature_names),
        ('icims', icims_names),
        ('orc', orc_names),
        ('tupu360', tupu360_names),
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
    for name in AVATURE_ONLY:
        assert p.REGISTRY[name] == AVATURE_MODULE, name
    for name in ORC_ONLY:
        assert p.REGISTRY[name] == ORC_MODULE, name
    # The 20260919c fixes keep their original platform owners.
    for name in WORKDAY_FIXED:
        assert p.REGISTRY[name] == 'qiuzhao.collector.p1_platform_workday', name
    for name in SF_FIXED:
        assert p.REGISTRY[name] == 'qiuzhao.collector.p1_platform_successfactors', name
    # 德州仪器 must stay on its moka campus tenant (the ORC tenant of the same name
    # was deliberately not registered so it cannot overwrite this slot).
    assert p.REGISTRY['德州仪器'] == 'qiuzhao.collector.p1_platform_moka'


def test_icims_module_still_exposes_the_collect_contract():
    # Signed off but with an empty config: the module must stay importable so a
    # future robots-permitted tenant is a one-line change.
    import importlib
    module = importlib.import_module(ICIMS_MODULE)
    assert callable(module.collect)
    assert module.COMPANIES == {}


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
    # Effective values, not source spellings: the p1 step limit is now derived from the
    # deadline it passes to p1 (see steps_for/P1_STEP_LIMIT and the 2026-09-20 P0).
    steps = {name: (args, limit) for name, args, limit in W.steps_for(Path('/stage'), False)}
    p1_args, p1_limit = steps['p1']
    assert p1_args[p1_args.index('--scope-timeout') + 1] == '600'
    assert p1_args[p1_args.index('--workers') + 1] == '8'
    assert p1_args[p1_args.index('--platform-workers') + 1] == '3'
    assert p1_args[p1_args.index('--max-run-seconds') + 1] == '18000'
    assert p1_limit > W.P1_MAX_RUN_SECONDS + 600, 'watchdog must outlast p1 finalisation'
    assert '--timeout' not in p1_args
    assert [name for name, _a, _l in W.steps_for(Path('/stage'), False)] == \
        ['basic', 'tencent', 'p1', 'normalize']
    # The ported production tail (base-sync via lark_sync_daemon) must be intact.
    assert "state['stage']='base-sync'" in source
    assert 'lark_sync_daemon' in source
    assert 'lark_sync_index' not in source


# --- 5. merged 20260918i + 20260918j registry guards --------------------------

def test_default_set_is_h_baseline_plus_i_j_a_c_and_discovery_additions():
    # 站长口径的 924 家 (20260918h) + 字节跳动/美的集团 + 外企第二批 + 外企 ATS
    # 批 A(13 家)+ 批 3(17 家,含 3 家 workday/1 家 SF 修复行)+ 外企发现两轮
    # (82 家,其中 4 家与批 A/B 同名)= 1061;tupu360 全段留档后再减 5 家 = 1056;
    # multi-entrance 复核再接入 13 家 = 1069(12 家 + 通用磨坊 Workday 替代 iCIMS);
    # gap-report 按站长 2026-09-20 决定启用 tupu360 60 家,其中 5 家沿用更早注册的
    # 适配器,故 +55 = 1124。
    assert len(p.DEFAULT_COMPANIES) == EXPECTED_DEFAULT_COMPANIES
    for name in (*PUBLIC_API_ONLY, *DAYEE_ONLY, *JOB51_ONLY, *EIGHTFOLD_ONLY,
                *PHENOM_ONLY, *AVATURE_ONLY, *ORC_ONLY, *WORKDAY_FIXED, *SF_FIXED):
        assert name in p.DEFAULT_COMPANIES, name
    assert p.REGISTRY['字节跳动'] == 'qiuzhao.collector.p1_bytedance_public'
    assert p.REGISTRY['美的集团'] == 'qiuzhao.collector.p1_midea_public'
    for name in DAYEE_ONLY:
        assert p.REGISTRY[name] == DAYEE_MODULE, name
    for name in JOB51_ONLY:
        assert p.REGISTRY[name] == JOB51_MODULE, name
    for name in EIGHTFOLD_ONLY:
        assert p.REGISTRY[name] == EIGHTFOLD_MODULE, name
    for name in PHENOM_ONLY:
        assert p.REGISTRY[name] == PHENOM_MODULE, name
    for name in AVATURE_ONLY:
        assert p.REGISTRY[name] == AVATURE_MODULE, name
    for name in ORC_ONLY:
        assert p.REGISTRY[name] == ORC_MODULE, name
    # Same-name conflicts: exactly one adapter owns each name; the 5 tupu360 names
    # that collide keep the earlier adapter, the other 55 are tupu360's own.
    for name, module in SAME_NAME_OWNERS.items():
        assert p.REGISTRY[name] == module, (name, p.REGISTRY[name])
    for name in TUPU360_ENABLED:
        assert name in p.DEFAULT_COMPANIES, name
    assert p.REGISTRY['IQVIA 艾昆纬'] == TUPU360_MODULE
    for name, module in TUPU360_SETDEFAULT_OWNERS.items():
        assert p.REGISTRY[name] == module, (name, p.REGISTRY[name])
    # Earlier blocks keep their owners after the merge.
    assert p.REGISTRY['中信建投'] == 'qiuzhao.collector.p1_platform_beisen'
    assert p.REGISTRY['英伟达'] == 'qiuzhao.collector.p1_platform_workday'
    assert p.REGISTRY['思爱普'] == 'qiuzhao.collector.p1_platform_successfactors'
    assert p.REGISTRY['中国工商银行'] == 'qiuzhao.collector.p1_banks_01'
    assert p.REGISTRY['阿里巴巴'] == 'qiuzhao.collector.alibaba_headless'
    assert p.REGISTRY['腾讯音乐'] == 'qiuzhao.collector.tencent_music'


def test_icims_registers_no_company_and_tupu360_registers_the_enabled_60():
    # iCIMS ships the adapter but no tenant: every China-relevant portal publishes
    # "Disallow: /". tupu360 also has a platform-wide Disallow, but 站长 decided on
    # 2026-09-20 ("接回来的60家都开") to crawl the 60 careersite tenants anyway, so the
    # module now contributes 55 net-new companies and keeps 8 rows parked with a
    # recorded reason (7 WeChat-only + 1 tenant with zero public postings).
    from qiuzhao.collector import p1_platform_icims as icims
    from qiuzhao.collector import p1_platform_tupu360 as tupu360
    assert icims.merged_registry() == {}
    registry = tupu360.merged_registry()
    assert len(registry) == 60
    assert set(registry.values()) == {'qiuzhao.collector.p1_platform_tupu360'}
    enabled = disabled = 0
    for key, entry in tupu360._read_platform().items():
        if str(key).startswith('_'):
            continue
        if entry.get('enabled') is False:
            disabled += 1
            assert entry.get('blocked_reason'), key
        else:
            enabled += 1
            assert entry.get('enabled_reason'), key
            assert '站长 2026-09-20' in entry['enabled_reason'], key
    assert (enabled, disabled) == (60, 8)


def test_parked_rows_are_inert_in_the_owning_adapter():
    # 惠普/应用材料/飞利浦 are parked in the workday section: the discovery rows must
    # not register, and the surviving workday rows keep their tenant ids.
    from qiuzhao.collector import p1_platform_workday as workday
    for name in PARKED_WORKDAY:
        assert name not in workday.NAME_TO_SLUG, name
    assert workday.NAME_TO_SLUG['可口可乐'] == 'coke/wd1/coca-cola-careers'
    assert workday.NAME_TO_SLUG['耐克'] == 'nike/wd1/nke'
    assert workday.NAME_TO_SLUG['GSK'] == 'gsk/wd5/GSKCareers'
    # 毕马威's second (newer) moka tenant is parked, so the shipped tenant wins by
    # configuration instead of by dict order.
    assert moka.NAME_TO_SLUG['毕马威'] == 'kpmg/76195'
    assert 'kpmg/74356' not in moka.COMPANIES


def test_every_config_driven_adapter_honours_the_enabled_false_park():
    # The enabled:false contract has to be uniform: one parked row must never
    # register a company, whichever config section it lives in.
    opened = 'REDACTED'
    parked = 'SU648133e50dcad45af15e3cb2'
    modules = sorted(set(CONFIG_SECTION_MODULES.values()) | {TUPU360_MODULE})
    for module_path in modules:
        module = importlib.import_module(module_path)
        reader = getattr(module, '_read_platform', None) or getattr(module, '_load_platform')
        with patch.object(module, reader.__name__,
                          lambda: {opened: {'name': '开启公司'},
                                   parked: {'name': '留档公司', 'enabled': False}}):
            names = list(module._load_companies().values())
        assert '开启公司' in names, module_path
        assert '留档公司' not in names, module_path


def _declared_config_names(section):
    path = Path(p.__file__).with_name('p1_platform_companies.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    names = []
    for key, entry in (data.get(section) or {}).items():
        if str(key).startswith('_'):  # section documentation, not a tenant
            continue
        if isinstance(entry, dict) and entry.get('enabled') is False:
            continue  # a disabled survey line never registers a company
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
    # No name may be declared by two different dedicated sections: the later block
    # would silently replace the earlier block's adapter through REGISTRY.update().
    # A setdefault section may shadow a name because it can never displace it, but
    # the shadow must be documented here rather than discovered in production.
    owners = {}
    shadowed = set()
    for section, names in declared.items():
        for name in set(names):
            if name in owners:
                assert section in SETDEFAULT_SECTIONS, (name, owners.get(name), section)
                assert p.REGISTRY[name] == CONFIG_SECTION_MODULES[owners[name]], \
                    (name, owners[name], p.REGISTRY[name])
                shadowed.add(name)
                continue
            owners[name] = section
    # Every declared name resolves to its own section's module. A setdefault
    # section is allowed to leave an earlier dedicated adapter in place;
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
                    # A setdefault section must keep the hardcoded p1_sources_* slot:
                    # feishu portals, and tupu360's 药明康德 line (the tenant is real,
                    # but the approved hardcoded adapter owns the name).
                    assert section in ('feishu', 'tupu360') and \
                        owner.startswith('qiuzhao.collector.p1_sources_'), (section, name, owner)
                continue
            if owner == CONFIG_SECTION_MODULES[section] or section in SETDEFAULT_SECTIONS:
                continue
            raise AssertionError((section, name, owner))
