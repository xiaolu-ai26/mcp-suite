"""Bounded per-company/per-scope public recruitment refresh in the existing daily chain.

Adapter contract: collect(company, scope, output_dir) -> {jobs: [...], coverage: {...}}.
Each invocation runs in an isolated process. Only validated complete snapshots may
remove previously P1-owned records; partial sources retain old records.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
from .portable_runtime import fcntl, stop_tree
import hashlib
import gzip
import importlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import urlsplit
from . import p1_pending_index as N

from qiuzhao.normalize import normalize_records
from qiuzhao.v4_fields import graduation_of, graduation_constraints_of, iter_json_file

COMPANIES = [
    '拼多多', '大疆', '华为', '小红书', '快手', 'OPPO', 'vivo', '荣耀', '比亚迪', '宁德时代',
    '米哈游', '哔哩哔哩', '蚂蚁集团', '百度', '滴滴', '携程', '联想', '海康威视', '安克创新', '影石Insta360',
    '鹰角网络', '叠纸游戏', '莉莉丝游戏', '完美世界', '三七互娱', '巨人网络', '金山办公', '用友网络', '金蝶', '科大讯飞',
    '商汤科技', '中兴通讯', '大华股份', '汇川技术', 'TP-LINK普联', '石头科技', '科沃斯', '理想汽车', '小鹏汽车', '蔚来汽车',
    '吉利汽车', '长城汽车', '迈瑞医疗', '恒瑞医药', '药明康德', '小米', '京东', '美团', '网易', '得物',
]
SCOPES = {'campus': '校园招聘', 'intern': '实习招聘', 'social': '社会招聘'}
# Stable order is the user-approved priority list. Missing modules are blocked,
# never interpreted as an empty successful source.
REGISTRY = {name: f'qiuzhao.collector.p1_sources_{(i // 10) * 10 + 1:02d}_{(i // 10 + 1) * 10:02d}'
            for i, name in enumerate(COMPANIES)}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def stream_sha(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1 << 20), b''):
        digest.update(chunk)
    return digest.hexdigest()


def sha(path):
    with path.open('rb') as stream:
        return stream_sha(stream)


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            st = path.stat()
            os.chmod(temporary, st.st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def blocked(reason, status='blocked'):
    return {'jobs': [], 'coverage': {'status': status, 'complete': False,
            'detail_complete': False, 'expected_total': None, 'collected_jobs': 0,
            'pages_scanned': 0, 'errors': [reason], 'checked_at': now()}}


def validate_result(payload, company, scope, evidence_dir=None):
    """Reject malformed evidence instead of letting a source corrupt the shared store."""
    if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
        raise ValueError('adapter result must contain jobs list')
    coverage = payload.get('coverage')
    if not isinstance(coverage, dict) or coverage.get('status') not in {'success', 'partial', 'blocked'}:
        raise ValueError('invalid coverage status')
    result = copy.deepcopy(payload)
    coverage = result['coverage']
    rows = result['jobs']
    if coverage.get('collected_jobs') != len(rows):
        raise ValueError('coverage count differs from returned jobs')
    if coverage.get('status') == 'blocked' and rows:
        raise ValueError('blocked result cannot publish rows')
    pending=N.normalize_pending_index(result.get('pending_index',[]),company,scope,SCOPES[scope])
    result['pending_index']=pending
    if (rows or pending or coverage.get('complete') is True) and not coverage.get('scope_evidence'):
        raise ValueError('missing official scope evidence')
    identities = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('job must be an object')
        for key in ('source_record_id', 'job_title', 'description_raw', 'recruitment_unit'):
            if not str(row.get(key) or '').strip():
                raise ValueError(f'job missing {key}')
        url = row.get('detail_url') or row.get('source_url')
        if not isinstance(url, str) or urlsplit(url).scheme not in {'http', 'https'} or not urlsplit(url).netloc:
            raise ValueError('missing official detail URL')
        source_id = str(row['source_record_id'])
        if source_id in identities:
            raise ValueError('duplicate source_record_id within scope')
        identities.add(source_id)
        row['source_record_id'] = source_id
        row['detail_url'] = url
        row['source_url'] = row.get('source_url') or url
        row['application_url'] = row.get('application_url') or url
        row['p1_company'] = company
        row['p1_scope'] = scope
        if row.get('recruitment_type') != SCOPES[scope]:
            raise ValueError('job recruitment_type conflicts with requested scope')
        row['canonical_company'] = company
        # Search company aliases without replacing the true hiring/legal unit.
        row['parent_unit_raw'] = ' / '.join(dict.fromkeys([company, str(row.get('parent_unit_raw') or company)]))
        row['recruiting_unit_raw'] = row.get('recruiting_unit_raw') or row['recruitment_unit']
        row['reviewed_at'] = row.get('reviewed_at') or now()
        row['id'] = 'p1-' + hashlib.sha256(f'{company}|{scope}|{source_id}'.encode()).hexdigest()[:24]
        row['p1_identity'] = row['id']
        row['status'] = row.get('status') if row.get('status') in {'open', 'unverified', 'expired'} else 'unverified'
        years = graduation_of(row)[0]
        if scope != 'social' and years and not graduation_constraints_of(row) and max(int(y[:4]) for y in years) < dt.datetime.now(dt.timezone.utc).year - 1:
            if row['status'] != 'expired':
                row['status'] = 'unverified'
            note = '官方列表仍公开，但明确届别较旧；请核验当前是否接受申请。'
            if note not in str(row.get('status_note') or ''):
                row['status_note'] = str(row.get('status_note') or '') + note
    for row in pending:
        if row['source_record_id'] in identities:raise ValueError('same source ID appears in jobs and pending_index')
        identities.add(row['source_record_id'])
        row.update(recruitment_unit=row.get('recruitment_unit') or company,canonical_company=company,
                   parent_unit_raw=company,source_url=row.get('source_url') or row['detail_url'],
                   application_url=row.get('application_url') or row['detail_url'])
        row['last_attempt_at']=row.get('last_attempt_at') or coverage.get('checked_at')
        if row['pending_reason']=='fetch_failed':row['reviewed_at']=None
        else:row['reviewed_at']=row.get('reviewed_at') or row['last_attempt_at']
        row['pending_note']=('本次详情请求未成功取得，岗位存在已由官方列表确认；详情仍待核验。' if row['pending_reason']=='fetch_failed'
                             else '官方详情已取得，但未披露有效岗位职责和任职要求；保留真实岗位索引。')
        if row.get('source_is_active') is False and {row.get('source_status_raw'),row.get('source_list_status_raw'),row.get('source_detail_status_raw')} & {'pause','closed','expired_jd_redirect'}:
            if 'expired_jd_redirect' in {row.get('source_status_raw'),row.get('source_list_status_raw'),row.get('source_detail_status_raw')} and (not isinstance(row.get('source_status_evidence'),dict) or not row['source_status_evidence']):
                raise ValueError('expired redirect requires official URL evidence')
            row['status']='expired'
        if evidence_dir is None:raise ValueError('pending index requires saved official evidence directory')
        root=Path(evidence_dir).resolve()
        references=[row[k] for k in ('listing_evidence_path','detail_evidence_path') if row.get(k)]
        for ref in references:
            path=Path(ref);path=(root/path).resolve() if not path.is_absolute() else path.resolve()
            if not (path.is_relative_to(root) or path.is_relative_to(root.parent/'shared')) or not path.is_file() or not path.stat().st_size:
                raise ValueError('pending index evidence must be a real current scope file')
    coverage['available_job_count']=len(rows);coverage['pending_count']=len(pending)
    complete = coverage.get('complete') is True
    if complete and any(row['detail_request_status']!='success' for row in pending):
        raise ValueError('failed detail request cannot have complete coverage')
    if complete:
        if (coverage.get('status') != 'success' or coverage.get('detail_complete') is not True
                or coverage.get('errors')
                or not coverage.get('source_url') or not coverage.get('evidence')):
            raise ValueError('complete requires successful full listing/details and evidence')
        if evidence_dir is not None:
            root = Path(evidence_dir).resolve()
            shared = root.parent / 'shared'
            request = coverage.get('scope_request')
            if (not isinstance(request, dict) or request.get('company') != company
                    or request.get('scope') != scope or not request.get('source_url')
                    or not isinstance(request.get('params'), dict)):
                raise ValueError('complete requires company/scope-bound official request metadata')
            evidence = coverage.get('evidence_files')
            if not isinstance(evidence, list) or not evidence:
                raise ValueError('complete requires saved response evidence_files')
            for reference in evidence:
                if not isinstance(reference, str):
                    raise ValueError('evidence file reference must be a string')
                path = Path(reference)
                path = (root / path).resolve() if not path.is_absolute() else path.resolve()
                allowed = path.is_relative_to(root) or path.is_relative_to(shared)
                if not allowed or not path.is_file() or not path.stat().st_size:
                    raise ValueError('evidence must be a nonempty current scope or company shared file')
        expected = coverage.get('expected_total')
        if expected is not None:
            if type(expected) is not int or expected != len(rows)+len(pending):
                raise ValueError('expected total differs from unique returned jobs')
        elif not (coverage.get('pagination_exhausted') is True
                  and coverage.get('unique_source_ids') == len(rows)+len(pending)
                  and coverage.get('last_page_evidence')):
            raise ValueError('no total requires unique count and proven pagination exhaustion')
    elif coverage.get('status') == 'success':
        # An adapter may finish its available subset, but that is not full coverage.
        coverage['status'] = 'partial'
    coverage['checked_at'] = now()
    return result


def collect_process(company, scope, output_dir, timeout=3600):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / 'result.json'
    # Do not permit stale result reuse after a killed/interrupted previous attempt.
    if result_path.exists():
        result_path.unlink()
    command = [sys.executable, '-m', 'qiuzhao.collector.p1_pipeline', '--adapter', REGISTRY[company],
               '--company', company, '--scope', scope, '--output-dir', str(output_dir)]
    with open(output_dir / 'adapter.log', 'w', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, cwd=Path(__file__).resolve().parents[2])
        cleanup = None
        try:
            rc = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                cleanup = stop_tree(process, strict=False)
            except Exception as error:
                # An adapter writes its own scope directory, never the shared jobs file.
                # Retain the timeout as a failure but do not abort every later scope.
                cleanup = {'pid': process.pid, 'cleanup_error': type(error).__name__+': '+str(error)[-1500:],
                           'process_terminated': process.poll() is not None}
            atomic_json(output_dir / 'timeout-cleanup.json', cleanup)
            rc = 'timeout'
    if rc:
        if result_path.exists() and not (cleanup and not cleanup.get('tree_termination_confirmed')):
            try:
                checkpoint = json.loads(result_path.read_text(encoding='utf-8'))
                if checkpoint.get('jobs') or checkpoint.get('pending_index'):
                    coverage = checkpoint['coverage']
                    coverage.update(status='partial', complete=False, detail_complete=False)
                    coverage.setdefault('errors', []).append(f'adapter interrupted: {rc}; scope timeout={timeout}s')
                    if cleanup is not None:coverage['timeout_cleanup'] = cleanup
                    return validate_result(checkpoint, company, scope, output_dir)
            except (ValueError, TypeError, KeyError):
                pass
        failed=blocked(f'adapter exit={rc}; inspect {output_dir / "adapter.log"}')
        if cleanup is not None:failed['coverage']['timeout_cleanup']=cleanup
        return failed
    if not result_path.exists():
        return blocked(f'adapter result missing; inspect {output_dir / "adapter.log"}')
    try:
        return validate_result(json.loads(result_path.read_text(encoding='utf-8')), company, scope, output_dir)
    except (ValueError, TypeError, KeyError) as error:
        return blocked(f'adapter contract rejected: {error}')


def official_uuid(row):
    """Only UUID source identities can bridge verified legacy URL changes."""
    value = str(row.get('source_record_id') or '')
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def merge_records(previous, results):
    """Update stable identities, retain failed-source rows, remove only proven absences."""
    merged = list(previous)
    changes = {'added': 0, 'updated': 0, 'removed': 0}
    for company, scope, result in results:
        rows, coverage = result['jobs'], result['coverage']
        pending=result.get('pending_index',[])
        if coverage['status'] == 'blocked' and not pending:
            continue
        rows=[*rows,*pending]
        by_id = {str(row.get('p1_identity') or row.get('id')): index for index, row in enumerate(merged) if row.get('id')}
        twin_indices = {}
        for index, row in enumerate(merged):
            if row.get('id'):twin_indices.setdefault(row['id'], []).append(index)
        # Exact detail URL + recruitment type can safely adopt a legacy record.
        by_url = {}
        for index, row in enumerate(merged):
            url = row.get('detail_url') or row.get('source_url')
            if url and row.get('id'):
                by_url.setdefault((url, row.get('recruitment_type')), []).append(index)
        by_source_uuid = {}
        for index, row in enumerate(merged):
            identity = official_uuid(row)
            owner = row.get('canonical_company') or row.get('p1_company') or row.get('recruitment_unit')
            if identity and owner == company and row.get('recruitment_type') == SCOPES[scope]:
                by_source_uuid.setdefault(identity, []).append(index)
        seen = N.presence_keys(result)
        adopted_indices = set()
        incoming_url_counts = {}
        for row in rows:
            incoming_url_counts[row['detail_url']] = incoming_url_counts.get(row['detail_url'], 0) + 1
        for incoming in rows:
            incoming = copy.deepcopy(incoming)
            canonical = incoming['p1_identity']
            normalize_records([incoming])
            index = by_id.get(canonical)
            if index is None and official_uuid(incoming):
                candidates = by_source_uuid.get(official_uuid(incoming), [])
                if len(candidates) == 1 and candidates[0] not in adopted_indices:
                    index = candidates[0]
            if index is None:
                matches = by_url.get((incoming['detail_url'], incoming['recruitment_type']), [])
                if (len(matches) == 1 and matches[0] not in adopted_indices
                        and incoming_url_counts[incoming['detail_url']] == 1):
                    candidate = merged[matches[0]]
                    if (not candidate.get('p1_company') or candidate.get('p1_company') == company) and (
                            not candidate.get('p1_scope') or candidate.get('p1_scope') == scope):
                        index = matches[0]
            if index is None:
                merged.append(incoming)
                by_id[canonical] = len(merged) - 1
                changes['added'] += 1
            else:
                old = merged[index]
                # Incoming evidence is authoritative; retaining old raw fields
                # could silently carry a stale cohort/campaign into new rows.
                incoming['id'] = old['id']
                if incoming.get('index_only') and old.get('description_raw'):
                    # A failed/empty current detail never destroys earlier verified prose.
                    retained=copy.deepcopy(old)
                    for field in ('p1_identity','p1_company','p1_scope','canonical_company','parent_unit_raw',
                                  'pending_reason','pending_note','detail_request_status','last_attempt_at'):
                        retained[field]=incoming.get(field)
                    if incoming.get('status')=='expired':
                        for field in ('status','status_note','source_is_active','source_status_raw','source_list_status_raw',
                                      'source_detail_status_raw','source_status_evidence','source_status_dates','source_status_conflict'):
                            if field in incoming:retained[field]=incoming[field]
                    incoming=retained
                # Preserve existing identical-ID multiplicity without leaving stale twin rows.
                for twin in twin_indices.get(old['id'], [index]):
                    prior = merged[twin]
                    if prior == old:
                        merged[twin] = copy.deepcopy(incoming)
                adopted_indices.add(index)
                by_id[canonical] = index
                from qiuzhao.normalize import business_value
                changes['updated'] += int(business_value(old) != business_value(incoming))
            seen.add(canonical)
        if coverage.get('complete') is True and coverage.get('status') == 'success' and result['jobs']:
            reviewed = coverage.get('checked_at') or now()
            for index, row in enumerate(merged):
                if row.get('p1_company') == company and row.get('p1_scope') == scope and (row.get('p1_identity') or row.get('id')) not in seen:
                    if row.get('status') != 'removed':
                        changes['removed'] += 1
                    row = dict(row)
                    merged[index] = row
                    row.update(status='removed', reviewed_at=reviewed,
                               removal_reason='Absent from complete current company/scope official listing',
                               source_is_active=False, source_status_raw='closed',
                               source_status_evidence={'list_status':'closed', 'reason':'complete_snapshot_absence',
                                   'company':company, 'scope':scope, 'complete':True,
                                   'source_url':coverage.get('source_url'),
                                   'checked_at':reviewed})
    return merged, changes


def publish(data_dir, results, run_dir):
    """Use current bytes, true pre-write backup, CAS recheck and atomic replacement."""
    data_dir, run_dir = Path(data_dir), Path(run_dir)
    jobs_path = data_dir / 'jobs.json'
    with open(data_dir / 'p1-publish.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before_hash = sha(jobs_path)
        previous = list(iter_json_file(jobs_path,strict=True))
        if not isinstance(previous, list):
            raise ValueError('production jobs must be a list')
        merged, changes = merge_records(previous, results)
        # One true pre-write snapshot per locked execution batch, not 150
        # complete database copies. Per-scope candidate snapshots and hashes
        # remain in the checkpoint for inspection/replay.
        run_dir.mkdir(parents=True, exist_ok=True)
        backup = run_dir / 'jobs.before.json.gz'
        manifest = run_dir / 'backup.json'
        if not backup.exists():
            with jobs_path.open('rb') as source, gzip.open(backup, 'wb', compresslevel=3) as stream:
                shutil.copyfileobj(source, stream, length=1 << 20)
            with gzip.open(backup, 'rb') as stream:
                backup_hash = stream_sha(stream)
            if backup_hash != before_hash:
                raise RuntimeError('pre-write backup hash mismatch')
            atomic_json(manifest, {'uncompressed_sha256': backup_hash, 'created_at': now()})
        else:
            backup_hash = json.loads(manifest.read_text(encoding='utf-8'))['uncompressed_sha256']
            with gzip.open(backup, 'rb') as stream:
                if stream_sha(stream) != backup_hash:
                    raise RuntimeError('existing batch backup hash mismatch; refusing publish')
        if sha(jobs_path) != before_hash:
            raise RuntimeError('jobs changed concurrently; refusing overwrite')
        atomic_json(jobs_path, merged)
        return dict(changes, before_sha256=before_hash, after_sha256=sha(jobs_path),
                    backup=str(backup), backup_sha256=backup_hash, total_jobs=len(merged), published_at=now())


def checkpoint_path(data_dir, companies, scopes):
    selection = json.dumps([companies, scopes], ensure_ascii=False).encode()
    key = hashlib.sha256(selection).hexdigest()[:20]
    return Path(data_dir) / 'p1-checkpoints' / (key + '.json')


def run(data_dir, run_dir, companies, scopes, timeout=3600, apply=False, resume=False, max_run_seconds=21600):
    data_dir, run_dir = Path(data_dir), Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    status_path = run_dir / 'status.json'
    if status_path.exists() and not resume:
        raise ValueError('run directory already exists; use --resume or a new directory')
    status = json.loads(status_path.read_text(encoding='utf-8')) if resume and status_path.exists() else {
        'started_at': now(), 'run_dir': str(run_dir), 'companies': companies, 'scopes': scopes, 'results': {}, 'publications': []}
    if status['companies'] != companies or status['scopes'] != scopes:
        raise ValueError('resume company/scope selection differs from checkpoint')
    def save_status():
        atomic_json(status_path, status)
        atomic_json(data_dir / 'p1-status.json', status)
        atomic_json(checkpoint_path(data_dir, companies, scopes), status)

    status.update(run_finished=False, success=False)
    save_status()
    publication_dir = run_dir / 'batches' / str(time.time_ns())
    deadline = time.monotonic() + max_run_seconds
    for company in companies:
        ordinal = COMPANIES.index(company) + 1
        for scope in scopes:
            key = f'{company}/{scope}'
            saved = status['results'].get(key)
            if saved and saved.get('attempted', True) and (not apply or saved.get('published')):
                continue
            if time.monotonic() >= deadline:
                status['run_finished'] = False
                status['success'] = False
                status['paused_at'] = now()
                status['pending'] = [f'{c}/{s}' for c in companies for s in scopes
                                     if f'{c}/{s}' not in status['results']]
                save_status()
                return 1
            output = run_dir / f'{ordinal:02d}' / scope
            if saved and Path(saved['result_path']).exists():
                result = validate_result(json.loads(Path(saved['result_path']).read_text(encoding='utf-8')), company, scope, output)
            else:
                result = collect_process(company, scope, output, min(timeout, max(1, deadline - time.monotonic())))
                atomic_json(output / 'validated.json', result)
            entry = {'coverage': result['coverage'], 'result_path': str(output / 'validated.json'),
                     'published': False, 'attempted': True}
            status['results'][key] = entry
            save_status()
            print(json.dumps({'company': company, 'scope': scope, **result['coverage']}, ensure_ascii=False), flush=True)
            if apply:
                if result['jobs'] or result.get('pending_index') or result['coverage'].get('complete'):
                    publication = publish(data_dir, [(company, scope, result)], publication_dir)
                    status['publications'].append(dict(company=company, scope=scope, **publication))
                entry['published'] = True  # processed; may intentionally retain existing data
                save_status()
    status['run_finished'] = True
    status['pending'] = []
    status['completed_at'] = now()
    status['success'] = all(e['coverage']['status'] == 'success' and e['coverage'].get('complete') is True
                            for e in status['results'].values())
    save_status()
    return 0 if status['success'] else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--adapter')
    parser.add_argument('--company')
    parser.add_argument('--scope', choices=list(SCOPES))
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--data-dir', type=Path, default=Path('/var/lib/mcp-suite'))
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--companies', help='comma-separated exact company names; default all 50')
    parser.add_argument('--scopes', default=','.join(SCOPES))
    parser.add_argument('--timeout', type=int, default=3600)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--resume-latest', action='store_true')
    parser.add_argument('--max-run-seconds', type=int, default=21600)
    args = parser.parse_args()
    if args.adapter:
        try:
            module = importlib.import_module(args.adapter)
            result = module.collect(args.company, args.scope, args.output_dir)
        except Exception as error:
            result = blocked(f'{type(error).__name__}: {error}')
        atomic_json(args.output_dir / 'result.json', result)
        return 0
    companies = args.companies.split(',') if args.companies else COMPANIES
    scopes = args.scopes.split(',')
    if any(c not in REGISTRY for c in companies) or any(s not in SCOPES for s in scopes):
        parser.error('unknown company or scope')
    if len(set(companies)) != len(companies) or len(set(scopes)) != len(scopes):
        parser.error('duplicate company or scope')
    run_dir = args.run_dir or args.data_dir / 'p1-runs' / dt.datetime.now().strftime('%Y%m%dT%H%M%S')
    def select_checkpoint():
        nonlocal run_dir
        latest = checkpoint_path(args.data_dir, companies, scopes)
        if not latest.exists():
            latest = args.data_dir / 'p1-status.json'
        if args.resume_latest and latest.exists():
            checkpoint = json.loads(latest.read_text(encoding='utf-8'))
            if checkpoint.get('run_dir'):
                saved_path = Path(checkpoint['run_dir']) / 'status.json'
                if saved_path.exists():
                    checkpoint = json.loads(saved_path.read_text(encoding='utf-8'))
            if (checkpoint.get('companies') == companies and checkpoint.get('scopes') == scopes
                    and not checkpoint.get('run_finished', True) and checkpoint.get('run_dir')):
                run_dir, args.resume = Path(checkpoint['run_dir']), True
    os.environ.setdefault('QIUZHAO_P1_DETAIL_CACHE_ROOT', str(args.data_dir / 'p1-detail-cache'))
    if args.apply:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        lock_path = args.data_dir / 'collector.lock'
        # Reuse the shell wrapper's inherited lock description when present.
        try:
            st = os.fstat(9)
            target = lock_path.stat()
            inherited = st.st_dev == target.st_dev and st.st_ino == target.st_ino
        except OSError:
            inherited = False
        lock = os.fdopen(os.dup(9), 'a') if inherited else open(lock_path, 'a')
        with lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            select_checkpoint()
            return run(args.data_dir, run_dir, companies, scopes, args.timeout,
                       args.apply, args.resume, args.max_run_seconds)
    select_checkpoint()
    return run(args.data_dir, run_dir, companies, scopes, args.timeout,
               args.apply, args.resume, args.max_run_seconds)


if __name__ == '__main__':
    raise SystemExit(main())
