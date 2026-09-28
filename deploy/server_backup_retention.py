"""Bounded retention of the receiver's gzip backups: archive -> verify -> exact unlink.

The live rotation (deploy/windows_receiver_rotation.py) compresses every raw backup but
never removes a gzip, so the server filled up and the capacity gate refused every
publication from 2026-09-25 03:36 on. This tool keeps those gzips inside an explicit
budget without touching the gate formula. It generalises the reviewed one-off
2026-09-24 archive (archive -> local verify -> identity re-check -> exact unlink):

* only names ``jobs.json.bak.windows.<YYYYmmddTHHMMSS>.gz`` are ever candidates; raw
  backups (R0 and the rotation's newest two), ``jobs.json``, receipts, the rotation module
  and anything in flight are outside it by construction; the newest ``keep_newest_gz``
  gzips and every ``--protect`` name are never selected;
* selection is oldest first, only while the server is below ``gate + margin`` free or the
  gzips exceed ``gz_budget_bytes``, and at most ``max_files`` / ``max_bytes`` per run;
* ``--plan`` (the default) only reads; ``--apply`` needs ``--expect-plan`` equal to the
  reviewed plan's hash, re-reads the server and refuses if the candidates changed;
* each file: server stat+sha256 -> streamed to the archive dir -> local sha256 equals the
  server's, ``gzip -t``, and the decompressed sha256/bytes equal the rotation receipt's
  record of the original -> durable receipt -> under the receiver's ``collector.lock``
  the same path is re-checked (regular, same size/inode/sha256, still not among the newest
  gzips) and unlinked. Any failure stops the run with the source in place; a delete whose
  outcome the transport lost is ``delete_unknown`` and is resolved by evidence next time.

It runs on the Mac (the only place with room for the archive), needs the Mac awake and
the server reachable, and is not a guarantee by being configured: each run's receipt is
the evidence.
"""
import argparse
import datetime as dt
import fcntl  # the tool runs on the Mac (POSIX); the server side runs the programs below
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


GZ_NAME = re.compile(r'^jobs\.json\.bak\.windows\.\d{8}T\d{6}\.gz$')
IN_FLIGHT = re.compile(r'^(\.windows-jobs\..*|jobs\.json\.bak\.windows\.\d{8}T\d{6}\.gz\.tmp\..*)$')
UPLOAD_LIMIT = 1024 ** 3  # the receiver's LIMIT; the gate is 2*jobs + UPLOAD_LIMIT + 256 MiB
GATE_EXTRA = 256 * 1024 ** 2
# Daily budget: every accepted publication leaves one more gzip behind (the rotation keeps
# the newest two raw copies and compresses older ones, never deleting a gzip). 2026-09-24
# accepted 30 versions in one day, so the margin above the gate is one such day of gzips
# (daily_publications x the newest gzip's size x 1.25) unless --margin-bytes is given.
DEFAULTS = {'keep_newest_gz': 8, 'gz_budget_bytes': 2 * 1024 ** 3, 'margin_bytes': None,
            'daily_publications': 30, 'max_files': 40, 'max_bytes': 6 * 1024 ** 3}
EXIT_NEEDS_MORE_SPACE = 3
LOCAL_RESERVE = 1024 ** 3  # never fill the archive disk below 1 GiB free


class RetentionError(RuntimeError):
    pass


def now():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def gate_required(jobs_bytes):
    return 2 * jobs_bytes + UPLOAD_LIMIT + GATE_EXTRA


# --- remote side (small read/delete programs run by python3 on the server) -------------

LIST_PROGRAM = r'''
import json, os, shutil, stat, sys
root = sys.argv[1]
entries = []
for name in sorted(os.listdir(root)):
    st = os.lstat(os.path.join(root, name))
    entries.append({"name": name, "regular": stat.S_ISREG(st.st_mode), "bytes": st.st_size,
                    "inode": st.st_ino, "mtime_ns": st.st_mtime_ns, "nlink": st.st_nlink})
sources = {}
path = os.path.join(root, "jobs.json.bak.windows.rotation-receipts.jsonl")
if os.path.isfile(path):
    for line in open(path, encoding="utf-8"):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if item.get("status") == "rotated" and item.get("gzip_path") and item.get("source_sha256"):
            sources[os.path.basename(item["gzip_path"])] = {"sha256": item["source_sha256"],
                                                            "bytes": item.get("source_bytes"),
                                                            "gzip_sha256": item.get("gzip_sha256")}
print(json.dumps({"entries": entries, "free": shutil.disk_usage(root).free, "sources": sources}))
'''

