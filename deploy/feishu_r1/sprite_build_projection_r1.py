"""Build the exact mirror projection (19 columns + 4 location columns since 2026-09-28) from the published jobs.json snapshot (R1 / 20260923).

Adapted from mcp-suite-recovery-20260921/scripts/sprite_build_projection.py: only SOURCE,
OUT_DIR and EXPECTED_SOURCE_SHA change (new snapshot, new run date). Logic copied verbatim.
READ-ONLY with respect to every cloud system and with respect to C:\\mcp-suite-collector
(only imported as a read-only library); only writes under C:\\mcp-recovery-20260923\\.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r'C:\mcp-suite-collector')
sys.path.insert(0, str(ROOT))

from qiuzhao import v4_fields as V                      # noqa: E402
from qiuzhao.collector import lark_sync_enrichment as E  # noqa: E402
from qiuzhao.collector import sync_lark_multivalue as S  # noqa: E402

SOURCE = Path(r'C:\mcp-recovery-20260923\R1.jobs.json')
OUT_DIR = Path(r'C:\mcp-recovery-20260923\excel-import')
EXPECTED_SOURCE_SHA = 'c963aeffe542a8ca751092d35af66075e015650ddb86105808920c4433e398ee'
NOTE_FIELD = E.NOTE_FIELD

COLUMNS = ['job_id', '岗位名称', '公司名称', '招聘单位', '行业', '岗位大类', '招聘性质', '状态',
           '截止类型', '专业', '毕业届别', '工作地点', '投递截止', '复核时间', '来源',
           '原链接', '投递入口', '备注', '届别条件说明', *S.LOCATION_COLUMNS]
# Location columns (2026-09-28): 国家/地区、州/省、办公方式、地点明细 from S.location_values_for.
MULTI = {'专业', '毕业届别', '工作地点', '国家/地区', '办公方式'}
SELECTS = ['行业', '岗位大类', '招聘性质', '状态', '截止类型', '专业', '毕业届别', '工作地点',
           '国家/地区', '办公方式']

GROUP_OF_INDUSTRY = {'互联网/科技': '互联网科技岗', '国企/央企': '国企央企岗',
                     '制造/工业': '制造工业岗'}
DEFAULT_GROUP = '其他行业岗'


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for blk in iter(lambda: fh.read(1 << 22), b''):
            h.update(blk)
    return h.hexdigest()


def company_of(raw):
    return (raw.get('p1_company') or raw.get('canonical_company')
            or raw.get('recruitment_unit') or raw.get('company') or '')


def business_projection(raw):
    identity = str(raw.get('id') or '').strip()
    if not identity:
        return None
    projection = {'job_id': identity}
    projection.update(E.business_fields(raw))
    projection.update(S.values_for(raw))
    projection.update(S.location_values_for(raw))
    projection[NOTE_FIELD] = E.qualification_note(raw)
    state = E.source_lifecycle_state(raw)
    if state:
        projection['状态'] = [state]
    return projection


def mirror_row(raw, industry):
    """append_row() payload composition, verbatim, with the industry routed in."""
    projection = business_projection(raw) or {'job_id': str(raw.get('id') or '').strip()}
    row = dict(projection)
    v, _ = V.convert(raw)
    row.update({'岗位名称': v['job_title'], '公司名称': company_of(raw),
                '招聘单位': raw.get('recruiting_unit_raw') or raw.get('recruitment_unit') or company_of(raw),
                '行业': [industry], '招聘性质': projection.get('招聘性质') or ['未注明'],
                '岗位大类': [v['job_category']],
                '状态': projection.get('状态') or ['unverified'],
                '原链接': raw.get('source_url') or raw.get('detail_url') or '',
                '投递入口': raw.get('application_url') or raw.get('detail_url') or '',
                '复核时间': str(raw.get('reviewed_at') or ''),
                '来源': raw.get('source_name') or (company_of(raw) + '官方招聘') if company_of(raw) else raw.get('source_name') or '',
                NOTE_FIELD: projection.get(NOTE_FIELD, '')})
    if raw.get('deadline'):
        row['投递截止'] = str(raw['deadline'])
    return row


def cell(value):
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        parts = [str(x) for x in value if x not in (None, '')]
        return ','.join(parts)
    return str(value)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    source_sha = sha256_file(SOURCE)
    if source_sha != EXPECTED_SOURCE_SHA:
        raise SystemExit(f'source sha mismatch: {source_sha}')

    report = Counter()
    groups = Counter()
    seen_ids = set()
    ids_per_group = defaultdict(list)
    observed = {name: Counter() for name in SELECTS}
    samples = defaultdict(list)
    industry_seen = Counter()
    degraded_industry = Counter()
    out_gz = OUT_DIR / 'projection.ndjson.gz'
    h_gz = hashlib.sha256()
    n_written = 0

    raw_fh = open(out_gz, 'wb')
    with gzip.GzipFile(filename='', mode='wb', fileobj=raw_fh, mtime=0) as gz:
        for raw in V.iter_json_file(SOURCE, strict=True):
            report['rows_total'] += 1
            if not (isinstance(raw, dict) and raw.get('source_url') and raw.get('application_url')):
                report['dropped_invalid'] += 1
                continue
            if V.test_rule(raw):
                report['dropped_test_record'] += 1
                continue
            identity = str(raw.get('id') or '').strip()
            if not identity:
                report['dropped_no_id'] += 1
                continue
            if identity in seen_ids:
                report['duplicate_id_first_wins'] += 1
                continue
            if raw.get('status') == 'removed':
                report['dropped_removed'] += 1
                continue
            seen_ids.add(identity)

            industry = str(raw.get('industry') or '').strip()
            industry_seen[industry or '<empty>'] += 1
            if industry not in V.INDUSTRIES:
                degraded_industry[industry or '<empty>'] += 1
                industry = '其他'
            group = GROUP_OF_INDUSTRY.get(industry, DEFAULT_GROUP)

            row = mirror_row(raw, industry)
            values = []
            for name in COLUMNS:
                value = row.get(name, '')
                values.append(cell(value))
                if name in SELECTS:
                    if name in MULTI:
                        for part in str(values[-1]).split(','):
                            if part:
                                observed[name][part] += 1
                    elif values[-1]:
                        observed[name][values[-1]] += 1
            payload = json.dumps({'g': group, 'c': values}, ensure_ascii=False,
                                 separators=(',', ':')).encode('utf-8') + b'\n'
            gz.write(payload)
            h_gz.update(payload)
            n_written += 1
            groups[group] += 1
            ids_per_group[group].append(identity)
            if len(samples[group]) < 2:
                samples[group].append({'job_id': identity, 'row': dict(zip(COLUMNS, values))})

    raw_fh.close()

    manifest = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'source_path': str(SOURCE),
        'source_sha256': source_sha,
        'source_bytes': SOURCE.stat().st_size,
        'columns': COLUMNS,
        'membership_report': dict(report),
        'rows_written': n_written,
        'groups': {g: {'rows': c} for g, c in sorted(groups.items())},
        'projection_ndjson_gz': {
            'path': str(out_gz),
            'bytes': out_gz.stat().st_size,
            'sha256_gz': sha256_file(out_gz),
            'sha256_plain_ndjson': h_gz.hexdigest(),
        },
        'industry_seen': dict(industry_seen.most_common()),
        'degraded_industry': dict(degraded_industry.most_common()),
        'observed_select_values': {k: dict(v.most_common()) for k, v in observed.items()},
        'samples': {g: v for g, v in samples.items()},
        'id_checks': {
            'unique_ids': len(seen_ids),
            'per_group_first_id': {g: ids[0] for g, ids in sorted(ids_per_group.items()) if ids},
            'per_group_last_id': {g: ids[-1] for g, ids in sorted(ids_per_group.items()) if ids},
            'per_group_id_sha256': {
                g: hashlib.sha256(('\n'.join(ids)).encode('utf-8')).hexdigest()
                for g, ids in sorted(ids_per_group.items())},
        },
        'seconds': round(time.time() - started, 2),
        'sprite_modules': {
            'v4_fields': sha256_file(ROOT / 'qiuzhao' / 'v4_fields.py'),
            'lark_sync_enrichment': sha256_file(ROOT / 'qiuzhao' / 'collector' / 'lark_sync_enrichment.py'),
            'sync_lark_multivalue': sha256_file(ROOT / 'qiuzhao' / 'collector' / 'sync_lark_multivalue.py'),
        },
    }
    (OUT_DIR / 'projection-manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'rows_written': n_written, 'groups': dict(groups),
                      'gz_bytes': manifest['projection_ndjson_gz']['bytes'],
                      'gz_sha256': manifest['projection_ndjson_gz']['sha256_gz'],
                      'seconds': manifest['seconds']}, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
