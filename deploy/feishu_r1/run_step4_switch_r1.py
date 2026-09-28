#!/usr/bin/env python3
"""STEP 4 (R1/20260923 batch) — switch the Base from the 8 current official (R0) tables to
the 10 imported mirror tables, and consolidate ALL old tables (the 8 outgoing R0 tables +
the 8 pre-existing "(20260920版)" tables) into one folder named exactly "待删除（旧版本）".

Adapted from mcp-suite-recovery-20260921/scripts/run_step4_switch.py for this batch:
  * LEGACY_TABLES -> the 8 CURRENT official tables (R0, published 2026-09-21); they are
    renamed to "<name>（20260921版）" before being archived (so the incoming tables can take
    the plain official names without a naming collision)
  * OFFICIAL_ORDER / OFFICIAL_BY_TEMP -> the 10 new tables driven by this batch's
    155,526-row projection (2/1/2/5 tables per group)
  * FOLDER_NAME -> "待删除（旧版本）" (per this batch's contract; distinct from the
    pre-existing "历史镜像（待清理）" folder, which the live Base still has and which
    already holds the 8 "(20260920版)" tables — contrary to the task briefing's claim that
    it had been deleted. Both the freshly-archived R0 tables AND those 8 pre-existing
    tables are moved into the NEW "待删除（旧版本）" folder; the old, now-empty
    "历史镜像（待清理）" folder is left in place untouched (nothing is deleted).
  * PRE_ARCHIVED adds the 8 "(20260920版)" tables: no rename needed, only the move.
Everything else (confirmation-gate handling, rate-limit retry, idempotent skip-on-already-
applied, critical-failure short circuit, fixed-id final readback) is copied verbatim.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = 'KaJIbYuIPacWersWD4jcO1AjnGh'
WORK = Path(os.environ.get('EXCEL_IMPORT_WORK')
            or '/Users/maxzhl/Projects/mcp-suite-recovery-20260921/feishu-20260923/work')
RUNS = WORK / 'runs'
OUT = Path(os.environ.get('EXCEL_IMPORT_OUT')
           or '/Users/maxzhl/Projects/mcp-suite-recovery-20260921/feishu-20260923/receipts')
LEGACY_SUFFIX = '（20260921版）'
FOLDER_NAME = '待删除（旧版本）'
# the 8 current official (R0) tables that this batch replaces
LEGACY_TABLES = [
    ('tbl4MpGJdhrmZbqx', '互联网科技岗'), ('tbl3n6KH9fv95xec', '互联网科技岗·续表1'),
    ('tbl1myUlUDUtp0k8', '国企央企岗'), ('tbl1Ml7WshEr9qW3', '制造工业岗'),
    ('tbl64ozef9QjLftm', '制造工业岗·续表1'), ('tbl4mnIRKO4jaQqI', '其他行业岗'),
    ('tblWY3Wan6gCSifM', '其他行业岗·续表1'), ('tbl1l2t6rEEF70vO', '其他行业岗·续表2'),
]
LEGACY_IDS = {tid for tid, _ in LEGACY_TABLES}
# the 8 pre-existing "(20260920版)" rollback tables: already correctly named, only moved
PRE_ARCHIVED = [
    ('tbl3Qd2coJ02xhMe', '互联网科技岗（20260920版）'),
    ('tbl5Y72YI5NDn2SM', '互联网科技岗·续表1（20260920版）'),
    ('tbl3AKwAgZOAYjwN', '国企央企岗（20260920版）'),
    ('tbl6sXDYVscOMLu2', '制造工业岗（20260920版）'),
    ('tbl1wfxv9pFoQd9s', '制造工业岗·续表1（20260920版）'),
    ('tbl6eaCyeeAC0WKB', '其他行业岗（20260920版）'),
    ('tbl7HJZXxpccpz8A', '其他行业岗·续表1（20260920版）'),
    ('tbl36Su1rLz5HTWO', '其他行业岗·续表2（20260920版）'),
]
OFFICIAL_ORDER = ['互联网科技岗', '互联网科技岗·续表1', '国企央企岗', '制造工业岗',
                  '制造工业岗·续表1', '其他行业岗', '其他行业岗·续表1', '其他行业岗·续表2',
                  '其他行业岗·续表3', '其他行业岗·续表4']
OFFICIAL_BY_TEMP = {'待切换-20260923-' + name: name for name in OFFICIAL_ORDER}
AUTHORISED_ACTIONS = {'base +table-update', 'base +base-block-create', 'base +base-block-move'}
STATE = WORK / 'switch-state.json'


def run(args, cwd=None, timeout=180):
    started = time.time()
    proc = subprocess.run(['lark-cli', *args, '--as', 'user'], cwd=cwd, timeout=timeout,
                          capture_output=True, text=True)
    body = None
    for stream in (proc.stdout, proc.stderr):
        try:
            body = json.loads(stream)
            break
        except ValueError:
            continue
    if body is None:
        body = {'ok': False, 'raw_stdout': proc.stdout[-1500:], 'raw_stderr': proc.stderr[-1500:]}
    return {'argv': args, 'exit_code': proc.returncode, 'seconds': round(time.time() - started, 2),
            'body': body}


def cli(args, cwd=None, timeout=180):
    out = run(args, cwd, timeout)
    err = out['body'].get('error') or {}
    if out['exit_code'] == 10 and err.get('subtype') == 'confirmation_required':
        action = err.get('action') or ''
        if action not in AUTHORISED_ACTIONS:
            raise SystemExit(f'refusing unauthorised confirmation gate: {json.dumps(out)[:400]}')
        gate = {'action': action, 'risk': err.get('risk'), 'hint': err.get('hint'),
                'note': 'pre-authorised by the task contract'}
        out = run([*args, '--yes'], cwd, timeout)
        out['confirmation_gate'] = gate
    return out


_cli_once = cli
_last_table_update = 0.0


def cli(args, cwd=None, timeout=180):
    global _last_table_update
    if args[:2] != ['base', '+table-update']:
        return _cli_once(args, cwd, timeout)
    started = time.monotonic()
    for attempt in range(4):
        pause = max(0.0, 3.0 - (time.monotonic() - _last_table_update))
        if pause:
            time.sleep(pause)
        out = _cli_once(args, cwd, timeout)
        _last_table_update = time.monotonic()
        if str((out['body'].get('error') or {}).get('code')) != '800004135':
            out['rate_limit_retries'] = attempt
            out['seconds'] = round(time.monotonic() - started, 2)
            return out
        if attempt < 3:
            delay = 5 * (2 ** attempt)
            print(json.dumps({'table_update_rate_limited': True, 'attempt': attempt + 1,
                              'retry_after_seconds': delay}), flush=True)
            time.sleep(delay)
    out['rate_limit_retries'] = 3
    out['seconds'] = round(time.monotonic() - started, 2)
    return out


def blocks():
    out = cli(['base', '+base-block-list', '--base-token', BASE])
    if not out['body'].get('ok'):
        raise SystemExit(f'base-block-list failed: {json.dumps(out)[:400]}')
    return out['body']['data']['blocks']


def save_state(state):
    state['updated_at'] = dt.datetime.now().isoformat()
    tmp = STATE.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, STATE)


def verify_gate():
    receipts = sorted(RUNS.glob('*/verify-receipt.json'))
    if not receipts:
        raise SystemExit('no verify receipt; run --phase verify first')
    v = json.loads(receipts[-1].read_text(encoding='utf-8'))
    import_receipts = sorted(RUNS.glob('*/import-receipt.json'))
    imp = json.loads(import_receipts[-1].read_text(encoding='utf-8'))
    problems = []
    if v.get('outcome') != 'completed' or not v.get('gate_passed'):
        problems.append(f"verify outcome={v.get('outcome')} gate={v.get('gate_passed')}")
    if v.get('base_token') != BASE:
        problems.append('verify receipt base_token mismatch')
    if v.get('projection_sha256_on_disk') != v.get('source_projection_sha256_gz'):
        problems.append('projection hash changed between build and verify')
    if imp.get('outcome') != 'completed':
        problems.append(f"import outcome={imp.get('outcome')}")
    if imp.get('batch_identity', {}).get('source_projection_sha256_gz') != \
            v.get('source_projection_sha256_gz'):
        problems.append('import and verify refer to different projection hashes')
    if sorted(v.get('expected_tables') or []) != sorted(OFFICIAL_BY_TEMP):
        problems.append('verify expected_tables != the 10 official names')
    xml = json.loads((WORK / 'xlsx-manifest.json').read_text(encoding='utf-8'))
    expected_sha = {f['table_name']: f['sha256'] for f in xml['files']}
    for name, sha in (v.get('xlsx_sha256_on_disk') or {}).items():
        if expected_sha.get(name) != sha:
            problems.append(f'xlsx hash mismatch for {name}')
    names = [t.get('table_name') for t in v.get('tables', [])]
    ids = [t.get('table_id') for t in v.get('tables', [])]
    if sorted(names) != sorted(OFFICIAL_BY_TEMP):
        problems.append(f'verify tables do not cover the 10 expected names: {names}')
    if len(set(ids)) != len(ids):
        problems.append('verify table ids are not unique')
    if set(ids) & LEGACY_IDS:
        problems.append('a legacy table id appears on the new side')
    bound = imp.get('targets_bound') or {}
    if bound != {n: i for i, n in zip(ids, names)}:
        problems.append('import binding does not match the verify table ids')
    if set(bound.values()) & LEGACY_IDS:
        problems.append('import binding contains a legacy table id')
    pre = {t['id'] for t in imp.get('tables_before', [])}
    if set(bound.values()) & pre:
        problems.append('import binding is not disjoint from the pre-import table set')
    for t in v.get('tables', []):
        tag = t.get('table_name')
        if not t.get('schema_ok'):
            problems.append(f'{tag}: schema')
        if not t.get('rows_ok'):
            problems.append(f'{tag}: rows')
        if 'duplicate_job_ids' not in t or t.get('duplicate_job_ids') != 0:
            problems.append(f'{tag}: duplicate_job_ids missing or non-zero')
        if 'null_job_ids' not in t or t.get('null_job_ids') != 0:
            problems.append(f'{tag}: null_job_ids missing or non-zero')
        if not t.get('id_set_ok'):
            problems.append(f'{tag}: job_id set')
        if not t.get('cells_ok'):
            problems.append(f'{tag}: cell comparison')
        if not t.get('view_order_ok'):
            problems.append(f'{tag}: view order')
        if not t.get('primary_field_ok'):
            problems.append(f'{tag}: primary field')
    if problems:
        raise SystemExit('verify gate failed: ' + json.dumps(problems[:12], ensure_ascii=False))
    return receipts[-1], v, import_receipts[-1], imp


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='perform the switch (gated)')
    args = ap.parse_args()
    verify_path, verify, imp_path, imp = verify_gate()
    new_tables = [(t['table_id'], t['table_name']) for t in verify['tables']]
    if sorted(n for _, n in new_tables) != sorted(OFFICIAL_BY_TEMP):
        raise SystemExit('new tables are not exactly the 10 expected temporary names')
    new_ids = {tid for tid, _ in new_tables}
    if new_ids & LEGACY_IDS:
        raise SystemExit('new table id collides with the legacy allowlist')
    live_blocks = {t['id']: t for t in blocks()}
    for tid, name in LEGACY_TABLES:
        got = live_blocks.get(tid, {}).get('name')
        if got not in (name, name + LEGACY_SUFFIX):
            raise SystemExit(f'legacy allowlist mismatch for {tid}: {got!r} is neither '
                             f'{name!r} nor {name + LEGACY_SUFFIX!r}')
    for tid, name in PRE_ARCHIVED:
        got = live_blocks.get(tid, {}).get('name')
        if got != name:
            raise SystemExit(f'pre-archived allowlist mismatch for {tid}: {got!r} != {name!r}')

    if not args.apply:
        print(json.dumps({'dry_run': True, 'gate_passed': True,
                          'legacy': LEGACY_TABLES, 'pre_archived': PRE_ARCHIVED,
                          'new': new_tables, 'temp_to_official': OFFICIAL_BY_TEMP},
                         ensure_ascii=False, indent=1))
        return 0
    batch = {'verify_receipt': str(verify_path), 'import_receipt': str(imp_path),
             'legacy': [list(x) for x in LEGACY_TABLES],
             'pre_archived': [list(x) for x in PRE_ARCHIVED],
             'new_tables': [list(x) for x in new_tables]}
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else \
        {'step': 'switch', 'started_at': dt.datetime.now().isoformat(), 'actions': {},
         'folder_id': None}
    if state.get('batch') and state['batch'] != batch:
        raise SystemExit('switch-state.json belongs to a different batch; refusing to continue')
    state['batch'] = batch
    state['critical_failure'] = None
    state['critical_failure_history'] = (state.get('critical_failure_history') or [])[-4:]
    state['verify_receipt'] = str(verify_path)
    state['import_receipt'] = str(imp_path)
    receipt = {'step': 'switch', 'base_token': BASE, 'started_at': state['started_at'],
               'verify_receipt': str(verify_path), 'import_receipt': str(imp_path),
               'legacy_tables': LEGACY_TABLES, 'pre_archived_tables': PRE_ARCHIVED,
               'new_tables': new_tables, 'temp_to_official': OFFICIAL_BY_TEMP,
               'actions': [], 'outcome': 'failed'}
    save_state(state)

    def act(key, fn):
        result = fn()
        entry = {'key': key, 'ok': bool(result['body'].get('ok')), 'body': result['body'],
                 'seconds': result['seconds']}
        if result.get('confirmation_gate'):
            entry['confirmation_gate'] = result['confirmation_gate']
        state['actions'][key] = {'ok': entry['ok'], 'at': dt.datetime.now().isoformat()}
        save_state(state)
        receipt['actions'].append(entry)
        return entry['ok']

    live = {t['id']: t for t in blocks()}

    # 1. legacy (outgoing R0) rename (critical)
    for tid, name in LEGACY_TABLES:
        target = name + LEGACY_SUFFIX
        if live.get(tid, {}).get('name') == target:
            receipt['actions'].append({'key': f'rename_legacy:{tid}', 'skipped': 'already renamed'})
            state['actions'][f'rename_legacy:{tid}'] = {'ok': True}
            continue
        if live.get(tid, {}).get('name') != name:
            state['critical_failure'] = f'legacy {tid} has an unexpected name'
            save_state(state)
            break
        if not act(f'rename_legacy:{tid}',
                    lambda tid=tid, target=target: cli(
                        ['base', '+table-update', '--base-token', BASE, '--table-id', tid,
                         '--name', target])):
            state['critical_failure'] = f'legacy rename failed for {tid}'
            save_state(state)
            break

    # 2. new tables take the official names (critical)
    if not state.get('critical_failure'):
        for tid, temp in new_tables:
            official = OFFICIAL_BY_TEMP[temp]
            live = {t['id']: t for t in blocks()}
            if live.get(tid, {}).get('name') == official:
                receipt['actions'].append({'key': f'rename_new:{tid}', 'skipped': 'already renamed'})
                state['actions'][f'rename_new:{tid}'] = {'ok': True}
                continue
            if live.get(tid, {}).get('name') != temp:
                state['critical_failure'] = f'new table {tid} has an unexpected name'
                save_state(state)
                break
            if not act(f'rename_new:{tid}',
                       lambda tid=tid, official=official: cli(
                           ['base', '+table-update', '--base-token', BASE, '--table-id', tid,
                            '--name', official])):
                state['critical_failure'] = f'new rename failed for {tid}'
                save_state(state)
                break

    if not state.get('critical_failure'):
        named = {x['id']: x for x in blocks()}
        if not all(named.get(tid, {}).get('name') == OFFICIAL_BY_TEMP[temp] for tid, temp in new_tables):
            state['critical_failure'] = 'new official names failed readback before archival'
            save_state(state)

    # 3. archive folder: create (if missing) and move BOTH the renamed-outgoing R0 tables
    #    AND the 8 pre-existing "(20260920版)" tables into it (non-critical)
    if not state.get('critical_failure'):
        live = {t['id']: t for t in blocks()}
        folder = next((b for b in live.values()
                       if b.get('type') == 'folder' and b.get('name') == FOLDER_NAME), None)
        if folder is None:
            out = cli(['base', '+base-block-create', '--base-token', BASE, '--type', 'folder',
                       '--name', FOLDER_NAME])
            receipt['actions'].append({'key': 'create_folder', 'ok': bool(out['body'].get('ok')),
                                       'body': out['body']})
            if out['body'].get('ok'):
                data = out['body'].get('data') or {}
                state['folder_id'] = (data.get('block_id') or data.get('id')
                                      or (data.get('block') or {}).get('id'))
        else:
            state['folder_id'] = folder['id']
            receipt['actions'].append({'key': 'create_folder', 'skipped': 'folder already exists',
                                       'folder_id': folder['id']})
        save_state(state)
        for tid, name in LEGACY_TABLES + PRE_ARCHIVED:
            live = {t['id']: t for t in blocks()}
            if not state.get('folder_id'):
                receipt['actions'].append({'key': f'move_old:{tid}', 'ok': False,
                                           'reason': 'no folder id'})
                continue
            if live.get(tid, {}).get('parent_id') == state['folder_id']:
                receipt['actions'].append({'key': f'move_old:{tid}', 'skipped': 'already moved'})
                state['actions'][f'move_old:{tid}'] = {'ok': True}
                continue
            act(f'move_old:{tid}',
                lambda tid=tid: cli(['base', '+base-block-move', '--base-token', BASE,
                                     '--block-id', tid, '--parent-id', state['folder_id']]))

    # 4. official order for the new 10 tables at root (non-critical)
    if not state.get('critical_failure'):
        by_official = {OFFICIAL_BY_TEMP[temp]: tid for tid, temp in new_tables}
        for i in range(1, len(OFFICIAL_ORDER)):
            prev, cur = by_official[OFFICIAL_ORDER[i - 1]], by_official[OFFICIAL_ORDER[i]]
            order_now = [b['id'] for b in blocks() if b.get('parent_id') is None]
            if cur in order_now and prev in order_now and \
                    order_now.index(cur) == order_now.index(prev) + 1:
                receipt['actions'].append({'key': f'order:{cur}', 'skipped': 'already ordered'})
                state['actions'][f'order:{cur}'] = {'ok': True}
                continue
            act(f'order:{cur}', lambda cur=cur, prev=prev: cli(
                ['base', '+base-block-move', '--base-token', BASE, '--block-id', cur,
                 '--after-id', prev]))

    # 5. final readback by fixed id
    final = blocks()
    receipt['final_blocks'] = final
    receipt['readback'] = {}
    folder_block = next((b for b in final if b['id'] == state.get('folder_id')), None) \
        if state.get('folder_id') else None
    receipt['folder_readback'] = {'folder_id': state.get('folder_id'),
                                  'block': folder_block,
                                  'is_folder': bool(folder_block)
                                  and folder_block.get('type') == 'folder'}
    old_tables = LEGACY_TABLES + PRE_ARCHIVED
    for tid, name in LEGACY_TABLES:
        blk = next((b for b in final if b['id'] == tid), None)
        in_folder = (bool(state.get('folder_id')) and bool(blk)
                     and blk.get('parent_id') == state.get('folder_id')
                     and bool(folder_block) and folder_block.get('type') == 'folder')
        receipt['readback'][tid] = {'name': blk and blk.get('name'),
                                    'parent_id': blk and blk.get('parent_id'),
                                    'expected_name': name + LEGACY_SUFFIX,
                                    'in_folder': in_folder}
    for tid, name in PRE_ARCHIVED:
        blk = next((b for b in final if b['id'] == tid), None)
        in_folder = (bool(state.get('folder_id')) and bool(blk)
                     and blk.get('parent_id') == state.get('folder_id')
                     and bool(folder_block) and folder_block.get('type') == 'folder')
        receipt['readback'][tid] = {'name': blk and blk.get('name'),
                                    'parent_id': blk and blk.get('parent_id'),
                                    'expected_name': name,
                                    'in_folder': in_folder}
    for tid, temp in new_tables:
        blk = next((b for b in final if b['id'] == tid), None)
        receipt['readback'][tid] = {'name': blk and blk.get('name'),
                                    'parent_id': blk and blk.get('parent_id'),
                                    'expected_name': OFFICIAL_BY_TEMP[temp],
                                    'at_root': bool(blk) and blk.get('parent_id') is None}
    root_new = [b['name'] for b in final if b.get('parent_id') is None and b['id'] in new_ids]
    receipt['root_order_new'] = root_new
    receipt['order_ok'] = root_new == OFFICIAL_ORDER
    legacy_ok = all(receipt['readback'][tid]['name'] == receipt['readback'][tid]['expected_name']
                    for tid, _ in LEGACY_TABLES)
    pre_archived_named_ok = all(
        receipt['readback'][tid]['name'] == receipt['readback'][tid]['expected_name']
        for tid, _ in PRE_ARCHIVED)
    new_ok = all(receipt['readback'][tid]['name'] == receipt['readback'][tid]['expected_name']
                 and receipt['readback'][tid]['at_root'] for tid, _ in new_tables)
    archived_ok = all(receipt['readback'][tid]['in_folder'] for tid, _ in old_tables)
    receipt['legacy_named_ok'] = legacy_ok
    receipt['pre_archived_named_ok'] = pre_archived_named_ok
    receipt['new_named_ok'] = new_ok
    receipt['folder_id'] = state.get('folder_id')
    receipt['archived_ok'] = archived_ok
    if state.get('critical_failure'):
        receipt['outcome'] = 'failed'
        receipt['failure'] = state['critical_failure']
    elif legacy_ok and pre_archived_named_ok and new_ok and receipt['order_ok'] and archived_ok:
        receipt['outcome'] = 'completed'
    elif legacy_ok and pre_archived_named_ok and new_ok and receipt['order_ok']:
        receipt['outcome'] = 'partial_archive'
        receipt['archive_note'] = ('names/order are correct but the folder move is unavailable '
                                   'or incomplete for at least one old table')
    else:
        receipt['outcome'] = 'failed'
    receipt['finished_at'] = dt.datetime.now().isoformat()
    path = Path(state['verify_receipt']).parent / 'switch-receipt.json'
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'switch-receipt.json').write_text(
            json.dumps({k: receipt[k] for k in
                        ('step', 'base_token', 'outcome', 'order_ok', 'legacy_named_ok',
                         'pre_archived_named_ok', 'new_named_ok', 'archived_ok', 'folder_id',
                         'root_order_new', 'failure', 'archive_note', 'finished_at')
                        if k in receipt},
                       ensure_ascii=False, indent=1), encoding='utf-8')
    except OSError:
        pass
    print(json.dumps({'outcome': receipt['outcome'], 'order_ok': receipt['order_ok'],
                      'archived_ok': archived_ok, 'root_order_new': root_new,
                      'receipt': str(path)}, ensure_ascii=False))
    return 0 if receipt['outcome'] == 'completed' else 1


if __name__ == '__main__':
    sys.exit(main())
