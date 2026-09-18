"""Scheduling safety for the 900+ company daily chain.

Covers: three-scope defaults (social included), per-company config narrowing,
per-platform host concurrency/spacing, deterministic multi-day rotation, per-company
chain plans, and the next-day fairness fallback that promotes units the
``--max-run-seconds`` cap never attempted. All tests are offline;
``collect_process`` is patched.
"""
import datetime as dt
import json
import threading
import time
from unittest.mock import patch

from qiuzhao.collector import p1_pipeline as p
from qiuzhao.collector import p1_platform_beisen as beisen
from qiuzhao.collector import p1_platform_moka as moka


def validated(company, scope='campus'):
    # A partial that still carried rows counts as trustworthy output, so run()
    # exits 2 instead of 1 and the calls are the only assertion target.
    return {'jobs': [], 'coverage': {'status': 'partial', 'complete': False,
            'detail_complete': False, 'available_job_count': 1, 'pending_count': 0,
            'collected_jobs': 0, 'pages_scanned': 1, 'errors': [],
            'checked_at': p.now(), 'scope_evidence': 'offline'}}


MOKA_COMPANIES = [name for name in moka.COMPANIES.values() if name not in p.COMPANIES][:6]


# --- scope policy -------------------------------------------------------------

def test_hardcoded_companies_keep_all_three_scopes():
    assert p.company_scopes('大疆') == ['campus', 'intern', 'social']
    # A platform config line may shadow a hardcoded REGISTRY entry (三七互娱); the
    # hardcoded slot must still keep three scopes.
    assert p.company_scopes('三七互娱') == ['campus', 'intern', 'social']


def test_platform_companies_default_to_three_scopes():
    # 站长 2026-09-18：社招也跑，平台公司不再默认跳过 social。
    for company in (MOKA_COMPANIES[0], '中信建投', '交通银行', '英伟达', '思爱普'):
        assert p.company_scopes(company) == ['campus', 'intern', 'social'], company


def test_ali_and_tencent_keep_three_scopes():
    assert p.company_scopes('腾讯音乐') == ['campus', 'intern', 'social']
    assert p.company_scopes('阿里巴巴') == ['campus', 'intern', 'social']


def test_config_scopes_override_can_narrow_a_platform_company(monkeypatch):
    monkeypatch.setitem(p.PLATFORM_SCOPE_OPT_INS, MOKA_COMPANIES[0],
                        {'campus', 'intern'})
    assert p.company_scopes(MOKA_COMPANIES[0]) == ['campus', 'intern']


def test_run_runs_social_by_default_for_platform_and_hardcoded(tmp_path):
    calls = []

    def fake(company, scope, output, timeout):
        calls.append((company, scope))
        return validated(company, scope)

    with patch.object(p, 'collect_process', side_effect=fake):
        assert p.run(tmp_path, tmp_path / 'run', ['大疆', MOKA_COMPANIES[0]],
                     ['campus', 'intern', 'social'], workers=2) == 2
    for company in ('大疆', MOKA_COMPANIES[0]):
        for scope in ('campus', 'intern', 'social'):
            assert (company, scope) in calls


def test_run_honours_config_narrowing(tmp_path, monkeypatch):
    monkeypatch.setitem(p.PLATFORM_SCOPE_OPT_INS, MOKA_COMPANIES[0], {'campus'})
    calls = []

    def fake(company, scope, output, timeout):
        calls.append((company, scope))
        return validated(company, scope)

    with patch.object(p, 'collect_process', side_effect=fake):
        p.run(tmp_path, tmp_path / 'run', [MOKA_COMPANIES[0]],
              ['campus', 'intern', 'social'], workers=1)
    assert (MOKA_COMPANIES[0], 'campus') in calls
    assert (MOKA_COMPANIES[0], 'intern') not in calls
    assert (MOKA_COMPANIES[0], 'social') not in calls


# --- per-platform gate --------------------------------------------------------

def test_platform_group_maps_known_hosts():
    assert p.platform_group('中信建投') == 'zhiye.com'
    assert p.platform_group(MOKA_COMPANIES[0]) == 'app.mokahr.com'
    assert p.platform_group('大疆') == 'company:大疆'


def test_platform_gate_caps_same_platform_concurrency(tmp_path):
    lock = threading.Lock()
    active = 0
    peak = 0

    def fake(company, scope, output, timeout):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.15)
        with lock:
            active -= 1
        return validated(company, scope)

    companies = MOKA_COMPANIES[:4]
    with patch.object(p, 'collect_process', side_effect=fake):
        p.run(tmp_path, tmp_path / 'run', companies, ['campus'], workers=4,
              platform_workers=2, platform_min_interval=0.0)
    assert peak <= 2, peak


