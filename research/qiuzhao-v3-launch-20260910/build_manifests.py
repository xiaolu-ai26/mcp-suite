"""Emit per-source manifest + filtered job snapshot into staging_adapters/{company}/.

Reads the merged staging_run/jobs.json + source_state.json and produces, for each
new source, a manifest.json (run_id, source_id, timing, pages, expected vs actual
unique ids, anomalies) and jobs.<prefix>.json (this source's rows only).
"""
import json, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STG_RUN = ROOT / 'research/qiuzhao-v3-launch-20260910/staging_run'
OUT = ROOT / 'research/qiuzhao-v3-launch-20260910/staging_adapters'
TZ = dt.timezone(dt.timedelta(hours=8))

jobs = json.loads((STG_RUN / 'jobs.json').read_text())
state = json.loads((STG_RUN / 'source_state.json').read_text())
run_id = dt.datetime.now(TZ).strftime('%Y%m%dT%H%M%S')

# source prefix -> (source_id, display name)
SOURCES = {
    'meituan': ('meituan', '美团'),
    'netease': ('netease', '网易(主站+互娱)'),
    'midea': ('midea', '美的'),
    'mindray': ('mindray', '迈瑞医疗'),
    'tencent': ('tencent', '腾讯'),
    'bytedance': ('bytedance', '字节跳动'),
    'alibaba': ('alibaba', '阿里巴巴(headless)'),
}

for prefix, (sid, name) in SOURCES.items():
    rows = [j for j in jobs if j['id'].startswith(prefix + '-')]
    s = state.get(sid, {})
    d = OUT / prefix
    d.mkdir(parents=True, exist_ok=True)
    # netease registers two state keys
    if prefix == 'netease':
        st_main = state.get('netease', {})
        st_huyu = state.get('netease-huyu', {})
        expected = (st_main.get('expected_total') or 0) + (st_huyu.get('expected_total') or 0)
        pages = (st_main.get('pages_scanned') or 0) + (st_huyu.get('pages_scanned') or 0)
        errors = st_main.get('errors', []) + st_huyu.get('errors', [])
    else:
        expected = s.get('expected_total')
        pages = s.get('pages_scanned')
        errors = s.get('errors', [])
    manifest = {
        'run_id': run_id,
        'source_id': sid,
        'display_name': name,
        'generated_at': dt.datetime.now(TZ).isoformat(timespec='seconds'),
        'transport': s.get('transport') or 'public-http-json',
        'api_url': s.get('api_url') or s.get('search_url'),
        'listing_url': s.get('listing_url'),
        'pages_scanned': pages,
        'expected_unique_ids': expected,
        'actual_unique_ids': len(rows),
        'diff': (len(rows) - expected) if isinstance(expected, int) else None,
        'complete': s.get('complete'),
        'status': s.get('status'),
        'anomalies': errors,
        'note': s.get('note', ''),
    }
    (d / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (d / 'jobs.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{prefix:10s} expected={expected} actual={len(rows)} complete={s.get("complete")} status={s.get("status")}')

print('manifests written to', OUT)
