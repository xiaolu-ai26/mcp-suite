"""Focused checks for platform queue order and persisted retry state."""
import json
import os
from unittest.mock import patch

from qiuzhao.collector import p1_pipeline as p
from qiuzhao.collector import p1_platform_moka as moka


def validated(company, scope='campus'):
    payload = {'jobs': [dict(source_record_id='1', job_title='软件工程师', description_raw='负责软件开发。',
                             recruitment_unit=company, recruitment_type=p.SCOPES[scope],
                             detail_url='https://example.com/jobs/1')],
               'coverage': {'status': 'success', 'complete': True, 'detail_complete': True,
                            'expected_total': 1, 'collected_jobs': 1, 'pages_scanned': 1,
                            'errors': [], 'source_url': 'https://example.com/jobs',
                            'evidence': ['listing.json'], 'scope_evidence': 'offline'}}
    return p.validate_result(payload, company, scope)


def test_run_publishes_distinct_logical_run_ids(tmp_path, monkeypatch):
    monkeypatch.delenv(p.LOGICAL_RUN_ENV, raising=False)
    seen = []

    def fake(company, scope, output, timeout):
        seen.append(os.environ.get(p.LOGICAL_RUN_ENV))
        return validated(company, scope)

    with patch.object(p, 'collect_process', side_effect=fake):
        p.run(tmp_path, tmp_path / 'run-a', ['大疆'], ['campus'], workers=1)
        p.run(tmp_path, tmp_path / 'run-b', ['大疆'], ['campus'], workers=1)
    assert seen[0] == p.logical_run_id(tmp_path / 'run-a')
    assert seen[1] == p.logical_run_id(tmp_path / 'run-b')
    assert seen[0] != seen[1]
    state = p.persistent_collector_state(tmp_path)
    assert state['retry_queue'].endswith('p1-retry-queue.json')
    assert state['last_attempt'].endswith('p1-last-attempt.json')
    assert state['logical_run_env'] == 'QIUZHAO_P1_LOGICAL_RUN_ID'
    assert state['detail_cache_root_env'] == 'QIUZHAO_P1_DETAIL_CACHE_ROOT'


def test_cache_root_setdefault_keeps_override_and_fills_default(tmp_path, monkeypatch):
    custom = str(tmp_path / 'custom')
    monkeypatch.setenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', custom)
    assert p.configure_detail_cache_root(tmp_path / 'data') == custom
    monkeypatch.delenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', raising=False)
    assert p.configure_detail_cache_root(tmp_path / 'data') == str(tmp_path / 'data' / 'p1-detail-cache')


def test_platform_interleave_keeps_input_index_and_checkpoint(tmp_path, monkeypatch):
    monkeypatch.delenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', raising=False)
    moka_names = [name for name in moka.COMPANIES.values() if name not in p.COMPANIES][:2]
    companies = [moka_names[0], moka_names[1], '大疆']
    scopes = ['campus']
    calls = []

    def fake(company, scope, output, timeout):
        calls.append(company)
        return validated(company, scope)

    signature = p.checkpoint_path(tmp_path, companies, scopes)
    with patch.object(p, 'collect_process', side_effect=fake):
        assert p.run(tmp_path, tmp_path / 'run', companies, scopes, workers=1) == 0
    assert p.checkpoint_path(tmp_path, companies, scopes) == signature
    assert signature.is_file()
    status = json.loads((tmp_path / 'run' / 'status.json').read_text(encoding='utf-8'))
    assert status['companies'] == companies
    assert json.loads(signature.read_text(encoding='utf-8'))['companies'] == companies
    # Final segment is the interleaved queue. The input company list stays put.
    assert status['segment_selected_companies'] == [moka_names[0], '大疆', moka_names[1]]
    assert calls == [moka_names[0], '大疆', moka_names[1]]
    for index, company in enumerate(companies, start=1):
        path = status['results'][f'{company}/campus']['result_path']
        assert f'/{index:02d}/campus/' in path.replace('\\', '/')