def test_platform_gate_spaces_same_platform_launches(tmp_path):
    starts = []
    lock = threading.Lock()

    def fake(company, scope, output, timeout):
        with lock:
            starts.append(time.monotonic())
        return validated(company, scope)

    companies = MOKA_COMPANIES[:3]
    with patch.object(p, 'collect_process', side_effect=fake):
        p.run(tmp_path, tmp_path / 'run', companies, ['campus'], workers=3,
              platform_workers=2, platform_min_interval=0.3)
    starts.sort()
    gaps = [later - earlier for earlier, later in zip(starts, starts[1:])]
    assert gaps and min(gaps) >= 0.2, gaps


# --- foreign batch 2: Dayee / 51job join the gate, 字节/美的 stay dedicated ----

def _companies_with_module(module):
    return [name for name in p.DEFAULT_COMPANIES if p.REGISTRY[name] == module]


def test_dayee_and_51job_companies_join_the_platform_gate():
    dayee = _companies_with_module('qiuzhao.collector.p1_foreign_01')
    job51 = _companies_with_module('qiuzhao.collector.p1_platform_51job')
    assert len(dayee) == 7 and '德勤' in dayee
    assert job51 == ['百事']
    for name in dayee:
        # Same multi-tenant host => one shared gate group, three scopes, no rotation.
        assert p.platform_group(name) == 'hotjob.cn', name
        assert p.company_scopes(name) == ['campus', 'intern', 'social'], name
    assert p.platform_group('百事') == '51job.com'
    assert p.company_scopes('百事') == ['campus', 'intern', 'social']
    assert not ({'qiuzhao.collector.p1_foreign_01', 'qiuzhao.collector.p1_platform_51job'}
                & p.ROTATING_MODULES)


def test_gate_caps_concurrency_across_dayee_tenants(tmp_path):
    # The 7 Dayee tenants are different companies on one upstream host, so the
    # per-platform cap (not the global worker count) must bound them.
    lock = threading.Lock()
    active = 0
    peak = 0

    def fake(company, scope, output, timeout):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.15)
        with lock:
            active -= 1
        return validated(company, scope)

    companies = _companies_with_module('qiuzhao.collector.p1_foreign_01')[:4]
    with patch.object(p, 'collect_process', side_effect=fake):
        p.run(tmp_path, tmp_path / 'run', companies, ['campus'], workers=4,
              platform_workers=2, platform_min_interval=0.0)
    assert peak <= 2, peak


def test_bytedance_and_midea_are_daily_dedicated_adapters():
    # 每天必跑的专用适配器：不进 PLATFORM_MODULES，所以各有独立 gate 组，
    # 不与其他公司共享限流，也不参与任何轮转；scope 由适配器自己决定
    # （美的 social 按其设计返回 blocked，见 test_p1_midea_public.py）。
    for name in ('字节跳动', '美的集团'):
        module = p.REGISTRY[name]
        assert module not in p.PLATFORM_MODULES, name
        assert module not in p.ROTATING_MODULES, name
        assert p.platform_group(name) == 'company:' + name, name
        assert p.company_scopes(name) == ['campus', 'intern', 'social'], name
    assert p.REGISTRY['字节跳动'] == 'qiuzhao.collector.p1_bytedance_public'
    assert p.REGISTRY['美的集团'] == 'qiuzhao.collector.p1_midea_public'
    assert p.REGISTRY['字节跳动'] not in p.PLATFORM_HOST_GROUPS
    assert p.REGISTRY['美的集团'] not in p.PLATFORM_HOST_GROUPS


# --- day rotation -------------------------------------------------------------

def test_rotation_partitions_only_config_platforms():
    groups = 3
    rotating = [name for name in p.DEFAULT_COMPANIES
                if name not in p.COMPANIES and p.REGISTRY[name] in p.ROTATING_MODULES]
    buckets = [p.platform_rotation_group(name, groups) for name in rotating]
    assert set(buckets) == {0, 1, 2}
    for day in (dt.date(2026, 9, 18), dt.date(2026, 9, 19), dt.date(2026, 9, 20)):
        selected = p.companies_for_day(p.DEFAULT_COMPANIES, groups, day=day)
        # Hardcoded 50 and every non-rotating adapter stay in every day.
        assert set(p.COMPANIES) <= set(selected)
        daily = {name for name in p.DEFAULT_COMPANIES
                 if name not in p.COMPANIES and p.REGISTRY[name] not in p.ROTATING_MODULES}
        assert daily <= set(selected)
        # Rotating companies appear exactly on their bucket day.
        bucket = day.toordinal() % groups
        assert {name for name in selected if name in rotating} == {
            name for name in rotating if p.platform_rotation_group(name, groups) == bucket}


