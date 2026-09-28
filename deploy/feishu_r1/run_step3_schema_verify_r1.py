#!/usr/bin/env python3
"""STEP 3 (R1/20260923 batch) — schema fix / clean-blank / verify for the NEW tables.

Adapted from mcp-suite-recovery-20260921/scripts/run_step3_schema_verify.py:
  * WORK path -> feishu-20260923/work
  * SOURCE_TABLE_ORDER -> the 8 CURRENT official tables (R0, published 2026-09-21), since
    those hold the live production schema/option-set this batch must match
  * LEGACY_IDS -> all 16 tables that exist before this batch (8 current official + 8
    "(20260920版)" rollback tables) so schema-fix/clean-blank can never touch them
  * table-count gates generalised from hardcoded 8 to len(expected) (this batch has 10
    tables, driven by the 155,526-row projection)
Everything else copied verbatim.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

BASE = 'KaJIbYuIPacWersWD4jcO1AjnGh'
WORK = Path(os.environ.get('EXCEL_IMPORT_WORK')
            or '/Users/maxzhl/Projects/mcp-suite-recovery-20260921/feishu-20260923/work')
NDJSON = WORK / 'ndjson'
RUNS = WORK / 'runs'
LIVE_ORDER = ['岗位名称', 'job_id', '公司名称', '招聘单位', '行业', '招聘性质', '毕业届别',
              '工作地点', '岗位大类', '投递截止', '截止类型', '原链接', '投递入口', '来源',
              '状态', '复核时间', '备注', '专业', '届别条件说明',
              '国家/地区', '州/省', '办公方式', '地点明细']
PRIMARY_FIELD = '岗位名称'
URL_TEXT = {'原链接', '投递入口'}
MULTI = {'专业', '毕业届别', '工作地点', '国家/地区', '办公方式'}
# 国家/地区、办公方式 have no live options yet: build_target takes them from the batch's observed values.
SELECTS = {'行业': False, '岗位大类': False, '招聘性质': False, '状态': False, '截止类型': False,
           '专业': True, '毕业届别': True, '工作地点': True, '国家/地区': True, '办公方式': True}
SOURCE_TABLE_ORDER = ['tbl4MpGJdhrmZbqx', 'tbl3n6KH9fv95xec', 'tbl1myUlUDUtp0k8',
                      'tbl1Ml7WshEr9qW3', 'tbl64ozef9QjLftm', 'tbl4mnIRKO4jaQqI',
                      'tblWY3Wan6gCSifM', 'tbl1l2t6rEEF70vO']
LEGACY_IDS = {
    'tbl4MpGJdhrmZbqx', 'tbl3n6KH9fv95xec', 'tbl1myUlUDUtp0k8', 'tbl1Ml7WshEr9qW3',
    'tbl64ozef9QjLftm', 'tbl4mnIRKO4jaQqI', 'tblWY3Wan6gCSifM', 'tbl1l2t6rEEF70vO',
    'tbl3Qd2coJ02xhMe', 'tbl5Y72YI5NDn2SM', 'tbl3AKwAgZOAYjwN', 'tbl6sXDYVscOMLu2',
    'tbl1wfxv9pFoQd9s', 'tbl6eaCyeeAC0WKB', 'tbl7HJZXxpccpz8A', 'tbl36Su1rLz5HTWO',
}
MARKDOWN_LINK = re.compile(r'^\[[^\]]*\]\(([^()]*)\)$')
ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def cli(args, cwd=None, timeout=300):
    started = time.time()
    proc = subprocess.run(['lark-cli', *args, '--as', 'user'], cwd=cwd, timeout=timeout,
                          capture_output=True, text=True)
    try:
        body = json.loads(proc.stdout)
    except ValueError:
        body = {'ok': False, 'raw_stdout': proc.stdout[-2000:], 'raw_stderr': proc.stderr[-2000:]}
    return {'argv': args, 'exit_code': proc.returncode, 'seconds': round(time.time() - started, 2),
            'body': body}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for blk in iter(lambda: fh.read(1 << 22), b''):
            h.update(blk)
    return h.hexdigest()


def field_list(table_id):
    out = cli(['base', '+field-list', '--base-token', BASE, '--table-id', table_id])
    if not out['body'].get('ok'):
        raise SystemExit(f'field-list failed for {table_id}: {json.dumps(out)[:500]}')
    return {f.get('field_name') or f['name']: f for f in out['body']['data']['fields']}


def full_options(table_id, field_id, total):
    opts, offset = [], 0
    while offset < total + 200:
        out = cli(['base', '+field-search-options', '--base-token', BASE, '--table-id', table_id,
                   '--field-id', field_id, '--limit', '200', '--offset', str(offset)])
        if not out['body'].get('ok'):
            raise SystemExit(f'field-search-options failed: {json.dumps(out)[:400]}')
        batch = out['body']['data'].get('options') or out['body']['data'].get('items') or []
        if not batch:
            break
        opts.extend(o['name'] for o in batch)
        offset += len(batch)
        if len(batch) < 200:
            break
    return opts


def build_target():
    snap = json.loads((WORK / 'prod-schema-snapshot.json').read_text(encoding='utf-8'))
    manifest = json.loads((WORK / 'xlsx-manifest.json').read_text(encoding='utf-8'))
    observed = manifest['observed_select_values']
    url_style = {}
    for tid in SOURCE_TABLE_ORDER:
        for f in snap['tables'][tid]['fields']:
            if f['type'] == 'text' and f['style'] == 'url':
                url_style[f['name']] = 'url'
    target = {}
    for name in LIVE_ORDER:
        if name in SELECTS:
            union, seen = [], set()
            for tid in SOURCE_TABLE_ORDER:
                for f in snap['tables'][tid]['fields']:
                    if f['name'] == name:
                        for o in f['options']:
                            if o not in seen:
                                seen.add(o)
                                union.append(o)
            extra = [v for v in sorted(observed.get(name) or {}) if v not in seen]
            target[name] = {'type': 'select', 'multiple': SELECTS[name],
                            'options': union + extra, 'live_options': len(union),
                            'batch_only_options': extra}
        else:
            target[name] = {'type': 'text', 'style': url_style.get(name, 'plain')}
    return target


def field_body(name, want):
    body = {'name': name, 'type': want['type']}
    if want['type'] == 'select':
        body['multiple'] = want['multiple']
        body['options'] = [{'name': o} for o in want['options']]
    else:
        body['style'] = {'type': want['style']}
    return body


def describe(field):
    if field['type'] == 'select':
        opts = len(field.get('options') or []) + (field.get('remaining_options_count') or 0)
        return f"select(multi={field.get('multiple')}) opts={opts}"
    return f"text(style={(field.get('style') or {}).get('type')})"


def describe_field_body(want):
    if want['type'] == 'select':
        return f"select(multi={want['multiple']}) opts={len(want['options'])}"
    return f"text(style={want['style']})"


def option_names(field):
    return [o['name'] if isinstance(o, dict) else str(o) for o in (field.get('options') or [])]


def diff_field(current, want, table_id):
    problems = []
    if current is None:
        return True, ['field missing']
    if current['type'] != want['type']:
        problems.append(f"type {current['type']} != {want['type']}")
    if want['type'] == 'select':
        if bool(current.get('multiple')) != bool(want['multiple']):
            problems.append(f"multiple {current.get('multiple')} != {want['multiple']}")
        opts = set(option_names(current))
        remaining = current.get('remaining_options_count') or 0
        if remaining:
            opts = set(full_options(table_id, current['id'], remaining)) or opts
        want_opts = set(want['options'])
        if opts != want_opts:
            problems.append(f"option set differs: missing={sorted(want_opts - opts)[:8]} "
                            f"extra={sorted(opts - want_opts)[:8]}")
    else:
        style = (current.get('style') or {}).get('type')
        if style != want['style']:
            problems.append(f"style {style} != {want['style']}")
    return bool(problems), problems


def load_new_tables():
    runs = sorted(RUNS.glob('*/import-receipt.json'))
    if not runs:
        raise SystemExit('no import receipt found')
    receipt = json.loads(runs[-1].read_text(encoding='utf-8'))
    if receipt.get('outcome') != 'completed':
        raise SystemExit(f"import receipt outcome is {receipt.get('outcome')}, not completed")
    out = []
    for r in receipt['results']:
        tid = r.get('table_id')
        if not tid:
            raise SystemExit(f"import result without table_id: {r['table_name']}")
        if tid in LEGACY_IDS:
            raise SystemExit('new-table allowlist violated: legacy table id in the new set')
        out.append((tid, r['table_name']))
    return out, runs[-1].parent


def phase_fix(new_tables, run_dir):
    target = build_target()
    receipt = {'step': 'schema-fix', 'base_token': BASE, 'started_at': dt.datetime.now().isoformat(),
               'target_schema': target, 'tables': []}
    path = run_dir / 'schema-fix-receipt.json'
    for table_id, table_name in new_tables:
        entry = {'table_id': table_id, 'table_name': table_name, 'updates': [], 'plan': []}
        cur = field_list(table_id)
        for name in LIVE_ORDER:
            want = target[name]
            need, problems = diff_field(cur.get(name), want, table_id)
            entry['plan'].append({'field': name, 'need': need, 'problems': problems,
                                  'current': describe(cur[name]) if name in cur else None,
                                  'target': describe_field_body(want)})
        for item in entry['plan']:
            if not item['need']:
                continue
            fid = cur[item['field']]['id']
            body = field_body(item['field'], target[item['field']])
            tmp = WORK / f'.field-{fid}.json'
            tmp.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
            out = cli(['base', '+field-update', '--base-token', BASE, '--table-id', table_id,
                       '--field-id', fid, '--json', '@' + tmp.name, '--yes'], cwd=str(WORK))
            tmp.unlink()
            entry['updates'].append({'field': item['field'], 'field_id': fid,
                                     'ok': bool(out['body'].get('ok')), 'seconds': out['seconds'],
                                     'error': None if out['body'].get('ok') else out['body'].get('error')})
            print(json.dumps({'table': table_name, 'field': item['field'],
                              'ok': bool(out['body'].get('ok'))}, ensure_ascii=False), flush=True)
        receipt['tables'].append(entry)
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
    receipt['finished_at'] = dt.datetime.now().isoformat()
    receipt['outcome'] = 'completed'
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
    failed = [u for t in receipt['tables'] for u in t['updates'] if not u['ok']]
    if failed:
        receipt['outcome'] = 'failed'
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
        print(json.dumps({'outcome': 'failed', 'failed_updates': failed}, ensure_ascii=False))
        return 1
    print(json.dumps({'outcome': 'completed',
                      'updates': sum(len(t['updates']) for t in receipt['tables']),
                      'receipt': str(path)}, ensure_ascii=False))
    return 0


def export_records(table_id, tag, fields=None, page=2000):
    NDJSON.mkdir(parents=True, exist_ok=True)
    root = NDJSON.resolve()

    def _record_path(record_file):
        path = Path(record_file)
        return path if path.is_absolute() else WORK / path

    def _page_rows(record_file, count, has_more, next_offset, offset):
        if not record_file:
            return None, 'artifact manifest carries no record_file'
        path = _record_path(record_file)
        try:
            inside = path.resolve().is_relative_to(root)
        except (OSError, ValueError):
            inside = False
        if not inside:
            return None, f'record_file outside {NDJSON}: {str(path)!r}'
        if not path.name.endswith(f'-{offset}.ndjson'):
            return None, f'record_file is not the offset-{offset} page: {path.name}'
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return None, f'records_count is not a non-negative int: {count!r}'
        try:
            text = path.read_text(encoding='utf-8')
        except OSError as exc:
            return None, f'record_file unreadable: {exc}'
        page = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                page.append(json.loads(line))
            except ValueError:
                return None, 'record_file contains a non-JSON line'
        if len(page) != count:
            return None, f'{len(page)} valid lines != records_count {count}'
        has_more = bool(has_more)
        if has_more and count == 0:
            return None, 'has_more is true with zero records: no pagination progress'
        if has_more and next_offset is not None and next_offset != offset + count:
            return None, f'next_offset {next_offset!r} != offset {offset} + records_count {count}'
        return page, {'records_count': count, 'has_more': has_more,
                      'record_file': str(path.resolve())}

    def _reusable(manifest, candidate, offset):
        if manifest.get('manifest_version') is None:
            return None, 'not an artifact manifest'
        if manifest.get('base_token') != BASE or manifest.get('table_id') != table_id:
            return None, 'artifact is bound to another base/table'
        if fields or (manifest.get('query_context') or {}).get('field_scope') != 'all_fields':
            return None, 'artifact field scope is not this query'
        if manifest.get('requested_limit') != page:
            return None, f"artifact requested_limit {manifest.get('requested_limit')!r} != {page}"
        record_file = manifest.get('record_file')
        if not record_file or Path(record_file).name != \
                candidate.name[:-len('.manifest.json')] + '.ndjson':
            return None, 'artifact record_file does not sit next to its manifest'
        return _page_rows(record_file, manifest.get('records_count'),
                          manifest.get('has_more'), manifest.get('next_offset'), offset)

    rows, offset, pages, reused = [], 0, 0, 0
    while True:
        rel = f'ndjson/{tag}-{offset}.ndjson'
        page_rows, info, from_reuse = None, None, False
        exact = NDJSON / f'{tag}-{offset}.manifest.json'
        candidates = ([exact] if exact.is_file() else []) + [
            p for p in sorted(NDJSON.glob(f'*-{offset}.manifest.json')) if p != exact]
        for candidate in candidates:
            try:
                manifest = json.loads(candidate.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if not isinstance(manifest, dict):
                continue
            page_rows, info = _reusable(manifest, candidate, offset)
            if page_rows is not None:
                info['manifest'] = str(candidate)
                from_reuse = True
                break
        if page_rows is None:
            args = ['base', '+record-list', '--base-token', BASE, '--table-id', table_id,
                    '--format', 'ndjson', '--output', rel, '--overwrite', '--offset', str(offset)]
            for name in (fields or []):
                args += ['--field-id', name]
            out = cli(args, cwd=str(WORK))
            body = out.get('body') if isinstance(out.get('body'), dict) else {}
            fail = {'error': body, 'offset': offset, 'pages': pages,
                    'exit_code': out.get('exit_code')}
            if out.get('exit_code') != 0 or body.get('ok') is False:
                return None, fail
            if body.get('ok') is True and isinstance(body.get('data'), dict):
                data = dict(body['data'])
                data.setdefault('record_file', str(WORK / rel))
            elif body.get('manifest_version') is not None and body.get('record_file'):
                data = body
            else:
                return None, fail
            page_rows, info = _page_rows(data.get('record_file'), data.get('records_count'),
                                         data.get('has_more'), data.get('next_offset'), offset)
            if page_rows is None:
                fail['error'] = info
                return None, fail
        pages += 1
        reused += 1 if from_reuse else 0
        rows.extend(page_rows)
        offset += info['records_count']
        if not info['has_more']:
            break
        if pages > 400:
            return None, {'error': 'page guard hit', 'offset': offset, 'pages': pages}
    return rows, {'pages': pages, 'records': len(rows), 'reused_pages': reused}


def phase_clean_blank(new_tables, run_dir):
    receipt = {'step': 'clean-blank', 'base_token': BASE, 'started_at': dt.datetime.now().isoformat(),
               'tables': []}
    path = run_dir / 'clean-blank-receipt.json'
    for table_id, table_name in new_tables:
        if table_id in LEGACY_IDS:
            raise SystemExit('clean-blank allowlist violated')
        entry = {'table_id': table_id, 'table_name': table_name}
        rows, meta = export_records(table_id, f'blank-{table_id}')
        entry['export'] = meta
        if rows is None:
            entry['outcome'] = 'failed'
            receipt['tables'].append(entry)
            path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
            receipt['outcome'] = 'failed'
            path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
            print(json.dumps({'outcome': 'failed', 'table': table_name}, ensure_ascii=False))
            return 1
        all_empty, content_without_id = [], []
        for row in rows:
            cells = {}
            for name in LIVE_ORDER:
                value = row.get(name)
                if isinstance(value, list):
                    value = ','.join(str(v) for v in value)
                cells[name] = '' if value is None else str(value)
            empty = all(v == '' for v in cells.values())
            if empty:
                all_empty.append(row.get('record_id'))
            elif cells['job_id'] == '':
                content_without_id.append(row.get('record_id'))
        entry['all_empty_rows'] = len(all_empty)
        entry['content_without_job_id'] = len(content_without_id)
        if content_without_id:
            entry['outcome'] = 'failed'
            entry['content_without_job_id_sample'] = content_without_id[:5]
            receipt['tables'].append(entry)
            receipt['outcome'] = 'failed'
            receipt['finished_at'] = dt.datetime.now().isoformat()
            path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
            print(json.dumps({'outcome': 'failed', 'table': table_name,
                              'reason': 'row with content but empty job_id'},
                             ensure_ascii=False))
            return 1
        entry['deleted'] = []
        for start in range(0, len(all_empty), 200):
            batch = [r for r in all_empty[start:start + 200] if r]
            if not batch:
                continue
            args = ['base', '+record-delete', '--base-token', BASE, '--table-id', table_id]
            for rid in batch:
                args += ['--record-id', rid]
            d = cli([*args, '--yes'])
            entry['deleted'].append({'count': len(batch), 'ok': bool(d['body'].get('ok')),
                                     'body': d['body'] if not d['body'].get('ok') else None})
        entry['outcome'] = 'completed' if all(d['ok'] for d in entry['deleted']) else 'failed'
        receipt['tables'].append(entry)
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
        print(json.dumps({'table': table_name, 'all_empty_rows': len(all_empty)},
                         ensure_ascii=False), flush=True)
    receipt['finished_at'] = dt.datetime.now().isoformat()
    receipt['outcome'] = 'completed' if all(t['outcome'] == 'completed' for t in receipt['tables']) \
        else 'failed'
    receipt['blank_total'] = sum(t['all_empty_rows'] for t in receipt['tables'])
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'outcome': receipt['outcome'], 'receipt': str(path),
                      'blank_total': receipt['blank_total']}, ensure_ascii=False))
    return 0 if receipt['outcome'] == 'completed' else 1


def extract_url(value):
    if value is None:
        return ''
    text = str(value)
    m = MARKDOWN_LINK.match(text)
    return m.group(1) if m else text


def compare_cell(name, want, value):
    if name in MULTI:
        got = sorted(str(v) for v in (value or []) if str(v) != '')
        exp = sorted(t for t in str(want).split(',') if t)
        return got == exp, got, exp
    if name in SELECTS:
        got = [str(v) for v in (value or []) if str(v) != '']
        exp = [want] if want else []
        return got == exp, got, exp
    if name in URL_TEXT:
        got = extract_url(value)
        return got == (want or ''), got, want or ''
    got = '' if value is None else str(value)
    return got == (want or ''), got, want or ''


def apply_excel_text_whitelist(per_group):
    report = json.loads((WORK / 'illegal-character-report.json').read_text(encoding='utf-8'))
    hits = report.get('hits') or []
    if len(hits) != 1 or report.get('cells_truncated'):
        raise SystemExit('illegal-character report is not the expected single-hit shape')
    hit = hits[0]
    before = ast.literal_eval(hit['before_repr'])
    after = ast.literal_eval(hit['after_repr'])
    applied = 0
    for row in per_group.get(hit['group'], []):
        if row['job_id'] == hit['job_id'] and row[hit['field']] == before:
            row[hit['field']] = after
            applied += 1
    if applied != 1:
        raise SystemExit(f'excel text whitelist hit {applied} times, expected exactly 1')
    return {'group': hit['group'], 'job_id': hit['job_id'], 'field': hit['field'],
            'before': before, 'after': after, 'applied': applied,
            'removed_codepoints': hit['removed_codepoints']}


def load_expected():
    proj = json.loads((WORK / 'projection-manifest.json').read_text(encoding='utf-8'))
    xml = json.loads((WORK / 'xlsx-manifest.json').read_text(encoding='utf-8'))
    columns = proj['columns']
    if columns[0] != 'job_id':
        raise SystemExit('projection column order changed: job_id is not first')
    per_group = {}
    with gzip.open(WORK / 'projection.ndjson.gz', 'rt', encoding='utf-8') as fh:
        for line in fh:
            rec = json.loads(line)
            row = dict(zip(columns, rec['c']))
            per_group.setdefault(rec['g'], []).append(row)
    whitelist = apply_excel_text_whitelist(per_group)
    return proj, xml, per_group, whitelist


def coverage(batch):
    counts = Counter()
    for row in batch:
        if row['投递截止'] and not ISO_DATE.match(row['投递截止']):
            counts['non_iso_deadline'] += 1
        if not row['投递截止']:
            counts['empty_deadline'] += 1
        for name in MULTI:
            n = len([t for t in row[name].split(',') if t])
            counts[f'multi_{name}_{"1" if n <= 1 else "2plus"}'] += 1
        for name in URL_TEXT:
            if '?' in row[name]:
                counts[f'query_url_{name}'] += 1
        if row['复核时间'] == '':
            counts['empty_reviewed_at'] += 1
        if row['备注'] == '' and row['截止类型'] == '':
            counts['empty_note_and_deadline_type'] += 1
    return dict(counts)


def phase_verify(new_tables, run_dir):
    target = build_target()
    proj, xml, per_group, whitelist = load_expected()
    expected = {f['table_name']: f for f in xml['files']}
    if sorted(t for _, t in new_tables) != sorted(expected):
        raise SystemExit('verify coverage mismatch: imported tables != xlsx manifest tables')
    imp = json.loads(sorted(RUNS.glob('*/import-receipt.json'))[-1].read_text(encoding='utf-8'))
    bound = imp.get('targets_bound') or {}
    if bound != {name: tid for tid, name in new_tables}:
        raise SystemExit('verify/import table binding mismatch')
    n_expected = len(expected)
    receipt = {'step': 'verify', 'base_token': BASE, 'started_at': dt.datetime.now().isoformat(),
               'tables': [], 'outcome': 'failed',
               'source_projection_sha256_gz': proj['projection_ndjson_gz']['sha256_gz'],
               'projection_sha256_on_disk': sha256_file(WORK / 'projection.ndjson.gz'),
               'xlsx_sha256_on_disk': {f['table_name']: sha256_file(Path(f['path']))
                                       for f in xml['files']},
               'projection_manifest': str(WORK / 'projection-manifest.json'),
               'xlsx_manifest': str(WORK / 'xlsx-manifest.json'),
               'import_receipt': str(sorted(RUNS.glob('*/import-receipt.json'))[-1]),
               'expected_tables': sorted(expected),
               'expected_table_count': n_expected,
               'column_decode_order': proj['columns'], 'live_order': LIVE_ORDER,
               'excel_text_whitelist': whitelist}
    path = run_dir / 'verify-receipt.json'
    totals = Counter()
    for table_id, table_name in new_tables:
        item = expected[table_name]
        group_rows = per_group[item['group']]
        start = item['chunk_index'] * xml['chunk_limit']
        want_rows = group_rows[start:start + xml['chunk_limit']]
        entry = {'table_id': table_id, 'table_name': table_name, 'expected_rows': item['rows'],
                 'expected_xlsx_sha256': item['sha256'], 'group': item['group'],
                 'chunk_index': item['chunk_index']}
        cur = field_list(table_id)
        schema_problems = {}
        for name in LIVE_ORDER:
            need, problems = diff_field(cur.get(name), target[name], table_id)
            if need:
                schema_problems[name] = problems
        entry['schema_ok'] = not schema_problems
        entry['schema_problems'] = schema_problems
        entry['columns_present'] = sorted(cur)
        vl = cli(['base', '+view-list', '--base-token', BASE, '--table-id', table_id])
        entry['views'] = vl['body'].get('data', {}).get('views')
        if entry['views']:
            vid = entry['views'][0]['id']
            vf = cli(['base', '+view-get-visible-fields', '--base-token', BASE,
                      '--table-id', table_id, '--view-id', vid])
            entry['view_field_order'] = vf['body'].get('data', {}).get('visible_fields')
            entry['view_order_ok'] = entry['view_field_order'] == LIVE_ORDER
            entry['primary_field_ok'] = bool(entry['view_field_order']) and \
                entry['view_field_order'][0] == PRIMARY_FIELD
            vfl = cli(['base', '+view-get-filter', '--base-token', BASE,
                       '--table-id', table_id, '--view-id', vid])
            entry['view_filter'] = vfl['body'].get('data', {}).get('filter')

        rows, meta = export_records(table_id, f'keys-{table_id}', fields=['job_id','岗位名称','公司名称','原链接','投递入口'])
        entry['record_export'] = meta
        if rows is None:
            entry.update({'rows_read': 0, 'id_set_ok': False, 'cells_ok': False,
                          'export_failed': True})
        else:
            got = {}
            duplicate_ids, null_ids = 0, 0
            for row in rows:
                jid = row.get('job_id')
                jid = jid[0] if isinstance(jid, list) and jid else jid
                if not jid:
                    null_ids += 1
                    continue
                if jid in got:
                    duplicate_ids += 1
                    continue
                got[jid] = row
            want_ids = [r['job_id'] for r in want_rows]
            entry.update({'rows_read': len(rows), 'distinct_job_ids': len(got),
                          'duplicate_job_ids': duplicate_ids, 'null_job_ids': null_ids,
                          'rows_ok': len(rows) == item['rows'],
                          'expected_id_count': len(want_ids)})
            entry['id_set_ok'] = sorted(got) == sorted(want_ids)
            entry['id_set_sha256'] = hashlib.sha256('\n'.join(sorted(got)).encode()).hexdigest()
            entry['expected_id_set_sha256'] = hashlib.sha256(
                '\n'.join(sorted(want_ids)).encode()).hexdigest()
            if not entry['id_set_ok']:
                w, g = set(want_ids), set(got)
                entry['missing_ids_sample'] = sorted(w - g)[:5]
                entry['unexpected_ids_sample'] = sorted(g - w)[:5]
                entry['missing_ids'] = len(w - g)
                entry['unexpected_ids'] = len(g - w)
            required=['job_id','岗位名称','公司名称','原链接','投递入口']
            required_missing=[jid for jid,row in got.items() if any(not row.get(name) for name in required)]
            sample_ids={r['id'] for r in json.loads((WORK/'samples24.json').read_text(encoding='utf8'))}
            want_sample=[row for row in want_rows if row['job_id'] in sample_ids]
            sample_got={}
            if want_sample:
                rel=f'ndjson/samples-{table_id}.ndjson'
                query={'logic':'or','conditions':[['job_id','==',row['job_id']] for row in want_sample]}
                response=cli(['base','+record-list','--base-token',BASE,'--table-id',table_id,
                              '--filter-json',json.dumps(query,ensure_ascii=False),'--format','ndjson',
                              '--output',rel,'--overwrite','--limit','100'],cwd=str(WORK))
                if response['exit_code']!=0 or response['body'].get('ok') is False:
                    raise RuntimeError('sample fetch failed')
                sample_rows=[json.loads(line) for line in (WORK/rel).read_text(encoding='utf8').splitlines() if line.strip()]
                sample_got={row['job_id']:row for row in sample_rows}
            mismatched_rows=0; mismatch_fields=Counter();samples={}
            for row in want_sample:
                live=sample_got.get(row['job_id'])
                if live is None:mismatched_rows+=1;continue
                bad=False
                for name in LIVE_ORDER:
                    ok,g,w=compare_cell(name,row[name],live.get(name))
                    if not ok:
                        bad=True;mismatch_fields[name]+=1
                        samples.setdefault(name,[]).append({'job_id':row['job_id'],'got':g,'want':w})
                mismatched_rows+=int(bad)
            entry['required_missing_rows']=len(required_missing)
            entry['semantic_sample_ids']=[row['job_id'] for row in want_sample]
            entry['semantic_sample_count']=len(want_sample)
            entry['cells_ok']=entry['id_set_ok'] and not required_missing and mismatched_rows==0
            entry['cell_check_scope']=f'required fields all rows; all {len(LIVE_ORDER)} fields only fixed 24 samples'
            entry['mismatched_rows']=mismatched_rows
            entry['mismatched_cells_by_field']=dict(mismatch_fields)
            entry['mismatch_samples']=samples
            entry['coverage'] = coverage(want_rows)
        receipt['tables'].append(entry)
        totals['tables'] += 1
        totals['schema_ok'] += 1 if entry.get('schema_ok') else 0
        totals['rows_ok'] += 1 if entry.get('rows_ok') else 0
        totals['no_duplicates'] += 1 if entry.get('duplicate_job_ids') == 0 else 0
        totals['id_set_ok'] += 1 if entry.get('id_set_ok') else 0
        totals['cells_ok'] += 1 if entry.get('cells_ok') else 0
        totals['view_order_ok'] += 1 if entry.get('view_order_ok') else 0
        totals['primary_field_ok'] += 1 if entry.get('primary_field_ok') else 0
        totals['no_null_ids'] += 1 if entry.get('null_job_ids') == 0 else 0
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
        print(json.dumps({'table': table_name, 'rows': entry.get('rows_read'),
                          'schema_ok': entry.get('schema_ok'), 'id_set_ok': entry.get('id_set_ok'),
                          'cells_ok': entry.get('cells_ok'),
                          'mismatched_rows': entry.get('mismatched_rows')},
                         ensure_ascii=False), flush=True)
    receipt['totals'] = dict(totals)
    ok = (totals['tables'] == len(expected) == n_expected and totals['schema_ok'] == n_expected
          and totals['rows_ok'] == n_expected and totals['no_duplicates'] == n_expected
          and totals['id_set_ok'] == n_expected
          and totals['cells_ok'] == n_expected and totals['view_order_ok'] == n_expected
          and totals['primary_field_ok'] == n_expected and totals['no_null_ids'] == n_expected
          and receipt['projection_sha256_on_disk'] == receipt['source_projection_sha256_gz']
          and all(receipt['xlsx_sha256_on_disk'][n] == expected[n]['sha256'] for n in expected))
    receipt['semantic_sample_total']=sum(t.get('semantic_sample_count',0) for t in receipt['tables'])
    ok=ok and receipt['semantic_sample_total']==24
    receipt['gate_passed'] = ok
    receipt['finished_at'] = dt.datetime.now().isoformat()
    receipt['outcome'] = 'completed' if ok else 'failed'
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'outcome': receipt['outcome'], 'gate_passed': ok, 'totals': dict(totals),
                      'receipt': str(path)}, ensure_ascii=False))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', choices=['fix', 'clean-blank', 'verify'], required=True)
    args = ap.parse_args()
    new_tables, run_dir = load_new_tables()
    if args.phase == 'fix':
        return phase_fix(new_tables, run_dir)
    if args.phase == 'clean-blank':
        return phase_clean_blank(new_tables, run_dir)
    return phase_verify(new_tables, run_dir)


if __name__ == '__main__':
    sys.exit(main())
