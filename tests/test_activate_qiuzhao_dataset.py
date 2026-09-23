"""Controlled dataset activation: one restart per new accepted version, under the receiver lock."""
import fcntl
import json

import pytest

from deploy import activate_qiuzhao_dataset as A


class Service:
    """systemd + the qiuzhao health route, as the activation sees them."""

    def __init__(self, serves=None):
        self.pid = 100
        self.alive = {100}
        self.calls = []
        self.serves = serves          # sha256 the next started process will serve
        self.current = serves
        self.stuck = False

    def systemctl(self, *args, timeout=120):
        self.calls.append(args[0])
        if args[0] == 'stop':
            if not self.stuck:
                self.alive.discard(self.pid)
        if args[0] == 'start':
            self.pid += 1
            self.alive.add(self.pid)
            self.current = self.serves
        return type('R', (), {'returncode': 0, 'stdout': str(self.pid), 'stderr': ''})()

    def health(self, deadline):
        self.calls.append('health')
        return {'status': 'ok', 'jobs': 3, 'data_as_of': 'x', 'reload_pending': False,
                'served': {'sha256': self.current}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ('ROOT', 'JOBS', 'RECEIVER_LOCK', 'SINGLETON_LOCK', 'STATE', 'RECEIPTS'):
        pass
    monkeypatch.setattr(A, 'ROOT', tmp_path)
    monkeypatch.setattr(A, 'JOBS', tmp_path / 'jobs.json')
    monkeypatch.setattr(A, 'RECEIVER_LOCK', tmp_path / 'collector.lock')
    monkeypatch.setattr(A, 'SINGLETON_LOCK', tmp_path / 'dataset-activation.lock')
    monkeypatch.setattr(A, 'STATE', tmp_path / 'dataset-activation.json')
    monkeypatch.setattr(A, 'RECEIPTS', tmp_path / 'receipts.jsonl')
    monkeypatch.setattr(A, 'LOCK_POLL_SECONDS', 0.05)
    monkeypatch.setattr(A.time, 'sleep', lambda s: None)
    service = Service()
    monkeypatch.setattr(A, 'systemctl', service.systemctl)
    monkeypatch.setattr(A, 'main_pid', lambda: service.pid)
    monkeypatch.setattr(A, 'pid_alive', lambda pid: pid in service.alive)
    monkeypatch.setattr(A, 'health_once', service.health)
    return tmp_path, service


def write(path, text):
    path.write_text(text, encoding='utf-8')
    return A.sample(path)['sha256']


def test_first_run_adopts_what_is_already_served_without_restarting(env):
    root, service = env
    sha = write(root / 'jobs.json', '[1]')
    service.current = sha
    code, receipt = A.run('hourly')
    assert code == 0 and receipt['outcome'] == 'baseline_adopted'
    assert service.calls == ['health'], 'nothing may be restarted'
    assert json.loads((root / 'dataset-activation.json').read_text())['active']['sha256'] == sha


def test_unchanged_file_is_a_no_op_without_health_or_restart(env):
    root, service = env
    sha = write(root / 'jobs.json', '[1]')
    service.current = sha
    A.run('hourly')
    service.calls.clear()
    code, receipt = A.run('hourly')
    assert code == 0 and receipt['outcome'] == 'unchanged' and service.calls == []


def test_new_version_restarts_once_waits_for_the_old_pid_and_verifies_the_served_hash(env):
    root, service = env
    old = write(root / 'jobs.json', '[1]')
    service.current = old
    A.run('hourly')
    new = write(root / 'jobs.json', '[1, 2]')
    service.serves = new
    service.calls.clear()
    code, receipt = A.run('hourly')
    assert code == 0 and receipt['outcome'] == 'activated'
    assert service.calls == ['stop', 'start', 'health'], 'exactly one restart and one warm request'
    assert receipt['service']['old_pid'] == 100 and receipt['service']['new_pid'] == 101
    state = json.loads((root / 'dataset-activation.json').read_text())
    assert state['active']['sha256'] == new and state['previous']['sha256'] == old
    assert 'activating' not in state


def test_wrong_served_version_needs_a_human_and_is_not_retried_hourly(env):
    root, service = env
    service.current = write(root / 'jobs.json', '[1]')
    A.run('hourly')
    new = write(root / 'jobs.json', '[1, 2]')
    service.serves = 'something-else'
    code, receipt = A.run('hourly')
    assert code == 1 and receipt['outcome'] == 'manual_attention'
    assert A.sample(root / 'jobs.json')['sha256'] == new, 'the accepted file is never rolled back'
    service.calls.clear()
    code, receipt = A.run('hourly')
    assert receipt['outcome'] == 'skipped_failed_version' and service.calls == []
    service.serves = new
    code, receipt = A.run('manual', expected_sha=new, retry_failed=True)
    assert code == 0 and receipt['outcome'] == 'activated'


def test_old_pid_that_will_not_exit_stops_before_any_start(env):
    root, service = env
    service.current = write(root / 'jobs.json', '[1]')
    A.run('hourly')
    write(root / 'jobs.json', '[1, 2]')
    service.stuck = True
    clock = iter(range(0, 10000, 30))
    A.time.monotonic = lambda: next(clock)
    try:
        code, receipt = A.run('hourly')
    finally:
        import time as _time
        A.time.monotonic = _time.monotonic
    assert code == 1 and 'still alive' in receipt['error'] and 'start' not in service.calls


def test_manual_activation_refuses_a_file_that_is_not_the_requested_version(env):
    root, service = env
    write(root / 'jobs.json', '[1]')
    code, receipt = A.run('manual', expected_sha='0' * 64)
    assert code == 2 and receipt['outcome'] == 'refused' and service.calls == []


def test_busy_receiver_lock_defers_after_a_bounded_wait(env):
    root, service = env
    write(root / 'jobs.json', '[1]')
    holder = open(root / 'collector.lock', 'a')
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)  # a publication in progress
    try:
        code, receipt = A.run('hourly', lock_wait=0)
    finally:
        holder.close()
    assert code == 75 and receipt['outcome'] == 'deferred' and service.calls == []


def test_second_activation_does_not_run_concurrently(env):
    root, service = env
    write(root / 'jobs.json', '[1]')
    holder = open(root / 'dataset-activation.lock', 'a')
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        code, receipt = A.run('hourly')
    finally:
        holder.close()
    assert code == 75 and 'another activation' in receipt['reason']


def test_file_changing_during_activation_is_reported_not_trusted(env, monkeypatch):
    root, service = env
    service.current = write(root / 'jobs.json', '[1]')
    A.run('hourly')
    new = write(root / 'jobs.json', '[1, 2]')
    service.serves = new
    real = service.systemctl

    def sneaky(*args, **kwargs):
        if args[0] == 'start':
            (root / 'jobs.json').write_text('[9]', encoding='utf-8')
        return real(*args, **kwargs)

    monkeypatch.setattr(A, 'systemctl', sneaky)
    code, receipt = A.run('hourly')
    assert code == 1 and 'changed during activation' in receipt['error']