IDENTITY_PROGRAM = r'''
import hashlib, json, os, stat, sys
path = sys.argv[1]
st = os.lstat(path)
h = hashlib.sha256()
with open(path, "rb") as f:
    for b in iter(lambda: f.read(1 << 20), b""):
        h.update(b)
print(json.dumps({"regular": stat.S_ISREG(st.st_mode), "bytes": st.st_size, "inode": st.st_ino,
                  "mtime_ns": st.st_mtime_ns, "sha256": h.hexdigest()}))
'''

# argv: root name size inode sha256 keep_newest lock_wait_seconds
DELETE_PROGRAM = r'''
import fcntl, hashlib, json, os, re, shutil, stat, sys, time
root, name, size, inode, sha, keep, wait = sys.argv[1:8]
pattern = re.compile(r"^jobs\.json\.bak\.windows\.\d{8}T\d{6}\.gz$")
if not pattern.fullmatch(name) or "/" in name:
    raise SystemExit("refused: not a gzip backup name")
path = os.path.join(root, name)
with open(os.path.join(root, "collector.lock"), "a") as lock:
    deadline = time.time() + int(wait)
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.time() > deadline:
                raise SystemExit("refused: collector.lock busy")
            time.sleep(2)
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode) or st.st_size != int(size) or st.st_ino != int(inode):
        raise SystemExit("refused: identity changed")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    if h.hexdigest() != sha:
        raise SystemExit("refused: content changed")
    newer = [n for n in os.listdir(root) if pattern.fullmatch(n) and n > name]
    if len(newer) < int(keep):
        raise SystemExit("refused: would leave fewer than the newest gzips")
    if st.st_nlink != 1:
        raise SystemExit("refused: file has other hard links")
    before = shutil.disk_usage(root).free
    print("UNLINKING", flush=True)
    os.unlink(path)
    fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    if os.path.lexists(path):
        raise SystemExit("unknown: still present after unlink")
    print(json.dumps({"deleted": name, "free_before": before, "free_after": shutil.disk_usage(root).free}))
'''


class Server:
    """Runs the programs above through ``ssh`` (argv prefix); tests pass a local shell."""

    def __init__(self, ssh, root, timeout=1800):
        self.ssh, self.root, self.timeout = list(ssh), root, timeout

    def _python(self, program, *args):
        return ' '.join(['python3', '-c', shlex.quote(program), *map(shlex.quote, map(str, args))])

    def run(self, program, *args):
        done = subprocess.run(self.ssh + [self._python(program, *args)], capture_output=True, text=True,
                              timeout=self.timeout)
        return done

    def json(self, program, *args):
        done = self.run(program, *args)
        if done.returncode:
            raise RetentionError('remote rc=%s: %s' % (done.returncode, (done.stderr or done.stdout)[-400:]))
        return json.loads(done.stdout)

    def listing(self):
        return self.json(LIST_PROGRAM, self.root)

    def identity(self, name):
        return self.json(IDENTITY_PROGRAM, os.path.join(self.root, name))

    def stream(self, name, out):
        command = 'cat -- ' + shlex.quote(os.path.join(self.root, name))
        done = subprocess.run(self.ssh + [command], stdout=out, stderr=subprocess.PIPE, timeout=self.timeout)
        if done.returncode:
            raise RetentionError('stream rc=%s: %s' % (done.returncode, done.stderr.decode(errors='replace')[-400:]))

    def delete(self, item, keep, wait=120):
        return self.run(DELETE_PROGRAM, self.root, item['name'], item['bytes'], item['inode'], item['sha256'],
                        keep, wait)


# --- planning (pure) ------------------------------------------------------------------

SHA256 = re.compile(r'^[0-9a-f]{64}$')


