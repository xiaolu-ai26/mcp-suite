"""Small cross-platform equivalents for collector process and file locks."""
import os
import signal
import subprocess

WINDOWS = os.name == 'nt'

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
            result = subprocess.run(
                [os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'taskkill.exe'),
                 '/PID', str(process.pid), '/T', '/F'], capture_output=True, text=True,
                check=False, timeout=30)
            report.update(taskkill_exit_code=result.returncode,
                          taskkill_stdout=result.stdout[-1000:], taskkill_stderr=result.stderr[-1000:])
            report['tree_termination_confirmed'] = result.returncode == 0
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
