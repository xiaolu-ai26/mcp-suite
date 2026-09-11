"""Single-process staging runner: run every new adapter once, capture all states,
emit per-source jobs.json + manifest.json into staging_adapters/{company}/.
"""
import json, datetime as dt
from pathlib import Path

from qiuzhao.collector.run import Collector, now
from qiuzhao.collector.tencent import collect_tencent
from qiuzhao.collector.bytedance import collect_bytedance
from qiuzhao.collector.meituan import collect_meituan
from qiuzhao.collector.netease import collect_netease_all
from qiuzhao.collector.midea import collect_midea
from qiuzhao.collector.mindray import collect_mindray
from qiuzhao.collector.alibaba_headless import collect_alibaba

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/qiuzhao-v3-launch-20260910/staging_adapters'
TZ = dt.timezone(dt.timedelta(hours=8))

JOBS_DIR = OUT.parent / 'staging_run_single'
JOBS_DIR.mkdir(parents=True, exist_ok=True)
collector = Collector(JOBS_DIR, delay=0.6)
run_id = dt.datetime.now(TZ).strftime('%Y%m%dT%H%M%S')

JOBS = {}
JOBS['tencent'] = collect_tencent(collector)
JOBS['bytedance'] = collect_bytedance(collector)
JOBS['meituan'] = collect_meituan(collector)
JOBS['netease'] = collect_netease_all(collector)
JOBS['midea'] = collect_midea(collector)
JOBS['mindray'] = collect_mindray(collector)
JOBS['alibaba'] = collect_alibaba(collector)

DISPLAY = {'tencent': '腾讯', 'bytedance': '字节跳动', 'meituan': '美团',
           'netease': '网易(主站+互娱)', 'midea': '美的', 'mindray': '迈瑞医疗',
           'alibaba': '阿里巴巴(headless)'}

for sid, rows in JOBS.items():
    d = OUT / sid
    d.mkdir(parents=True, exist_ok=True)
    if sid == 'netease':
        st_main = collector.states.get('netease', {})
        st_huyu = collector.states.get('netease-huyu', {})
        expected = (st_main.get('expected_total') or 0) + (st_huyu.get('expected_total') or 0)
        pages = (st_main.get('pages_scanned') or 0) + (st_huyu.get('pages_scanned') or 0)
        errors = st_main.get('errors', []) + st_huyu.get('errors', [])
        status = 'success' if not errors else 'partial'
        complete = bool(st_main.get('complete') and st_huyu.get('complete'))
        api_url = st_main.get('api_url')
    else:
        st = collector.states.get(sid, {})
        expected = st.get('expected_total')
        pages = st.get('pages_scanned')
        errors = st.get('errors', [])
        status = st.get('status')
        complete = st.get('complete')
        api_url = st.get('api_url') or st.get('search_url')
    manifest = {
        'run_id': run_id, 'source_id': sid, 'display_name': DISPLAY[sid],
        'generated_at': dt.datetime.now(TZ).isoformat(timespec='seconds'),
        'transport': (collector.states.get(sid) or {}).get('transport') or 'public-http-json',
        'api_url': api_url, 'listing_url': (collector.states.get(sid) or {}).get('listing_url'),
        'pages_scanned': pages, 'expected_unique_ids': expected,
        'actual_unique_ids': len(rows),
        'diff': (len(rows) - expected) if isinstance(expected, int) else None,
        'complete': complete, 'status': status, 'anomalies': errors,
    }
    (d / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (d / 'jobs.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{sid:10s} expected={expected} actual={len(rows)} complete={complete} status={status}')

print('done')