def test_budget_interleave_includes_a_later_platform(tmp_path, monkeypatch):
    monkeypatch.setenv('QIUZHAO_P1_COMPANY_BUDGET', '40')
    monkeypatch.delenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', raising=False)
    seen = []
    moka_names = []
    for name in moka.COMPANIES.values():
        if name in seen or name in p.COMPANIES:
            continue
        if p.REGISTRY.get(name) != 'qiuzhao.collector.p1_platform_moka':
            continue
        seen.append(name)
        moka_names.append(name)
        if len(moka_names) == 40:
            break
    assert len(moka_names) == 40
    assert len({p.platform_group(name) for name in moka_names}) == 1
    companies = moka_names + ['大疆']
    assert p.platform_group('大疆') != p.platform_group(moka_names[0])
    calls = []

    def fake(company, scope, output, timeout):
        calls.append(company)
        return validated(company, scope)

    signature = p.checkpoint_path(tmp_path, companies, ['campus'])
    with patch.object(p, 'collect_process', side_effect=fake):
        # One same-platform company stays outside this segment, so the run is partial.
        assert p.run(tmp_path, tmp_path / 'run', companies, ['campus'], workers=1) == 2
    status = json.loads((tmp_path / 'run' / 'status.json').read_text(encoding='utf-8'))
    selected = status['segment_selected_companies']
    assert status['segment_company_budget'] == 40
    assert len(selected) == 40
    assert selected[0] == moka_names[0]
    assert '大疆' in selected
    assert moka_names[-1] not in selected
    assert len({p.platform_group(name) for name in selected}) >= 2
    assert calls == selected
    assert status['companies'] == companies
    assert p.checkpoint_path(tmp_path, companies, ['campus']) == signature
    assert json.loads(signature.read_text(encoding='utf-8'))['companies'] == companies
    assert '/01/campus/' in status['results'][f'{moka_names[0]}/campus']['result_path'].replace('\\', '/')
    assert '/41/campus/' in status['results']['大疆/campus']['result_path'].replace('\\', '/')


def test_retry_queue_and_last_attempt_persist_across_runs(tmp_path, monkeypatch):
    monkeypatch.delenv('QIUZHAO_P1_DETAIL_CACHE_ROOT', raising=False)

    def first(company, scope, output, timeout):
        if company == '大疆':
            return p.blocked('SSLError: certificate verify failed')
        return validated(company, scope)

    with patch.object(p, 'collect_process', side_effect=first):
        assert p.run(tmp_path, tmp_path / 'run1', ['拼多多', '大疆'], ['campus'], workers=1) == 2
    retry_path = p.retry_queue_path(tmp_path)
    attempt_path = p.last_attempt_path(tmp_path)
    assert retry_path.name == 'p1-retry-queue.json'
    assert attempt_path.name == 'p1-last-attempt.json'
    state_names = {path.name for path in tmp_path.iterdir() if 'retry' in path.name or 'attempt' in path.name}
    assert state_names == {'p1-retry-queue.json', 'p1-last-attempt.json'}
    saved_retry = json.loads(retry_path.read_text(encoding='utf-8'))['entries']['大疆/campus']
    assert saved_retry['reason'] == 'ssl'
    assert '大疆/campus' in json.loads(attempt_path.read_text(encoding='utf-8'))['entries']

    order = []

    def second(company, scope, output, timeout):
        order.append(company)
        return validated(company, scope)

    with patch.object(p, 'collect_process', side_effect=second):
        assert p.run(tmp_path, tmp_path / 'run2', ['拼多多', '大疆'], ['campus'], workers=1) == 0
    # Persisted retry still leads. Interleaving does not invent another queue.
    assert order[0] == '大疆'
    assert '大疆/campus' not in json.loads(retry_path.read_text(encoding='utf-8'))['entries']