def plan(listing, *, protect=(), protect_sha=(), allow_protect_sha_absent=False, **policy):
    """Candidates oldest first. ``protect`` are exact server names (unknown names are an error);
    ``protect_sha`` are versions (working baseline, served, Base, their rollbacks) whose gzip,
    identified by the rotation receipt's original sha256, is never selected."""
    policy = {**DEFAULTS, **{k: v for k, v in policy.items() if v is not None}}
    entries = {e['name']: e for e in listing['entries']}
    if 'jobs.json' not in entries:
        raise RetentionError('server listing has no jobs.json')
    unknown = sorted(set(protect) - set(entries))
    if unknown:
        raise RetentionError('--protect names not on the server: ' + ', '.join(unknown))
    bad = [sha for sha in protect_sha if not SHA256.fullmatch(sha)]
    if bad:
        raise RetentionError('--protect-sha must be a full lowercase sha256: ' + ', '.join(bad))
    sources = listing.get('sources', {})
    in_flight = sorted(n for n in entries if IN_FLIGHT.fullmatch(n))
    gz = sorted((e for e in entries.values() if GZ_NAME.fullmatch(e['name'])), key=lambda e: e['name'])
    irregular = [e['name'] for e in gz if not e['regular']]
    linked = [e['name'] for e in gz if e.get('nlink', 1) != 1]
    keep_newest = {e['name'] for e in gz[-policy['keep_newest_gz']:]} if policy['keep_newest_gz'] else set()
    by_version = {sources[e['name']]['sha256']: e['name'] for e in gz if e['name'] in sources}
    version_protected = {sha: by_version.get(sha) for sha in protect_sha}
    absent = sorted(sha for sha, name in version_protected.items() if not name)
    if absent and not allow_protect_sha_absent:
        # A version whose rollback copy is jobs.json itself or a raw backup has no gzip; saying so
        # must be deliberate (--allow-protect-sha-absent), a typo must not pass silently.
        raise RetentionError('--protect-sha with no gzip on the server: ' + ', '.join(absent))
    protected = sorted(keep_newest | set(protect) | {n for n in version_protected.values() if n})
    required = gate_required(entries['jobs.json']['bytes'])
    newest_gz = gz[-1]['bytes'] if gz else 0
    margin = policy['margin_bytes'] if policy['margin_bytes'] is not None else \
        int(policy['daily_publications'] * newest_gz * 1.25)
    target = required + margin
    free = listing['free']
    gz_total = sum(e['bytes'] for e in gz)
    candidates, freed, capped = [], 0, None
    for e in gz:
        if e['name'] in protected or not e['regular'] or e.get('nlink', 1) != 1:
            continue
        if free + freed >= target and gz_total - freed <= policy['gz_budget_bytes']:
            break
        if len(candidates) >= policy['max_files'] or freed + e['bytes'] > policy['max_bytes']:
            capped = 'max_files' if len(candidates) >= policy['max_files'] else 'max_bytes'
            break
        source = sources.get(e['name'])
        candidates.append({'name': e['name'], 'bytes': e['bytes'], 'inode': e['inode'], 'mtime_ns': e['mtime_ns'],
                           'original_sha256': (source or {}).get('sha256'),
                           'original_bytes': (source or {}).get('bytes'),
                           'gzip_sha256': (source or {}).get('gzip_sha256')})
        freed += e['bytes']
    identity = [[c['name'], c['bytes'], c['inode'], c['mtime_ns']] for c in candidates]
    return {'policy': policy, 'protected': protected,
            'protected_versions': {sha: name or 'no gzip on the server (raw backup, jobs.json or already gone)'
                                   for sha, name in version_protected.items()},
            'in_flight': in_flight, 'irregular_gz': irregular, 'hard_linked_gz': linked,
            'jobs_bytes': entries['jobs.json']['bytes'], 'free': free, 'gate_required': required,
            'margin_bytes': margin, 'target_free': target, 'gz_count': len(gz), 'gz_bytes': gz_total,
            'candidates': candidates, 'expected_freed': freed, 'projected_free': free + freed,
            'projected_gz_bytes': gz_total - freed, 'capped_by': capped,
            'meets_target': free + freed >= target,
            'plan_sha256': hashlib.sha256(json.dumps(identity).encode()).hexdigest()}


# --- durability -------------------------------------------------------------------------

