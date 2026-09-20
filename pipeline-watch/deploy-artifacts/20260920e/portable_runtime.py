"""Small cross-platform equivalents for collector process and file locks."""
import os
import signal
import subprocess

WINDOWS = os.name == 'nt'

# Child diagnostics are never decoded strictly. taskkill prints its message in the
# console codepage (GBK on the jingling box) while the collector runs with ``-X utf8``,
# so a strict decode raised inside ``subprocess._readerthread`` on Windows. CPython's
# Windows ``_communicate`` then hands back ``None`` instead of text
# (``stderr = stderr[0] if stderr else None``), which turned the report line
# ``result.stderr[-1000:]`` into "TypeError: 'NoneType' object is not subscriptable".
# 2026-09-20 P0: the daily chain's 18100s watchdog fired 100s after p1's own 18000s
# deadline, that TypeError escaped ``step()``, and the whole day (basic 634 new /
# 62491 refreshed + 958 p1 units) was rolled back before publication.
CHILD_TEXT = {'text': True, 'encoding': 'utf-8', 'errors': 'replace'}


def taskkill_command(pid):
    return [os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'taskkill.exe'),
            '/PID', str(pid), '/T', '/F']


def child_output(command, timeout=30):
    """Run a short diagnostic command; always return decoded text, never raise.

    ``errors='replace'`` keeps one undecodable byte from killing subprocess' reader
    thread, and the ``or ''`` fallbacks absorb the ``None`` CPython returns for a
    stream whose reader thread died anyway.
    """
    try:
        result = subprocess.run(command, capture_output=True, check=False,
                                timeout=timeout, **CHILD_TEXT)
    except (OSError, subprocess.SubprocessError) as error:
        # Same keys as the success path: callers index stdout/stderr unconditionally.
        return {'exit_code': None, 'stdout': '', 'stderr': '',
                'error': type(error).__name__ + ': ' + str(error)[:300]}
    return {'exit_code': result.returncode,
            'stdout': (result.stdout or '')[-1000:],
            'stderr': (result.stderr or '')[-1000:]}


if os.name == 'nt':
    import msvcrt
    class _Locks:
        LOCK_EX = 2
        LOCK_NB = 4
        LOCK_UN = 8
        @staticmethod
        def flock(handle, flags):
            fd = handle if isinstance(handle, int) else handle.fileno()
            os.lseek(fd, 0, os.SEEK_SET)
            if os.fstat(fd).st_size == 0:
                os.write(fd, b'0')
                os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK if flags & 8 else (msvcrt.LK_NBLCK if flags & 4 else msvcrt.LK_LOCK), 1)
    fcntl = _Locks()
else:
    import fcntl

def stop_tree(process, *, strict=True):
    report = {'pid': process.pid, 'already_exited': process.poll() is not None,
              'tree_termination_confirmed': False}
    if report['already_exited']:
        report['process_terminated'] = True
        report['cleanup_error'] = 'parent already exited; descendant termination is unverified'
        if strict:raise RuntimeError('process cleanup incomplete: '+str(report))
        return report
    try:
        if WINDOWS:
            output = child_output(taskkill_command(process.pid))
            report.update(taskkill_exit_code=output['exit_code'],
                          taskkill_stdout=output['stdout'], taskkill_stderr=output['stderr'])
            if output.get('error'):
                report['taskkill_error'] = output['error']
            report['tree_termination_confirmed'] = output['exit_code'] == 0
        else:
            os.killpg(process.pid, signal.SIGKILL)
            report['tree_termination_confirmed'] = True
    except (OSError, subprocess.TimeoutExpired) as error:
        report['tree_cleanup_error'] = type(error).__name__ + ': ' + str(error)
    if process.poll() is None:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                report['parent_kill_fallback'] = True
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired) as error:
                report['parent_cleanup_error'] = type(error).__name__ + ': ' + str(error)
    report['process_terminated'] = process.poll() is not None
    if not report['process_terminated'] or not report['tree_termination_confirmed']:
        report['cleanup_error'] = 'parent or complete process-tree termination could not be confirmed'
        # Strict callers must not continue writing shared data while a writer is alive.
        if strict:raise RuntimeError('process cleanup incomplete: ' + str(report))
    return report
