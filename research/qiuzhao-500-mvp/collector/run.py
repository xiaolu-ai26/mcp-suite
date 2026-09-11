"""Main runner: process companies from queue, discover endpoints, collect, save.

Usage:
  run.sh --limit 20 [--batch-name batch1] [--only slug1,slug2]
"""
import argparse, json, sys, time
from pathlib import Path
from .core import WORK, State, Blocked, build_record, now_iso
from . import adapters, discover
from .seeds import build_queue, load_prod_units
from .discover import affinity

# 仅保留已人工核验过的端点（host/slug 与公司名强匹配）
KNOWN = {
    # (verified at runtime, persisted into state/known_endpoints.json automatically)
}


def load_known():
    p = WORK / 'state' / 'known_endpoints.json'
    if p.exists():
        return json.loads(p.read_text())
    return {}


def save_known(known):
    p = WORK / 'state' / 'known_endpoints.json'
    p.write_text(json.dumps(known, ensure_ascii=False, indent=1))


def collect_company(co, known):
    cfg = co.get('adapter') or KNOWN.get(co['slug']) or known.get(co['slug'])
    cands = []
    if cfg:
        cands = [(cfg, 'known')]
    else:
        for c, u in discover.discover_all(co):
            cands.append((c, u))
    if not cands:
        raise Blocked('未找到可用的招聘API入口')
    last_err = None
    for cfg, src in cands:
        if not affinity(cfg, co):
            last_err = '端点与公司名不匹配(疑似错配)'
            continue
        try:
            raws = adapters.collect({**co, 'adapter': cfg})
            recs = []
            for i, raw in enumerate(raws, 1):
                try:
                    recs.append(build_record(co, raw, i))
                except Blocked:
                    continue
            if recs:
                known[co['slug']] = cfg
                for r in recs:
                    r['source_note'] = src
                return recs, cfg
            last_err = '采集到0条合格岗位'
        except Blocked as e:
            last_err = str(e.reason)
    raise Blocked(last_err or '全部端点失败')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--batch-name', default=None)
    ap.add_argument('--only', default=None)
    ap.add_argument('--prio', type=int, default=None)
    ap.add_argument('--rebuild-queue', action='store_true')
    args = ap.parse_args()

    state = State()
    qfile = WORK / 'state' / 'queue.json'
    prod_units = load_prod_units()
    if prod_units is None:
        print('!! 缺少 state/prod_units.json')
        sys.exit(2)
    if args.rebuild_queue or not qfile.exists():
        q = build_queue(prod_units)
        print(f'queue rebuilt: {len(q)}')
    queue = json.loads(qfile.read_text())

    if args.only:
        only = set(args.only.split(','))
        queue = [c for c in queue if c['slug'] in only]
    if args.prio is not None:
        queue = [c for c in queue if c['priority'] == args.prio]

    known = load_known()
    batch_recs, batch_meta = [], []
    processed = 0
    for co in queue:
        if processed >= args.limit:
            break
        if co['slug'] in state.d['done'] or co['slug'] in state.d['blocked']:
            continue
        t0 = time.time()
        try:
            recs, cfg = collect_company(co, known)
            save_known(known)
            state.add_done(co['slug'], {'cn_name': co['cn_name'],
                                        'jobs': len(recs), 'at': now_iso(),
                                        'kind': cfg.get('kind')})
            batch_recs.extend(recs)
            batch_meta.append({'slug': co['slug'], 'cn_name': co['cn_name'],
                               'jobs': len(recs)})
            print(f"OK  {co['cn_name']} ({co['slug']}) +{len(recs)} [{cfg.get('kind')}] "
                  f"{time.time()-t0:.0f}s", flush=True)
        except Blocked as e:
            state.add_blocked(co['slug'], str(e.reason))
            print(f"BLK {co['cn_name']} ({co['slug']}): {e.reason} {time.time()-t0:.0f}s",
                  flush=True)
        except Exception as e:
            state.add_blocked(co['slug'], f'异常: {type(e).__name__}:{e}')
            print(f"ERR {co['cn_name']}: {type(e).__name__} {e}", flush=True)
        processed += 1

    if batch_recs:
        bname = args.batch_name or f"candidate_batch_{now_iso()[:16].replace(':','').replace('T','')}"
        out = WORK / 'candidate_batches' / f'{bname}.json'
        out.write_text(json.dumps({'batch': bname, 'generated_at': now_iso(),
                                   'companies': batch_meta, 'jobs': batch_recs},
                                  ensure_ascii=False, indent=1))
        print(f'\nbatch saved: {out} companies={len(batch_meta)} jobs={len(batch_recs)}')
    print(f'processed={processed} ok={len(batch_meta)} blocked={processed-len(batch_meta)}')


if __name__ == '__main__':
    main()
