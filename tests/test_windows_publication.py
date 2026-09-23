"""Working-baseline publication, deferred delivery and recovery gates (2026-09-23 plan, step 1).

Every scenario drives the real ``windows_collector.main`` / ``publish_with_rebase`` /
``rebase_files`` against an in-memory stand-in for ``deploy/windows_receiver.py`` that
keeps the receiver's contract: ``already_published`` when it already holds the upload,
a CAS refusal when it holds anything other than the expected hash, otherwise replace.
Only p1 and normalize are faked.
"""
import json
from pathlib import Path
import shutil

import pytest

from deploy import windows_collector as W
from deploy import windows_recover_run as R
from deploy.windows_rebase import CASConflict


def job(ident, title, status='open'):
    return {'id': ident, 'job_title': title, 'status': status}


def rows_of(path):
    return {row['id']: row for row in json.loads(Path(path).read_text(encoding='utf-8'))}


class Crash(BaseException):
    """A process death: not an ``Exception``, so main() cannot write its receipt."""


class Server:
    """The receiver's CAS contract over one file."""

    def __init__(self, path, rows):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        self.cas_conflicts = 0
        self.accepted = []
        self.lose_receipts = 0
        self.unreachable = False
        self.crash_after_accept = False
        self.publish_calls = 0
        self.unavailable = W.PublishUnavailable
        self.inject = {}  # publish call number -> external write made just before it

    def sha(self):
        return W.digest(self.path)

    def rows(self):
        return rows_of(self.path)

    def write(self, rows):
        self.path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')

    def pull(self, target, receipt=None):
        if self.unreachable:
            raise self.unavailable('pull_snapshot unreachable')
        shutil.copyfile(self.path, target)
        return self.sha()

    def publish(self, candidate, expected, folder, receipt=None):
        self.publish_calls += 1
        if self.publish_calls in self.inject:
            self.inject.pop(self.publish_calls)()
        if self.unreachable:
            raise self.unavailable('publish_snapshot unreachable')
        after = W.digest(Path(candidate))
        if self.sha() == after:
            return {'published': True, 'already_published': True, 'after_sha256': after}
        if self.sha() != expected:
            self.cas_conflicts += 1
            raise CASConflict('production changed: pull and recollect')
        shutil.copyfile(candidate, self.path)
        self.accepted.append(after)
        if self.crash_after_accept:
            self.crash_after_accept = False
            raise Crash('died after the receiver replaced jobs.json')
        if self.lose_receipts:
            self.lose_receipts -= 1
            raise self.unavailable('publish_snapshot receipt lost after acceptance')
        return {'published': True, 'before_sha256': expected, 'after_sha256': after}


