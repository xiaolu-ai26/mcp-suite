#!/usr/bin/env python3
"""STEP 2 (R1/20260923 batch) — serial `drive +import --type bitable --target-token <BASE>`.

Adapted from mcp-suite-recovery-20260921/scripts/run_step2_import.py: only WORK path and the
allowlist of pre-existing table ids (now 16: 8 current official R0 tables + 8 "(20260920版)"
tables) change. Logic copied verbatim.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = 'KaJIbYuIPacWersWD4jcO1AjnGh'
WORK = Path(os.environ.get('EXCEL_IMPORT_WORK')
            or '/Users/maxzhl/Projects/mcp-suite-recovery-20260921/feishu-20260923/work')
XLSX = WORK / 'xlsx'
RUNS = WORK / 'runs'
STATE = WORK / 'import-state.json'
# all 16 tables that exist in the Base before this batch starts: 8 current official (R0,
# published 2026-09-21) + 8 "(20260920版)" rollback tables. None of these may ever be
# mistaken for a newly-imported table.
LEGACY_IDS = {
    'tbl4MpGJdhrmZbqx', 'tbl3n6KH9fv95xec', 'tbl1myUlUDUtp0k8', 'tbl1Ml7WshEr9qW3',
    'tbl64ozef9QjLftm', 'tbl4mnIRKO4jaQqI', 'tblWY3Wan6gCSifM', 'tbl1l2t6rEEF70vO',
    'tbl3Qd2coJ02xhMe', 'tbl5Y72YI5NDn2SM', 'tbl3AKwAgZOAYjwN', 'tbl6sXDYVscOMLu2',
    'tbl1wfxv9pFoQd9s', 'tbl6eaCyeeAC0WKB', 'tbl7HJZXxpccpz8A', 'tbl36Su1rLz5HTWO',
}
CONCURRENCY_CODES = ('232140101', '232140100', '233523001')
NOT_ACCEPTED_ERROR_TYPES = ('validation',)
IMPORT_TIMEOUT = 420
POLL_ROUNDS = 20
POLL_SLEEP = 6


def cli(args, cwd=None, timeout=120):
    started = time.time()
    proc = subprocess.run(['lark-cli', *args, '--as', 'user'], cwd=cwd, timeout=timeout,
                          capture_output=True, text=True)
    try:
        body = json.loads(proc.stdout)
    except ValueError:
        body = {'ok': False, 'raw_stdout': proc.stdout[-2000:], 'raw_stderr': proc.stderr[-2000:]}
    return {'argv': args, 'exit_code': proc.returncode, 'seconds': round(time.time() - started, 2),
            'body': body, 'stderr_tail': proc.stderr[-800:]}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for blk in iter(lambda: fh.read(1 << 22), b''):
            h.update(blk)
    return h.hexdigest()


def batch_identity(manifest):
    ident = {'source_projection_sha256_gz': sha256_file(WORK / 'projection.ndjson.gz'),
             'xlsx': {}}
    for item in manifest['files']:
        ident['xlsx'][item['table_name']] = sha256_file(Path(item['path']))
    return ident


def check_identity(manifest):
    live = batch_identity(manifest)
    problems = []
    if live['source_projection_sha256_gz'] != manifest['source_projection_sha256_gz']:
        problems.append('projection sha256 changed on disk')
    for item in manifest['files']:
        if live['xlsx'][item['table_name']] != item['sha256']:
            problems.append(f"xlsx sha256 changed on disk: {item['table_name']}")
    if problems:
        raise SystemExit('batch identity check failed: ' + json.dumps(problems, ensure_ascii=False))
    return live


def table_map():
    out = cli(['base', '+table-list', '--base-token', BASE])
    if not out['body'].get('ok'):
        raise SystemExit(f'table-list failed: {json.dumps(out)[:600]}')
    tables = out['body']['data']['tables']
    return {t['name']: t for t in tables}, tables


def save_state(state):
    state['updated_at'] = dt.datetime.now().isoformat()
    tmp = STATE.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, STATE)


def load_state(manifest, ident):
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding='utf-8'))
        if state.get('batch_identity') != ident:
            raise SystemExit('import-state.json belongs to a different batch; refusing to continue')
        return state
    return {'step': 'import', 'base_token': BASE, 'batch_identity': ident,
            'created_at': dt.datetime.now().isoformat(), 'targets': {}}


def poll_ticket(ticket, record, state, receipt_path, receipt):
    polls = []
    for rounds in range(1, POLL_ROUNDS + 1):
        time.sleep(POLL_SLEEP)
        poll = cli(['drive', '+task_result', '--scenario', 'import', '--ticket', ticket])
        polls.append({'round': rounds, 'body': poll['body']})
        pdata = poll['body'].get('data') or {}
        if pdata.get('ready'):
            record['polls'] = polls
            record['import_status'] = {k: pdata.get(k) for k in
                                       ('ready', 'job_status', 'job_status_label',
                                        'job_error_msg', 'type', 'token')}
            ready_ok = str(pdata.get('job_status_label') or '').lower() in ('success', '') \
                and not pdata.get('job_error_msg') and not pdata.get('job_status')
            record['import_ok'] = bool(ready_ok)
            return 'ready'
        if poll['body'].get('ok') is False:
            break
    record['polls'] = polls
    record['import_ok'] = False
    return 'unknown'


def finish(receipt, receipt_path, outcome, message=None, detail=None):
    receipt['finished_at'] = dt.datetime.now().isoformat()
    receipt['outcome'] = outcome
    if message:
        receipt['outcome_message'] = message
    if detail is not None:
        receipt['outcome_detail'] = detail
    try:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
    except OSError as exc:
        print(json.dumps({'receipt_write_error': repr(exc)}, ensure_ascii=False), file=sys.stderr)
    print(json.dumps({'outcome': outcome, 'message': message, 'detail': detail},
                     ensure_ascii=False))
    return 0 if outcome == 'completed' else 1


def main():
    manifest = json.loads((WORK / 'xlsx-manifest.json').read_text(encoding='utf-8'))
    files = manifest['files']
    names = [f['table_name'] for f in files]
    if len(set(names)) != len(names):
        raise SystemExit('duplicate target table names in the xlsx manifest')
    ident = check_identity(manifest)

    state = load_state(manifest, ident)
    run_dir = RUNS / (state.get('run_dir_name') or dt.datetime.now().strftime('%Y%m%dT%H%M%S'))
    run_dir.mkdir(parents=True, exist_ok=True)
    state['run_dir_name'] = run_dir.name
    receipt_path = run_dir / 'import-receipt.json'
    receipt = {'step': 'import', 'base_token': BASE, 'outcome': 'failed',
               'started_at': dt.datetime.now().isoformat(),
               'lark_cli_version': subprocess.run(['lark-cli', '--version'], capture_output=True,
                                                  text=True).stdout.strip(),
               'xlsx_manifest': str(WORK / 'xlsx-manifest.json'),
               'batch_identity': ident, 'expected_target_names': names, 'results': []}
    by_name = {}
    if 'batch_pre_ids' in state:
        pre_ids = set(state['batch_pre_ids'])
        receipt['tables_before'] = state.get('tables_before', [])
        receipt['tables_before_source'] = 'reused from the batch state (not rescanned)'
    else:
        _, before_tables = table_map()
        state['tables_before'] = before_tables
        state['batch_pre_ids'] = [t['id'] for t in before_tables]
        state['batch_pre_ids_at'] = dt.datetime.now().isoformat()
        save_state(state)
        receipt['tables_before'] = before_tables
        receipt['tables_before_source'] = 'captured on the first run of this batch'
        pre_ids = set(state['batch_pre_ids'])
    for tid in LEGACY_IDS:
        if tid not in pre_ids:
            raise SystemExit(f'legacy table {tid} missing before the import; refusing to start')

    for item in files:
        target = item['table_name']
        record = by_name.get(target) or {'table_name': target, 'xlsx': item['path'],
                                         'xlsx_sha256': item['sha256'],
                                         'expected_rows': item['rows']}
        record['started_at'] = record.get('started_at') or dt.datetime.now().isoformat()
        if target not in by_name:
            receipt['results'].append(record)
        by_name[target] = record
        st = state['targets'].get(target, {})

        if st.get('status') == 'completed' and st.get('table_id'):
            names_now, _ = table_map()
            live = names_now.get(target)
            if live and live['id'] == st['table_id'] and live.get('records_count') == item['rows']:
                record.update({'status': 'already_completed', 'table_id': st['table_id'],
                               'records_count_reported': live.get('records_count')})
                save_state(state)
                receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1),
                                        encoding='utf-8')
                print(json.dumps({'skip': target, 'table_id': st['table_id']}, ensure_ascii=False),
                      flush=True)
                continue
            return finish(receipt, receipt_path, 'failed',
                          f'{target}: completed state no longer matches the live Base')

        if st.get('status') == 'unknown_without_ticket':
            return finish(receipt, receipt_path, 'needs_input',
                          f'{target}: previous run ended with an unknown submit outcome; '
                          'no resubmission is allowed without manual resolution',
                          {'unknown_reason': st.get('unknown_reason')})
        if st.get('status') == 'ticketed' and not st.get('ticket'):
            st['status'] = 'unknown_without_ticket'
            st['unknown_reason'] = 'ticketed state without a ticket'
            save_state(state)
            return finish(receipt, receipt_path, 'needs_input',
                          f'{target}: ticketed state carries no ticket; unknown outcome')
        if st.get('ticket'):
            record['ticket'] = st['ticket']
            record['note'] = 'resumed from stored ticket; no resubmission'
            verdict = poll_ticket(st['ticket'], record, state, receipt_path, receipt)
            if verdict != 'ready':
                st['status'] = 'unknown'
                state['targets'][target] = st
                save_state(state)
                return finish(receipt, receipt_path, 'needs_input',
                              f'{target}: ticket {st["ticket"]} outcome still unknown; '
                              'no resubmission attempted')
            if not record.get('import_ok'):
                st['status'] = 'import_failed'
                state['targets'][target] = st
                save_state(state)
                return finish(receipt, receipt_path, 'failed',
                              f'{target}: import task reported failure')
        elif st.get('status') == 'submitting':
            return finish(receipt, receipt_path, 'needs_input',
                          f'{target}: a submit was recorded without a persisted ticket; '
                          'status unknown, refusing to resubmit')
        elif st.get('status') not in (None, 'rejected_not_accepted'):
            return finish(receipt, receipt_path, 'needs_input',
                          f'{target}: previous state {st.get("status")!r} needs manual review; '
                          'no resubmission attempted',
                          {'state': {k: v for k, v in st.items() if k != 'snapshot_table_ids'}})
        else:
            check_identity(manifest)
            _, snapshot_tables = table_map()
            st = {'status': 'submitting', 'xlsx_sha256': item['sha256'],
                  'snapshot_table_ids': sorted(set(
                      [t['id'] for t in snapshot_tables]
                      + list(st.get('snapshot_table_ids') or []))),
                  'snapshot_at': dt.datetime.now().isoformat(),
                  'snapshot_rescans': st.get('snapshot_rescans', 0) + 1,
                  'submitting_at': dt.datetime.now().isoformat(), 'attempts': st.get('attempts', 0) + 1}
            state['targets'][target] = st
            save_state(state)
            result = cli(['drive', '+import', '--file', Path(item['path']).name, '--type', 'bitable',
                          '--target-token', BASE], cwd=str(XLSX), timeout=IMPORT_TIMEOUT)
            record['import'] = result
            data = result['body'].get('data') or {}
            ticket = data.get('ticket')
            st['ticket'] = ticket
            st['status'] = 'ticketed'
            st['import_exit_code'] = result['exit_code']
            state['targets'][target] = st
            save_state(state)
            record['import_status'] = {k: data.get(k) for k in
                                       ('ready', 'timed_out', 'job_status', 'job_status_label',
                                        'job_error_msg', 'type', 'token', 'ticket')}
            if result['body'].get('ok') and data.get('ready'):
                record['import_ok'] = str(data.get('job_status_label') or '').lower() in ('success', '') \
                    and not data.get('job_error_msg') and not data.get('job_status')
            elif ticket:
                verdict = poll_ticket(ticket, record, state, receipt_path, receipt)
                if verdict != 'ready':
                    st['status'] = 'unknown'
                    save_state(state)
                    return finish(receipt, receipt_path, 'needs_input',
                                  f'{target}: ticket {ticket} not resolved')
                if not record.get('import_ok'):
                    st['status'] = 'import_failed'
                    save_state(state)
                    return finish(receipt, receipt_path, 'failed',
                                  f'{target}: import task reported failure')
            else:
                blob = json.dumps(result['body'], ensure_ascii=False)
                err = result['body'].get('error') or {}
                rejected = (result['body'].get('ok') is False
                            and err.get('type') in NOT_ACCEPTED_ERROR_TYPES)
                if rejected:
                    st['status'] = 'rejected_not_accepted'
                    st['rejected_error'] = err
                    save_state(state)
                    return finish(receipt, receipt_path, 'failed',
                                  f'{target}: the request was rejected before acceptance '
                                  '(whitelisted client-side error); rerun may resubmit',
                                  {'error': err})
                if any(code in blob for code in CONCURRENCY_CODES):
                    st['status'] = 'unknown_without_ticket'
                    st['unknown_reason'] = 'concurrent-import conflict without a ticket'
                    save_state(state)
                    return finish(receipt, receipt_path, 'needs_input',
                                  f'{target}: concurrent-import conflict without a ticket; '
                                  'treated as unknown, rerun only polls (no resubmission)')
                st['status'] = 'unknown_without_ticket'
                st['unknown_reason'] = 'non-JSON, empty or ticket-less response'
                st['unknown_body'] = blob[:2000]
                save_state(state)
                return finish(receipt, receipt_path, 'needs_input',
                              f'{target}: response carried no ticket; the request may or may '
                              'not have been accepted, so no resubmission is allowed')

        names_now, after_tables = table_map()
        new_blocks = [t for t in after_tables if t['id'] not in pre_ids]
        matches = [t for t in after_tables if t['name'] == target]
        record['new_blocks'] = new_blocks
        record['tables_after_count'] = len(after_tables)
        if len(matches) != 1:
            st['status'] = 'unbound'
            save_state(state)
            return finish(receipt, receipt_path, 'failed',
                          f'{target}: expected exactly one table named {target}',
                          {'matches': matches, 'new_blocks': new_blocks})
        created = matches[0]
        if st.get('snapshot_table_ids') and created['id'] in set(st['snapshot_table_ids']):
            st['status'] = 'unbound'
            save_state(state)
            return finish(receipt, receipt_path, 'failed',
                          f'{target}: the named table already existed before this submit')
        if created['id'] in LEGACY_IDS or created['id'] in pre_ids:
            st['status'] = 'unbound'
            save_state(state)
            return finish(receipt, receipt_path, 'failed',
                          f'{target}: new block collides with a pre-existing table')
        if any(v.get('table_id') == created['id'] and k != target
               for k, v in state['targets'].items()):
            st['status'] = 'unbound'
            save_state(state)
            return finish(receipt, receipt_path, 'failed',
                          f'{target}: table id already bound to another target')
        record.update({'table_id': created['id'], 'table_name_actual': created['name'],
                       'records_count_reported': created.get('records_count')})
        if created.get('records_count') != item['rows']:
            st['status'] = 'row_mismatch'
            save_state(state)
            return finish(receipt, receipt_path, 'failed',
                          f'{target}: imported row count mismatch',
                          {'live': created.get('records_count'), 'expected': item['rows']})
        st.update({'status': 'completed', 'table_id': created['id'],
                   'records_count': created.get('records_count'),
                   'completed_at': dt.datetime.now().isoformat()})
        state['targets'][target] = st
        save_state(state)
        record['status'] = 'imported'
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
        print(json.dumps({'table': target, 'status': 'imported', 'table_id': created['id'],
                          'rows': created.get('records_count')}, ensure_ascii=False), flush=True)

    receipt['targets_bound'] = {k: v.get('table_id') for k, v in state['targets'].items()}
    return finish(receipt, receipt_path, 'completed', None, {'run_dir': str(run_dir)})


if __name__ == '__main__':
    sys.exit(main())
