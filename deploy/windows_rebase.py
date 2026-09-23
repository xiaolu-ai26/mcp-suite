"""Three-way, record-level rebase of collected changes onto a fresh server snapshot.

This module never collects or normalizes data. The online version wins conflicts;
anonymous online rows and the multiplicity of existing online IDs stay unchanged.
"""
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import tempfile

from qiuzhao.collector.p1_pipeline import atomic_json
from qiuzhao.v4_fields import iter_json_file


class CASConflict(RuntimeError):
    """The receiver rejected the expected production version."""


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def scan(path):
    counts, anonymous, hashes = Counter(), Counter(), defaultdict(set)
    total = 0
    for row in iter_json_file(path, strict=True):
        if not isinstance(row, dict) or not row.get('job_title'):
            raise ValueError('invalid job record')
        total += 1
        value = fingerprint(row)
        if row.get('id'):
            key = str(row['id'])
            counts[key] += 1
            hashes[key].add(value)
        else:
            anonymous[value] += 1
    if not total:
        raise ValueError('empty snapshot')
    return counts, anonymous, dict(hashes), total


def rebase_files(baseline, collected, latest, output):
    """Replay only baseline->collected changes; latest wins a same-ID conflict."""
    baseline, collected, latest, output = map(Path, (baseline, collected, latest, output))
    if output.resolve() in {p.resolve() for p in (baseline, collected, latest)}:
        raise ValueError('rebase output must not overwrite an input')
    before_hashes = {str(p): digest(p) for p in (baseline, collected, latest)}
    base_counts, base_anon, base_hashes, base_total = scan(baseline)
    local_counts, local_anon, local_hashes, local_total = scan(collected)
    remote_counts, remote_anon, remote_hashes, remote_total = scan(latest)
    changed = {key for key, value in local_hashes.items() if value != base_hashes.get(key)}
    apply_updates, apply_additions, conflicts, already = set(), set(), [], []
    for key in sorted(changed):
        local, base, remote = local_hashes[key], base_hashes.get(key), remote_hashes.get(key)
        if remote == local:
            already.append(key)
        elif base is None and remote is None:
            if len(local) != 1:
                raise ValueError('conflicting new local duplicate ID: ' + key)
            apply_additions.add(key)
        elif remote is not None and remote == base and len(local) == len(remote) == 1:
            apply_updates.add(key)
        else:
            conflicts.append({'id': key, 'resolution': 'keep_online',
                              'base_hashes': sorted(base or []),
                              'collected_hashes': sorted(local),
                              'online_hashes': sorted(remote or []),
                              'online_deleted': remote is None})
    chosen = apply_updates | apply_additions
    replacements = {}
    for row in iter_json_file(collected, strict=True):
        key = str(row['id']) if row.get('id') else None
        if key in chosen:
            replacements.setdefault(key, row)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix='.rebased-', suffix='.json', dir=output.parent)
    temporary = Path(temporary_name)
    result_counts, result_anon, total = Counter(), Counter(), 0
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as target:
            target.write('[\n')
            def emit(row):
                nonlocal total
                if total:
                    target.write(',\n')
                target.write(json.dumps(row, ensure_ascii=False, indent=2))
                total += 1
                if row.get('id'):
                    result_counts[str(row['id'])] += 1
                else:
                    result_anon[fingerprint(row)] += 1
            for row in iter_json_file(latest, strict=True):
                key = str(row['id']) if row.get('id') else None
                emit(replacements[key] if key in apply_updates else row)
            for key in sorted(apply_additions):
                for _ in range(local_counts[key]):
                    emit(replacements[key])
            target.write('\n]\n')
            target.flush()
            os.fsync(target.fileno())
        if result_anon != remote_anon:
            raise ValueError('anonymous online multiset changed')
        if any(result_counts[key] != n for key, n in remote_counts.items()):
            raise ValueError('existing online ID multiplicity changed')
        if any(digest(p) != before_hashes[str(p)] for p in (baseline, collected, latest)):
            raise ValueError('input changed during rebase')
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    receipt = {
        'baseline_sha256': before_hashes[str(baseline)],
        'collected_sha256': before_hashes[str(collected)],
        'latest_sha256': before_hashes[str(latest)], 'merged_sha256': digest(output),
        'base_rows': base_total, 'collected_rows': local_total,
        'online_rows': remote_total, 'merged_rows': total,
        'applied_update_ids': sorted(apply_updates),
        'applied_addition_ids': sorted(apply_additions),
        'added_rows': sum(local_counts[k] for k in apply_additions),
        'already_applied_ids': already, 'conflicts': conflicts,
        'local_deletions_ignored': sorted(set(base_counts) - set(local_counts)),
        'local_anonymous_changes_ignored': local_anon != base_anon,
        'online_anonymous_rows': sum(remote_anon.values()),
        'online_anonymous_multiset_preserved': True,
        'online_existing_id_multiplicities_preserved': True,
        'normalization_run': False, 'output': str(output),
    }
    atomic_json(output.with_suffix('.receipt.json'), receipt)
    return receipt