def full_sync(fd):
    """Data on stable storage: F_FULLFSYNC where the platform has it (macOS), else fsync."""
    if hasattr(fcntl, 'F_FULLFSYNC'):
        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        full_sync(fd)
    finally:
        os.close(fd)


def save(path, receipt):
    path = Path(path)
    tmp = Path(str(path) + '.tmp')
    with tmp.open('w', encoding='utf-8') as out:
        json.dump(receipt, out, ensure_ascii=False, indent=1)
        out.flush()
        full_sync(out.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    sync_dir(path.parent)


# --- apply --------------------------------------------------------------------------

def verify_original(h_sha, size, original_sha, original_bytes):
    if not original_sha:
        return 'no rotation receipt records the original of this gzip; not deleting unverifiable content'
    if h_sha != original_sha or (original_bytes is not None and size != original_bytes):
        return 'content differs from the rotation receipt'
    return None


def verify_archive(path, server_sha, original_sha, original_bytes):
    if sha_file(path) != server_sha:
        return 'archive sha256 differs from the server file'
    if subprocess.run(['gzip', '-t', str(path)], capture_output=True).returncode:
        return 'gzip -t failed'
    h, size = hashlib.sha256(), 0
    with gzip.open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1 << 20), b''):
            h.update(chunk)
            size += len(chunk)
    return verify_original(h.hexdigest(), size, original_sha, original_bytes)


def reusable_original(reuse_dirs, original_sha, original_bytes):
    """A local uncompressed copy named ``<sha>.jobs.json`` whose own sha256/bytes match."""
    if not original_sha:
        return None
    for folder in reuse_dirs:
        path = Path(folder) / (original_sha + '.jobs.json')
        if path.is_file() and not path.is_symlink() and \
                verify_original(sha_file(path), path.stat().st_size, original_sha, original_bytes) is None:
            return path
    return None


def ensure_local_space(folder, need):
    free = shutil.disk_usage(folder).free
    if free < need + LOCAL_RESERVE:
        raise RetentionError('local archive disk has %d bytes free, needs %d + %d reserve' % (free, need, LOCAL_RESERVE))


def independent_copy(source, target):
    """A copy with its own inode: an APFS clone (copy-on-write) when possible, else a byte copy."""
    target.unlink(missing_ok=True)
    cloned = subprocess.run(['cp', '-c', str(source), str(target)], capture_output=True)
    if cloned.returncode:
        target.unlink(missing_ok=True)
        shutil.copyfile(source, target)


def secure_archive(server, candidate, ident, archive_dir, reuse_dirs):
    """A durable, verified recovery copy in ``archive_dir``; returns (path, kind)."""
    final = archive_dir / candidate['name']
    if final.exists():
        if verify_archive(final, ident['sha256'], candidate['original_sha256'], candidate['original_bytes']):
            raise RetentionError(candidate['name'] + ': a different archive already exists; source kept')
        return final, 'transferred_gzip'
    original = archive_dir / (candidate['name'] + '.original.jobs.json')
    # Reuse only when the rotation receipt proves this server gzip is the compression of that
    # original: the receipt's gzip_sha256 must equal the sha256 just read from the server.
    proven = bool(candidate.get('gzip_sha256')) and candidate['gzip_sha256'] == ident['sha256']
    source = None
    if proven and not original.exists():
        source = reusable_original(reuse_dirs, candidate['original_sha256'], candidate['original_bytes'])
    if source:
        ensure_local_space(archive_dir, source.stat().st_size)
        tmp = archive_dir / (original.name + '.tmp')
        independent_copy(source, tmp)
        with tmp.open('rb') as copied:
            full_sync(copied.fileno())
        problem = verify_original(sha_file(tmp), tmp.stat().st_size,
                                  candidate['original_sha256'], candidate['original_bytes'])
        if problem:
            tmp.unlink(missing_ok=True)
            raise RetentionError(candidate['name'] + ': copied original does not verify: ' + problem)
        os.chmod(tmp, 0o400)
        os.replace(tmp, original)
        sync_dir(archive_dir)
    if original.exists():
        if not proven:
            raise RetentionError(candidate['name'] + ': an original is archived but the server gzip is not proven '
                                 'to be its compression; source kept')
        problem = verify_original(sha_file(original), original.stat().st_size,
                                  candidate['original_sha256'], candidate['original_bytes'])
        if problem:
            raise RetentionError(candidate['name'] + ': archived original does not verify: ' + problem)
        return original, 'copied_original'
    ensure_local_space(archive_dir, ident['bytes'])
    partial = archive_dir / (candidate['name'] + '.partial')
    with partial.open('wb') as out:
        server.stream(candidate['name'], out)
        out.flush()
        full_sync(out.fileno())
    problem = verify_archive(partial, ident['sha256'], candidate['original_sha256'], candidate['original_bytes'])
    if problem:
        raise RetentionError(candidate['name'] + ': ' + problem + '; source kept')
    os.replace(partial, final)
    os.chmod(final, 0o600)
    sync_dir(archive_dir)
    problem = verify_archive(final, ident['sha256'], candidate['original_sha256'], candidate['original_bytes'])
    if problem:
        raise RetentionError(candidate['name'] + ': archive no longer verifies: ' + problem)
    return final, 'transferred_gzip'


