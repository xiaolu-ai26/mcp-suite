"""Local user-authenticated, backed-up field-only sync for the existing Qiuzhao Base.

No credentials leave lark-cli. Snapshot and plan are read-only remotely; --apply
changes only the three authorized select fields and their existing records.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import tempfile
import shutil
from qiuzhao.collector.portable_runtime import fcntl, WINDOWS
from contextlib import contextmanager
from collections import Counter
from qiuzhao import v4_fields as V
from qiuzhao.collector import lark_continuation as C

BASE = 'REDACTED'
EXTERNAL_MOUNT=Path('/Volumes/臭垃圾桶')
EXTERNAL_RUNS=EXTERNAL_MOUNT/'MCP产品/qiuzhao-p1-20260913/runtime-runs'
TABLES = ['tblX7rOpjWaRArng', 'tbl0xkmJUMmLqZ1W', 'tbl0gDcxEaIOYERw', 'tblcrBAi0ld7uej8']
ORIGINAL_TABLES = tuple(TABLES)
# Hardcoded continuation ids are now derived from the shared continuation
# module; live discovery is the write authority and a name/id mismatch raises a
# legacy_id_drift alert (never a silent wrong-table write).
INTERNET_CONTINUATION_1 = C.LEGACY_TABLE_IDS['互联网科技岗·续表1']
# 互联网科技岗·续表2:已建表并逐字段核对通过(19/19 字段名/类型/顺序/选项一致,含 工作地点
# 624 个选项),0 条记录。核对证据见 research/qiuzhao-p1-20260912/base-overflow/internet2.*.json。
INTERNET_CONTINUATION = C.LEGACY_TABLE_IDS['互联网科技岗·续表2']
MANUFACTURING_CONTINUATION_1 = C.LEGACY_TABLE_IDS['制造工业岗·续表1']
MANUFACTURING_CONTINUATION = C.LEGACY_TABLE_IDS['制造工业岗·续表2']
TABLES_V6 = [*ORIGINAL_TABLES, INTERNET_CONTINUATION_1, MANUFACTURING_CONTINUATION_1]
PREVIOUS_TABLES = [*TABLES_V6, MANUFACTURING_CONTINUATION]
TABLES = [*PREVIOUS_TABLES, INTERNET_CONTINUATION]

def valid_table_selection(tables):
    """Strict legacy allowlist (kept for compatibility and its regression test)."""
    return set(tables) in (set(ORIGINAL_TABLES), {*ORIGINAL_TABLES, INTERNET_CONTINUATION_1}, set(TABLES_V6), set(PREVIOUS_TABLES), set(TABLES))


def valid_selection_for_snapshot(out, tables):
    """Accept the legacy exact sets or the exact set discovered in a snapshot.

    Continuation tables are discovered by name, so a dynamic backup/plan can no
    longer be compared against a static allowlist. The snapshot's own
    ``tables.before.json`` (written by :func:`snapshot`) is the authority: the
    selection must equal its name-discovered table set and cover the four
    originals.
    """
    tables = set(tables)
    if valid_table_selection(tables):
        return True
    inventory_path = Path(out) / 'tables.before.json'
    if not set(ORIGINAL_TABLES) <= tables or not inventory_path.exists():
        return False
    plan, problems = C.discover(json.loads(inventory_path.read_text(encoding='utf-8')))
    if problems:
        return False
    discovered = {slot['table_id'] for name in C.BASE_TABLE_NAMES for slot in plan.get(name, [])}
    return bool(discovered) and tables == discovered


def discover_tables():
    """Live ``{base name: [slot, ...]}`` plus discovery problems.

    Reads the Base inventory once; the fixed ids above are never consulted for
    writes. Callers that need the ids use :func:`discovered_table_ids`.
    """
    inventory = cli('+table-list', '--base-token', BASE, '--format', 'json')['data']['tables']
    return C.discover(inventory)


def discovered_table_ids():
    plan, _ = discover_tables()
    return [slot['table_id'] for name in C.BASE_TABLE_NAMES for slot in plan.get(name, [])]

TARGETS = ['毕业届别', '工作地点', '专业']


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def business_source_hash(path):
    from qiuzhao.normalize import business_value
    fingerprints=[]
    for row in V.iter_json_file(path):
        if not row.get('id'):
            continue  # Anonymous legacy records never get invented Feishu identities.
        value=business_value(row)
        fingerprints.append(hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
    return hashlib.sha256('\n'.join(sorted(set(fingerprints))).encode()).hexdigest()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_external_storage(path):
    if not EXTERNAL_MOUNT.is_mount() or not path.resolve().is_relative_to(EXTERNAL_RUNS.resolve()):
        raise ValueError('external artifact mount is unavailable or path is unapproved')
    if path.parent.stat().st_dev!=EXTERNAL_MOUNT.stat().st_dev:
        raise ValueError('artifact is not physically on external storage')


def cli_file_context(args):
    values=list(args);files=[];root=Path.cwd().resolve()
    for index,value in enumerate(values):
        if index and values[index-1]=='--output':files.append((index,Path(value).resolve(),False))
        elif index and values[index-1]=='--json' and isinstance(value,str) and value.startswith('@'):
            files.append((index,Path(value[1:]).resolve(),True))
    if not any(not path.is_relative_to(root) for _,path,_ in files):return values,None
    for _,path,_ in files:
        if not path.is_relative_to(EXTERNAL_RUNS.resolve()):raise ValueError('mixed or unapproved external CLI artifact path')
        verify_external_storage(path)
    working=Path(os.path.commonpath([str(path.parent) for _,path,_ in files]))
    for index,path,is_input in files:values[index]=('@' if is_input else '')+str(path.relative_to(working))
    return values,working


NETWORK_RETRY_DELAYS = (5, 15, 45)


def cli_error_payload(proc):
    # lark-cli reports structured errors as a JSON body, on stdout (ok:false)
    # or on stderr together with a non-zero exit code.
    for text in (proc.stdout, proc.stderr):
        try:
            value = json.loads(text or '')
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get('error'), dict):
            return value['error']
    return None


def cli(*args):
    env = dict(os.environ, LARKSUITE_CLI_NO_UPDATE_NOTIFIER='1', LARKSUITE_CLI_NO_SKILLS_NOTIFIER='1')
    values,working=cli_file_context(args)
    attempt = 0
    while True:
        temporary_bodies = []
        timed_out = None
        try:
            # Windows command-line length is finite; preserve JSON bytes via the CLI's existing @file protocol.
            if WINDOWS:
                for index, value in enumerate(values):
                    if index and values[index-1] == '--json' and isinstance(value,str) and not value.startswith('@') and len(value)>4096:
                        directory=(Path(working) if working else Path.cwd())/'.lark-json-transport'
                        directory.mkdir(parents=True,exist_ok=True)
                        fd, name=tempfile.mkstemp(prefix='request-',suffix='.json',dir=directory)
                        path=Path(name);temporary_bodies.append(path)
                        with os.fdopen(fd,'w',encoding='utf-8') as target:target.write(value)
                        values[index]='@'+os.path.relpath(path,Path(working) if working else Path.cwd())
            try:
                proc = subprocess.run([shutil.which('lark-cli') or 'lark-cli', 'base', *values, '--as', 'user'], capture_output=True,
                                      text=True, encoding='utf-8', env=env, timeout=180,cwd=working)
            except subprocess.TimeoutExpired as error:
                proc = None; timed_out = error
        finally:
            for path in temporary_bodies:path.unlink(missing_ok=True)
        if proc is None:
            error = {'type': 'network', 'subtype': 'timeout', 'message': str(timed_out)}
        elif proc.returncode:
            error = cli_error_payload(proc) or {'type': 'exit', 'message': proc.stderr[:2000]}
        else:
            result = json.loads(proc.stdout)
            if result.get('ok') is not False:
                return result
            error = result.get('error') or {'type': 'unknown'}
        if error.get('type') == 'network' and attempt < len(NETWORK_RETRY_DELAYS):
            delay = NETWORK_RETRY_DELAYS[attempt]; attempt += 1
            print(json.dumps({'cli_retry': attempt, 'delay_seconds': delay, 'command': values[0],
                              'error_subtype': error.get('subtype'),
                              'error_message': str(error.get('message', ''))[:300]}, ensure_ascii=False), flush=True)
            time.sleep(delay)
            continue
        raise RuntimeError('lark-cli rejected request: ' + json.dumps(error, ensure_ascii=False)[:2000])


def rel(path):
    # lark-cli requires a cwd-relative file argument. Keep the approved local
    # alias spelling while files physically reside on the mounted external disk.
    root=Path.cwd();lexical=Path(os.path.abspath(path));relative=lexical.relative_to(root)
    resolved=lexical.resolve()
    if not resolved.is_relative_to(root.resolve()):
        alias=root/'research/qiuzhao-p1-sync-runtime/runs'
        expected=EXTERNAL_RUNS
        if not alias.is_symlink() or alias.resolve()!=expected.resolve() or not lexical.is_relative_to(alias):
            raise ValueError('unapproved file path outside workspace')
    return str(relative)


def full_fields(table):
    # Single shared option-pagination implementation lives in the continuation
    # module so schema reads and schema validation cannot drift apart.
    return C.read_fields(cli, BASE, table)


def snapshot(out):
    if (out / 'backup.json').exists():
        raise ValueError('snapshot already exists; use a new output directory')
    tables = cli('+table-list', '--base-token', BASE, '--format', 'json')['data']['tables']
    actual = {t['id']: t for t in tables}
    plan, problems = C.discover(tables)
    if problems:
        raise ValueError('target table name ambiguity: ' + json.dumps(problems, ensure_ascii=False))
    current = [slot['table_id'] for name in C.BASE_TABLE_NAMES for slot in plan.get(name, [])]
    if not set(ORIGINAL_TABLES) <= actual.keys() or not current:
        raise ValueError('target table identity drift')
    save(out / 'tables.before.json', tables)
    manifest = {'base': BASE, 'tables': {}}
    for table in current:
        fields = full_fields(table)
        by_name = {f['name']: f for f in fields}
        if 'job_id' not in by_name or any(by_name.get(n, {}).get('type') != 'select' for n in TARGETS):
            raise ValueError('schema drift in ' + table)
        schema = out / (table + '.fields.before.json'); save(schema, fields)
        all_rows = []; offset = 0; revision = None
        # This full pagination is a pre-write backup and exact record locator,
        # not a limited sample used to infer a whole-table analytical result.
        for page in range(100):
            path = out / f'{table}.before.{page:03d}.ndjson'
            args = ['+record-list', '--base-token', BASE, '--table-id', table,
                    '--format', 'ndjson', '--output', rel(path), '--limit', '2000', '--offset', str(offset)]
            for name in ['job_id', *TARGETS]:
                args += ['--field-id', name]
            m = cli(*args)
            if revision is None:
                revision = m['rev']
            if revision != m['rev']:
                raise ValueError('table changed during backup: ' + table)
            all_rows.extend(json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line)
            if not m['has_more']:
                break
            next_offset = m.get('next_offset')
            if next_offset is None or next_offset <= offset:
                raise ValueError('nonadvancing backup pagination')
            offset = next_offset
        else:
            raise ValueError('backup pagination limit')
        if len(all_rows) != actual[table]['records_count'] or len({r['record_id'] for r in all_rows}) != len(all_rows):
            raise ValueError('backup count/record identity mismatch: ' + table)
        records = out / (table + '.records.before.json'); save(records, all_rows)
        manifest['tables'][table] = {'records': rel(records), 'schema': rel(schema),
            'records_sha256': digest(records), 'schema_sha256': digest(schema),
            'records_count': len(all_rows), 'rev': revision}
        print(json.dumps({'backed_up': table, 'records': len(all_rows)}), flush=True)
    save(out / 'backup.json', manifest)
    return manifest


def values_for(raw):
    years, _, note, _ = V.graduation_of(raw)
    majors = V.major_categories_of(raw)
    return {'毕业届别': years or [note or '未注明'],
            '工作地点': V.cities_of(raw) or ['未注明'],
            '专业': majors or [V.major_state(raw)]}


def make_plan(out, jobs_path):
    backup = json.loads((out / 'backup.json').read_text(encoding='utf-8'))
    if backup['base'] != BASE or not valid_selection_for_snapshot(out, backup['tables']):
        raise ValueError('backup target mismatch')
    jobs = {}; ambiguous = set()
    for raw in V.iter_json_file(jobs_path):
        identity = str(raw.get('id') or '')
        if not identity:
            continue
        values = values_for(raw)
        if identity in jobs and jobs[identity] != values:
            ambiguous.add(identity)
        jobs[identity] = values
    plan = {'base': BASE, 'source_jobs_sha256': digest(jobs_path), 'tables': {}}
    for table, meta in backup['tables'].items():
        records_path = Path(meta['records']); schema_path = Path(meta['schema'])
        if digest(records_path) != meta['records_sha256'] or digest(schema_path) != meta['schema_sha256']:
            raise ValueError('backup integrity mismatch')
        records = json.loads(records_path.read_text(encoding='utf-8')); fields = json.loads(schema_path.read_text(encoding='utf-8'))
        if any(f.get('remaining_options_count') for f in fields if f['name'] in TARGETS):
            raise ValueError('incomplete select metadata cannot be used for PUT')
        updates = {}; unmatched = []; options = {name: set() for name in TARGETS}
        for record in records:
            identity = record.get('job_id')
            if identity not in jobs or identity in ambiguous:
                unmatched.append({'record_id': record['record_id'], 'job_id': identity})
                continue
            delta = {}
            for name, desired in jobs[identity].items():
                options[name].update(desired)
                if set(record.get(name) or []) != set(desired):
                    delta[name] = desired
            if delta:
                updates[record['record_id']] = delta
        schema_updates = []
        for field in fields:
            if field['name'] not in TARGETS:
                continue
            definition = {k: v for k, v in field.items() if k in ['name', 'type', 'description', 'multiple', 'options', 'default_value']}
            if field.get('dynamic_options_source'):
                raise ValueError('dynamic options are outside sync scope')
            definition['multiple'] = True
            existing = {o['name'] for o in definition['options']}
            definition['options'] = list(definition['options']) + [{'name': n, 'hue': 'Blue', 'lightness': 'Lighter'} for n in sorted(options[field['name']] - existing)]
            if not field.get('multiple') or options[field['name']] - existing:
                schema_updates.append({'field_id': field['id'], 'definition': definition})
        plan['tables'][table] = {'schema_updates': schema_updates, 'updates': updates,
                                'unmatched': unmatched, 'backup': meta}
    save(out / 'plan.json', plan)
    print(json.dumps({t: {'schema_updates': len(p['schema_updates']), 'record_updates': len(p['updates']),
                         'unmatched': len(p['unmatched'])} for t,p in plan['tables'].items()}), flush=True)
    return plan


def assert_current_values(current, old, updates):
    for record_id, delta in updates.items():
        if record_id not in current:
            raise ValueError('target record missing before update: ' + record_id)
        for field, desired in delta.items():
            actual = set(current[record_id].get(field) or [])
            if actual not in (set(old[record_id].get(field) or []), set(desired)):
                raise ValueError('target value changed after backup: ' + record_id + '/' + field)


def read_target_values(table, ids, path):
    args = ['+record-get', '--base-token', BASE, '--table-id', table,
            '--json', json.dumps({'record_id_list': ids}), '--format', 'ndjson',
            '--output', rel(path), '--overwrite']
    for name in TARGETS:
        args += ['--field-id', name]
    result = cli(*args)
    if result.get('record_not_found') or result.get('ignored_fields'):
        raise ValueError('record read omitted requested targets')
    return {r['record_id']: r for r in (json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line)}


def writable_schema(field):
    return {k: v for k, v in field.items() if k in
            ['name', 'type', 'description', 'multiple', 'options', 'default_value'] and v is not None}


def wait_schema_ready(table, expected, timeout=45):
    if not expected:
        return
    deadline = time.monotonic() + timeout
    while True:
        actual = {f['id']: f for f in full_fields(table)}
        if all(writable_schema(actual.get(fid, {})) == writable_schema(definition)
               for fid, definition in expected.items()):
            return
        if time.monotonic() >= deadline:
            raise ValueError('schema activation pending or changed; no record write: ' + table)
        time.sleep(2)


def apply_plan(out):
    plan_path = out / 'plan.json'; plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if plan['base'] != BASE or not valid_selection_for_snapshot(out, plan['tables']):
        raise ValueError('plan target mismatch')
    state_path = out / 'apply-status.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'plan_sha256': digest(plan_path), 'done': []}
    if state['plan_sha256'] != digest(plan_path):
        raise ValueError('plan changed after partial apply')
    if not state['done']:
        live = {t['id']: t for t in cli('+table-list', '--base-token', BASE, '--format', 'json')['data']['tables']}
        for table, data in plan['tables'].items():
            if live.get(table, {}).get('rev') != data['backup']['rev']:
                raise ValueError('table changed after backup; refresh before applying: ' + table)
    for table, data in plan['tables'].items():
        # Backups must still be readable and unmodified before any writes.
        meta = data['backup']
        if digest(Path(meta['records'])) != meta['records_sha256'] or digest(Path(meta['schema'])) != meta['schema_sha256']:
            raise ValueError('backup integrity mismatch')
        old_records = {r['record_id']: r for r in json.loads(Path(meta['records']).read_text(encoding='utf-8'))}
        old_fields = {f['id']: f for f in json.loads(Path(meta['schema']).read_text(encoding='utf-8'))}
        if any(f.get('remaining_options_count') for f in old_fields.values() if f['name'] in TARGETS):
            raise ValueError('incomplete backup schema cannot be applied')
        desired_for_resume = {c['field_id']: c['definition'] for c in data['schema_updates']
                              if table + '/' + c['field_id'] in state['done']}
        wait_schema_ready(table, desired_for_resume)
        current_fields = {f['id']: f for f in full_fields(table)}
        desired_fields = {c['field_id']: c['definition'] for c in data['schema_updates']}
        for field_id, original in old_fields.items():
            if original['name'] not in TARGETS:
                continue
            current = writable_schema(current_fields.get(field_id, {}))
            expected = writable_schema(desired_fields.get(field_id, original))
            if current not in (writable_schema(original), expected):
                raise ValueError('target schema changed after backup: ' + table + '/' + field_id)
            if table + '/' + field_id in state['done'] and current != expected:
                raise ValueError('previous schema update was changed externally')
        for change in data['schema_updates']:
            key = table + '/' + change['field_id']
            if key in state['done']:
                continue
            result = cli('+field-update', '--base-token', BASE, '--table-id', table,
                         '--field-id', change['field_id'], '--json', json.dumps(change['definition'], ensure_ascii=False), '--yes')
            save(out / ('response-' + key.replace('/', '-') + '.json'), result)
            state['done'].append(key); save(state_path, state)
        wait_schema_ready(table, desired_fields)
        rows = list(data['updates'].items())
        for start in range(0, len(rows), 200):
            key = table + '/records-' + str(start)
            if key in state['done']:
                continue
            body = out / (table + '.batch-' + str(start) + '.json')
            batch = dict(rows[start:start+200])
            current = read_target_values(table, list(batch), out / (table + '.prewrite-' + str(start) + '.ndjson'))
            assert_current_values(current, old_records, batch)
            save(body, {'update_records': batch})
            for attempt in range(4):
                try:
                    result = cli('+record-batch-update', '--base-token', BASE, '--table-id', table, '--json', '@'+rel(body))
                    break
                except RuntimeError as error:
                    if '800010401' not in str(error) or 'only one option' not in str(error) or attempt == 3:
                        raise
                    live_fields = {f['name']: f for f in full_fields(table)}
                    if any(not live_fields.get(name, {}).get('multiple') for delta in batch.values() for name in delta):
                        raise ValueError('multiselect schema is not active') from error
                    print(json.dumps({'schema_pending': table, 'retry': attempt + 1}), flush=True)
                    time.sleep(5 * (attempt + 1))
                    current = read_target_values(table, list(batch), out / (table + '.prewrite-' + str(start) + '.ndjson'))
                    assert_current_values(current, old_records, batch)
            if result.get('data', {}).get('ignored_fields'):
                raise ValueError('fields ignored during update')
            save(out / ('response-' + key.replace('/', '-') + '.json'), result)
            state['done'].append(key); save(state_path, state)
            print(json.dumps({'updated_table': table, 'processed': min(start+200, len(rows)), 'total': len(rows)}), flush=True)
    state['finished'] = True; save(state_path, state)


@contextmanager
def sync_lock():
    default = Path(__file__).resolve().parents[2] / 'research/qiuzhao-p1-sync-runtime/sync.lock'
    path = Path(os.environ.get('QIUZHAO_LARK_SYNC_LOCK_PATH', str(default)))
    path.parent.mkdir(parents=True, exist_ok=True)
    inherited = None
    try:
        descriptor = int(os.environ.get('QIUZHAO_LARK_SYNC_LOCK_FD', '-1'))
        actual, target = os.fstat(descriptor), path.stat()
        if (actual.st_dev, actual.st_ino) == (target.st_dev, target.st_ino):
            inherited = os.dup(descriptor)
    except (OSError, ValueError):
        pass
    with os.fdopen(inherited, 'a') if inherited is not None else path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield lock


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--jobs', type=Path)
    p.add_argument('--snapshot', action='store_true')
    p.add_argument('--plan', action='store_true')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--explain', action='store_true', help='sync qualification text without overwriting human text')
    p.add_argument('--deduplicate-exact', action='store_true', help='reconcile only full-cell identical known job IDs')
    p.add_argument('--sync-business', action='store_true', help='sync changed product business columns')
    p.add_argument('--sync-status', action='store_true', help='sync evidence-backed lifecycle states')
    p.add_argument('--append-p1', action='store_true', help='append missing verified P1 IDs to existing industry tables')
    args = p.parse_args(); out = args.output_dir; out.mkdir(parents=True, exist_ok=True)
    if args.snapshot:
        snapshot(out)
    if args.plan:
        if not args.jobs:
            p.error('--plan requires --jobs')
        make_plan(out, args.jobs)
    if args.apply:
        apply_plan(out)
    if args.explain or args.append_p1 or args.sync_status or args.sync_business or args.deduplicate_exact:
        if not args.jobs:
            p.error('--explain/--append-p1 requires --jobs')
        from qiuzhao.collector.lark_sync_enrichment import note_sync, append_p1, status_sync, business_sync, deduplicate_exact
        if args.deduplicate_exact:
            deduplicate_exact(out,args.jobs)
        if args.sync_business:
            business_sync(out,args.jobs)
        if args.sync_status:
            status_sync(out,args.jobs)
        if args.explain:
            note_sync(out, args.jobs)
        if args.append_p1:
            append_p1(out, args.jobs)


if __name__ == '__main__':
    with sync_lock():
        main()