def publish_with_rebase(baseline, candidate, expected_base, workdir,
                        pull_snapshot, publish_snapshot, *, force_rebase=False,
                        max_rebases=3, aligned=None):
    """Keep the real original base immutable; every retry uses a fresh CAS snapshot.

    ``aligned`` maps the sha256 of an artifact this run sent earlier without a
    confirmed receipt (ssh dropped after the receiver replaced jobs.json, or the
    local state write was interrupted) to the local candidate that artifact was built
    from. When the fresh snapshot turns out to be exactly such an artifact, the local
    changes are replayed from that candidate instead of from ``baseline``: the server
    already holds everything up to it, so diffing against the older base would turn
    this run's own later edits of the same IDs into keep-online conflicts. Once one
    attempt has seen such an artifact, later bounded retries keep replaying from that
    candidate: a further external write on top of it (the reason the attempt lost its
    CAS) does not make the server stop descending from our own accepted artifact.
    Genuine external edits of the same IDs still resolve to the online version.
    """
    baseline, candidate, workdir = Path(baseline), Path(candidate), Path(workdir)
    aligned = dict(aligned or {})
    confirmed = None  # (server sha256 that matched, local candidate it was built from)
    if digest(baseline) != expected_base:
        raise ValueError('original baseline does not match its recorded hash')
    workdir.mkdir(parents=True, exist_ok=True)
    attempts = []
    candidate_hash = digest(candidate)
    if not force_rebase:
        try:
            publication = publish_snapshot(candidate, expected_base, workdir/'direct')
            result = {'publication': publication, 'published_path': str(candidate),
                      'source_candidate_sha256': candidate_hash, 'attempts': attempts}
            atomic_json(workdir/'receipt.json', result)
            return result
        except CASConflict as error:
            attempts.append({'phase': 'direct', 'cas_conflict': str(error)})
            atomic_json(workdir/'attempts.json', attempts)
    for number in range(1, max_rebases+1):
        folder = workdir/f'rebase-{number:02d}'
        folder.mkdir(parents=True, exist_ok=False)
        latest, output = folder/'latest.jobs.json', folder/'merged.jobs.json'
        latest_hash = pull_snapshot(latest)
        if digest(latest) != latest_hash:
            raise ValueError('latest snapshot hash mismatch')
        alignment = aligned.get(latest_hash)
        if alignment is not None:
            confirmed = (latest_hash, Path(alignment))
        base = confirmed[1] if confirmed else baseline
        if confirmed and not base.is_file():
            raise ValueError('aligned local base is missing: ' + str(base))
        report = rebase_files(base, candidate, latest, output)
        if report['collected_sha256'] != candidate_hash:
            raise ValueError('collected candidate changed between attempts')
        attempt = {'phase': 'rebase', 'number': number,
                   'latest_sha256': latest_hash, 'report': str(output.with_suffix('.receipt.json'))}
        if confirmed:
            attempt['aligned_unconfirmed_publication'] = {'server_sha256': confirmed[0],
                                                          'local_base': str(base),
                                                          'matched_this_attempt': alignment is not None}
        attempts.append(attempt)
        try:
            publication = publish_snapshot(output, latest_hash, folder/'publish')
        except CASConflict as error:
            attempt['cas_conflict'] = str(error)
            atomic_json(workdir/'attempts.json', attempts)
            continue
        attempt['published'] = True
        result = {'publication': publication, 'published_path': str(output),
                  'source_candidate_sha256': candidate_hash, 'attempts': attempts,
                  'rebase_report': report}
        if confirmed:
            result['aligned_unconfirmed_publication'] = attempt['aligned_unconfirmed_publication']
        atomic_json(workdir/'receipt.json', result)
        return result
    raise CASConflict('production changed during all bounded rebase attempts; evidence retained')
