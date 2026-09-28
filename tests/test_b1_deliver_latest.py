"""deliver-latest: the scheduled Base delivery entry point (batch 1, 2026-09-28).

Real ``deliver()`` with the existing FakeRunner (no lark-cli); the manifest and artifact
"remote" commands are local ``cat`` / ``gzip -c`` so the hash checks run for real.
"""
import datetime as dt
import fcntl
import json
from pathlib import Path

import pytest

from deploy import windows_excel_delivery as X
from test_windows_excel_delivery import FakeRunner, approved_policy, chain, lineage_source


RUN = 'C:/collector/runs/20300110'
NOW = '2030-01-10T10:00:00+08:00'   # after the fixture's real-clock delivery, so "today" is free


def manifest_file(tmp_path, source, name=None):
    path = tmp_path / (name or ('m-' + source['sha256'][:8] + '.json'))
    path.write_text(json.dumps({'sha256': source['sha256'], 'accepted_at': '2026-09-28T01:00:00+08:00',
                                'lineage': source['lineage'], 'artifact': source['path'], 'run': RUN}),
                    encoding='utf-8')
    return path


def receipt_file(tmp_path, source, stage, ended_on=None):
    """What run_receipt_command prints: fields of the run's receipt.json (windows_collector.main)."""
    path = tmp_path / ('r-%s-%s.json' % (source['sha256'][:8], stage))
    terminal = stage in ('completed', 'partial-or-failed')
    path.write_text(json.dumps({'run': RUN, 'mode': 'daily', 'stage': stage,
                                'completed_at': '2030-01-10T09:00:00+08:00' if terminal else None,
                                'finished': stage == 'completed', 'success': stage == 'completed',
                                'collection': {'state': 'complete' if terminal else 'running'},
                                'working_baseline': {'sha256': ended_on or source['sha256']}}))
    return path


def commands(tmp_path, source, *, now=NOW, stage='completed', ended_on=None):
    return {'manifest_command': ['cat', str(manifest_file(tmp_path, source))],
            'fetch_command': ['gzip', '-c', source['path']],
            'run_receipt_command': ['cat', str(receipt_file(tmp_path, source, stage, ended_on))],
            'timezone': 'Asia/Shanghai', 'daily_fallback': '22:20',
            'clock': lambda: dt.datetime.fromisoformat(now)}


def live_blocks(root, *, drop=(), rename=None, extra=()):
    ledger = json.loads((root / 'ledger.json').read_text())
    blocks = [{'id': tid, 'name': (rename or {}).get(tid, name), 'type': 'table', 'parent_id': None}
              for tid, name in ledger['official_tables'] if tid not in drop]
    return blocks + [{'id': tid, 'name': 'archived', 'type': 'table', 'parent_id': 'fld'} for tid in extra]


@pytest.fixture
def delivered_b(tmp_path):
    a, b, c, d, e = chain(tmp_path, 5)
    policy = approved_policy(tmp_path, a['sha256'])
    root = tmp_path / 'root'
    assert X.deliver(root, b, FakeRunner(), policy=policy)['outcome'] == 'delivered'
    return root, policy, (a, b, c, d, e)


def test_newest_successor_is_delivered_once_skipping_intermediate_versions(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy, **commands(tmp_path, d))
    assert status['action'] == 'deliver' and status['outcome'] == 'delivered'
    assert runner.calls.count('import') == 1
    ledger = json.loads((root / 'ledger.json').read_text())
    assert ledger['last_delivered'] == d['sha256'] and c['sha256'] not in ledger['delivered']
    assert status['alerts'] == []
    # Same latest again: nothing runs, nothing alerts.
    again = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, again, policy=policy, **commands(tmp_path, d))
    assert status['outcome'] == 'up_to_date' and again.calls == [] and again.block_reads == 0
    assert status['layers']['base']['sha256'] == status['layers']['accepted']['sha256']


