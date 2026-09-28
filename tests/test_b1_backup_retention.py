"""Bounded gzip-backup retention: plan -> archive -> verify -> exact unlink (batch 1).

The remote programs run for real against a temporary "server" directory through a local
shell instead of ssh; nothing here touches a real server.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path

import pytest

from deploy import server_backup_retention as T

SHELL = ['bash', '-c']


def make_server(tmp_path, count=6, *, receipts=True):
    root = tmp_path / 'srv'
    root.mkdir()
    (root / 'jobs.json').write_bytes(b'[' + b'{"id":"x","job_title":"A"}' * 3 + b']')
    (root / 'jobs.json.bak.windows.20260921T181458').write_bytes(b'R0 raw')
    (root / 'jobs.json.bak.windows.20260925T030325').write_bytes(b'newest raw')
    (root / 'jobs.json.bak.windows.rotation.py').write_text('# rotation module')
    lines = []
    for i in range(count):
        original = ('original %d ' % i).encode() * 200
        name = 'jobs.json.bak.windows.202609%02dT000000.gz' % (10 + i)
        with gzip.open(root / name, 'wb') as out:
            out.write(original)
        lines.append({'status': 'rotated', 'gzip_path': str(root / name),
                      'source_sha256': hashlib.sha256(original).hexdigest(), 'source_bytes': len(original),
                      'gzip_sha256': hashlib.sha256((root / name).read_bytes()).hexdigest()})
    if receipts:
        (root / 'jobs.json.bak.windows.rotation-receipts.jsonl').write_text(
            ''.join(json.dumps(line) + '\n' for line in lines))
    return root


def names(root):
    return sorted(p.name for p in root.iterdir())


def test_plan_is_read_only_and_only_selects_old_gzips(tmp_path):
    root = make_server(tmp_path)
    before = names(root)
    server = T.Server(SHELL, str(root))
    p = T.plan(server.listing(), keep_newest_gz=2, gz_budget_bytes=0, margin_bytes=0)
    assert names(root) == before
    assert [c['name'] for c in p['candidates']] == ['jobs.json.bak.windows.202609%02dT000000.gz' % d
                                                   for d in (10, 11, 12, 13)]
    assert set(p['protected']) == {'jobs.json.bak.windows.20260914T000000.gz', 'jobs.json.bak.windows.20260915T000000.gz'}
    assert all(c['original_sha256'] for c in p['candidates'])
    assert p['gate_required'] == 2 * (root / 'jobs.json').stat().st_size + T.UPLOAD_LIMIT + T.GATE_EXTRA


def test_plan_stops_at_budget_limits_and_protect(tmp_path):
    root = make_server(tmp_path)
    listing = T.Server(SHELL, str(root)).listing()
    capped = T.plan(listing, keep_newest_gz=2, gz_budget_bytes=0, margin_bytes=0, max_files=2)
    assert len(capped['candidates']) == 2
    protected = T.plan(listing, keep_newest_gz=2, gz_budget_bytes=0, margin_bytes=0,
                       protect=['jobs.json.bak.windows.20260910T000000.gz'])
    assert 'jobs.json.bak.windows.20260910T000000.gz' not in [c['name'] for c in protected['candidates']]
    satisfied = T.plan(listing, keep_newest_gz=2, gz_budget_bytes=10 ** 12, margin_bytes=0)
    assert satisfied['candidates'] == [] and satisfied['meets_target']
    assert capped['plan_sha256'] != protected['plan_sha256']


def test_plan_needs_free_space_for_the_gate_plus_margin(tmp_path):
    root = make_server(tmp_path, count=4)
    listing = T.Server(SHELL, str(root)).listing()
    listing['free'] = 0
    p = T.plan(listing, keep_newest_gz=1, gz_budget_bytes=10 ** 12, margin_bytes=0)
    assert len(p['candidates']) == 3 and not p['meets_target'], 'short of target: take all allowed, say so'


def run_apply(root, tmp_path, **policy):
    server = T.Server(SHELL, str(root))
    p = T.plan(server.listing(), **policy)
    receipt = T.apply(server, tmp_path / 'archive', tmp_path / 'archive' / 'r.json', p['plan_sha256'], **policy)
    return p, receipt


POLICY = dict(keep_newest_gz=2, gz_budget_bytes=0, margin_bytes=0)


def test_apply_archives_verifies_and_unlinks_exactly_the_candidates(tmp_path):
    root = make_server(tmp_path)
    p, receipt = run_apply(root, tmp_path, **POLICY)
    for c in p['candidates']:
        assert not (root / c['name']).exists()
        archived = tmp_path / 'archive' / c['name']
        assert hashlib.sha256(gzip.decompress(archived.read_bytes())).hexdigest() == c['original_sha256']
        assert receipt['items'][c['name']]['status'] == 'deleted'
    kept = names(root)
    for protected in ('jobs.json', 'jobs.json.bak.windows.20260921T181458', 'jobs.json.bak.windows.20260925T030325',
                      'jobs.json.bak.windows.20260914T000000.gz', 'jobs.json.bak.windows.20260915T000000.gz',
                      'jobs.json.bak.windows.rotation.py', 'jobs.json.bak.windows.rotation-receipts.jsonl'):
        assert protected in kept
    # Re-running with the same (now empty) plan is a no-op.
    again, _ = run_apply(root, tmp_path, **POLICY)
    assert again['candidates'] == []


def test_apply_refuses_a_plan_that_no_longer_matches(tmp_path):
    root = make_server(tmp_path)
    server = T.Server(SHELL, str(root))
    reviewed = T.plan(server.listing(), **POLICY)['plan_sha256']
    (root / 'jobs.json.bak.windows.20260909T000000.gz').write_bytes(gzip.compress(b'older'))
    with pytest.raises(T.RetentionError, match='changed since the reviewed plan'):
        T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', reviewed, **POLICY)
    assert (root / 'jobs.json.bak.windows.20260910T000000.gz').exists()


def test_apply_refuses_while_an_upload_is_in_flight(tmp_path):
    root = make_server(tmp_path)
    (root / '.windows-jobs.abc123').write_bytes(b'partial upload')
    server = T.Server(SHELL, str(root))
    p = T.plan(server.listing(), **POLICY)
    with pytest.raises(T.RetentionError, match='in flight'):
        T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', p['plan_sha256'], **POLICY)
    assert len([n for n in names(root) if n.endswith('.gz')]) == 6


def test_unverifiable_gzip_is_archived_but_never_deleted(tmp_path):
    root = make_server(tmp_path, receipts=False)
    server = T.Server(SHELL, str(root))
    p = T.plan(server.listing(), **POLICY)
    with pytest.raises(T.RetentionError, match='no rotation receipt'):
        T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', p['plan_sha256'], **POLICY)
    assert len([n for n in names(root) if n.endswith('.gz')]) == 6


def test_content_changed_after_archiving_is_refused_by_the_server_side(tmp_path, monkeypatch):
    root = make_server(tmp_path)
    server = T.Server(SHELL, str(root))
    p = T.plan(server.listing(), **POLICY)
    real_delete = server.delete
    target = root / p['candidates'][0]['name']

    def tamper_then_delete(item, keep, wait=120):
        with target.open('r+b') as f:   # same inode and size, different bytes
            f.seek(0)
            f.write(b'\x00')
        return real_delete(item, keep, wait)
    monkeypatch.setattr(server, 'delete', tamper_then_delete)
    with pytest.raises(T.RetentionError, match='content changed'):
        T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', p['plan_sha256'], **POLICY)
    assert target.exists()


def test_lost_delete_answer_is_resolved_from_evidence(tmp_path, monkeypatch):
    root = make_server(tmp_path)
    server = T.Server(SHELL, str(root))
    p = T.plan(server.listing(), **POLICY)
    real_delete = server.delete

    def delete_then_lose_answer(item, keep, wait=120):
        real_delete(item, keep, wait)
        return type('Done', (), {'returncode': 255, 'stderr': 'Connection reset', 'stdout': ''})()
    monkeypatch.setattr(server, 'delete', delete_then_lose_answer)
    receipt_path = tmp_path / 'a' / 'r.json'
    with pytest.raises(T.RetentionError, match='outcome unknown'):
        T.apply(server, tmp_path / 'a', receipt_path, p['plan_sha256'], **POLICY)
    first = p['candidates'][0]['name']
    assert json.loads(receipt_path.read_text())['items'][first]['status'] == 'delete_unknown'
    monkeypatch.setattr(server, 'delete', real_delete)
    fresh = T.plan(server.listing(), **POLICY)
    receipt = T.apply(server, tmp_path / 'a', receipt_path, fresh['plan_sha256'], **POLICY)
    assert receipt['items'][first]['status'] == 'deleted'
    assert receipt['items'][first]['resolved'].startswith('absent')


def test_server_side_delete_never_takes_the_newest_gzips(tmp_path):
    root = make_server(tmp_path, count=3)
    server = T.Server(SHELL, str(root))
    newest = 'jobs.json.bak.windows.20260912T000000.gz'
    ident = server.identity(newest)
    done = server.delete(dict(ident, name=newest), keep=1)
    assert done.returncode and 'fewer than the newest' in done.stderr
    assert (root / newest).exists()
    done = server.delete({'name': 'jobs.json', 'bytes': 1, 'inode': 1, 'sha256': 'x'}, keep=0)
    assert done.returncode and 'not a gzip backup name' in done.stderr


def test_single_instance_lock(tmp_path):
    root = make_server(tmp_path)
    server = T.Server(SHELL, str(root))
    receipt_path = tmp_path / 'a' / 'r.json'
    receipt_path.parent.mkdir()
    import fcntl
    with open(str(receipt_path) + '.lock', 'a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        with pytest.raises(T.RetentionError, match='holds the lock'):
            T.apply(server, tmp_path / 'a', receipt_path, 'x', **POLICY)


# --- review fixes (7800d304): durability, target, protect, hard links, unknown, reuse ----

def plan_for(root, **policy):
    server = T.Server(SHELL, str(root))
    return server, T.plan(server.listing(), **policy)


def test_no_remote_unlink_unless_the_archive_reached_stable_storage(tmp_path, monkeypatch):
    root = make_server(tmp_path)
    server, p = plan_for(root, **POLICY)
    real = T.full_sync
    calls = {'n': 0}

    def failing_sync(fd):
        calls['n'] += 1
        if calls['n'] > 2:            # the run record syncs first; the archive's sync then fails
            raise OSError(5, 'F_FULLFSYNC failed')
        return real(fd)
    monkeypatch.setattr(T, 'full_sync', failing_sync)
    deleted = []
    monkeypatch.setattr(server, 'delete', lambda *a, **k: deleted.append(a))
    with pytest.raises(OSError):
        T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', p['plan_sha256'], **POLICY)
    assert deleted == [] and len([n for n in names(root) if n.endswith('.gz')]) == 6


def test_a_run_short_of_the_target_is_needs_more_space_not_success(tmp_path):
    root = make_server(tmp_path)
    policy = dict(keep_newest_gz=2, gz_budget_bytes=0, margin_bytes=10 ** 15)
    server, p = plan_for(root, **policy)
    assert p['meets_target'] is False
    receipt = T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', p['plan_sha256'], **policy)
    run = receipt['runs'][-1]
    assert run['outcome'] == 'needs_more_space' and run['plan']['meets_target'] is False
    assert run['free_after'] < run['plan']['target_free'] and len(run['deleted_this_run']) == 4
    code = T.main(['--ssh', json.dumps(SHELL), '--server-dir', str(root), '--apply', '--archive-dir',
                   str(tmp_path / 'b'), '--expect-plan', T.plan(server.listing(), **policy)['plan_sha256'],
                   '--keep-newest-gz', '2', '--gz-budget-bytes', '0', '--margin-bytes', str(10 ** 15)])
    assert code == T.EXIT_NEEDS_MORE_SPACE


def test_capped_progress_is_reported(tmp_path):
    root = make_server(tmp_path)
    _, p = plan_for(root, keep_newest_gz=2, gz_budget_bytes=0, margin_bytes=0, max_files=1)
    assert p['capped_by'] == 'max_files' and len(p['candidates']) == 1


def test_unknown_protect_names_are_an_error_and_raw_names_are_fine(tmp_path):
    root = make_server(tmp_path)
    listing = T.Server(SHELL, str(root)).listing()
    with pytest.raises(T.RetentionError, match='not on the server'):
        T.plan(listing, protect=['jobs.json.bak.windows.20260910T000000'], **POLICY)   # missing .gz
    ok = T.plan(listing, protect=['jobs.json.bak.windows.20260921T181458'], **POLICY)
    assert 'jobs.json.bak.windows.20260921T181458' in ok['protected']


def test_protect_sha_keeps_the_rollback_gzip_of_that_version(tmp_path):
    root = make_server(tmp_path)
    listing = T.Server(SHELL, str(root)).listing()
    first = 'jobs.json.bak.windows.20260910T000000.gz'
    sha = listing['sources'][first]['sha256']
    p = T.plan(listing, protect_sha=[sha, 'f' * 64], allow_protect_sha_absent=True, **POLICY)
    assert first not in [c['name'] for c in p['candidates']] and first in p['protected']
    assert p['protected_versions'][sha] == first
    assert p['protected_versions']['f' * 64].startswith('no gzip on the server')


def test_hard_linked_gzips_are_never_candidates(tmp_path):
    root = make_server(tmp_path)
    first = root / 'jobs.json.bak.windows.20260910T000000.gz'
    os.link(first, tmp_path / 'elsewhere.gz')
    _, p = plan_for(root, **POLICY)
    assert first.name in p['hard_linked_gz'] and first.name not in [c['name'] for c in p['candidates']]
    assert p['expected_freed'] == sum(c['bytes'] for c in p['candidates'])


def test_failure_after_the_unlink_is_unknown_then_resolved(tmp_path, monkeypatch):
    root = make_server(tmp_path)
    server, p = plan_for(root, **POLICY)
    real_delete = server.delete

    def unlink_then_fail(item, keep, wait=120):
        done = real_delete(item, keep, wait)
        return type('Done', (), {'returncode': 1, 'stdout': 'UNLINKING\n',
                                 'stderr': 'OSError: [Errno 5] fsync failed'})()
    monkeypatch.setattr(server, 'delete', unlink_then_fail)
    receipt_path = tmp_path / 'a' / 'r.json'
    with pytest.raises(T.RetentionError, match='outcome unknown'):
        T.apply(server, tmp_path / 'a', receipt_path, p['plan_sha256'], **POLICY)
    receipt = json.loads(receipt_path.read_text())
    first = p['candidates'][0]['name']
    assert receipt['items'][first]['status'] == 'delete_unknown'
    assert receipt['runs'][-1]['outcome'] == 'error' and receipt['runs'][-1]['finished_at']
    monkeypatch.setattr(server, 'delete', real_delete)
    receipt = T.apply(server, tmp_path / 'a', receipt_path, T.plan(server.listing(), **POLICY)['plan_sha256'],
                      **POLICY)
    assert receipt['items'][first]['status'] == 'deleted'


def test_a_verified_local_original_is_copied_instead_of_transferred(tmp_path, monkeypatch):
    root = make_server(tmp_path, count=4)
    server, p = plan_for(root, **POLICY)
    reuse = tmp_path / 'delivery-artifacts'
    reuse.mkdir()
    first = p['candidates'][0]
    original = gzip.decompress((root / first['name']).read_bytes())
    (reuse / (first['original_sha256'] + '.jobs.json')).write_bytes(original)
    second = p['candidates'][1]
    (reuse / (second['original_sha256'] + '.jobs.json')).write_bytes(b'same name, other bytes')
    streamed = []
    real_stream = server.stream
    monkeypatch.setattr(server, 'stream', lambda name, out: (streamed.append(name), real_stream(name, out)))
    receipt = T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', p['plan_sha256'],
                      reuse_dirs=[reuse], **POLICY)
    assert receipt['items'][first['name']]['archive_kind'] == 'copied_original'
    assert first['name'] not in streamed, 'a verified original is not transferred again'
    assert receipt['items'][second['name']]['archive_kind'] == 'transferred_gzip', 'wrong bytes are not trusted'
    pinned = Path(receipt['items'][first['name']]['archive'])
    (reuse / (first['original_sha256'] + '.jobs.json')).unlink()     # cache cleanup
    assert hashlib.sha256(pinned.read_bytes()).hexdigest() == first['original_sha256']


# --- re-review fixes: independent copy, proof of the server gzip, protect-sha input ------

def seed_reuse(tmp_path, root, candidate):
    reuse = tmp_path / 'reuse'
    reuse.mkdir(exist_ok=True)
    path = reuse / (candidate['original_sha256'] + '.jobs.json')
    path.write_bytes(gzip.decompress((root / candidate['name']).read_bytes()))
    return reuse, path


def test_the_reused_original_is_an_independent_read_only_copy(tmp_path):
    root = make_server(tmp_path, count=3)
    server, p = plan_for(root, **POLICY)
    first = p['candidates'][0]
    reuse, cache = seed_reuse(tmp_path, root, first)
    receipt = T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', p['plan_sha256'], reuse_dirs=[reuse], **POLICY)
    item = receipt['items'][first['name']]
    assert item['archive_kind'] == 'copied_original' and item['status'] == 'deleted'
    archived = Path(item['archive'])
    assert archived.stat().st_ino != cache.stat().st_ino
    assert oct(archived.stat().st_mode & 0o777) == '0o400'
    with cache.open('r+b') as f:          # the cache is rewritten in place afterwards
        f.write(b'garbage')
    cache.write_bytes(b'short')
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == first['original_sha256']


@pytest.mark.parametrize('failure', ['copy', 'verify'])
def test_a_failed_copy_or_verification_deletes_nothing(tmp_path, monkeypatch, failure):
    root = make_server(tmp_path, count=3)
    server, p = plan_for(root, **POLICY)
    first = p['candidates'][0]
    reuse, _ = seed_reuse(tmp_path, root, first)
    if failure == 'copy':
        def broken(source, target):
            raise OSError(28, 'No space left on device')
        monkeypatch.setattr(T, 'independent_copy', broken)
    else:
        monkeypatch.setattr(T, 'independent_copy', lambda source, target: target.write_bytes(b'wrong bytes'))
    deleted = []
    monkeypatch.setattr(server, 'delete', lambda *a, **k: deleted.append(a))
    receipt_path = tmp_path / 'a' / 'r.json'
    with pytest.raises((OSError, T.RetentionError)):
        T.apply(server, tmp_path / 'a', receipt_path, p['plan_sha256'], reuse_dirs=[reuse], **POLICY)
    assert deleted == [] and (root / first['name']).exists()
    assert json.loads(receipt_path.read_text())['runs'][-1]['outcome'] == 'error'


def test_reuse_needs_the_receipt_to_prove_the_server_gzip(tmp_path, monkeypatch):
    root = make_server(tmp_path, count=3)
    receipts = root / 'jobs.json.bak.windows.rotation-receipts.jsonl'
    lines = [json.loads(line) for line in receipts.read_text().splitlines()]
    lines[0]['gzip_sha256'] = '0' * 64            # stale receipt: server gzip is not that one
    lines[1].pop('gzip_sha256')                   # no evidence at all
    receipts.write_text(''.join(json.dumps(line) + '\n' for line in lines))
    server, p = plan_for(root, **POLICY)
    reuse = None
    for candidate in p['candidates'][:2]:
        reuse, _ = seed_reuse(tmp_path, root, candidate)
    receipt = T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', p['plan_sha256'], reuse_dirs=[reuse], **POLICY)
    for candidate in p['candidates'][:2]:
        assert receipt['items'][candidate['name']]['archive_kind'] == 'transferred_gzip'


def test_not_enough_local_space_deletes_nothing(tmp_path, monkeypatch):
    root = make_server(tmp_path, count=3)
    server, p = plan_for(root, **POLICY)
    real_usage = T.shutil.disk_usage
    monkeypatch.setattr(T.shutil, 'disk_usage', lambda path: real_usage(path)._replace(free=10))
    deleted = []
    monkeypatch.setattr(server, 'delete', lambda *a, **k: deleted.append(a))
    with pytest.raises(T.RetentionError, match='local archive disk'):
        T.apply(server, tmp_path / 'a', tmp_path / 'a' / 'r.json', p['plan_sha256'], **POLICY)
    assert deleted == []


def test_protect_sha_must_be_well_formed_and_absent_ones_must_be_allowed(tmp_path):
    root = make_server(tmp_path)
    listing = T.Server(SHELL, str(root)).listing()
    with pytest.raises(T.RetentionError, match='full lowercase sha256'):
        T.plan(listing, protect_sha=['deadbeef'], **POLICY)
    with pytest.raises(T.RetentionError, match='no gzip on the server'):
        T.plan(listing, protect_sha=['e' * 64], **POLICY)
    assert T.plan(listing, protect_sha=['e' * 64], allow_protect_sha_absent=True, **POLICY)['candidates']
