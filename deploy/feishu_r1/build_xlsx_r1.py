#!/usr/bin/env python3
"""Build the per-target-table xlsx files for the Excel-import mirror (R1 / 20260923 batch).

Adapted from mcp-suite-recovery-20260921/scripts/build_xlsx.py: only WORK and PREFIX change;
table-count-per-group is dynamic (same CHUNK=19500 logic), driven by the new projection's
row counts. Logic copied verbatim otherwise.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from itertools import islice
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

WORK = Path('/Users/maxzhl/Projects/mcp-suite-recovery-20260921/feishu-20260923/work')
CHUNK = 19500
PREFIX = '待切换-20260923-'
GROUPS = ['互联网科技岗', '国企央企岗', '制造工业岗', '其他行业岗']
LIVE_ORDER = ['岗位名称', 'job_id', '公司名称', '招聘单位', '行业', '招聘性质', '毕业届别',
              '工作地点', '岗位大类', '投递截止', '截止类型', '原链接', '投递入口', '来源',
              '状态', '复核时间', '备注', '专业', '届别条件说明',
              '国家/地区', '州/省', '办公方式', '地点明细']
MULTI = {'专业', '毕业届别', '工作地点', '国家/地区', '办公方式'}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for blk in iter(lambda: fh.read(1 << 22), b''):
            h.update(blk)
    return h.hexdigest()


SANITIZED = Counter()


def text_cell(ws, value):
    cleaned = ILLEGAL_CHARACTERS_RE.sub('', value)
    if cleaned != value:
        SANITIZED['cells'] += 1
        SANITIZED['removed_chars'] += len(value) - len(cleaned)
    if len(cleaned) > 32767:
        SANITIZED['truncated_cells'] += 1
        cleaned = cleaned[:32767]
    cell = WriteOnlyCell(ws, value=cleaned)
    cell.data_type = 's'
    cell.number_format = '@'
    return cell


def main():
    manifest = json.loads((WORK / 'projection-manifest.json').read_text(encoding='utf-8'))
    src_order = manifest['columns']
    index = [src_order.index(name) for name in LIVE_ORDER]
    missing = [n for n in LIVE_ORDER if n not in src_order]
    if missing:
        raise SystemExit(f'columns missing from projection: {missing}')

    by_group = WORK / 'by-group'
    by_group.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    observed = defaultdict(Counter)
    handles = {}
    t0 = time.time()
    try:
        for g in GROUPS:
            handles[g] = (by_group / f'{g}.ndjson').open('w', encoding='utf-8')
        with gzip.open(WORK / 'projection.ndjson.gz', 'rt', encoding='utf-8') as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                g = rec['g']
                handles[g].write(line)
                counts[g] += 1
                cells = [rec['c'][i] for i in index]
                for name, value in zip(LIVE_ORDER, cells):
                    if name in MULTI:
                        for part in value.split(','):
                            if part:
                                observed[name][part] += 1
                    elif value:
                        observed[name][value] += 1
    finally:
        for fh in handles.values():
            fh.close()

    out_dir = WORK / 'xlsx'
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for g in GROUPS:
        total = counts[g]
        if not total:
            continue
        n_chunks = (total + CHUNK - 1) // CHUNK
        with (by_group / f'{g}.ndjson').open('r', encoding='utf-8') as fh:
            for chunk_index in range(n_chunks):
                table_name = PREFIX + g + ('' if chunk_index == 0 else f'·续表{chunk_index}')
                path = out_dir / f'{table_name}.xlsx'
                wb = Workbook(write_only=True)
                ws = wb.create_sheet(title=table_name)
                ws.append([text_cell(ws, name) for name in LIVE_ORDER])
                first_id = last_id = None
                rows = 0
                for line in islice(fh, CHUNK):
                    rec = json.loads(line)
                    cells = [rec['c'][i] for i in index]
                    if first_id is None:
                        first_id = cells[LIVE_ORDER.index('job_id')]
                    last_id = cells[LIVE_ORDER.index('job_id')]
                    ws.append([text_cell(ws, v) for v in cells])
                    rows += 1
                wb.save(path)
                files.append({'group': g, 'table_name': table_name, 'rows': rows,
                              'path': str(path), 'bytes': path.stat().st_size,
                              'sha256': sha256_file(path),
                              'first_job_id': first_id, 'last_job_id': last_id,
                              'chunk_index': chunk_index})
                print(f'{table_name}: {rows} rows, {path.stat().st_size} bytes',
                      file=sys.stderr)

    result = {
        'built_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'source_projection_manifest': str(WORK / 'projection-manifest.json'),
        'source_projection_sha256_gz': manifest['projection_ndjson_gz']['sha256_gz'],
        'source_snapshot_sha256': manifest['source_sha256'],
        'live_column_order': LIVE_ORDER,
        'chunk_limit': CHUNK,
        'temp_prefix': PREFIX,
        'group_counts': dict(counts),
        'files': files,
        'observed_select_values': {k: dict(v.most_common()) for k, v in observed.items()},
        'sanitized_cells': dict(SANITIZED),
        'seconds': round(time.time() - t0, 2),
    }
    (WORK / 'xlsx-manifest.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'group_counts': dict(counts), 'files': len(files),
                      'total_rows': sum(counts.values())}, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