def test_an_active_version_is_resumed_before_a_newer_one(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    first = FakeRunner(blocks=live_blocks(root), fail={'verify': 1})
    status = X.deliver_latest(root, first, policy=policy, **commands(tmp_path, d))
    assert status['outcome'] == 'failed' and status['failed_stage'] == 'verify'
    assert any('behind accepted' in alert for alert in status['alerts'])
    resume = FakeRunner()                     # no live read on a resume
    status = X.deliver_latest(root, resume, policy=policy, **commands(tmp_path, e))
    assert status['action'] == 'resume' and status['target_sha256'] == d['sha256']
    assert status['outcome'] == 'delivered' and resume.calls == ['verify', 'switch']
    assert any('behind accepted' in alert for alert in status['alerts']), 'e is still owed'
    final = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, final, policy=policy, **commands(tmp_path, e, now='2030-01-11T10:00:00+08:00'))
    assert status['outcome'] == 'delivered' and status['alerts'] == []
    alerts = [json.loads(line) for line in (root / 'alerts.jsonl').read_text().splitlines()]
    assert len(alerts) == 2


def test_a_version_not_descending_from_the_delivered_one_is_refused(tmp_path, delivered_b):
    root, policy, _ = delivered_b
    stranger = lineage_source(tmp_path, 'stranger.json', [{'id': 'unrelated'}])
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy, **commands(tmp_path, stranger))
    assert status['outcome'] == 'error' and 'does not descend' in status['error']
    assert runner.calls == [] and status['alerts']


