import sys, json, time
sys.path.insert(0, '/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-500-mvp')
from collector.run import collect_company
from collector.core import State, WORK

q = json.load(open(WORK / 'state' / 'queue.json'))
known = {}
slugs = sys.argv[1].split(',') if len(sys.argv) > 1 else ['f500-2', 'f500-4', 'f500-1']
state = State()
for co in [c for c in q if c['slug'] in slugs]:
    t0 = time.time()
    try:
        recs, cfg = collect_company(co, known)
        print('OK', co['cn_name'], len(recs), cfg.get('kind'), f"{time.time()-t0:.0f}s",
              recs[0]['job_title'][:60])
    except Exception as e:
        print('FAIL', co['cn_name'], type(e).__name__, str(e)[:90], f"{time.time()-t0:.0f}s")
