"""Segmented p1 publication + step-cleanup hardening (2026-09-20).

The chain used to run p1 once and publish once, at the very end. On 2026-09-20 a cleanup
failure inside ``step()`` (``TypeError: 'NoneType' object is not subscriptable`` from
``stop_tree``) escaped, the p1 step was never recorded, staging was rolled back and 958
collected units (19,619 new rows) never reached the server.

Two independent guarantees are pinned here:

1. **A cleanup failure never escapes ``step()``.** It records whatever ``stop_tree`` did
   (report, or exception + traceback) in ``state['cleanup_errors']`` and returns 125 --
   termination unconfirmed -- which the caller turns into ``unsafe_writer``: nothing is
   rolled back, normalized or published while a writer may still be alive.
2. **Segments publish.** p1 runs with a per-segment deadline and ``--resume-latest``; after
   every segment the same ``normalize`` + ``preserve`` + ``publish_with_rebase`` chain
   runs, and a segment whose staging did not change is not uploaded again.

Receipt: pipeline-watch/RECEIPT-segmented-publish.md.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import types

from deploy import windows_collector as W
from qiuzhao.collector import portable_runtime as RT

GBK_SUCCESS = '成功: 已终止 PID 12345 的进程。'
GBK_FAILURE = '错误: 没有找到进程 "999999"。'
SLEEP = ['-c', 'import time; time.sleep(30)']


def gbk_script(tmp_path, text, code):
    """A stand-in for taskkill that answers in the Chinese Windows console codepage."""
    script = tmp_path / f'fake_taskkill_{code}.py'
    script.write_text('import sys\n'
                      f'sys.stdout.buffer.write({text!r}.encode("gbk"))\n'
                      'sys.stdout.buffer.flush()\n'
                      f'raise SystemExit({code})\n', encoding='utf-8')
    return [sys.executable, str(script)]


def sleeping_child():
    return subprocess.Popen([sys.executable, *SLEEP], start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class FakeChild:
    """Child stand-in for step(): ``alive`` decides whether wait() blocks or reaps."""

    def __init__(self, alive=False):
        self.pid = 24680
        self.alive = alive

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout=None):
        self.alive = False
        return 0

    def kill(self):
        self.alive = False


class TimingOutChild(FakeChild):
    def __init__(self):
        super().__init__(alive=True)

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired('child', timeout)


# --- 1. cleanup hardening ---------------------------------------------------

def test_gbk_taskkill_output_does_not_make_stop_tree_raise(tmp_path, monkeypatch):
    """The 2026-09-20 bytes: taskkill answering in GBK must decode, not kill the reader."""
    monkeypatch.setattr(RT, 'WINDOWS', True)
    monkeypatch.setattr(RT, 'taskkill_command', lambda pid: gbk_script(tmp_path, GBK_SUCCESS, 0))
    child = sleeping_child()
    report = RT.stop_tree(child)  # strict: the call windows_collector.step() makes
    assert report['tree_termination_confirmed'] is True
    assert report['process_terminated'] is True
    assert '\ufffd' in report['taskkill_stdout']
    assert 'cleanup_error' not in report
    assert child.poll() is not None


def test_step_records_a_failed_taskkill_and_returns_125(tmp_path, monkeypatch):
    """GBK + a non-zero taskkill: the report carries the cleanup error, step() says 125."""
    monkeypatch.setattr(W, 'PYTHON', Path(sys.executable))
    monkeypatch.setattr(RT, 'WINDOWS', True)
    monkeypatch.setattr(RT, 'taskkill_command', lambda pid: gbk_script(tmp_path, GBK_FAILURE, 3))
    state = {}
    assert W.step(SLEEP, tmp_path / 'child.log', dict(os.environ), 0.3, state, 'p1') == 125
    entry = state['cleanup_errors'][0]
    assert entry['step'] == 'p1' and entry['pid'] > 0
    assert 'cleanup_error' in entry and 'process cleanup incomplete' in entry['cleanup_error']
    # The GBK bytes decoded to U+FFFD (P0 fix) and are recorded inside the strict error.
    assert 'taskkill_stderr' in entry['cleanup_error'] and '\ufffd' in entry['cleanup_error']


def test_step_absorbs_any_stop_tree_exception_and_returns_125(tmp_path, monkeypatch):
    """A future cleanup bug must stay a recorded 125 (unconfirmed), never an escaping exception."""
    def exploding_stop_tree(*_args, **_kwargs):
        raise TypeError("'NoneType' object is not subscriptable")

    monkeypatch.setattr(W, 'PYTHON', Path(sys.executable))
    monkeypatch.setattr(W, 'stop_tree', exploding_stop_tree)
    monkeypatch.setattr(W.subprocess, 'Popen', lambda *a, **k: TimingOutChild())
    state = {}
    assert W.step(['-m', 'whatever'], tmp_path / 'child.log', {}, 1, state, 'basic') == 125
    entry = state['cleanup_errors'][0]
    assert entry['step'] == 'basic' and entry['pid'] == 24680
    assert 'TypeError' in entry['cleanup_error'] and 'NoneType' in entry['cleanup_error']
    assert entry['cleanup_traceback'].startswith('Traceback (most recent call last)')
    assert 'exploding_stop_tree' in entry['cleanup_traceback']
    # The base-sync call site passes no receipt; that must not raise either.
    assert W.step(['-m', 'whatever'], tmp_path / 'child.log', {}, 1) == 125


# --- 2. segment loop -------------------------------------------------------

class Clock:
    """Deterministic stand-in for windows_collector.time (segment budget only)."""

    def __init__(self, start=1000.0):
        self.value = start

    def monotonic(self):
        return self.value

    def time(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def build_collector(tmp_path, monkeypatch, plans, *, step_seconds=60.0, budget=None,
                    basic_times_out=False, publish_error=None):
    """Drive ``windows_collector.main`` with one fake p1 segment per entry in ``plans``.

    plans[i] = {'exit': int, 'add': int, 'run_finished': bool, 'pending': [...],
                'write_status': bool}

    ``basic_times_out`` routes the basic stage through the real ``step()`` with a child
    that never finishes and a ``stop_tree`` that explodes -- the 2026-09-20 shape.
    """
    clock = Clock()
    real_step = W.step
    monkeypatch.setattr(W, 'time', clock)
    monkeypatch.setattr(W, 'PYTHON', Path(sys.executable))
    if budget is not None:
        monkeypatch.setattr(W, 'P1_TOTAL_BUDGET_SECONDS', budget)
    run_dir = tmp_path / 'runs' / 'day'
    run_dir.mkdir(parents=True, exist_ok=True)
    calls = {'publish': [], 'p1': 0, 'normalize': 0}

    def fake_pull(target, receipt=None):
        Path(target).write_text(json.dumps([{'id': 'old', 'job_title': 't', 'status': 'open'}]),
                                encoding='utf-8')
        return W.digest(Path(target))

    def fake_step(args, log, env, timeout, receipt=None, name=None):
        if name == 'basic' and basic_times_out:
            return real_step(args, log, env, timeout, receipt, name)
        module = args[args.index('-m') + 1]
        stage = Path(env['QIUZHAO_DATA_DIR'])
        if module == 'qiuzhao.collector.p1_pipeline':
            plan = plans[min(calls['p1'], len(plans) - 1)]
            calls['p1'] += 1
            clock.value += step_seconds
            rows = json.loads((stage / 'jobs.json').read_text(encoding='utf-8'))
            for index in range(plan.get('add', 0)):
                rows.append({'id': f"seg{calls['p1']}-{index}", 'job_title': 't', 'status': 'open'})
            (stage / 'jobs.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            (stage / 'p1-checkpoints').mkdir(exist_ok=True)
            (stage / 'p1-checkpoints' / 'marker.json').write_text('{}')
            if plan.get('write_status', True):
                (stage / 'p1-status.json').write_text(json.dumps(
                    {'run_finished': plan['run_finished'], 'pending': plan.get('pending', []),
                     'results': {}}, ensure_ascii=False), encoding='utf-8')
            return plan['exit']
        if module == 'qiuzhao.normalize':
            calls['normalize'] += 1
        return 0

    def fake_publish_with_rebase(baseline, candidate, expected_base, work, pull, publish, **_kwargs):
        calls['publish'].append({'candidate': str(candidate),
                                 'sha256': W.digest(Path(candidate))})
        if publish_error:
            raise publish_error
        return {'publication': {'published': True, 'after_sha256': W.digest(Path(candidate))},
                'published_path': str(candidate), 'attempts': []}

    def exploding_stop_tree(*_args, **_kwargs):
        raise RuntimeError('cleanup exploded')

    monkeypatch.setattr(W, 'ROOT', tmp_path)
    monkeypatch.setattr(W, 'pull', fake_pull)
    monkeypatch.setattr(W, 'step', fake_step)
    monkeypatch.setattr(W, 'publish_with_rebase', fake_publish_with_rebase)
    if basic_times_out:
        monkeypatch.setattr(W.subprocess, 'Popen', lambda argv, **k: TimingOutChild()
                            if 'qiuzhao.collector.run' in argv else FakeChild(alive=False))
        monkeypatch.setattr(W, 'stop_tree', exploding_stop_tree)
    monkeypatch.setattr('sys.argv', ['windows_collector', '--no-sync', '--resume-run', str(run_dir)])
    code = W.main()
    return code, json.loads((run_dir / 'receipt.json').read_text(encoding='utf-8')), calls


def row_ids(path):
    return [row['id'] for row in json.loads(Path(path).read_text(encoding='utf-8'))]


def test_every_unfinished_segment_is_published(tmp_path, monkeypatch):
    """Three segments with pending work: three normalize passes, three publications."""
    plans = [{'exit': 2, 'add': 1, 'run_finished': False, 'pending': ['A/campus', 'B/campus']},
             {'exit': 2, 'add': 1, 'run_finished': False, 'pending': ['B/campus']},
             {'exit': 2, 'add': 1, 'run_finished': True, 'pending': []}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert calls['p1'] == 3 and calls['normalize'] == 3
    assert len(calls['publish']) == 3, 'each segment must reach publish_with_rebase'
    assert row_ids(tmp_path / 'data' / 'jobs.json') == ['old', 'seg1-0', 'seg2-0', 'seg3-0']
    assert [segment['exit'] for segment in receipt['p1_segments']] == [2, 2, 2]
    assert [segment['pending_count'] for segment in receipt['p1_segments']] == [2, 1, 0]
    assert [segment['p1_seconds'] for segment in receipt['p1_segments']] == [60.0, 60.0, 60.0]
    assert all(segment['elapsed_seconds'] >= segment['p1_seconds']
               for segment in receipt['p1_segments'])
    first = receipt['p1_segments'][0]['publication']
    assert first['action'] == 'published' and first['server_rows_before'] == 1
    assert first['server_rows_after'] == 2
    assert receipt['p1_segments'][2]['publication']['server_rows_after'] == 4
    assert receipt['p1_segments'][0]['step_changes']['p1']['exit'] == 2
    assert receipt['p1_finished'] is True
    assert receipt['p1_concurrency'] == {'workers': W.P1_WORKERS,
                                         'platform_workers': W.P1_PLATFORM_WORKERS,
                                         'platform_min_interval': 1.0,
                                         'memory': W.P1_MEMORY_NOTE,
                                         'company_budget': W.P1_COMPANY_BUDGET,
                                         'batch_publish': True,
                                         'segment_seconds': W.P1_SEGMENT_SECONDS,
                                         'segment_step_limit': W.P1_SEGMENT_STEP_LIMIT,
                                         'total_budget_seconds': W.P1_TOTAL_BUDGET_SECONDS,
                                         'detail_cache_root': str(tmp_path / 'data' / 'p1-detail-cache'),
                                         'persistent_state_root': str(tmp_path / 'data' / 'p1-state')}
    assert receipt['steps']['p1'] == 2 and code == 1  # partial units, never a crash


def test_finished_p1_breaks_the_loop(tmp_path, monkeypatch):
    """``run_finished`` + empty ``pending`` after one segment: no second segment runs."""
    plans = [{'exit': 0, 'add': 1, 'run_finished': True, 'pending': []}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert calls['p1'] == 1 and calls['normalize'] == 1 and len(calls['publish']) == 1
    assert len(receipt['p1_segments']) == 1
    assert receipt['p1_finished'] is True and receipt['steps']['p1'] == 0
    assert code == 0


def test_unchanged_segment_is_not_published_twice(tmp_path, monkeypatch):
    """Two segments, the second collecting nothing new: one upload, not two."""
    plans = [{'exit': 2, 'add': 1, 'run_finished': False, 'pending': ['B/campus']},
             {'exit': 2, 'add': 0, 'run_finished': True, 'pending': []}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert calls['p1'] == 2 and calls['normalize'] == 2
    assert len(calls['publish']) == 1, 'the second segment re-uploaded unchanged bytes'
    second = receipt['p1_segments'][1]['publication']
    assert second['action'] == 'unchanged' and second['server_rows_after'] == 2
    assert receipt['p1_finished'] is True


def test_resume_run_skips_finished_segments_and_does_not_republish(tmp_path, monkeypatch):
    """Re-entry after everything finished: no p1 process, no upload, local mirror intact."""
    plans = [{'exit': 0, 'add': 1, 'run_finished': True, 'pending': []}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert calls['p1'] == 1 and len(calls['publish']) == 1
    # The interruption this change exists for: p1 and its publication finished, the
    # process died before the run itself was marked complete.
    statepath = tmp_path / 'runs' / 'day' / 'receipt.json'
    interrupted = json.loads(statepath.read_text(encoding='utf-8'))
    interrupted.pop('finished'); interrupted.pop('success')
    statepath.write_text(json.dumps(interrupted, ensure_ascii=False), encoding='utf-8')
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert calls['p1'] == 0, 'a finished p1 must not be re-collected'
    assert calls['publish'] == [], 'a finished p1 must not be re-uploaded'
    assert receipt['resume_mode'] == 'publication-only'
    assert receipt['publication_retry']['action'] == 'unchanged'
    assert receipt['delivery']['publication'] == 'accepted'
    assert row_ids(tmp_path / 'data' / 'jobs.json') == ['old', 'seg1-0']
    # A second re-entry after the run is complete is a complete no-op.
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert code == 0 and calls['p1'] == 0 and calls['publish'] == []


def test_segment_timeout_keeps_the_checkpoint_and_publishes(tmp_path, monkeypatch):
    """124 from the segment watchdog: staging and checkpoint survive, data is published."""
    plans = [{'exit': 124, 'add': 1, 'run_finished': False, 'pending': ['B/campus']}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert calls['p1'] == 1 and len(calls['publish']) == 1
    assert receipt['step_changes']['p1'] == {'exit': 124, 'result': 'kept'}
    data = tmp_path / 'runs' / 'day' / 'data'
    assert (data / 'p1-status.json').exists() and (data / 'p1-checkpoints' / 'marker.json').exists()
    assert receipt['p1_stopped']['reason'].startswith('p1 watchdog fired')
    assert receipt['p1_pending'] == ['B/campus']
    assert receipt['steps']['p1'] == 124 and code == 1


def test_segment_exit_1_rolls_back_that_segment_and_is_retried_once(tmp_path, monkeypatch):
    """Exit 1 means no trustworthy output: roll back + reset p1, retry once, then stop."""
    plans = [{'exit': 1, 'add': 1, 'run_finished': False, 'pending': ['B/campus']},
             {'exit': 1, 'add': 1, 'run_finished': False, 'pending': ['B/campus']}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert calls['p1'] == 2, 'exit 1 must be retried exactly once'
    assert receipt['p1_segments'][0]['attempts'] == [1, 1]
    assert not (tmp_path / 'runs' / 'day' / 'data' / 'p1-status.json').exists()
    assert receipt['step_changes']['p1'] == {'exit': 1, 'result': 'rolled_back'}
    assert receipt['p1_stopped']['reason'].startswith('p1 exited 1')
    # The rolled-back segment must not leak its rows into the published library.
    assert row_ids(tmp_path / 'data' / 'jobs.json') == ['old']
    assert code == 1


def test_publish_failure_still_records_the_segment(tmp_path, monkeypatch):
    """A failing upload must not erase the segment's exit code/step_changes from the receipt."""
    plans = [{'exit': 2, 'add': 1, 'run_finished': False, 'pending': ['B/campus']}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans,
                                           publish_error=RuntimeError('receiver exploded'))
    assert code == 1 and receipt['error'].startswith('RuntimeError: receiver exploded')
    assert receipt['error_step'] == 'validate-and-publish'
    assert len(receipt['p1_segments']) == 1, 'the segment record was written too late'
    segment = receipt['p1_segments'][0]
    assert segment['exit'] == 2 and segment['pending_count'] == 1
    assert segment['step_changes']['p1']['exit'] == 2 and segment['step_changes']['p1']['added'] == 1
    assert segment['finished_at'] and segment['elapsed_seconds'] > 0
    assert 'publication' not in segment