def test_archived_tables_deleted_outside_are_moved_with_live_evidence(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    ledger = json.loads((root / 'ledger.json').read_text())
    ledger['archived_table_ids'] = ['tblGONE1', 'tblSTILL']
    (root / 'ledger.json').write_text(json.dumps(ledger, ensure_ascii=False))
    runner = FakeRunner(blocks=live_blocks(root, extra=['tblSTILL']))
    status = X.deliver_latest(root, runner, policy=policy, **commands(tmp_path, d))
    assert status['reconcile']['archived_absent_moved'] == ['tblGONE1']
    ledger = json.loads((root / 'ledger.json').read_text())
    moved = list(ledger['deleted_outside_delivery'].values())[0]
    assert moved['table_ids'] == ['tblGONE1'] and Path(moved['evidence']).is_file()
    assert status['outcome'] == 'delivered' and 'tblSTILL' in ledger['archived_table_ids']
    assert 'tblGONE1' not in runner.last_overrides['LEGACY_IDS']


@pytest.mark.parametrize('change', ['missing', 'renamed'])
def test_an_official_table_changed_outside_stops_before_import(tmp_path, delivered_b, change):
    root, policy, (a, b, c, d, e) = delivered_b
    official = json.loads((root / 'ledger.json').read_text())['official_tables'][0][0]
    blocks = live_blocks(root, drop=[official]) if change == 'missing' else \
        live_blocks(root, rename={official: 'someone renamed it'})
    runner = FakeRunner(blocks=blocks)
    status = X.deliver_latest(root, runner, policy=policy, **commands(tmp_path, d))
    assert status['outcome'] == 'error' and 'differs from the ledger' in status['error']
    assert runner.calls == []
    assert json.loads((root / 'ledger.json').read_text())['active'] is None


def test_a_fetched_artifact_with_another_hash_is_refused(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    cmd = commands(tmp_path, d)
    cmd['fetch_command'] = ['gzip', '-c', e['path']]          # the server moved on
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy, **cmd)
    assert status['outcome'] == 'error' and 'retry later' in status['error']
    assert not list((root / 'artifacts').glob('*.partial')) and runner.calls == []


def test_second_instance_is_busy(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    with (root / 'deliver-latest.lock').open('a+') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        status = X.deliver_latest(root, FakeRunner(), policy=policy, **commands(tmp_path, d))
    assert status['outcome'] == 'busy'


def test_served_differs_from_accepted_is_an_alert(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    served = tmp_path / 'activation.json'
    served.write_text(json.dumps({'active': {'sha256': c['sha256'], 'activated_at': 't'}}))
    status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy,
                              served_command=['cat', str(served)], **commands(tmp_path, d))
    assert status['layers']['served']['sha256'] == c['sha256']
    assert any(alert.startswith('served') for alert in status['alerts'])


def test_scripts_default_to_the_repo_copy():
    assert X.DEFAULT_SCRIPTS == Path(X.__file__).resolve().parent / 'feishu_r1'
    assert all((X.DEFAULT_SCRIPTS / name).is_file() for name in set(X.SCRIPT.values()))


# --- deliver-latest review P1 fixes (2026-09-28) --------------------------------------

OFFLINE = {'manifest_command': ['false'], 'fetch_command': ['false']}


def failed_at_verify(tmp_path, root, policy, source, *, via_latest=True):
    runner = FakeRunner(blocks=live_blocks(root), fail={'verify': 1})
    if via_latest:
        status = X.deliver_latest(root, runner, policy=policy, **commands(tmp_path, source))
        assert status['outcome'] == 'failed'
    else:
        assert X.deliver(root, source, runner, policy=policy)['outcome'] == 'failed'
    assert json.loads((root / 'ledger.json').read_text())['active'] == source['sha256']


def test_active_version_resumes_with_the_collector_offline(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    failed_at_verify(tmp_path, root, policy, d)
    resume = FakeRunner()
    status = X.deliver_latest(root, resume, policy=policy, **OFFLINE)
    assert status['action'] == 'resume' and status['outcome'] == 'delivered'
    assert resume.calls == ['verify', 'switch'] and resume.block_reads == 0
    assert any(alert.startswith('accepted version unknown') for alert in status['alerts'])


def test_manual_delivery_resumes_without_manifests_or_cache(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    failed_at_verify(tmp_path, root, policy, d, via_latest=False)
    assert not (root / 'manifests').exists() and not (root / 'artifacts').exists()
    status = X.deliver_latest(root, FakeRunner(), policy=policy, **OFFLINE)
    assert status['outcome'] == 'delivered' and status['target_sha256'] == d['sha256']


def test_resume_uses_the_recorded_projection_when_source_bytes_are_gone(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    failed_at_verify(tmp_path, root, policy, d, via_latest=False)
    Path(d['path']).unlink()
    resume = FakeRunner()
    status = X.deliver_latest(root, resume, policy=policy, **OFFLINE)
    assert status['outcome'] == 'delivered' and resume.calls == ['verify', 'switch']


@pytest.mark.parametrize('loss', ['projection', 'state'])
def test_missing_old_material_blocks_and_never_takes_another_version(tmp_path, delivered_b, loss):
    root, policy, (a, b, c, d, e) = delivered_b
    failed_at_verify(tmp_path, root, policy, d, via_latest=False)
    Path(d['path']).unlink()
    work = X.version_dir(root, d['sha256'])
    (work / ('work/projection.ndjson.gz' if loss == 'projection' else 'state.json')).unlink()
    runner = FakeRunner()
    # The server has moved on to e: its bytes are not d and must not stand in.
    status = X.deliver_latest(root, runner, policy=policy, **commands(tmp_path, e))
    assert status['outcome'] == 'blocked' and d['sha256'][:12] in status['blocked']['reason']
    assert runner.calls == [] and any('blocked' in alert for alert in status['alerts'])
    ledger = json.loads((root / 'ledger.json').read_text())
    assert ledger['active'] == d['sha256'] and e['sha256'] not in ledger['delivered']
    assert not ledger.get('abandoned') and not list((root / 'artifacts').glob('*'))


def broken_stream(tmp_path, source, kind):
    if kind == 'truncated':
        return ['sh', '-c', 'gzip -c "$0" | head -c 20', source['path']]
    import gzip
    data = bytearray(gzip.compress(Path(source['path']).read_bytes()))
    if kind == 'bad_crc':
        data[-6] ^= 0xFF
    elif kind == 'bad_deflate':
        data[10] = 0xFF
    else:
        data = bytearray(b'not gzip at all')
    path = tmp_path / ('broken-' + kind)
    path.write_bytes(bytes(data))
    return ['cat', str(path)]


@pytest.mark.parametrize('kind', ['truncated', 'bad_crc', 'bad_deflate', 'not_gzip'])
def test_a_broken_stream_replaces_an_old_success_with_a_failure_and_alert(tmp_path, delivered_b, kind):
    root, policy, (a, b, c, d, e) = delivered_b
    assert X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy,
                            **commands(tmp_path, b))['outcome'] == 'up_to_date'
    assert json.loads((root / 'deliver-latest-status.json').read_text())['outcome'] == 'up_to_date'
    cmd = dict(commands(tmp_path, d), fetch_command=broken_stream(tmp_path, d, kind))
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy, **cmd)
    assert status['outcome'] == 'error' and 'stream for %s broke' % d['sha256'][:12] in status['error'], status
    written = json.loads((root / 'deliver-latest-status.json').read_text())
    assert written['outcome'] == 'error' and written['alerts']
    assert json.loads((root / 'alerts.jsonl').read_text().splitlines()[-1])['outcome'] == 'error'
    assert not list((root / 'artifacts').glob('*.partial')) and runner.calls == []


def test_an_unexpected_exception_is_a_recorded_failure(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    status = X.deliver_latest(root, FakeRunner(blocks=None), policy=policy, **commands(tmp_path, d))
    assert status['outcome'] == 'error' and status['error'].startswith('AssertionError')
    assert json.loads((root / 'deliver-latest-status.json').read_text())['outcome'] == 'error'


def test_reconcile_waits_for_the_delivery_lock(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    ledger = json.loads((root / 'ledger.json').read_text())
    ledger['archived_table_ids'] = ['tblGONE1']
    (root / 'ledger.json').write_text(json.dumps(ledger, ensure_ascii=False))
    before = (root / 'ledger.json').read_bytes()
    runner = FakeRunner(blocks=live_blocks(root))
    with (root / 'delivery.lock').open('a+') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        status = X.deliver_latest(root, runner, policy=policy, **commands(tmp_path, d))
    assert status['outcome'] == 'error' and 'holds the lock' in status['error']
    assert (root / 'ledger.json').read_bytes() == before and runner.calls == []


def test_an_unreadable_served_layer_is_unknown_and_alerts(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    status = X.deliver_latest(root, FakeRunner(), policy=policy, served_command=['false'],
                              **commands(tmp_path, b))
    assert status['outcome'] == 'up_to_date' and 'error' in status['layers']['served']
    assert 'sha256' not in status['layers']['served']
    assert any(alert.startswith('served version unknown') for alert in status['alerts'])


def test_failed_preflight_acts_on_nothing_and_alerts(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy, preflight=lambda **_: ['lark-cli not found'],
                              **commands(tmp_path, d))
    assert status['outcome'] == 'preflight_failed' and 'lark-cli' in status['error']
    assert runner.calls == [] and runner.block_reads == 0 and status['alerts']


def fake_bin(tmp_path, *names):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(exist_ok=True)
    for name in names:
        tool = bin_dir / name
        tool.write_text('#!/bin/sh\nexit 0\n')
        tool.chmod(0o755)
    return bin_dir


def test_preflight_probes_the_tools_rather_than_trusting_the_config(tmp_path, monkeypatch):
    policy = tmp_path / 'policy.json'
    policy.write_text('{}')
    config = {'policy': str(policy), 'manifest_command': ['collector-ssh'], 'fetch_command': ['cat'],
              'run_receipt_command': ['collector-ssh'], 'timezone': 'Asia/Shanghai', 'daily_fallback': '22:00'}
    monkeypatch.setenv('PATH', '%s:/usr/bin:/bin' % fake_bin(tmp_path, 'collector-ssh'))
    # Probe results are the host's business; stub openpyxl present, then absent, explicitly.
    monkeypatch.setattr(X.importlib.util, 'find_spec', lambda name: object())
    problems = X.preflight(config, apply=True, scripts_dir=X.DEFAULT_SCRIPTS, frozen_check=lambda s: [])
    assert problems == ['lark-cli not found on PATH=%s' % X.os.environ['PATH']]
    fake_bin(tmp_path, 'lark-cli')
    assert X.preflight(config, apply=True, scripts_dir=X.DEFAULT_SCRIPTS, frozen_check=lambda s: []) == []
    pending = X.preflight(config, apply=True, scripts_dir=X.DEFAULT_SCRIPTS,
                          frozen_check=lambda s: ['qiuzhao/v4_fields.py: not frozen'])
    assert pending == ['qiuzhao/v4_fields.py: not frozen']
    monkeypatch.setattr(X.importlib.util, 'find_spec', lambda name: None)
    broken = dict(config, manifest_command=['no-such-tool'], policy=str(tmp_path / 'missing.json'))
    problems = X.preflight(broken, apply=False, scripts_dir=tmp_path, frozen_check=None)
    assert any('policy unreadable' in p for p in problems)
    assert any('no-such-tool not found' in p for p in problems)
    assert any('R1 scripts missing' in p for p in problems)
    assert any(p.startswith('openpyxl is not importable') for p in problems)
    unscheduled = dict(config, timezone=None, force=True)
    problems = X.preflight(unscheduled, apply=False, scripts_dir=X.DEFAULT_SCRIPTS, frozen_check=None)
    assert any('timezone/daily_fallback invalid' in p for p in problems)
    assert any('never a config key' in p for p in problems)


# --- settlement gate: one new batch per day, only after the run ends (2026-09-28) ------

def versions(root):
    return sorted(p.name for p in (root / 'versions').iterdir())


def test_a_collecting_run_starts_no_batch_for_its_many_accepted_versions(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    before = versions(root)
    for hour, source in (('10', c), ('11', d), ('12', e)):
        runner = FakeRunner(blocks=live_blocks(root))
        status = X.deliver_latest(root, runner, policy=policy, **commands(
            tmp_path, source, now='2030-01-10T%s:20:00+08:00' % hour, stage='p1-collect'))
        assert status['outcome'] == 'waiting' and status['schedule']['trigger'] is None
        assert 'still in stage p1-collect' in status['schedule']['reason']
        assert runner.calls == [] and runner.block_reads == 0 and status['alerts'] == []
    assert versions(root) == before and not (root / 'artifacts').exists()


def test_a_partial_run_that_ended_delivers_its_accepted_version(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy,
                              **commands(tmp_path, d, stage='partial-or-failed'))
    assert status['outcome'] == 'delivered' and status['schedule']['trigger'] == 'run_settled'


def test_a_partial_receipt_with_resumable_collection_waits_until_fallback(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    cmd = commands(tmp_path, d, stage='partial-or-failed')
    receipt_path = Path(cmd['run_receipt_command'][1])
    receipt = json.loads(receipt_path.read_text())
    receipt['collection'] = {'state': 'stopped', 'reason': 'retryable P1 failure'}
    receipt_path.write_text(json.dumps(receipt))
    runner = FakeRunner(blocks=live_blocks(root))
    early = X.deliver_latest(root, runner, policy=policy, **cmd)
    assert early['outcome'] == 'waiting' and early['schedule']['trigger'] is None
    assert 'can still resume' in early['schedule']['reason']
    assert runner.calls == [] and runner.block_reads == 0
    late = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy,
                            **dict(cmd, clock=lambda: dt.datetime.fromisoformat('2030-01-10T22:20:00+08:00')))
    assert late['outcome'] == 'delivered' and late['schedule']['trigger'] == 'daily_fallback'


def test_example_receipt_projection_preserves_collection_settlement(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    example = json.loads((Path(X.__file__).parent / 'launchd' /
                          'qiuzhao-deliver-latest.config.example.json').read_text())
    assert "'collection'" in example['run_receipt_command'][-1]
    receipt = json.loads(receipt_file(tmp_path, d, 'partial-or-failed').read_text())
    names = ('mode', 'stage', 'completed_at', 'finished', 'success', 'collection', 'working_baseline')
    projected = dict(run=RUN, **{key: receipt.get(key) for key in names})
    settled, reason = X.run_settlement(projected, {'run': RUN, 'sha256': d['sha256']})
    assert settled and 'partial-or-failed' in reason


def test_the_daily_fallback_delivers_a_run_that_never_ends(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy,
                              **commands(tmp_path, d, now='2030-01-10T22:20:00+08:00', stage='p1-collect'))
    assert status['outcome'] == 'delivered' and status['schedule']['trigger'] == 'daily_fallback'
    early = X.deliver_latest(root, FakeRunner(), policy=policy,
                             **commands(tmp_path, e, now='2030-01-11T22:19:00+08:00', stage='p1-collect'))
    assert early['outcome'] == 'waiting', 'one minute before 22:20 the fallback is not due'


def test_an_unknown_receipt_is_not_an_end_and_alerts(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    cmd = dict(commands(tmp_path, d), run_receipt_command=['false'])
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy, **cmd)
    assert status['outcome'] == 'waiting' and runner.calls == []
    assert any(alert.startswith('run receipt unknown') for alert in status['alerts'])
    # A receipt that ended on another accepted version does not settle this one either.
    status = X.deliver_latest(root, runner, policy=policy, **commands(tmp_path, d, ended_on=c['sha256']))
    assert status['outcome'] == 'waiting' and 'not the latest' in status['schedule']['reason']


def test_one_new_batch_per_day_then_the_next_day(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    assert X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy,
                            **commands(tmp_path, d))['outcome'] == 'delivered'
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy,
                              **commands(tmp_path, e, now='2030-01-10T23:20:00+08:00'))
    assert status['outcome'] == 'waiting' and 'already made today' in status['schedule']['reason']
    assert runner.calls == [] and e['sha256'] not in versions(root)
    status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy,
                              **commands(tmp_path, e, now='2030-01-11T00:20:00+08:00'))
    assert status['outcome'] == 'delivered' and status['target_sha256'] == e['sha256']
    batches = json.loads((root / X.AUTO_BATCHES).read_text())['batches']
    assert [(x['date'], x['trigger']) for x in batches] == [('2030-01-10', 'run_settled'), ('2030-01-11', 'run_settled')]


def test_force_skips_the_gate_but_never_overtakes_an_active_version(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    failed_at_verify(tmp_path, root, policy, d)
    resume = FakeRunner()
    status = X.deliver_latest(root, resume, policy=policy, force=True, **commands(tmp_path, e))
    assert status['action'] == 'resume' and status['target_sha256'] == d['sha256'] and 'ignored' in status['force']
    assert e['sha256'] not in json.loads((root / 'ledger.json').read_text())['delivered']
    # Same day, run still collecting: only the manual force starts e.
    status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy, force=True,
                              **commands(tmp_path, e, stage='p1-collect'))
    assert status['outcome'] == 'delivered' and status['schedule']['trigger'] == 'force'
    # Already delivered: force changes nothing.
    again = FakeRunner()
    status = X.deliver_latest(root, again, policy=policy, force=True, **commands(tmp_path, e))
    assert status['outcome'] == 'up_to_date' and again.calls == []


def test_fallback_with_the_collector_offline_uses_the_cached_accepted_manifest(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    # 10:20 online, run collecting: d's manifest is cached, nothing starts.
    assert X.deliver_latest(root, FakeRunner(), policy=policy,
                            **commands(tmp_path, d, stage='p1-collect'))['outcome'] == 'waiting'
    offline = dict(commands(tmp_path, d, now='2030-01-10T22:20:00+08:00'),
                   manifest_command=['false'], run_receipt_command=['false'])
    status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy, **offline)
    assert status['outcome'] == 'delivered' and status['target_sha256'] == d['sha256']
    assert status['manifest_source'].startswith('cached')
    assert any(alert.startswith('accepted version unknown') for alert in status['alerts'])


def test_fallback_with_nothing_trustworthy_is_blocked(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    offline = dict(commands(tmp_path, d, now='2030-01-10T22:20:00+08:00'),
                   manifest_command=['false'], run_receipt_command=['false'])
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy, **offline)
    assert status['outcome'] == 'blocked' and 'unreachable' in status['blocked']['reason']
    assert runner.calls == [] and status['alerts']


# --- forced/manual catch-ups keep the automatic daily slot (2026-09-28, final) ----------

def successor(tmp_path, parent, name='f.json'):
    return lineage_source(tmp_path, name, [{'id': name}], parent=parent['sha256'], lineage=parent['lineage'])


@pytest.mark.parametrize('catch_up', ['force', 'manual_deliver'])
def test_a_daytime_catch_up_leaves_the_evening_run_end_its_automatic_start(tmp_path, delivered_b, catch_up):
    root, policy, (a, b, c, d, e) = delivered_b
    f = successor(tmp_path, e)
    if catch_up == 'force':
        status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy, force=True,
                                  **commands(tmp_path, d, now='2030-01-10T11:00:00+08:00', stage='p1-collect'))
        assert status['outcome'] == 'delivered' and status['schedule']['trigger'] == 'force'
    else:
        assert X.deliver(root, d, FakeRunner(), policy=policy)['outcome'] == 'delivered'
    # 21:40 the real run ends on e: the automatic start still happens today.
    status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy,
                              **commands(tmp_path, e, now='2030-01-10T21:40:00+08:00'))
    assert status['outcome'] == 'delivered' and status['schedule']['trigger'] == 'run_settled'
    # A second automatic start the same day is refused, even for a newer settled version.
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy, **commands(tmp_path, f, now='2030-01-10T23:20:00+08:00'))
    assert status['outcome'] == 'waiting' and 'automatic start' in status['schedule']['reason']
    assert runner.calls == [] and f['sha256'] not in versions(root)


def test_a_crashed_force_is_resumed_and_does_not_take_the_automatic_slot(tmp_path, delivered_b):
    root, policy, (a, b, c, d, e) = delivered_b
    status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root), fail={'verify': 1}), policy=policy,
                              force=True, **commands(tmp_path, d, now='2030-01-10T11:00:00+08:00', stage='p1-collect'))
    assert status['outcome'] == 'failed'
    # The run ends on e while d is active: d resumes first, e does not start.
    resume = FakeRunner()
    status = X.deliver_latest(root, resume, policy=policy, **commands(tmp_path, e, now='2030-01-10T21:40:00+08:00'))
    assert status['action'] == 'resume' and status['target_sha256'] == d['sha256'] and status['outcome'] == 'delivered'
    assert resume.calls == ['verify', 'switch'] and e['sha256'] not in versions(root)
    # Next hour e starts automatically: the forced start did not use the slot.
    status = X.deliver_latest(root, FakeRunner(blocks=live_blocks(root)), policy=policy,
                              **commands(tmp_path, e, now='2030-01-10T22:20:00+08:00'))
    assert status['outcome'] == 'delivered' and status['schedule']['trigger'] == 'run_settled'
    batches = json.loads((root / X.AUTO_BATCHES).read_text())['batches']
    assert [b['trigger'] for b in batches] == ['force', 'run_settled'] and batches[1]['run'] == RUN


