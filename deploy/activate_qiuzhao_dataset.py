#!/usr/bin/env python3
"""Controlled activation of an accepted jobs.json for the qiuzhao MCP service (server side).

The service serves the first dataset it loads and never builds a second copy in-process
(qiuzhao/tools.py); the 1.87 GB host cannot hold two. A new accepted version therefore goes
live only here:

  under the receiver's own collector.lock (so no publication can replace jobs.json between
  sampling and verification) -> sample size/mtime/sha256 -> stop mcp-suite.service, wait until
  the old PID is gone -> start it once -> one bounded warm request (<= 120 s) -> verify the
  served sha256 equals the sampled one -> re-check the file did not change -> receipt.

Modes: ``--hourly`` (cron, top of the hour; activates only a version that differs from the
last activated one, never retries a version that already failed) and ``--activate SHA256``
(manual, before a Base delivery: the file must currently be exactly that version).

A failure never touches jobs.json, never restarts again and never loops on health: it is
recorded as ``manual_attention`` and that version is skipped by later hourly runs until an
operator passes ``--retry-failed``. A busy lock is waited on for a bounded time, then the
run is deferred to the next hour. Nothing here listens on a port or runs as a daemon.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path('/var/lib/mcp-suite')
JOBS = ROOT / 'jobs.json'
RECEIVER_LOCK = ROOT / 'collector.lock'          # deploy/windows_receiver.py takes this lock
SINGLETON_LOCK = ROOT / 'dataset-activation.lock'
STATE = ROOT / 'dataset-activation.json'
RECEIPTS = ROOT / 'dataset-activation-receipts.jsonl'
UNIT = 'mcp-suite.service'
HEALTH_URL = 'http://127.0.0.1:8768/health'      # nginx maps /qiuzhao/ onto this port's root
LOCK_WAIT_SECONDS = 600
LOCK_POLL_SECONDS = 5
STOP_WAIT_SECONDS = 90
WARM_SECONDS = 120


class ActivationFailed(RuntimeError):
    pass


def now():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def sample(path=None):
    """(size, mtime_ns, sha256) of the file, read through one descriptor."""
    with open(path or JOBS, 'rb') as fh:
        st = os.fstat(fh.fileno())
        digest = hashlib.sha256()
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return {'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'sha256': digest.hexdigest()}


def load_state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_state(state):
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(temporary, STATE)


def record(receipt):
    with RECEIPTS.open('a', encoding='utf-8') as out:
        out.write(json.dumps(receipt, ensure_ascii=False) + '\n')


def systemctl(*args, timeout=120):
    return subprocess.run(['systemctl', *args], capture_output=True, text=True, timeout=timeout)


def main_pid():
    out = systemctl('show', '-p', 'MainPID', '--value', UNIT).stdout.strip()
    return int(out) if out.isdigit() else 0


def pid_alive(pid):
    return pid > 0 and Path(f'/proc/{pid}').exists()


def health_once(deadline):
    """One warm request: retries only while nothing is listening yet, bounded by ``deadline``."""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ActivationFailed('warm window of %s s elapsed without a health answer' % WARM_SECONDS)
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=remaining) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            body = error.read().decode('utf-8', 'replace')[:300]
            raise ActivationFailed(f'health answered {error.code}: {body}')
        except (urllib.error.URLError, ConnectionError) as error:
            reason = getattr(error, 'reason', error)
            if isinstance(reason, (ConnectionRefusedError, ConnectionResetError)):
                time.sleep(min(2, max(0, deadline - time.monotonic())))
                continue
            raise ActivationFailed(f'health request failed: {reason}')


def restart_and_verify(target):
    """Stop, wait for the old PID, start once, warm once, verify. Raises ActivationFailed."""
    old = main_pid()
    stopped = systemctl('stop', UNIT)
    if stopped.returncode:
        raise ActivationFailed('systemctl stop failed: ' + stopped.stderr[-300:])
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while pid_alive(old):
        if time.monotonic() > deadline:
            raise ActivationFailed(f'old PID {old} still alive {STOP_WAIT_SECONDS} s after stop')
        time.sleep(1)
    started = systemctl('start', UNIT)
    if started.returncode:
        raise ActivationFailed('systemctl start failed: ' + started.stderr[-300:])
    begun = time.monotonic()
    health = health_once(begun + WARM_SECONDS)
    served = health.get('served') or {}
    result = {'old_pid': old, 'new_pid': main_pid(), 'warm_seconds': round(time.monotonic() - begun, 1),
              'health': {k: health.get(k) for k in ('status', 'jobs', 'data_as_of', 'reload_pending')},
              'served': served}
    if health.get('status') != 'ok' or served.get('sha256') != target['sha256'] or health.get('reload_pending'):
        raise ActivationFailed('service does not serve the sampled version: ' + json.dumps(result)[:600])
    return result


def acquire(path, wait_seconds):
    handle = open(path, 'a')
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                return None
            time.sleep(LOCK_POLL_SECONDS)


def run(mode, expected_sha=None, retry_failed=False, lock_wait=LOCK_WAIT_SECONDS):
    """Returns (exit_code, receipt)."""
    receipt = {'at': now(), 'mode': mode, 'unit': UNIT, 'jobs': str(JOBS)}
    singleton = acquire(SINGLETON_LOCK, 0)
    if singleton is None:
        receipt.update(outcome='deferred', reason='another activation is running')
        record(receipt)
        return 75, receipt
    with singleton:
        lock = acquire(RECEIVER_LOCK, lock_wait)
        if lock is None:
            receipt.update(outcome='deferred', reason=f'receiver lock busy for {lock_wait} s; next hour retries')
            record(receipt)
            return 75, receipt
        with lock:
            state = load_state()
            target = sample()
            receipt['target'] = target
            active = (state.get('active') or {}).get('sha256')
            failed = state.get('failed') or {}
            if expected_sha and target['sha256'] != expected_sha:
                receipt.update(outcome='refused', reason='jobs.json is not the requested accepted version')
                record(receipt)
                return 2, receipt
            if target['sha256'] == active:
                receipt.update(outcome='unchanged', reason='already the active version; no restart')
                record(receipt)
                return 0, receipt
            if not active:
                # First run on this host: adopt what the running service already serves instead
                # of restarting it. One health read; anything else falls through to activation.
                try:
                    served = (health_once(time.monotonic() + WARM_SECONDS).get('served') or {})
                except ActivationFailed:
                    served = {}
                if served.get('sha256') == target['sha256']:
                    state['active'] = {'sha256': target['sha256'], 'size': target['size'],
                                       'mtime_ns': target['mtime_ns'], 'activated_at': now(),
                                       'mode': 'baseline_adopted'}
                    save_state(state)
                    receipt.update(outcome='baseline_adopted', reason='service already serves this version')
                    record(receipt)
                    return 0, receipt
            if failed.get('sha256') == target['sha256'] and not retry_failed:
                receipt.update(outcome='skipped_failed_version',
                               reason='this version already failed activation; needs --retry-failed')
                record(receipt)
                return 1, receipt
            state['activating'] = {'sha256': target['sha256'], 'at': receipt['at'], 'mode': mode}
            save_state(state)
            try:
                receipt['service'] = restart_and_verify(target)
                after = sample()
                if after != target:
                    raise ActivationFailed('jobs.json changed during activation despite the lock')
            except (ActivationFailed, OSError, subprocess.SubprocessError) as error:
                message = f'{type(error).__name__}: {str(error)[:600]}'
                state.pop('activating', None)
                state['failed'] = {'sha256': target['sha256'], 'at': now(), 'error': message}
                save_state(state)
                receipt.update(outcome='manual_attention', error=message,
                               note='jobs.json left as accepted; no further restart or health loop')
                record(receipt)
                return 1, receipt
            state.pop('activating', None)
            state.pop('failed', None)
            state['previous'] = state.get('active')
            state['active'] = {'sha256': target['sha256'], 'size': target['size'],
                               'mtime_ns': target['mtime_ns'], 'activated_at': now(), 'mode': mode}
            save_state(state)
            receipt.update(outcome='activated')
            record(receipt)
            return 0, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--hourly', action='store_true')
    group.add_argument('--activate', metavar='SHA256')
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--lock-wait', type=int, default=LOCK_WAIT_SECONDS)
    a = parser.parse_args(argv)
    mode = 'hourly' if a.hourly else 'manual'
    code, receipt = run(mode, expected_sha=a.activate, retry_failed=a.retry_failed, lock_wait=a.lock_wait)
    print(json.dumps(receipt, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
