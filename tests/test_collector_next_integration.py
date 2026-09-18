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
    platform = [name for name in p.DEFAULT_COMPANIES if name not in p.COMPANIES]
    assert set(platform) == set(PLATFORM_ONLY)
    # p1_platform_companies.json lists beisen first, then moka.
    assert platform.index('中信建投') < platform.index('安踏集团')
    assert platform[-1] == '信也科技'


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
                 resume=False, max_run_seconds=21600, workers=4):
        captured['companies'] = list(companies)
        return 0

    with patch.object(p, 'run', side_effect=fake_run):
        with patch('sys.argv', ['p1', '--data-dir', str(tmp_path), '--scopes', 'campus']):
            assert p.main() == 0
    assert captured['companies'] == p.DEFAULT_COMPANIES
    assert '小天才' in captured['companies']


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
    assert "'--workers','4'" in source
    assert "'--max-run-seconds','18000'" in source
    assert "'--timeout','1200'" not in source
    # The ported production tail (base-sync via lark_sync_daemon) must be intact.
    assert "state['stage']='base-sync'" in source
    assert 'lark_sync_daemon' in source
    assert 'lark_sync_index' not in source