def test_start_only_config_errors_do_not_stop_an_active_resume(tmp_path, delivered_b, monkeypatch):
    root, policy, (a, b, c, d, e) = delivered_b
    monkeypatch.setattr(X.importlib.util, 'find_spec', lambda name: object())
    policy_file = tmp_path / 'policy.json'
    policy_file.write_text(json.dumps(policy))
    config = {'policy': str(policy_file), 'manifest_command': ['false'], 'fetch_command': ['false']}
    check = lambda new_batch: X.preflight(config, apply=False, scripts_dir=X.DEFAULT_SCRIPTS,
                                          frozen_check=None, new_batch=new_batch)
    assert check(False) == []
    assert any('timezone/daily_fallback' in p for p in check(True))
    assert any('run_receipt_command' in p for p in check(True))
    # No active version: the incomplete config refuses to start anything.
    runner = FakeRunner(blocks=live_blocks(root))
    status = X.deliver_latest(root, runner, policy=policy, preflight=check, **OFFLINE)
    assert status['outcome'] == 'preflight_failed' and runner.calls == []
    # Active version: it resumes from its frozen material with the same config.
    failed_at_verify(tmp_path, root, policy, d, via_latest=False)
    status = X.deliver_latest(root, FakeRunner(), policy=policy, preflight=check, **OFFLINE)
    assert status['action'] == 'resume' and status['outcome'] == 'delivered'
    # Checks a resume itself needs still apply.
    broken = dict(config, policy=str(tmp_path / 'missing.json'))
    assert any('policy unreadable' in p for p in X.preflight(broken, apply=False, scripts_dir=X.DEFAULT_SCRIPTS,
                                                             frozen_check=None, new_batch=False))
