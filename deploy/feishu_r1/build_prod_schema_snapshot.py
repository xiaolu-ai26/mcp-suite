#!/usr/bin/env python3
"""Build prod-schema-snapshot.json for the CURRENT 8 official tables (the R0 tables that
this batch is about to replace). Mirrors the shape of
mcp-suite-recovery-20260921/work/prod-schema-snapshot.json so run_step3_schema_verify_r1.py
can reuse the same build_target() logic against these as SOURCE_TABLE_ORDER.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

BASE = 'KaJIbYuIPacWersWD4jcO1AjnGh'
OUT = Path('/Users/maxzhl/Projects/mcp-suite-recovery-20260921/feishu-20260923/work/prod-schema-snapshot.json')
# current official tables (R0, published 2026-09-21) in root display order
TABLES = [
    ('tbl4MpGJdhrmZbqx', '互联网科技岗'),
    ('tbl3n6KH9fv95xec', '互联网科技岗·续表1'),
    ('tbl1myUlUDUtp0k8', '国企央企岗'),
    ('tbl1Ml7WshEr9qW3', '制造工业岗'),
    ('tbl64ozef9QjLftm', '制造工业岗·续表1'),
    ('tbl4mnIRKO4jaQqI', '其他行业岗'),
    ('tblWY3Wan6gCSifM', '其他行业岗·续表1'),
    ('tbl1l2t6rEEF70vO', '其他行业岗·续表2'),
]


def cli(args):
    proc = subprocess.run(['lark-cli', *args, '--as', 'user'], capture_output=True, text=True, timeout=120)
    body = json.loads(proc.stdout)
    if not body.get('ok'):
        raise SystemExit(f'cli failed: {args} -> {proc.stdout[:500]}')
    return body['data']


def full_options(table_id, field_id, total):
    opts, offset = [], 0
    while offset < total + 200:
        data = cli(['base', '+field-search-options', '--base-token', BASE, '--table-id', table_id,
                    '--field-id', field_id, '--limit', '200', '--offset', str(offset)])
        batch = data.get('options') or data.get('items') or []
        if not batch:
            break
        opts.extend(o['name'] for o in batch)
        offset += len(batch)
        if len(batch) < 200:
            break
    return opts


def main():
    tables = {}
    for tid, name in TABLES:
        data = cli(['base', '+field-list', '--base-token', BASE, '--table-id', tid])
        fields = []
        for f in data['fields']:
            fname = f.get('field_name') or f['name']
            ftype = f['type']
            entry = {'id': f['id'], 'name': fname, 'type': ftype,
                     'multiple': f.get('multiple'), 'style': (f.get('style') or {}).get('type'),
                     'options': [], 'remaining': 0}
            if ftype == 'select':
                opts = [o['name'] if isinstance(o, dict) else str(o) for o in (f.get('options') or [])]
                remaining = f.get('remaining_options_count') or 0
                if remaining:
                    full = full_options(tid, f['id'], remaining)
                    if full:
                        opts = full
                        remaining = 0
                entry['options'] = opts
                entry['remaining'] = remaining
            fields.append(entry)
        tables[tid] = {'name': name, 'fields': fields}
        print(f'{name} ({tid}): {len(fields)} fields', file=sys.stderr)
    snapshot = {'base_token': BASE, 'tables': tables}
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'tables': len(tables), 'out': str(OUT)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