def test_missing_p1_status_stops_instead_of_looping_forever(tmp_path, monkeypatch):
    """No readable ``p1-status.json`` means progress cannot be proven: stop, do not spin."""
    plans = [{'exit': 2, 'add': 1, 'run_finished': False, 'pending': [], 'write_status': False}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert calls['p1'] == 1
    assert receipt['p1_stopped']['reason'].startswith('p1-status.json missing or unreadable')
    assert len(calls['publish']) == 1


# --- 3. segment budget arithmetic ------------------------------------------

def test_segment_budget_covers_drain_finalisation_and_publishing():
    assert W.P1_SEGMENT_STEP_LIMIT == (W.P1_SEGMENT_SECONDS + W.P1_SCOPE_TIMEOUT
                                       + W.P1_SEGMENT_FINALIZE_BUDGET)
    # The argv must carry the configured values; the values themselves are configuration
    # (2026-09-23: 1800s segments, 16 workers, 1 per platform) and are not pinned here.
    args, limit = {name: (a, l) for name, a, l in W.steps_for(Path('/stage'), False)}['p1']
    assert args[args.index('--max-run-seconds') + 1] == str(W.P1_SEGMENT_SECONDS)
    assert args[args.index('--workers') + 1] == str(W.P1_WORKERS)
    assert args[args.index('--platform-workers') + 1] == str(W.P1_PLATFORM_WORKERS)
    assert args[args.index('--scope-timeout') + 1] == str(W.P1_SCOPE_TIMEOUT)
    assert '--resume-latest' in args and '--apply' in args and '--batch-publish' in args
    assert limit == W.P1_SEGMENT_STEP_LIMIT


def test_total_budget_stops_at_a_segment_boundary_with_everything_published(tmp_path, monkeypatch):
    """The 20h backstop never kills a running p1: it refuses to start the next segment."""
    plans = [{'exit': 2, 'add': 1, 'run_finished': False, 'pending': ['C/campus']}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans, step_seconds=60.0,
                                           budget=100.0)
    assert calls['p1'] == 2, 'segment 2 starts (60s < 100s); segment 3 must not'
    assert len(calls['publish']) == 2, 'both finished segments are published'
    assert receipt['p1_budget']['exhausted'] is True
    assert receipt['p1_budget']['stopped_at'] == 'segment-boundary'
    assert receipt['p1_stopped']['reason'].startswith('total budget reached')
    assert receipt['p1_pending'] == ['C/campus']
    assert receipt['steps']['p1'] == 2 and code == 1


def test_pending_that_stops_shrinking_stops_the_loop(tmp_path, monkeypatch):
    """A segment that cannot reduce ``pending`` twice in a row is a stall, not progress."""
    plans = [{'exit': 2, 'add': 1, 'run_finished': False, 'pending': ['A', 'B', 'C']}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans)
    assert calls['p1'] == W.P1_MAX_STALLED_SEGMENTS + 1
    assert receipt['p1_stopped']['reason'].startswith('pending stopped shrinking')
    assert len(calls['publish']) == 3


# --- 4. cleanup failure inside a full run ----------------------------------

def test_unconfirmed_cleanup_blocks_the_day_as_an_unsafe_writer(tmp_path, monkeypatch):
    """A timed-out basic whose cleanup explodes: recorded, and nothing else touches staging."""
    plans = [{'exit': 2, 'add': 1, 'run_finished': True, 'pending': []}]
    code, receipt, calls = build_collector(tmp_path, monkeypatch, plans, basic_times_out=True)
    assert code == 1
    assert receipt['steps']['basic'] == 125
    assert receipt['unsafe_writer']['step'] == 'basic'
    assert receipt['cleanup_errors'][0]['cleanup_error'].startswith('RuntimeError: cleanup exploded')
    assert receipt['cleanup_errors'][0]['cleanup_traceback'].startswith('Traceback')
    # A writer that may still be alive: no p1, no normalize, no publication, no rollback.
    assert calls['p1'] == 0 and calls['normalize'] == 0 and calls['publish'] == []
    assert receipt['finished'] is False and receipt['success'] is False
    # ... and a resume refuses until termination is confirmed by hand.
    monkeypatch.setattr('sys.argv', ['windows_collector', '--resume-run', str(tmp_path / 'runs' / 'day')])
    try:
        W.main()
    except RuntimeError as error:
        assert 'unsafe writer' in str(error)
    else:
        raise AssertionError('resume ignored unsafe_writer')


# --- 5. overlapping daily runs ---------------------------------------------

class BusyLock:
    """A second collector already holds data/windows-runner.lock."""

    LOCK_EX = 2
    LOCK_NB = 4

    @staticmethod
    def flock(*_args, **_kwargs):
        raise OSError(11, 'Resource temporarily unavailable')


def test_runner_lock_conflict_returns_75_and_writes_an_alert(tmp_path, monkeypatch):
    """The 06:10 task overlapping a long run must stop being silent (exit 75)."""
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data' / 'windows-status.json').write_text(json.dumps(
        {'started_at': '2026-09-20T06:10:01+08:00', 'stage': 'p1', 'finished': False,
         'success': False, 'total_jobs': 114739}), encoding='utf-8')
    monkeypatch.setattr(W, 'ROOT', tmp_path)
    monkeypatch.setattr(W, 'fcntl', BusyLock)
    monkeypatch.setattr('sys.argv', ['windows_collector', '--no-sync'])
    assert W.main() == 75
    lines = (tmp_path / 'data' / 'runner-skipped.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record['event'] == 'runner_skipped' and record['exit_code'] == 75
    assert record['mode'] == 'daily' and record['previous']['stage'] == 'p1'
    assert record['previous']['total_jobs'] == 114739
    assert '上一轮采集仍在运行' in record['message']
    assert 'still holds data/windows-runner.lock' in record['reason']
    # This branch has no qiuzhao/notify.py yet; the record must say how to enable Feishu.
    assert 'feat/cc-bot-notifier' in record['notified']


def test_runner_lock_conflict_uses_the_cc_bot_notifier_when_present(tmp_path, monkeypatch):
    """Once feat/cc-bot-notifier lands, the same call site delivers over Feishu."""
    sent = []

    def fake_notify(event, **kwargs):
        sent.append((event, kwargs.get('text')))
        return {'sent': True, 'channel': 'feishu'}

    module = types.ModuleType('qiuzhao.notify')
    module.notify = fake_notify
    monkeypatch.setitem(sys.modules, 'qiuzhao.notify', module)
    monkeypatch.setattr(W, 'ROOT', tmp_path)
    monkeypatch.setattr(W, 'fcntl', BusyLock)
    monkeypatch.setattr('sys.argv', ['windows_collector', '--smoke'])
    assert W.main() == 75
    assert sent and sent[0][0] == 'runner_skipped' and '上一轮采集仍在运行' in sent[0][1]
    record = json.loads((tmp_path / 'data' / 'runner-skipped.jsonl').read_text(encoding='utf-8'))
    assert record['notified'] == {'sent': True, 'channel': 'feishu'}
    assert record['mode'] == 'smoke'


def test_runner_skipped_alert_survives_a_missing_data_directory(tmp_path, monkeypatch):
    """The alert is best effort: it must not raise, and must report what it could not do."""
    monkeypatch.setattr(W, 'ROOT', tmp_path)
    monkeypatch.setattr(W, 'fcntl', BusyLock)
    monkeypatch.setattr('sys.argv', ['windows_collector'])
    assert W.main() == 75  # data/ is created before the lock is taken
    assert (tmp_path / 'data' / 'runner-skipped.jsonl').exists()
