"""Exit-code contract 0/1/2 and partial-keep behavior for the daily collection chain.

0 = every attempted source/scope validated; 2 = at least one validated and merged
while another failed (callers keep the stage output); 1 = nothing trustworthy.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from qiuzhao.collector import run as R
from qiuzhao.collector import guopin as G
from qiuzhao.collector import p1_pipeline as P
from deploy import windows_collector as W


def fake_job(ident, group='测试集团', title='软件工程师'):
    job = R.base_job(ident, group, title, 'https://official.example.com/job/' + ident, R.now())
    return job


def success_source(collector, name, ident):
    def fn(*_args):
        collector.states[name] = {'status': 'success', 'checked_at': R.now(),
                                  'collected_jobs': 1, 'complete': True}
        return [fake_job(ident)]
    return fn


def failing_source(*_args):
    raise RuntimeError('source exploded')


def patch_basic(monkeypatch, collector, behavior):
    """behavior: name -> 'ok' or 'fail' for the six basic sources."""
    monkeypatch.setattr(collector, 'postal', success_source(collector, 'postal', 'postal-1') if behavior['postal'] == 'ok' else failing_source)
    monkeypatch.setattr(collector, 'chnenergy', success_source(collector, 'chnenergy', 'chn-1') if behavior['chnenergy'] == 'ok' else failing_source)
    monkeypatch.setattr(collector, 'telecom', success_source(collector, 'telecom', 'telecom-1') if behavior['telecom'] == 'ok' else failing_source)
    monkeypatch.setattr(collector, 'boc', success_source(collector, 'boc', 'boc-1') if behavior['boc'] == 'ok' else failing_source)
    if behavior['ccb'] == 'ok':
        monkeypatch.setattr('qiuzhao.collector.ccb.collect_ccb', success_source(collector, 'ccb', 'ccb-1'))
    else:
        monkeypatch.setattr('qiuzhao.collector.ccb.collect_ccb', failing_source)
    if behavior['guopin'] == 'ok':
        monkeypatch.setattr('qiuzhao.collector.guopin.collect_guopin', success_source(collector, 'guopin', 'guopin-1'))
    else:
        monkeypatch.setattr('qiuzhao.collector.guopin.collect_guopin', failing_source)


ALL = ['postal', 'chnenergy', 'telecom', 'boc', 'ccb', 'guopin']


def test_run_all_sources_succeed_exits_0(tmp_path, monkeypatch):
    collector = R.Collector(tmp_path, delay=0)
    patch_basic(monkeypatch, collector, dict.fromkeys(ALL, 'ok'))
    assert collector.run('all', 0) == 0
    jobs = json.loads((tmp_path / 'jobs.json').read_text())
    assert {j['id'] for j in jobs} == {'postal-1', 'chn-1', 'telecom-1', 'boc-1', 'ccb-1', 'guopin-1'}


def test_run_one_source_failure_keeps_validated_sources_and_exits_2(tmp_path, monkeypatch):
    collector = R.Collector(tmp_path, delay=0)
    behavior = dict.fromkeys(ALL, 'ok')
    behavior['chnenergy'] = 'fail'
    patch_basic(monkeypatch, collector, behavior)
    assert collector.run('all', 0) == 2
    jobs = json.loads((tmp_path / 'jobs.json').read_text())
    assert {j['id'] for j in jobs} == {'postal-1', 'telecom-1', 'boc-1', 'ccb-1', 'guopin-1'}
    states = json.loads((tmp_path / 'source_state.json').read_text())
    assert states['chnenergy']['status'] == 'failed'
    assert states['postal']['status'] == 'success'
    alerts = json.loads((tmp_path / 'alerts.json').read_text())['alerts']
    assert [a['source'] for a in alerts] == ['chnenergy']


def test_run_all_sources_fail_exits_1(tmp_path, monkeypatch):
    collector = R.Collector(tmp_path, delay=0)
    patch_basic(monkeypatch, collector, dict.fromkeys(ALL, 'fail'))
    assert collector.run('all', 0) == 1


def test_run_single_source_failure_exits_1(tmp_path, monkeypatch):
    collector = R.Collector(tmp_path, delay=0)
    monkeypatch.setattr(collector, 'postal', failing_source)
    assert collector.run('postal', 0) == 1
    collector = R.Collector(tmp_path, delay=0)
    monkeypatch.setattr(collector, 'postal', success_source(collector, 'postal', 'postal-1'))
    assert collector.run('postal', 0) == 0


def test_run_failed_state_preserves_source_scope_detail(tmp_path, monkeypatch):
    """A rejected source keeps its per-campaign detail in source_state.json."""
    collector = R.Collector(tmp_path, delay=0)

    def rejected_guopin(c):
        c.states['guopin'] = {'status': 'partial_failure', 'checked_at': R.now(), 'complete': False,
                              'campaigns': {'zgyd': {'status': 'success', 'complete': True},
                                            'cgnpc': {'status': 'failed', 'error': 'delisted'}}}
        return []
    behavior = dict.fromkeys(ALL, 'fail')
    monkeypatch.setattr('qiuzhao.collector.guopin.collect_guopin', rejected_guopin)
    for name, attr in [('postal', 'postal'), ('chnenergy', 'chnenergy'), ('telecom', 'telecom'), ('boc', 'boc')]:
        monkeypatch.setattr(collector, attr, failing_source)
    monkeypatch.setattr('qiuzhao.collector.ccb.collect_ccb', failing_source)
    assert collector.run('all', 0) == 1
    states = json.loads((tmp_path / 'source_state.json').read_text())
    assert states['guopin']['status'] == 'failed'
    assert states['guopin']['campaigns']['cgnpc']['error'] == 'delisted'


def partial_guopin(collector):
    """One complete campaign (zgyd) accepted; cgnpc failed per-campaign."""
    def fn(c):
        c.alert('guopin:cgnpc', 'Current official directory no longer advertises this 2027 campaign')
        c.states['guopin'] = {'status': 'partial', 'checked_at': R.now(), 'complete': False,
                              'collected_jobs': 1,
                              'campaigns': {'zgyd': {'status': 'success', 'complete': True},
                                            'cgnpc': {'status': 'failed', 'error': 'delisted'}}}
        job = fake_job('guopin-new-zgyd')
        job['source_group_key'] = 'zgyd'
        return [job]
    return fn


def test_guopin_partial_accepted_and_removal_scoped_to_complete_campaigns(tmp_path, monkeypatch):
    previous = [dict(fake_job('guopin-old-zgyd'), source_group_key='zgyd', status='open'),
                dict(fake_job('guopin-old-cgnpc'), source_group_key='cgnpc', status='open')]
    (tmp_path / 'jobs.json').write_text(json.dumps(previous, ensure_ascii=False))
    collector = R.Collector(tmp_path, delay=0)
    behavior = dict.fromkeys(ALL, 'fail')
    behavior['postal'] = 'ok'
    patch_basic(monkeypatch, collector, behavior)
    monkeypatch.setattr('qiuzhao.collector.guopin.collect_guopin', partial_guopin(collector))
    assert collector.run('all', 0) == 2
    jobs = {j['id']: j for j in json.loads((tmp_path / 'jobs.json').read_text())}
    assert 'guopin-new-zgyd' in jobs
    # Absence => removed only applies to success+complete campaigns.
    assert jobs['guopin-old-zgyd']['status'] == 'removed'
    assert jobs['guopin-old-cgnpc']['status'] == 'open'
    states = json.loads((tmp_path / 'source_state.json').read_text())
    assert states['guopin']['status'] == 'partial'
    assert states['guopin']['campaigns']['cgnpc']['status'] == 'failed'


GUOPIN_DOMAINS = ['zgyd', 'ceec', 'cam2027', 'casicjob', 'zglt']


def fake_guopin_api(advertised):
    counter = iter(range(1000))

    def api(collector, url, payload=None):
        path = url.split('gp-api.iguopin.com')[1].split('?')[0]
        if path == '/api/base/ads/v1/list':
            return {'list': [{'id': str(i), 'title': '某集团2027校园招聘',
                              'link_url': f'https://{d}.iguopin.com/'}
                             for i, d in enumerate(advertised)]}
        if path == '/api/activity/exclusive/v1/info':
            return {'company_id': 'c1', 'title': '2027校园招聘',
                    'company': {'id': 'c1', 'name': '某集团', 'show_name': '某', 'nature_cn': '央企'},
                    'content': json.dumps({'params': {'nav': [{'type': 'job', 'props': {}, 'route': '/campus'}]}})}
        if path == '/api/jobs/v1/list':
            ident = 'job-%d' % next(counter)
            return {'total': 1, 'list': [{
                'job_id': ident, 'job_name': '工程师', 'company_id': 'c1', 'company_name': '某子公司',
                'recruitment_type_cn': '校园招聘', 'nature_cn': '校招', 'category_cn': '技术',
                'education_cn': '本科', 'experience_cn': '应届', 'is_graduates': True,
                'department_cn': '技术部', 'start_time': '2026-09-01 00:00:00',
                'end_time': '2027-06-30 23:59:59', 'district_list': [{'area_cn': '北京'}],
                'contents': '岗位职责：开发。\n2027届应届毕业生', 'status': 1, 'is_apply': True,
                'apply_instruction': '', 'refresh_time': '', 'update_time': ''}]}
        raise AssertionError('unexpected guopin API path: ' + path)
    return api


def test_collect_guopin_one_campaign_delisted_marks_partial(tmp_path, monkeypatch):
    # cgnpc is no longer hardcoded (auto-campaign branch); delist zglt instead to
    # exercise the same "one campaign gone => partial, not rejected" semantics.
    advertised = [d for d in GUOPIN_DOMAINS if d != 'zglt']
    monkeypatch.setattr(G, 'public_api', fake_guopin_api(advertised))
    collector = R.Collector(tmp_path, delay=0)
    rows = G.collect_guopin(collector)
    assert len(rows) == 4
    state = collector.states['guopin']
    assert state['status'] == 'partial'
    assert state['complete'] is False
    assert state['campaigns']['zglt']['status'] == 'failed'
    assert 'no longer advertises' in state['campaigns']['zglt']['error']
    assert all(state['campaigns'][d]['status'] == 'success' for d in advertised)
    assert [a['source'] for a in collector.alerts] == ['guopin:zglt']


def test_collect_guopin_all_campaigns_failed_stays_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(G, 'public_api', fake_guopin_api([]))
    collector = R.Collector(tmp_path, delay=0)
    rows = G.collect_guopin(collector)
    assert rows == []
    assert collector.states['guopin']['status'] == 'partial_failure'
    assert len(collector.alerts) == len(GUOPIN_DOMAINS)


def p1_validated(company='大疆', scope='campus'):
    payload = {'jobs': [dict(source_record_id='1', job_title='软件工程师', description_raw='负责软件开发。',
                             recruitment_unit='深圳市大疆创新科技有限公司', recruitment_type=P.SCOPES[scope],
                             detail_url='https://careers.dji.com/jobs/1')],
               'coverage': {'status': 'success', 'complete': True, 'detail_complete': True,
                            'expected_total': 1, 'collected_jobs': 1, 'pages_scanned': 1, 'errors': [],
                            'source_url': 'https://careers.dji.com/jobs', 'evidence': ['listing.json'],
                            'scope_evidence': 'official employment type field'}}
    return P.validate_result(payload, company, scope)


def test_p1_partial_scopes_exit_2(tmp_path, monkeypatch):
    results = iter([p1_validated(), P.blocked('SSLError')])
    monkeypatch.setattr(P, 'collect_process', lambda *a, **k: next(results))
    assert P.run(tmp_path, tmp_path / 'run', ['大疆'], ['campus', 'intern']) == 2
    status = json.loads((tmp_path / 'run' / 'status.json').read_text())
    assert status['success'] is False


def test_p1_all_blocked_exits_1(tmp_path, monkeypatch):
    monkeypatch.setattr(P, 'collect_process', lambda *a, **k: P.blocked('HTTP 400'))
    assert P.run(tmp_path, tmp_path / 'run', ['大疆'], ['campus']) == 1


def test_p1_all_success_exits_0(tmp_path, monkeypatch):
    monkeypatch.setattr(P, 'collect_process', lambda *a, **k: p1_validated(scope='campus'))
    assert P.run(tmp_path, tmp_path / 'run', ['大疆'], ['campus']) == 0


def test_p1_budget_pause_with_validated_scope_exits_2(tmp_path):
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    status = {'started_at': P.now(), 'run_dir': str(run_dir), 'companies': ['大疆'],
              'scopes': ['campus', 'intern'],
              'results': {'大疆/campus': {'coverage': p1_validated()['coverage'],
                                        'result_path': str(run_dir / 'missing.json'),
                                        'published': True, 'attempted': True}},
              'publications': []}
    (run_dir / 'status.json').write_text(json.dumps(status))
    assert P.run(tmp_path, run_dir, ['大疆'], ['campus', 'intern'], resume=True, max_run_seconds=0) == 2


def write_jobs(path, ids):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{'id': i, 'job_title': 't', 'status': 'open'} for i in ids],
                               ensure_ascii=False))


def read_ids(path):
    return {r['id'] for r in json.loads(Path(path).read_text())}


def run_windows_collector(tmp_path, monkeypatch, behavior, smoke=True, module=W):
    """Drive main with fake pull/step/publish. behavior: step name -> exit code."""
    run_dir = tmp_path / 'runs' / ('day-smoke' if smoke else 'day')
    run_dir.mkdir(parents=True)
    baseline_rows = ['old']

    def fake_pull(target, receipt=None):
        write_jobs(Path(target), baseline_rows)
        return module.digest(Path(target))

    def stage_of(args, env):
        for flag in ('--output-dir', '--data-dir', '--path'):
            if flag in args:
                p = Path(args[args.index(flag) + 1])
                return p if p.is_dir() else p.parent
        return Path(env['QIUZHAO_DATA_DIR'])  # auto_collect reads the stage dir from env

    def fake_step(args, log, env, timeout, *_extra, **_kwargs):
        module_name = args[args.index('-m') + 1]
        name = {'qiuzhao.collector.run': 'basic', 'qiuzhao.collector.auto_collect': 'tencent',
                'qiuzhao.collector.p1_pipeline': 'p1', 'qiuzhao.normalize': 'normalize'}[module_name]
        stage = stage_of(args, env)
        code = behavior.get(name, 0)
        if code != 1:  # a failing stage leaves the shared file untouched
            rows = json.loads((stage / 'jobs.json').read_text())
            rows.append({'id': name + '-new', 'job_title': 't', 'status': 'open'})
            (stage / 'jobs.json').write_text(json.dumps(rows, ensure_ascii=False))
        if name == 'p1':
            (stage / 'p1-checkpoints').mkdir(exist_ok=True)
            (stage / 'p1-checkpoints' / 'marker.json').write_text('{}')
            (stage / 'p1-status.json').write_text('{}')
        return code

    def fake_publish(baseline, candidate, expected_base, work, pull, publish, **_kwargs):
        return {'publication': {'published': True, 'after_sha256': module.digest(Path(candidate))},
                'published_path': str(candidate)}

    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'pull', fake_pull)
    monkeypatch.setattr(module, 'step', fake_step)
    monkeypatch.setattr(module, 'publish_with_rebase', fake_publish)
    argv = ['windows_collector', '--no-sync', '--resume-run', str(run_dir)]
    if smoke:
        argv.append('--smoke')
    monkeypatch.setattr('sys.argv', argv)
    code = module.main()
    receipt = json.loads((run_dir / 'receipt.json').read_text())
    return code, receipt, run_dir


def test_windows_collector_all_ok_publishes(tmp_path, monkeypatch):
    code, receipt, _ = run_windows_collector(tmp_path, monkeypatch, {})
    assert code == 0
    assert receipt['steps'] == {'basic': 0, 'normalize': 0}
    assert receipt['step_changes']['basic']['result'] == 'ok'
    assert receipt['step_changes']['basic']['added'] == 1
    assert 'basic-new' in read_ids(tmp_path / 'data' / 'jobs.json')


def test_windows_collector_partial_step_is_kept_and_published(tmp_path, monkeypatch):
    code, receipt, run_dir = run_windows_collector(tmp_path, monkeypatch, {'basic': 2})
    assert code == 1  # not fully clean, but the partial output is published
    assert receipt['steps']['basic'] == 2
    assert receipt['step_changes']['basic']['result'] == 'partial'
    assert receipt['step_changes']['basic']['added'] == 1
    assert 'basic-new' in read_ids(tmp_path / 'data' / 'jobs.json')
    assert 'publication' in receipt


def test_windows_collector_failed_step_rolls_back(tmp_path, monkeypatch):
    behavior = {'basic': 1, 'tencent': 2, 'p1': 2}
    code, receipt, run_dir = run_windows_collector(tmp_path, monkeypatch, behavior, smoke=False)
    assert code == 1
    assert receipt['steps'] == {'basic': 1, 'tencent': 2, 'p1': 2, 'normalize': 0}
    assert receipt['step_changes']['basic']['result'] == 'rolled_back'
    published = read_ids(tmp_path / 'data' / 'jobs.json')
    assert 'basic-new' not in published
    assert {'tencent-new', 'p1-new', 'old'} <= published
    # Partial p1 keeps its checkpoints and status; rollback would have removed them.
    assert (run_dir / 'data' / 'p1-status.json').exists()
    assert (run_dir / 'data' / 'p1-checkpoints' / 'marker.json').exists()


def test_windows_collector_all_stages_failed_keeps_production(tmp_path, monkeypatch):
    code, receipt, _ = run_windows_collector(tmp_path, monkeypatch, {'basic': 1})
    assert code == 1
    assert 'all collection stages failed' in receipt['error']
    assert 'publication' not in receipt
    assert receipt['step_changes']['basic']['result'] == 'rolled_back'


def test_windows_collector_p1_watchdog_outlasts_p1_finalisation():
    """P0 2026-09-20: the p1 step limit was deadline+100s and killed p1 mid-finalisation.

    p1 only checks its own --max-run-seconds deadline between units, so it can still be
    draining one in-flight unit (up to --scope-timeout) and writing its status, merged
    rows and gap report after that deadline. The watchdog now covers ONE segment and must
    leave that room; the day itself is bounded by the segment loop, not by this limit.
    """
    steps = {name: (args, limit) for name, args, limit in W.steps_for(Path('/stage'), False)}
    args, limit = steps['p1']
    max_run = int(args[args.index('--max-run-seconds') + 1])
    scope_timeout = int(args[args.index('--scope-timeout') + 1])
    assert max_run == W.P1_SEGMENT_SECONDS
    assert scope_timeout == W.P1_SCOPE_TIMEOUT
    assert limit - max_run >= scope_timeout + W.P1_SEGMENT_FINALIZE_BUDGET, 'no room to drain the in-flight unit'
    assert limit == W.P1_SEGMENT_STEP_LIMIT
    assert 'p1' not in {name for name, _args, _limit in W.steps_for(Path('/stage'), True)}


def test_windows_collector_publishes_when_p1_hits_its_deadline(tmp_path, monkeypatch):
    """A deadline-capped p1 (exit 2) is partial: its collected rows must be published."""
    code, receipt, run_dir = run_windows_collector(tmp_path, monkeypatch, {'p1': 2}, smoke=False)
    assert code == 1  # not a fully clean day, but nothing was thrown away
    assert receipt['steps']['p1'] == 2
    assert receipt['step_changes']['p1']['result'] == 'partial'
    assert receipt['step_changes']['p1']['added'] == 1
    assert 'publication' in receipt
    assert 'p1-new' in read_ids(tmp_path / 'data' / 'jobs.json')
    # Resume material for a deadline-capped run stays on disk (rollback would drop it).
    assert (run_dir / 'data' / 'p1-status.json').exists()
    assert (run_dir / 'data' / 'p1-checkpoints' / 'marker.json').exists()
    assert 'error' not in receipt


def test_windows_collector_receipt_records_the_full_traceback(tmp_path, monkeypatch):
    """The receipt must carry the raising line, not only the message (2026-09-20 P0)."""
    def exploding_preserve(*_args, **_kwargs):
        raise RuntimeError('preserve exploded')

    monkeypatch.setattr(W, 'preserve', exploding_preserve)
    code, receipt, _ = run_windows_collector(tmp_path, monkeypatch, {})
    assert code == 1
    assert receipt['error'].startswith('RuntimeError: preserve exploded')
    assert receipt['error_step'] == 'validate-and-publish'
    traceback_text = receipt['error_traceback']
    assert traceback_text.startswith('Traceback (most recent call last)')
    assert 'exploding_preserve' in traceback_text
    assert 'RuntimeError: preserve exploded' in traceback_text
    assert 'publication' not in receipt


def load_ported_collector():
    """The jingling deploy artifact, loaded by path so it runs under the same harness."""
    path = (Path(__file__).resolve().parents[1] / 'pipeline-watch' / 'deploy-artifacts'
            / '20260918' / 'windows_collector.py')
    spec = importlib.util.spec_from_file_location('windows_collector_ported', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('module', [W, load_ported_collector()], ids=['branch', 'ported'])
def test_windows_collector_diff_counts_failure_is_reporting_only(tmp_path, monkeypatch, module):
    def exploding_diff(*_args):
        raise RuntimeError('diff exploded')

    monkeypatch.setattr(module, 'diff_counts', exploding_diff)
    code, receipt, _ = run_windows_collector(tmp_path, monkeypatch, {}, module=module)
    assert code == 0  # the run still reaches publication and succeeds
    assert 'publication' in receipt
    changes = receipt['step_changes']['basic']
    assert changes['exit'] == 0
    assert changes['result'] == 'ok'
    assert changes['diff_error'].startswith('RuntimeError: diff exploded')
    assert 'added' not in changes
    assert 'basic-new' in read_ids(tmp_path / 'data' / 'jobs.json')