def test_rotation_is_deterministic_and_off_by_default_one():
    rotating = [name for name in p.DEFAULT_COMPANIES
                if name not in p.COMPANIES and p.REGISTRY[name] in p.ROTATING_MODULES]
    assert p.companies_for_day(rotating, 2, day=dt.date(2026, 9, 18)) == \
        p.companies_for_day(rotating, 2, day=dt.date(2026, 9, 18))
    assert p.companies_for_day(p.DEFAULT_COMPANIES, 1) == p.DEFAULT_COMPANIES


def test_rotation_default_is_one_full_set():
    # 站长口径：默认不轮转，每天全公司跑。
    assert p.PLATFORM_ROTATION_DEFAULT == 1
    assert p.companies_for_day(p.DEFAULT_COMPANIES, p.PLATFORM_ROTATION_DEFAULT) == \
        p.DEFAULT_COMPANIES


def test_plan_chains_uses_per_company_scopes():
    scopes_by_company = {'大疆': ['campus', 'intern', 'social'],
                         MOKA_COMPANIES[0]: ['campus', 'intern']}
    chains = {chain['company']: chain['scopes'] for chain in p.plan_chains(
        ['大疆', MOKA_COMPANIES[0]], ['campus', 'intern', 'social'], {},
        scopes_by_company=scopes_by_company)}
    assert chains['大疆'] == ['campus', 'intern', 'social']
    assert chains[MOKA_COMPANIES[0]] == ['campus', 'intern']


# --- next-day fairness fallback for the 5h hard cap ----------------------------

def test_plan_chains_leads_with_never_attempted_then_stalest():
    companies = ['大疆', '拼多多', '小米']
    scopes = ['campus']
    # 大疆 attempted most recently, 拼多多 long ago, 小米 was never reached.
    last_attempt = {'大疆/campus': 2000.0, '拼多多/campus': 1000.0}
    order = [chain['company'] for chain in p.plan_chains(
        companies, scopes, {}, last_attempt=last_attempt)]
    assert order == ['小米', '拼多多', '大疆']


def test_plan_chains_prioritizes_failed_units_next_day():
    companies = ['大疆', '拼多多']
    scopes = ['campus']
    queue = {'拼多多/campus': {'company': '拼多多', 'scope': 'campus',
                               'consecutive_days': 1, 'reason': 'timeout'}}
    # 拼多多 was attempted later than 大疆 but failed, so the retry leads.
    last_attempt = {'大疆/campus': 1000.0, '拼多多/campus': 2000.0}
    order = [chain['company'] for chain in p.plan_chains(
        companies, scopes, queue, last_attempt=last_attempt)]
    assert order == ['拼多多', '大疆']


def test_two_day_simulation_attempts_every_unit_once():
    companies = ['大疆', '拼多多', '小米']
    scopes = ['campus', 'intern']
    # Day 1 cold start: the cap only fits the first company's two scopes.
    day1 = p.plan_chains(companies, scopes, {})
    attempted, last_attempt = set(), {}
    for chain in day1[:1]:
        for scope in chain['scopes']:
            attempted.add((chain['company'], scope))
            last_attempt[f"{chain['company']}/{scope}"] = 1000.0
    # Day 2: the two companies the cap never reached lead the plan.
    day2 = p.plan_chains(companies, scopes, {}, last_attempt=last_attempt)
    assert day2[0]['company'] == '拼多多'
    assert day2[0]['company'] not in {chain['company'] for chain in day1[:1]}
    for chain in day2:
        for scope in chain['scopes']:
            attempted.add((chain['company'], scope))
    assert attempted == {(company, scope) for company in companies for scope in scopes}


def test_run_records_last_attempts_and_promotes_missing_unit(tmp_path):
    calls = []

    def fake(company, scope, output, timeout):
        calls.append((company, scope))
        return validated(company, scope)

    with patch.object(p, 'collect_process', side_effect=fake):
        p.run(tmp_path, tmp_path / 'run1', ['大疆', '拼多多'], ['campus'], workers=1)
    entries = json.loads(p.last_attempt_path(tmp_path).read_text(encoding='utf-8'))['entries']
    assert set(entries) == {'大疆/campus', '拼多多/campus'}
    # Simulate the hard cap cutting 拼多多 off before it ever ran.
    entries.pop('拼多多/campus')
    p.atomic_json(p.last_attempt_path(tmp_path), {'entries': entries})
    calls.clear()
    with patch.object(p, 'collect_process', side_effect=fake):
        p.run(tmp_path, tmp_path / 'run2', ['大疆', '拼多多'], ['campus'], workers=1)
    assert calls[0] == ('拼多多', 'campus')
