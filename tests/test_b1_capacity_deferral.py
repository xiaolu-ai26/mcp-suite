"""A server capacity refusal defers the segment instead of ending the day (2026-09-28, batch 1).

2026-09-25..28 every run stopped at its first publication because the receiver's capacity
gate refused (free ~2.71 GB < required ~2.82 GB) and the publisher treated that like an
unknown receiver error. The receiver now marks the refusal (exit 75 + RECEIVER_REFUSED);
only that complete marker, bound to this call's base and candidate, becomes
``CapacityRefused`` (a ``PublishUnavailable``): filed as refused, not unconfirmed, and
collection continues. Any other receiver result -- including the old receiver's plain
capacity-gate traceback -- keeps the "may or may not hold it" (unconfirmed) handling.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess

import pytest

from deploy import windows_collector as W
from test_windows_publication import add_row, drive, harness, job, publications, set_title

REPO = Path(__file__).resolve().parents[1]
REAL_PUBLISH = W.publish_snapshot          # the harness replaces it with an in-memory receiver
BASE, CAND = 'a' * 64, 'b' * 64
# What the pre-marker receiver (95890f03) printed on 2026-09-28: still an unknown outcome now.
OLD_RECEIVER_STDERR = (
    b'** WARNING: connection is not using a post-quantum key exchange algorithm.\r\n'
    b'Traceback (most recent call last):\n'
    b'  File "/opt/mcp-suite/deploy/windows_receiver.py", line 93, in <module>\n'
    b"    if __name__=='__main__':main()\n"
    b'  File "/opt/mcp-suite/deploy/windows_receiver.py", line 64, in main\n'
    b'    _rotation.ensure_capacity(ROOT,JOBS.stat().st_size)\n'
    b'  File "/var/lib/mcp-suite/jobs.json.bak.windows.rotation.py", line 74, in ensure_capacity\n'
    b"    if free<required:raise ValueError(f'capacity gate: free={free} required={required}; publication stopped before upload')\n"
    b'ValueError: capacity gate: free=2708889600 required=2823685866; publication stopped before upload\n\n')


def marker(**change):
    body = {'reason': 'capacity_gate', 'before_upload': True, 'accepted': False, 'stage': 'pre_receive',
            'expected_sha256': BASE, 'candidate_sha256': CAND, 'error': 'capacity gate: free=1 required=2'}
    body.update(change)
    body = {k: v for k, v in body.items() if v is not DROP}
    return b'** WARNING: banner\r\nRECEIVER_REFUSED ' + json.dumps(body, sort_keys=True).encode() + b'\n'


DROP = object()


def completed(code, stderr=b'', stdout=b''):
    return subprocess.CompletedProcess([], code, stdout, stderr)


# --- classification -----------------------------------------------------------------

def test_only_the_complete_structured_marker_of_this_call_is_a_refusal():
    detail = W.capacity_refusal(completed(75, marker()), BASE, CAND)
    assert detail['reason'] == 'capacity_gate' and detail['accepted'] is False


@pytest.mark.parametrize('result', [
    completed(1, OLD_RECEIVER_STDERR),                                        # proven old stack: still unknown
    completed(2, b'ValueError: capacity gate: free=1 required=2; publication stopped before upload\n'),  # no stack
    completed(1, b'  File "/var/lib/mcp-suite/jobs.json.bak.windows.rotation.py", line 84, in <module>\n'
                 b'    done=rotate_backups();space=ensure_capacity()\n'
                 b'ValueError: capacity gate: free=1 required=2; publication stopped before upload\n'),  # post-accept
    completed(255, marker()),                                                 # transport failure
    completed(1, marker()),                                                   # marker with another exit
    completed(75, b'no marker\n'),
    completed(75, marker() + marker()),                                       # two markers
    completed(75, b'RECEIVER_REFUSED {not json\n'),
    completed(75, marker(before_upload=DROP)),
    completed(75, marker(before_upload='true')),
    completed(75, marker(accepted=DROP)),
    completed(75, marker(accepted=True)),
    completed(75, marker(accepted=0)),
    completed(75, marker(stage='post_receive')),
    completed(75, marker(reason='other')),
    completed(75, marker(expected_sha256='c' * 64)),                          # another call's base
    completed(75, marker(candidate_sha256='c' * 64)),                         # another call's candidate
    completed(75, marker(candidate_sha256=DROP)),
    completed(1, b'BlockingIOError: [Errno 11]\n'),
])
def test_anything_else_is_an_unknown_outcome(result):
    assert W.capacity_refusal(result, BASE, CAND) is None


def publish_with(monkeypatch, tmp_path, result):
    candidate = tmp_path / 'c.json'
    candidate.write_text('[]', encoding='utf-8')
    monkeypatch.setattr(W.subprocess, 'run', lambda *a, **k: result)
    return W.publish_snapshot(candidate, BASE, tmp_path / 'work')


def test_publish_snapshot_raises_capacity_refused_only_for_the_marker(tmp_path, monkeypatch):
    (tmp_path / 'c.json').write_text('[]', encoding='utf-8')
    cand = W.digest(tmp_path / 'c.json')
    with pytest.raises(W.CapacityRefused):
        publish_with(monkeypatch, tmp_path, completed(75, marker(candidate_sha256=cand)))
    for unknown in (completed(1, OLD_RECEIVER_STDERR), completed(1, b'ValueError: upload hash mismatch\n')):
        with pytest.raises(RuntimeError) as other:
            publish_with(monkeypatch, tmp_path, unknown)
        assert not isinstance(other.value, W.PublishUnavailable)
    with pytest.raises(W.CASConflict):
        publish_with(monkeypatch, tmp_path, completed(1, b'ValueError: CAS mismatch\n'))


# --- receiver side --------------------------------------------------------------------

def load_receiver(monkeypatch, tmp_path, *, free, required):
    rotation = tmp_path / 'rotation.py'
    rotation.write_text('def ensure_capacity(root, current_bytes=None):\n'
                        f'    raise ValueError("capacity gate: free={free} required={required}; '
                        'publication stopped before upload")\n', encoding='utf-8')
    monkeypatch.setenv('QIUZHAO_ROTATION_MODULE', str(rotation))
    spec = importlib.util.spec_from_file_location('receiver_under_test', REPO / 'deploy' / 'windows_receiver.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / 'srv'
    root.mkdir()
    (root / 'jobs.json').write_text(json.dumps([job('x', 'A')]), encoding='utf-8')
    monkeypatch.setattr(module, 'ROOT', root)
    monkeypatch.setattr(module, 'JOBS', root / 'jobs.json')
    return module


class NoRead(io.RawIOBase):
    def readable(self):
        return True

    def readinto(self, _):
        raise AssertionError('the upload must not be read after a capacity refusal')


def test_receiver_refuses_before_reading_the_upload_with_a_marker(tmp_path, monkeypatch, capsys):
    receiver = load_receiver(monkeypatch, tmp_path, free=5, required=9)
    expected = receiver.digest(receiver.JOBS)
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', f'publish {expected} {"1" * 64}')
    monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BufferedReader(NoRead())))
    with pytest.raises(SystemExit) as stop:
        receiver.main()
    assert stop.value.code == receiver.REFUSED_EXIT == W.RECEIVER_REFUSED_EXIT
    err = capsys.readouterr().err
    detail = W.capacity_refusal(completed(stop.value.code, err.encode()), expected, '1' * 64)
    assert detail['reason'] == 'capacity_gate' and 'free=5 required=9' in detail['error']
    assert detail['before_upload'] is True and detail['accepted'] is False and detail['stage'] == 'pre_receive'
    assert W.capacity_refusal(completed(stop.value.code, err.encode()), expected, '2' * 64) is None
    assert receiver.digest(receiver.JOBS) == expected
    assert sorted(p.name for p in receiver.ROOT.iterdir()) == ['collector.lock', 'jobs.json'], \
        'no temp upload, no backup'


def test_receiver_cas_and_already_published_run_before_the_gate(tmp_path, monkeypatch, capsys):
    receiver = load_receiver(monkeypatch, tmp_path, free=5, required=9)
    current = receiver.digest(receiver.JOBS)
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', f'publish {"2" * 64} {current}')
    receiver.main()
    assert json.loads(capsys.readouterr().out)['already_published'] is True
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', f'publish {"2" * 64} {"3" * 64}')
    with pytest.raises(ValueError, match='production changed'):
        receiver.main()


# --- the day keeps going ---------------------------------------------------------------

class Refusing:
    """Wraps the harness server: the first ``count`` publish calls hit the capacity gate."""

    def __init__(self, server, count):
        self.server, self.count, self.refused = server, count, 0

    def publish(self, candidate, expected, folder, receipt=None):
        if self.count:
            self.count -= 1
            self.refused += 1
            raise W.CapacityRefused('receiver capacity gate refused before upload: {}')
        return self.server.publish(candidate, expected, folder, receipt=receipt)


def test_capacity_refusal_defers_and_later_segments_catch_up(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    original = server.sha()
    gate = Refusing(server, 2)
    monkeypatch.setattr(W, 'publish_snapshot', gate.publish)
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p1', 'p2']},
             {'mutate': add_row('y', 'Y'), 'pending': ['p2']},
             {'mutate': add_row('z', 'Z'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 3, 'collection went on after the refusals'
    assert publications(receipt) == ['deferred', 'deferred', 'published']
    assert len(receipt['refused_publications']) == 2 and not receipt.get('unconfirmed_publications')
    assert receipt['delivery']['refused_publications'] == 2
    rows = server.rows()
    assert rows['x']['job_title'] == 'B' and {'y', 'z'} <= set(rows), 'the catch-up carried every segment'
    assert server.sha() != original and code == 0 and receipt['finished'] is True


def test_refusals_until_the_end_leave_a_pending_not_finished_run(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    original = server.sha()
    gate = Refusing(server, 99)
    monkeypatch.setattr(W, 'publish_snapshot', gate.publish)
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p']},
             {'mutate': add_row('y', 'Y'), 'run_finished': True, 'pending': []}]
    code, receipt, _ = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert publications(receipt) == ['deferred', 'deferred']
    assert receipt['final_publication']['action'] == 'deferred'
    assert receipt['delivery']['publication'] == 'pending'
    assert receipt['finished'] is False and receipt['success'] is False and code == 1
    assert server.sha() == original and not receipt.get('unconfirmed_publications')
    budget = receipt['p1_budget_ledger']
    # Space freed later: the resume only publishes, with the same budget ledger.
    gate.count = 0
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 0 and receipt['publication_retry']['action'] == 'published'
    assert receipt['p1_budget_ledger']['started_epoch'] == budget['started_epoch']
    assert code == 0 and server.rows()['x']['job_title'] == 'B'


def test_an_unknown_receiver_error_still_aborts_and_stays_unconfirmed(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])

    def unknown(candidate, expected, folder, receipt=None):
        raise RuntimeError('receiver rejected publication: ValueError: upload hash mismatch')
    monkeypatch.setattr(W, 'publish_snapshot', unknown)
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p']},
             {'mutate': add_row('y', 'Y'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 1, 'an unknown outcome is not treated as a refusal'
    assert len(receipt['unconfirmed_publications']) == 1 and not receipt.get('refused_publications')
    assert receipt['error'].startswith('RuntimeError') and code == 1


def test_missing_normalize_tables_is_visible_in_the_receipt(tmp_path, monkeypatch):
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    plans = [{'mutate': set_title('x', 'B'), 'run_finished': True, 'pending': []}]
    _, receipt, _ = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert receipt['resources']['missing'] == ['qiuzhao/normalize_tables.json']
    assert receipt['delivery']['resources_missing'] == ['qiuzhao/normalize_tables.json']
    table = tmp_path / 'qiuzhao' / 'normalize_tables.json'
    table.parent.mkdir(parents=True)
    table.write_text('{}', encoding='utf-8')
    assert W.resource_check(tmp_path)['missing'] == []


def test_old_receiver_capacity_text_is_unknown_end_to_end(tmp_path, monkeypatch):
    """The pre-marker receiver's traceback (exactly as on 2026-09-28) is not trusted as a refusal."""
    server, clock, run_dir = harness(tmp_path, monkeypatch, [job('x', 'A')])
    monkeypatch.setattr(W.subprocess, 'run', lambda *a, **k: completed(1, OLD_RECEIVER_STDERR))
    monkeypatch.setattr(W, 'publish_snapshot', REAL_PUBLISH)
    plans = [{'mutate': set_title('x', 'B'), 'pending': ['p']},
             {'mutate': add_row('y', 'Y'), 'run_finished': True, 'pending': []}]
    code, receipt, calls = drive(tmp_path, monkeypatch, run_dir, clock, plans)
    assert calls['p1'] == 1 and code == 1
    assert len(receipt['unconfirmed_publications']) == 1 and not receipt.get('refused_publications')