class Clock:
    def __init__(self):
        self.value = 1000.0

    def monotonic(self):
        return self.value

    def time(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def harness(tmp_path, monkeypatch, initial):
    server = Server(tmp_path / 'server' / 'jobs.json', initial)
    clock = Clock()
    monkeypatch.setattr(W, 'ROOT', tmp_path)
    monkeypatch.setattr(W, 'time', clock)
    monkeypatch.setattr(W, 'pull', server.pull)
    monkeypatch.setattr(W, 'publish_snapshot', server.publish)
    monkeypatch.setattr(R, 'pull', server.pull)
    run_dir = tmp_path / 'runs' / 'day'
    run_dir.mkdir(parents=True, exist_ok=True)
    return server, clock, run_dir


def drive(tmp_path, monkeypatch, run_dir, clock, plans, *, calls=None, step_seconds=60.0, module=W):
    """One ``main()`` invocation. plans[i]: mutate(rows), before(), run_finished, pending, exit."""
    calls = calls if calls is not None else {'p1': 0, 'normalize': 0}

    def fake_step(args, log, env, timeout, receipt=None, name=None):
        module = args[args.index('-m') + 1]
        stage = Path(env['QIUZHAO_DATA_DIR'])
        if module == 'qiuzhao.collector.p1_pipeline':
            plan = plans[min(calls['p1'], len(plans) - 1)]
            calls['p1'] += 1
            clock.value += step_seconds
            if plan.get('before'):
                plan['before']()
            rows = json.loads((stage / 'jobs.json').read_text(encoding='utf-8'))
            if plan.get('mutate'):
                plan['mutate'](rows)
            (stage / 'jobs.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            if plan.get('p1_state'):
                plan['p1_state'](stage)
            (stage / 'p1-status.json').write_text(json.dumps(
                {'run_finished': plan.get('run_finished', False), 'pending': plan.get('pending', []),
                 'results': {}}), encoding='utf-8')
            return plan.get('exit', 0)
        if module == 'qiuzhao.normalize':
            calls['normalize'] += 1
        return 0

    monkeypatch.setattr(module, 'step', fake_step)
    monkeypatch.setattr('sys.argv', ['windows_collector', '--no-sync', '--resume-run', str(run_dir)])
    code = module.main()
    return code, json.loads((run_dir / 'receipt.json').read_text(encoding='utf-8')), calls


def set_title(ident, title):
    def mutate(rows):
        for row in rows:
            if row['id'] == ident:
                row['job_title'] = title
    return mutate


def add_row(ident, title):
    return lambda rows: rows.append(job(ident, title))


def publications(receipt):
    return [segment['publication']['action'] for segment in receipt['p1_segments']]


# --- 1. A -> B -> C on one ID, no other writer ------------------------------------

def test_three_segments_on_one_id_end_at_c_without_self_made_conflicts(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A'), job('y', 'Y')])
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p', 'q']},
             {'mutate': set_title('x', 'C'), 'pending': ['q']},
             {'mutate': add_row('z', 'Z'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 3
    assert server.rows()['x']['job_title'] == 'C'
    assert set(server.rows()) == {'x', 'y', 'z'}
    assert server.cas_conflicts == 0, 'segment publications conflicted with their own predecessors'
    assert publications(receipt) == ['published'] * 3
    assert all(segment['publication']['direct'] for segment in receipt['p1_segments'])
    # Evidence stays the original pull; the working baseline is what the server holds.
    assert W.digest(run_dir / 'jobs.before.json') == receipt['before_sha256']
    assert receipt['working_baseline']['sha256'] == server.sha()
    assert len(receipt['accepted_publications']) == 3
    assert receipt['delivery']['publication'] == 'accepted'
    assert receipt['delivery']['server_accepted_sha256'] == server.sha()
    assert code == 0 and receipt['success'] is True and receipt['finished'] is True


# --- 2. real external conflict ----------------------------------------------------

def test_external_update_is_kept_and_the_next_baseline_is_the_accepted_merge(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A'), job('y', 'Y')])

    def external_writer():
        rows = list(server.rows().values())
        for row in rows:
            if row['id'] == 'x':
                row['job_title'] = 'EXTERNAL'
        rows.append(job('ext', 'from another publisher'))
        server.write(rows)

    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p', 'q']},
             {'before': external_writer, 'mutate': set_title('x', 'LOCAL'), 'pending': ['q']},
             {'mutate': set_title('y', 'Y2'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    second = receipt['p1_segments'][1]['publication']
    assert second['action'] == 'published' and second['direct'] is False and second['conflicts'] == 1
    assert server.cas_conflicts == 1, 'only the genuine external change may cause a CAS refusal'
    # The accepted merge became the working baseline and staging followed it, so the
    # third segment published directly and did not replay LOCAL over EXTERNAL.
    final = server.rows()
    assert final['x']['job_title'] == 'EXTERNAL'
    assert final['ext']['job_title'] == 'from another publisher'
    assert final['y']['job_title'] == 'Y2'
    assert receipt['p1_segments'][2]['publication']['direct'] is True
    assert receipt['accepted_publications'][1]['rebased'] is True
    assert receipt['working_baseline']['sha256'] == server.sha()
    assert rows_of(run_dir / 'data' / 'jobs.json') == final
    assert code == 0


# --- 3. server accepted, receipt lost ---------------------------------------------

def test_lost_receipt_is_aligned_by_hash_and_later_edits_are_not_dropped(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A'), job('y', 'Y')])
    server.lose_receipts = 1
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p', 'q']},
             {'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert publications(receipt) == ['deferred', 'published']
    second = receipt['p1_segments'][1]['publication']
    assert second['aligned_unconfirmed_publication']['server_sha256'] == server.accepted[0]
    assert second['conflicts'] == 0
    assert server.rows()['x']['job_title'] == 'C'
    assert receipt['unconfirmed_publications'] == []
    assert code == 0 and receipt['delivery']['publication'] == 'accepted'


def test_receipt_lost_on_the_final_segment_is_confirmed_by_already_published(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    server.lose_receipts = 1
    plans = [{'mutate': set_title('x', 'B'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert publications(receipt) == ['deferred']
    # The closing publication attempt of the same run confirms it without re-uploading.
    assert receipt['final_publication']['publication'].get('already_published') is True
    assert len(server.accepted) == 1, 'the same content was uploaded twice'
    assert receipt['unconfirmed_publications'] == []
    assert code == 0 and receipt['success'] is True
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 0 and code == 0


# --- 4. local interruption --------------------------------------------------------

def test_crash_between_receiver_accept_and_local_state_is_realigned(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    server.crash_after_accept = True
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p']},
             {'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    calls = {'p1': 0, 'normalize': 0}
    with pytest.raises(Crash):
        drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    on_disk = json.loads((run_dir / 'receipt.json').read_text(encoding='utf-8'))
    assert on_disk['publication_intent']['candidate_sha256'] == server.accepted[0]
    assert 'working_baseline' not in on_disk
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    assert server.rows()['x']['job_title'] == 'C'
    assert server.cas_conflicts <= 1
    # The crashed segment has no publication entry; the resumed one aligned by hash.
    assert [s.get('publication', {}).get('conflicts', 0) for s in receipt['p1_segments']] == [0, 0]
    assert receipt['working_baseline']['sha256'] == server.sha()
    assert code == 0


def test_crash_while_staging_follows_a_rebased_acceptance_is_completed_on_resume(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])

    def external_writer():
        server.write([job('x', 'EXTERNAL'), job('ext', 'E')])

    real_replace = W.os.replace
    armed = {'on': True}

    def crashing_replace(source, target):
        if armed['on'] and Path(target).name == 'jobs.json' and Path(source).name == 'jobs.accepted.tmp':
            armed['on'] = False
            raise Crash('died while replacing staging')
        return real_replace(source, target)

    monkeypatch.setattr(W.os, 'replace', crashing_replace)
    plans = [{'before': external_writer, 'mutate': set_title('x', 'LOCAL'), 'pending': ['p']},
             {'mutate': add_row('z', 'Z'), 'run_finished': True, 'pending': []}]
    calls = {'p1': 0, 'normalize': 0}
    with pytest.raises(Crash):
        drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    on_disk = json.loads((run_dir / 'receipt.json').read_text(encoding='utf-8'))
    assert on_disk['stage_advance']['stage_sha256'], 'expected staging hash must be durable first'
    assert rows_of(run_dir / 'data' / 'jobs.json')['x']['job_title'] == 'LOCAL'
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    assert 'stage_advance' not in receipt
    final = server.rows()
    assert final['x']['job_title'] == 'EXTERNAL' and 'ext' in final and 'z' in final
    assert code == 0


# --- 5. every publication deferred ------------------------------------------------

def test_all_deferred_is_not_success_and_resume_only_publishes(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    original = server.sha()
    plans = [{'before': lambda: setattr(server, 'unreachable', True),
              'mutate': set_title('x', 'B'), 'pending': ['p']},
             {'mutate': add_row('z', 'Z'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert publications(receipt) == ['deferred', 'deferred']
    assert receipt['steps']['p1'] == 0, 'collection itself was clean'
    assert receipt['collection'] == {'state': 'complete', 'reason': 'p1 finished'}
    assert receipt['delivery']['publication'] == 'pending'
    assert receipt['finished'] is False and receipt['success'] is False and code == 1
    assert server.sha() == original
    # Transport back: the resume publishes what was collected and nothing more.
    server.unreachable = False
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 0 and calls['normalize'] == 0
    assert receipt['resume_mode'] == 'publication-only'
    assert receipt['publication_retry']['action'] == 'published'
    assert server.rows()['x']['job_title'] == 'B' and 'z' in server.rows()
    assert code == 0 and receipt['finished'] is True
    # A further resume is a no-op.
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert code == 0 and calls['p1'] == 0


def test_legacy_finished_receipt_with_a_deferral_is_not_short_circuited(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = [{'before': lambda: setattr(server, 'unreachable', True),
              'mutate': set_title('x', 'B'), 'run_finished': True, 'pending': []}]
    drive(tmp_path, monkeypatch, run_dir, clock, plans)
    statepath = run_dir / 'receipt.json'
    legacy = json.loads(statepath.read_text(encoding='utf-8'))
    legacy.pop('delivery')
    legacy['finished'] = legacy['success'] = True  # what the old runner wrote
    statepath.write_text(json.dumps(legacy), encoding='utf-8')
    server.unreachable = False
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert server.rows()['x']['job_title'] == 'B' and code == 0


# --- 6. persisted budget ----------------------------------------------------------

def test_resume_continues_the_same_budget(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    monkeypatch.setattr(W, 'P1_TOTAL_BUDGET_SECONDS', 100)
    plans = [{'exit': 124, 'mutate': add_row('a', 'A'), 'pending': ['p', 'q']}]
    calls = {'p1': 0, 'normalize': 0}
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    assert calls['p1'] == 1 and receipt['collection']['state'] == 'stopped'
    ledger = receipt['p1_budget_ledger']
    assert ledger['used_seconds'] == 60.0
    plans[0] = {'exit': 2, 'mutate': add_row('b', 'B'), 'pending': ['q']}
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    assert calls['p1'] == 2, 'resume received a fresh budget'
    assert receipt['p1_budget_ledger']['deadline_epoch'] == ledger['deadline_epoch']
    assert receipt['p1_budget']['exhausted'] is True
    assert receipt['collection']['state'] == 'complete'
    assert {'a', 'b'} <= set(server.rows())


def test_resume_after_the_wall_clock_deadline_starts_no_segment(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = [{'exit': 124, 'mutate': add_row('a', 'A'), 'pending': ['p']}]
    calls = {'p1': 0, 'normalize': 0}
    drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    clock.value += W.P1_TOTAL_BUDGET_SECONDS  # the process was down past the deadline
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    assert calls['p1'] == 1
    assert receipt['p1_stopped']['reason'].startswith('total budget reached')


# --- 7. cross-day p1 state + stable cache root ------------------------------------

def test_retry_state_survives_into_the_next_run_and_cache_root_is_stable(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    seen = {}

    def write_retry(stage):
        (stage / 'p1-retry-queue.json').write_text(json.dumps(
            {'updated_at': '2026-09-23T01:00:00+00:00', 'entries': {'大疆/campus': {'reason': 'ssl'}}}))

    def read_retry(stage):
        seen['retry'] = json.loads((stage / 'p1-retry-queue.json').read_text())['entries']

    envs = []
    real = W.run_stage_step

    def capture(state, statepath, run, stage, name, args, limit, env, **kwargs):
        envs.append(env.get('QIUZHAO_P1_DETAIL_CACHE_ROOT'))
        return real(state, statepath, run, stage, name, args, limit, env, **kwargs)

    monkeypatch.setattr(W, 'run_stage_step', capture)
    drive(tmp_path, monkeypatch, run_dir, clock,
          [{'p1_state': write_retry, 'run_finished': True, 'pending': []}])
    persisted = tmp_path / 'data' / 'p1-state' / 'p1-retry-queue.json'
    assert json.loads(persisted.read_text())['entries'] == {'大疆/campus': {'reason': 'ssl'}}
    next_run = tmp_path / 'runs' / 'next'
    next_run.mkdir()
    drive(tmp_path, monkeypatch, next_run, clock,
          [{'p1_state': read_retry, 'run_finished': True, 'pending': []}])
    assert seen['retry'] == {'大疆/campus': {'reason': 'ssl'}}
    assert set(envs) == {str(tmp_path / 'data' / 'p1-detail-cache')}


# --- 8. recovery uses the same gates ----------------------------------------------

def terminal_run_with_pending_segment(tmp_path, monkeypatch):
    """Segment 1 accepted (x=B), segment 2 (x=C) deferred: a terminal, pending run."""
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A'), job('y', 'Y')])
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p']},
             {'before': lambda: setattr(server, 'unreachable', True),
              'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert publications(receipt) == ['published', 'deferred'] and code == 1
    server.unreachable = False
    return server, run_dir, receipt


def test_recover_publishes_against_the_working_baseline(tmp_path, monkeypatch):
    server, run_dir, state = terminal_run_with_pending_segment(tmp_path, monkeypatch)
    source_hash = W.digest(run_dir / 'data' / 'jobs.json')
    workdir = tmp_path / 'recovery' / 'r1'
    workdir.mkdir(parents=True)
    result = R.recover(run_dir, workdir, state)
    assert server.rows()['x']['job_title'] == 'C', 'recovery replayed from the original base'
    assert result['result']['rebase_report']['conflicts'] == []
    assert result['source_working_sha256'] == state['working_baseline']['sha256']
    assert W.digest(run_dir / 'data' / 'jobs.json') == source_hash
    # Re-running reuses the attested publication instead of uploading again.
    again = R.recover(run_dir, workdir, state)
    assert again['publication_reused'] is True and len(server.accepted) == 2


def test_recover_refuses_an_unsafe_writer_like_the_runner(tmp_path, monkeypatch):
    server, run_dir, state = terminal_run_with_pending_segment(tmp_path, monkeypatch)
    state = dict(state, unsafe_writer={'step': 'p1', 'reason': 'process tree termination unconfirmed'})
    workdir = tmp_path / 'recovery' / 'r2'
    workdir.mkdir(parents=True)
    before = server.sha()
    with pytest.raises(RuntimeError, match='unsafe writer'):
        R.recover(run_dir, workdir, state)
    assert server.sha() == before


def test_recover_cannot_retire_rows_the_runner_would_have_frozen(tmp_path, monkeypatch):
    server, run_dir, state = terminal_run_with_pending_segment(tmp_path, monkeypatch)
    stage = run_dir / 'data' / 'jobs.json'
    rows = json.loads(stage.read_text(encoding='utf-8'))
    for row in rows:
        if row['id'] == 'y':
            row['status'] = 'removed'
    stage.write_text(json.dumps(rows), encoding='utf-8')
    workdir = tmp_path / 'recovery' / 'r3'
    workdir.mkdir(parents=True)
    R.recover(run_dir, workdir, state)
    assert server.rows()['y']['status'] == 'open'
    assert server.rows()['x']['job_title'] == 'C'


def test_recover_refuses_an_unfinished_stage_advance(tmp_path, monkeypatch):
    server, run_dir, state = terminal_run_with_pending_segment(tmp_path, monkeypatch)
    state = dict(state, stage_advance={'from_sha256': 'a', 'to_sha256': 'b', 'artifact': 'x'})
    workdir = tmp_path / 'recovery' / 'r4'
    workdir.mkdir(parents=True)
    with pytest.raises(ValueError, match='unfinished publication step'):
        R.recover(run_dir, workdir, state)


def test_recover_sync_is_retired(tmp_path, monkeypatch):
    server, run_dir, state = terminal_run_with_pending_segment(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='retired'):
        R.recover(run_dir, tmp_path / 'recovery' / 'r5', state, sync=True)


def test_publication_waits_for_an_unresolved_p1_batch(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    before = server.sha()

    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p'], 'exit': 2}]
    real_status = W.p1_status
    monkeypatch.setattr(W, 'p1_status', lambda stage: dict(real_status(stage), active_batch={'id': 'b'}))
    monkeypatch.setattr(W, 'P1_MAX_STALLED_SEGMENTS', 1)
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert receipt['p1_segments'][0]['publication']['action'] == 'deferred'
    assert 'active_batch' in receipt['p1_segments'][0]['publication']['reason']
    assert server.sha() == before and code == 1


# --- 9. review round 2 -------------------------------------------------------------

def test_confirmed_alignment_survives_an_external_addition_on_the_next_retry(tmp_path, monkeypatch):
    """B accepted without receipt; while replaying C onto B someone adds X: expect C + X."""
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    server.lose_receipts = 1

    def add_external():
        server.write(list(server.rows().values()) + [job('ext', 'X')])

    # publish calls: 1 = segment 1 (receipt lost), 2 = segment 2 direct (CAS), 3 = rebase-01
    server.inject[3] = add_external
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p']},
             {'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    final = server.rows()
    assert final['x']['job_title'] == 'C', 'fell back to the original base and dropped C'
    assert final['ext']['job_title'] == 'X'
    second = receipt['p1_segments'][1]['publication']
    assert second['conflicts'] == 0 and second['rebase_attempts'] == 3  # direct + 2 rebases
    assert second['aligned_unconfirmed_publication']['matched_this_attempt'] is False
    assert code == 0


def test_confirmed_alignment_still_protects_a_real_external_same_id_update(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    server.lose_receipts = 1

    def external_same_id():
        rows = list(server.rows().values())
        rows[0]['job_title'] = 'EXTERNAL'
        server.write(rows)

    server.inject[3] = external_same_id
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p']},
             {'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert server.rows()['x']['job_title'] == 'EXTERNAL'
    assert receipt['p1_segments'][1]['publication']['conflicts'] == 1
    assert receipt['working_baseline']['sha256'] == server.sha()


def load_head_collector():
    """The runner as committed at c408b7a, to write receipts exactly as it did."""
    import importlib.util
    import subprocess
    source = subprocess.run(['git', 'show', 'c408b7a:deploy/windows_collector.py'], capture_output=True,
                            text=True, check=True, cwd=Path(W.__file__).resolve().parents[1]).stdout
    path = Path(__file__).resolve().parent / '.head_windows_collector.py'
    path.write_text(source, encoding='utf-8')
    try:
        spec = importlib.util.spec_from_file_location('head_windows_collector', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        path.unlink()
    return module


def legacy_run(tmp_path, monkeypatch, server, clock, run_dir, plans, *, budget=None, **kwargs):
    """Drive the c408b7a runner; its publish_snapshot keeps the real on-disk evidence."""
    import gzip
    old = load_head_collector()

    def old_publish_snapshot(candidate, expected, workdir, *, receipt=None):
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        with gzip.open(workdir / 'jobs.upload.gz', 'wb') as out, Path(candidate).open('rb') as src:
            shutil.copyfileobj(src, out)
        publication = server.publish(candidate, expected, workdir)
        (workdir / 'receiver-receipt.json').write_text(json.dumps(publication))
        return publication

    for name, value in (('ROOT', tmp_path), ('time', clock), ('pull', server.pull),
                        ('publish_snapshot', old_publish_snapshot)):
        monkeypatch.setattr(old, name, value)
    if budget is not None:
        monkeypatch.setattr(old, 'P1_TOTAL_BUDGET_SECONDS', budget)
    server.unavailable = old.PublishUnavailable
    try:
        return drive(tmp_path, monkeypatch, run_dir, clock, plans, module=old, **kwargs)
    finally:
        server.unavailable = W.PublishUnavailable


def deferred_c_plans(server):
    return [{'mutate': set_title('x', 'B'), 'pending': ['p']},
            {'before': lambda: setattr(server, 'unreachable', True),
             'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]


def test_legacy_finished_run_with_a_deferred_segment_is_migrated_not_replayed_from_a(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A'), job('y', 'Y')])
    plans = deferred_c_plans(server)
    code, legacy, _ = legacy_run(tmp_path, monkeypatch, server, clock, run_dir, plans)
    assert legacy['finished'] is True and legacy['publish_deferrals'], 'old runner shape'
    assert server.rows()['x']['job_title'] == 'B'
    server.unreachable = False
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 0
    assert receipt['legacy_migration']['accepted_sha256'] == legacy['publication']['after_sha256']
    assert server.rows()['x']['job_title'] == 'C'
    assert code == 0 and receipt['success'] is True
    assert W.digest(run_dir / 'jobs.before.json') == receipt['before_sha256']


def test_legacy_rebased_publication_is_migrated_with_a_three_way_stage_merge(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A'), job('y', 'Y')])

    def external():
        rows = list(server.rows().values())
        rows[1]['job_title'] = 'EXTERNAL'
        server.write(rows + [job('ext', 'E')])

    def local(rows):
        set_title('x', 'B')(rows)
        set_title('y', 'LOCAL')(rows)

    plans = [{'before': external, 'mutate': local, 'pending': ['p']},
             {'before': lambda: setattr(server, 'unreachable', True),
              'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    legacy_run(tmp_path, monkeypatch, server, clock, run_dir, plans)
    assert server.rows()['y']['job_title'] == 'EXTERNAL'
    server.unreachable = False
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    final = server.rows()
    assert final['x']['job_title'] == 'C' and final['y']['job_title'] == 'EXTERNAL' and 'ext' in final
    # The y conflict was settled by the old rebase; staging did not touch y since the
    # candidate that merge was built from, so the migration merge has nothing to resolve.
    assert receipt['legacy_migration']['stage_merge']['conflicts'] == 0
    assert receipt['accepted_publications'][0]['expected_server_sha256'] == receipt['legacy_migration']['accepted_sha256']
    assert code == 0


def test_legacy_publication_without_evidence_fails_closed(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = deferred_c_plans(server)
    legacy_run(tmp_path, monkeypatch, server, clock, run_dir, plans)
    shutil.rmtree(run_dir / 'rebase')
    server.unreachable = False
    before = server.sha()
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert code == 1 and receipt['success'] is False
    assert 'frozen artifact cannot be found' in receipt['error']
    assert server.sha() == before and calls['p1'] == 0


def test_legacy_exhausted_budget_only_publishes(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p', 'q']},
             {'before': lambda: setattr(server, 'unreachable', True),
              'mutate': set_title('x', 'C'), 'pending': ['q']}]
    code, legacy, calls = legacy_run(tmp_path, monkeypatch, server, clock, run_dir, plans, budget=100)
    assert legacy['p1_budget']['exhausted'] is True and calls['p1'] == 2
    server.unreachable = False
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 0, 'an exhausted legacy run received a fresh budget'
    assert receipt['p1_budget_ledger']['migrated_from'] == 'legacy p1_budget.exhausted'
    assert receipt['collection']['state'] == 'complete'
    assert server.rows()['x']['job_title'] == 'C'
    assert receipt['delivery']['publication'] == 'accepted'


def test_legacy_run_with_19h_spent_gets_only_the_remaining_hour(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = [{'exit': 124, 'mutate': add_row('a', 'A'), 'pending': [str(i) for i in range(10)]}]
    calls = {'p1': 0, 'normalize': 0}
    legacy_run(tmp_path, monkeypatch, server, clock, run_dir, plans, calls=calls, step_seconds=68400.0)
    assert calls['p1'] == 1
    plans = [{'exit': 2, 'mutate': add_row(f'r{i}', 'R'), 'pending': [str(j) for j in range(9 - i)]}
             for i in range(6)]
    calls = {'p1': 0, 'normalize': 0}
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls, step_seconds=1800.0)
    assert receipt['p1_budget_ledger']['migrated_from'] == 'legacy p1 segment records'
    assert receipt['p1_budget_ledger']['used_seconds'] >= 72000
    assert calls['p1'] == 2, '68400s spent + 2 x 1800s reaches 72000s; no fresh 20h'
    assert receipt['p1_budget']['exhausted'] is True


def test_recovery_publication_is_adopted_before_the_run_collects_again(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A'), job('y', 'Y')])
    plans = [{'before': lambda: setattr(server, 'unreachable', True),
              'exit': 124, 'mutate': set_title('x', 'B'), 'pending': ['p', 'q']}]
    code, state, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert state['collection']['state'] == 'stopped' and code == 1
    server.unreachable = False
    workdir = tmp_path / 'recovery' / 'r1'
    workdir.mkdir(parents=True)
    R.recover(run_dir, workdir, state)
    assert server.rows()['x']['job_title'] == 'B'
    assert (run_dir / 'data' / 'p1-status.json').exists()
    plans = [{'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 1, 'remaining work must still be collected, once'
    assert server.rows()['x']['job_title'] == 'C'
    assert [a['result'] for a in receipt['recovery_adoptions']] == ['adopted']
    assert receipt['accepted_publications'][0]['source'] == 'recovery'
    assert all(s.get('publication', {}).get('conflicts', 0) == 0 for s in receipt['p1_segments'])
    assert W.digest(run_dir / 'jobs.before.json') == receipt['before_sha256']
    assert code == 0


def test_recovery_publication_from_another_state_refuses_the_resume(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = [{'before': lambda: setattr(server, 'unreachable', True),
              'exit': 124, 'mutate': set_title('x', 'B'), 'pending': ['p']}]
    code, state, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    server.unreachable = False
    workdir = tmp_path / 'recovery' / 'r1'
    workdir.mkdir(parents=True)
    R.recover(run_dir, workdir, state)
    rows = json.loads((run_dir / 'data' / 'jobs.json').read_text())
    rows[0]['job_title'] = 'EDITED AFTER RECOVERY'
    (run_dir / 'data' / 'jobs.json').write_text(json.dumps(rows))
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert code == 1 and 'another state of this run' in receipt['error'] and calls['p1'] == 0


def test_recover_refuses_a_legacy_receipt_it_cannot_prove(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    code, legacy, _ = legacy_run(tmp_path, monkeypatch, server, clock, run_dir, deferred_c_plans(server))
    server.unreachable = False
    with pytest.raises(ValueError, match='predates the working-baseline ledger'):
        R.recover(run_dir, tmp_path / 'recovery' / 'r9', legacy)


def test_accepted_version_manifest_carries_the_lineage(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    start = server.sha()
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p']},
             {'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    latest = json.loads((tmp_path / 'data' / 'accepted-versions' / 'latest.json').read_text())
    first, second = (r['sha256'] for r in receipt['accepted_publications'])
    assert latest['sha256'] == second == server.sha()
    assert latest['lineage'] == {first: start, second: first}
    assert W.digest(Path(latest['artifact'])) == second
    assert latest['artifact_relpath'].startswith('runs/day/rebase/')


def test_old_recover_command_line_with_sync_ready_file_still_parses(tmp_path, monkeypatch):
    monkeypatch.setattr(R, 'ROOT', tmp_path)
    (tmp_path / 'runs').mkdir()
    monkeypatch.setattr('sys.argv', ['windows_recover_run', '--run', str(tmp_path / 'runs' / 'missing'),
                                     '--work-dir', str(tmp_path / 'recovery' / 'r'),
                                     '--sync-ready-file', str(tmp_path / 'data' / 'sync-owner-ready.json')])
    with pytest.raises(ValueError, match='invalid source run'):  # parsed; argparse did not exit 2
        R.main()


def test_crash_after_adopting_a_recovery_before_anything_else_resumes_idempotently(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = [{'before': lambda: setattr(server, 'unreachable', True),
              'exit': 124, 'mutate': set_title('x', 'B'), 'pending': ['p', 'q']}]
    code, state, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    server.unreachable = False
    workdir = tmp_path / 'recovery' / 'r1'
    workdir.mkdir(parents=True)
    R.recover(run_dir, workdir, state)
    real_accept = W.accept_publication

    def accept_then_die(*args, **kwargs):
        real_accept(*args, **kwargs)
        raise Crash('died after acceptance, before the consumer returned')

    monkeypatch.setattr(W, 'accept_publication', accept_then_die)
    plans = [{'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    with pytest.raises(Crash):
        drive(tmp_path, monkeypatch, run_dir, clock, plans)
    on_disk = json.loads((run_dir / 'receipt.json').read_text())
    assert on_disk['consumed_recoveries'] == [str(workdir / 'attempts' / Path(
        on_disk['accepted_publications'][0]['workdir']).parent.name)]
    monkeypatch.setattr(W, 'accept_publication', real_accept)
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert code == 0 and server.rows()['x']['job_title'] == 'C'
    assert [r['source'] for r in receipt['accepted_publications']].count('recovery') == 1


def test_receipt_that_recorded_the_adoption_without_the_marker_is_not_readopted(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = [{'before': lambda: setattr(server, 'unreachable', True),
              'exit': 124, 'mutate': set_title('x', 'B'), 'pending': ['p', 'q']}]
    code, state, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    server.unreachable = False
    workdir = tmp_path / 'recovery' / 'r1'
    workdir.mkdir(parents=True)
    R.recover(run_dir, workdir, state)
    real_accept = W.accept_publication

    def accept_then_die(*args, **kwargs):
        real_accept(*args, **kwargs)
        raise Crash('died')

    monkeypatch.setattr(W, 'accept_publication', accept_then_die)
    plans = [{'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    with pytest.raises(Crash):
        drive(tmp_path, monkeypatch, run_dir, clock, plans)
    monkeypatch.setattr(W, 'accept_publication', real_accept)
    statepath = run_dir / 'receipt.json'
    older = json.loads(statepath.read_text())
    older.pop('consumed_recoveries')  # what the pre-fix ordering could leave behind
    statepath.write_text(json.dumps(older))
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert code == 0 and server.rows()['x']['job_title'] == 'C'


def test_stage_changes_count_business_updates_not_observations(tmp_path):
    def write(name, rows):
        path = tmp_path / name
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        return path

    base = {'id': 'x', 'job_title': 'A', 'status': 'open', 'reviewed_at': '2026-09-22T08:00:00+08:00',
            'list_checked_at': '2026-09-22T08:00:00+08:00', 'detail_evidence_path': 'old.json'}
    before = write('before.json', [base, dict(base, id='gone'), dict(base, id='r')])
    observed = dict(base, reviewed_at='2026-09-23T08:00:00+08:00', list_checked_at='2026-09-23T08:00:00+08:00',
                    detail_evidence_path='new.json')
    after = write('after.json', [observed, dict(base, id='r', status='removed'), dict(base, id='new')])
    assert W.diff_counts(before, after) == {'added': 1, 'updated': 0, 'observed_only': 1,
                                            'marked_removed': 1, 'disappeared': 1}
    edited = write('edited.json', [dict(observed, job_title='B')])
    assert W.diff_counts(before, edited)['updated'] == 1
    assert W.diff_counts(before, edited)['observed_only'] == 0


def test_recovery_artifact_that_fails_verification_is_not_consumed_and_adopts_once_fixed(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = [{'before': lambda: setattr(server, 'unreachable', True),
              'exit': 124, 'mutate': set_title('x', 'B'), 'pending': ['p', 'q']}]
    code, state, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    server.unreachable = False
    workdir = tmp_path / 'recovery' / 'r1'
    workdir.mkdir(parents=True)
    result = R.recover(run_dir, workdir, state)
    artifact = Path(result['result']['published_path'])
    good = artifact.read_bytes()
    artifact.write_bytes(good.replace(b'"B"', b'"TAMPERED"'))
    before = json.loads((run_dir / 'receipt.json').read_text())
    plans = [{'mutate': set_title('x', 'C'), 'run_finished': True, 'pending': []}]
    calls = {'p1': 0, 'normalize': 0}
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    assert code == 1 and 'accepted artifact does not match' in receipt['error'] and calls['p1'] == 0
    assert not receipt.get('consumed_recoveries'), 'refused recovery was marked consumed'
    assert receipt.get('working_baseline') == before.get('working_baseline')
    assert not any(r.get('source') == 'recovery' for r in receipt.get('accepted_publications') or [])
    # The evidence is repaired; the same attempt is still fresh and is adopted now.
    artifact.write_bytes(good)
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans, calls=calls)
    assert code == 0 and calls['p1'] == 1
    assert [r['source'] for r in receipt['accepted_publications']].count('recovery') == 1
    assert receipt['consumed_recoveries'] == [str(artifact.parents[2])]
    assert server.rows()['x']['job_title'] == 'C'