def apply(server, archive_dir, receipt_path, expected_plan, *, protect=(), protect_sha=(), reuse_dirs=(),
          allow_protect_sha_absent=False, **policy):
    """Returns the receipt; the last run's ``outcome`` is target_met / needs_more_space / error."""
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = Path(receipt_path)
    with open(str(receipt_path) + '.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RetentionError('another retention run holds the lock')
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {'items': {}, 'runs': []}
        run = {'started_at': now(), 'expected_plan': expected_plan, 'outcome': 'running'}
        receipt['runs'].append(run)
        save(receipt_path, receipt)
        try:
            resolve_unknown(server, receipt, receipt_path)
            current = plan(server.listing(), protect=protect, protect_sha=protect_sha,
                           allow_protect_sha_absent=allow_protect_sha_absent, **policy)
            run['plan'] = {k: current[k] for k in ('plan_sha256', 'free', 'gate_required', 'margin_bytes',
                                                   'target_free', 'expected_freed', 'projected_free',
                                                   'meets_target', 'capped_by', 'protected', 'protected_versions',
                                                   'in_flight')}
            if current['in_flight']:
                raise RetentionError('upload or rotation in flight: ' + ', '.join(current['in_flight']))
            if current['plan_sha256'] != expected_plan:
                raise RetentionError('server candidates changed since the reviewed plan (%s != %s)'
                                     % (current['plan_sha256'], expected_plan))
            for candidate in current['candidates']:
                item = receipt['items'].setdefault(candidate['name'], {'status': 'pending'})
                if item['status'] == 'deleted':
                    continue
                ident = server.identity(candidate['name'])
                if not ident['regular'] or [ident['bytes'], ident['inode'], ident['mtime_ns']] != \
                        [candidate['bytes'], candidate['inode'], candidate['mtime_ns']]:
                    raise RetentionError(candidate['name'] + ': identity changed since planning; source kept')
                item.update(name=candidate['name'], bytes=ident['bytes'], inode=ident['inode'], sha256=ident['sha256'],
                            original_sha256=candidate['original_sha256'], checked_at=now())
                try:
                    path, kind = secure_archive(server, candidate, ident, archive_dir, reuse_dirs)
                except RetentionError as error:
                    item.update(status='verify_failed', error=str(error)[:300])
                    save(receipt_path, receipt)
                    raise
                # The copy, its directory entry and this receipt are on stable storage before
                # anything is removed on the server.
                item.update(status='archived', archive=str(path), archive_kind=kind, archived_at=now())
                save(receipt_path, receipt)
                delete(server, item, receipt, receipt_path, current['policy']['keep_newest_gz'])
            after = server.listing()
            free_after = after['free']
            run.update(free_after=free_after, finished_at=now(),
                       deleted_this_run=[c['name'] for c in current['candidates']
                                         if receipt['items'].get(c['name'], {}).get('status') == 'deleted'])
            run['outcome'] = 'target_met' if free_after >= current['target_free'] else 'needs_more_space'
        except BaseException as error:
            run.update(outcome='error', error=type(error).__name__ + ': ' + str(error)[:500], finished_at=now())
            save(receipt_path, receipt)
            raise
        save(receipt_path, receipt)
        return receipt


def delete(server, item, receipt, receipt_path, keep):
    item['status'] = 'deleting'
    save(receipt_path, receipt)
    done = server.delete(item, keep)
    output = (done.stderr or '') + (done.stdout or '')
    if done.returncode == 0:
        result = json.loads(done.stdout.splitlines()[-1])
        item.update(status='deleted', deleted_at=now(), free_before=result['free_before'],
                    free_after=result['free_after'])
        save(receipt_path, receipt)
        return
    refused_before_unlink = (done.returncode != 255 and 'UNLINKING' not in (done.stdout or '')
                             and (done.stderr or '').strip().startswith('refused:'))
    if refused_before_unlink:
        item.update(status='archived', delete_refused=(done.stderr or '')[-300:])
        save(receipt_path, receipt)
        raise RetentionError(item['name'] + ': server refused the delete: ' + item['delete_refused'])
    # Transport lost, or anything after the unlink started: resolved from evidence next run.
    item.update(status='delete_unknown', error=output[-300:])
    save(receipt_path, receipt)
    raise RetentionError(item['name'] + ': delete outcome unknown (rc=%s)' % done.returncode)


def resolve_unknown(server, receipt, receipt_path):
    """A delete whose answer was lost: absent now -> deleted; same identity -> archived again."""
    names = {e['name']: e for e in server.listing()['entries']}
    for name, item in receipt['items'].items():
        if item['status'] not in ('delete_unknown', 'deleting'):
            continue
        present = names.get(name)
        if present is None:
            item.update(status='deleted', deleted_at=now(), resolved='absent on the server after an unknown delete')
        elif [present['bytes'], present['inode']] == [item.get('bytes'), item.get('inode')]:
            item.update(status='archived', resolved='still present with the same identity')
        else:
            raise RetentionError(name + ': a different file now has this name; resolve by hand')
        save(receipt_path, receipt)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--ssh', type=json.loads, required=True, help='JSON argv prefix, e.g. ["ssh", "-o", ..., "user@host"]')
    ap.add_argument('--server-dir', default='/var/lib/mcp-suite')
    ap.add_argument('--archive-dir', type=Path, help='required with --apply')
    ap.add_argument('--receipt', type=Path)
    ap.add_argument('--protect', action='append', default=[], help='exact server name; unknown names are an error')
    ap.add_argument('--protect-sha', action='append', default=[],
                    help='version sha256 whose rollback gzip must stay (working baseline, served, Base, ...)')
    ap.add_argument('--allow-protect-sha-absent', action='store_true',
                    help='a --protect-sha may have no gzip (its rollback copy is jobs.json or a raw backup)')
    ap.add_argument('--reuse-dir', action='append', default=[], type=Path,
                    help='local folder of verified <sha>.jobs.json originals, copied (not linked) instead of transferring')
    for key, value in DEFAULTS.items():
        ap.add_argument('--' + key.replace('_', '-'), type=int, default=value)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true', help='default: read only')
    mode.add_argument('--apply', action='store_true')
    ap.add_argument('--expect-plan')
    a = ap.parse_args(argv)
    policy = {key: getattr(a, key) for key in DEFAULTS}
    server = Server(a.ssh, a.server_dir)
    if not a.apply:
        print(json.dumps(plan(server.listing(), protect=a.protect, protect_sha=a.protect_sha,
                              allow_protect_sha_absent=a.allow_protect_sha_absent, **policy),
                         ensure_ascii=False, indent=1))
        return 0
    if not a.archive_dir or not a.expect_plan:
        raise SystemExit('--apply needs --archive-dir and --expect-plan (the reviewed plan_sha256)')
    receipt = apply(server, a.archive_dir, a.receipt or a.archive_dir / 'retention-receipt.json', a.expect_plan,
                    protect=a.protect, protect_sha=a.protect_sha, reuse_dirs=a.reuse_dir,
                    allow_protect_sha_absent=a.allow_protect_sha_absent, **policy)
    run = receipt['runs'][-1]
    print(json.dumps(run, ensure_ascii=False))
    return 0 if run['outcome'] == 'target_met' else EXIT_NEEDS_MORE_SPACE


if __name__ == '__main__':
    raise SystemExit(main())
