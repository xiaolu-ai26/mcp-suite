"""Windows flock translation (2026-09-24: 12 p1 units failed on the shared browser lock).

The fake CRT reproduces what msvcrt.locking did on the collector (verified there with two
processes on a scratch file): a region held by another handle -> OSError errno EACCES
(PermissionError, winerror None); unlocking a region that is not locked -> the same errno.
"""
import errno
import os
import sys
import time

import pytest

from qiuzhao.collector import portable_runtime as RT


class FakeCRT:
    LK_UNLCK, LK_LOCK, LK_NBLCK = 0, 1, 2

    def __init__(self):
        self.owner = {}  # path -> fd holding byte 0
        self.calls = []

    def _key(self, fd):
        st = os.fstat(fd)
        return (st.st_dev, st.st_ino)

    def locking(self, fd, mode, nbytes):
        self.calls.append(mode)
        key = self._key(fd)
        holder = self.owner.get(key)
        if mode == self.LK_UNLCK:
            if holder != fd:
                raise OSError(errno.EACCES, 'Permission denied')
            del self.owner[key]
        elif holder is not None and holder != fd:
            if mode == self.LK_NBLCK:
                raise OSError(errno.EACCES, 'Permission denied')
            raise OSError(errno.EDEADLK, 'Resource deadlock avoided')
        else:
            self.owner[key] = fd


@pytest.fixture
def locks(tmp_path):
    crt = FakeCRT()
    return RT.WindowsLocks(crt), crt, tmp_path / 'browser.lock'


def test_contention_on_a_non_blocking_lock_is_busy_not_permission(locks):
    flock, crt, path = locks
    with path.open('a') as holder, path.open('a') as waiter:
        flock.flock(holder, flock.LOCK_EX | flock.LOCK_NB)
        with pytest.raises(BlockingIOError) as caught:
            flock.flock(waiter, flock.LOCK_EX | flock.LOCK_NB)
        assert not isinstance(caught.value, PermissionError)
        assert caught.value.errno == errno.EWOULDBLOCK
        assert isinstance(caught.value.__cause__, PermissionError)  # the CRT's original error is kept


def test_release_lets_the_other_handle_acquire(locks):
    flock, crt, path = locks
    with path.open('a') as first, path.open('a') as second:
        flock.flock(first, flock.LOCK_EX | flock.LOCK_NB)
        flock.flock(first, flock.LOCK_UN)
        flock.flock(second, flock.LOCK_EX | flock.LOCK_NB)
        assert crt.owner and list(crt.owner.values()) == [second.fileno()]


def test_unlocking_an_unlocked_region_still_raises_permission_error(locks):
    flock, crt, path = locks
    with path.open('a') as handle:
        with pytest.raises(PermissionError):
            flock.flock(handle, flock.LOCK_UN)


def test_blocking_lock_that_gives_up_is_not_translated(locks):
    flock, crt, path = locks
    with path.open('a') as holder, path.open('a') as waiter:
        flock.flock(holder, flock.LOCK_EX | flock.LOCK_NB)
        with pytest.raises(OSError) as caught:
            flock.flock(waiter, flock.LOCK_EX)
        assert caught.value.errno == errno.EDEADLK and not isinstance(caught.value, BlockingIOError)


def test_other_errnos_on_a_non_blocking_lock_pass_through(tmp_path):
    class BadHandleCRT(FakeCRT):
        def locking(self, fd, mode, nbytes):
            raise OSError(errno.EBADF, 'Bad file descriptor')

    flock = RT.WindowsLocks(BadHandleCRT())
    with (tmp_path / 'x.lock').open('a') as handle:
        with pytest.raises(OSError) as caught:
            flock.flock(handle, flock.LOCK_EX | flock.LOCK_NB)
    assert caught.value.errno == errno.EBADF and not isinstance(caught.value, BlockingIOError)


def wait_like_feishu(flock, handle, deadline_seconds, clock, sleep):
    """p1_feishu_public.collect's bounded wait, verbatim in shape."""
    deadline = clock() + deadline_seconds
    while True:
        try:
            flock.flock(handle, flock.LOCK_EX | flock.LOCK_NB)
            return 'acquired'
        except BlockingIOError:
            if clock() > deadline:
                raise TimeoutError('single public careers browser is busy')
            sleep(1)


def test_feishu_wait_now_waits_for_the_browser_and_then_gets_it(locks):
    flock, crt, path = locks
    now = [0.0]
    with path.open('a') as holder, path.open('a') as waiter:
        flock.flock(holder, flock.LOCK_EX | flock.LOCK_NB)

        def sleep(seconds):
            now[0] += seconds
            if now[0] >= 5:  # the other unit finishes its browser work
                flock.flock(holder, flock.LOCK_UN)

        assert wait_like_feishu(flock, waiter, 120, lambda: now[0], sleep) == 'acquired'
        assert now[0] == 5


def test_feishu_wait_is_bounded_when_the_browser_never_frees(locks):
    flock, crt, path = locks
    now = [0.0]
    with path.open('a') as holder, path.open('a') as waiter:
        flock.flock(holder, flock.LOCK_EX | flock.LOCK_NB)
        with pytest.raises(TimeoutError, match='browser is busy'):
            wait_like_feishu(flock, waiter, 120, lambda: now[0],
                             lambda s: now.__setitem__(0, now[0] + s))
        assert 120 < now[0] <= 122


@pytest.mark.skipif(os.name == 'nt' or getattr(os, 'geteuid', lambda: 0)() == 0,
                    reason='needs POSIX permissions and a non-root user')
def test_a_real_permission_problem_is_not_turned_into_busy(tmp_path):
    locked_dir = tmp_path / 'locked'
    locked_dir.mkdir()
    locked_dir.chmod(0)
    try:
        with pytest.raises(PermissionError):
            with (locked_dir / 'browser.lock').open('a') as handle:
                RT.WindowsLocks(FakeCRT()).flock(handle, 6)
    finally:
        locked_dir.chmod(0o755)


@pytest.mark.skipif(os.name != 'nt', reason='real msvcrt only on Windows')
def test_real_msvcrt_contention_maps_to_blocking_io(tmp_path):
    path = tmp_path / 'real.lock'
    with path.open('a') as holder, path.open('a') as waiter:
        RT.fcntl.flock(holder, RT.fcntl.LOCK_EX | RT.fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            RT.fcntl.flock(waiter, RT.fcntl.LOCK_EX | RT.fcntl.LOCK_NB)
        RT.fcntl.flock(holder, RT.fcntl.LOCK_UN)
        RT.fcntl.flock(waiter, RT.fcntl.LOCK_EX | RT.fcntl.LOCK_NB)
        RT.fcntl.flock(waiter, RT.fcntl.LOCK_UN)
        with pytest.raises(PermissionError):
            RT.fcntl.flock(waiter, RT.fcntl.LOCK_UN)
