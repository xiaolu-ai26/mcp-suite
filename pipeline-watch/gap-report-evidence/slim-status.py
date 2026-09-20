import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
p = sys.argv[1] if len(sys.argv) > 1 else r'C:\mcp-suite-collector\runs\20260920\data\p1-runs\20260920T064151\status.json'
st = json.load(open(p, encoding='utf-8'))
out = {'started_at': st.get('started_at'), 'run_finished': st.get('run_finished'),
       'success': st.get('success'), 'pending': len(st.get('pending') or []),
       'results': {}}
for k, e in (st.get('results') or {}).items():
    c = e.get('coverage') or {}
    out['results'][k] = {
        'published': e.get('published'), 'publish_error': e.get('publish_error'),
        'coverage': {kk: c.get(kk) for kk in
                     ('company', 'scope', 'status', 'complete', 'expected_total',
                      'collected_jobs', 'pages_scanned', 'pagination_exhausted',
                      'retries', 'errors', 'detail_missing_count', 'source_url')},
    }
sys.stdout.write(json.dumps(out, ensure_ascii=False))
