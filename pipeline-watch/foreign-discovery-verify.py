#!/usr/bin/env python3
"""Read-only verification runner for the foreign "find-all" discovery batch.

Every target runs through the real pipeline adapter path
(``python -m qiuzhao.collector.p1_pipeline --adapter ...``) so the payload is
validated by ``p1_pipeline.validate_result``. Per-tenant request budget defaults
to 15 (the discovery-batch politeness cap), every outbound request is spaced by
>=2s (``QIUZHAO_PLATFORM_REQUEST_INTERVAL``) and tenants are spaced by >=2.2s.
Nothing is deployed, nothing is written to the shared store, no account is used
and every request is a bare public GET/POST.

Usage:
    python pipeline-watch/foreign-discovery-verify.py --targets <targets.json>
    python pipeline-watch/foreign-discovery-verify.py --only job51,moka

Targets file: ``[[adapter_module, company, scope, slug], ...]`` (same shape as
``foreign-batch2-verify.py``). Artifacts land under $FOREIGN_DISCOVERY_VERIFY_OUT.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
DEFAULT_OUT = '/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/verify'
OUT = Path(os.environ.get('FOREIGN_DISCOVERY_VERIFY_OUT', DEFAULT_OUT))
BUDGET = os.environ.get('QIUZHAO_PLATFORM_REQUEST_BUDGET', '15')
SLEEP = float(os.environ.get('FOREIGN_DISCOVERY_VERIFY_SLEEP', '2.2'))
PER_REQUEST_SLEEP = float(os.environ.get('FOREIGN_DISCOVERY_VERIFY_REQUEST_INTERVAL', '2.0'))
WORKERS = int(os.environ.get('FOREIGN_DISCOVERY_VERIFY_WORKERS', '4'))

MOKA = 'qiuzhao.collector.p1_platform_moka'
BEISEN = 'qiuzhao.collector.p1_platform_beisen'
FEISHU = 'qiuzhao.collector.p1_feishu_public'
DAYEE = 'qiuzhao.collector.p1_foreign_01'
WORKDAY = 'qiuzhao.collector.p1_platform_workday'
JOB51 = 'qiuzhao.collector.p1_platform_51job'


def summarize(payload):
    c = payload.get('coverage') or {}
    jobs = payload.get('jobs') or []
    published = sum(1 for j in jobs if j.get('published_at'))
    deadline = sum(1 for j in jobs if j.get('deadline_raw'))
    cohort = sum(1 for j in jobs if str(j.get('cohort_raw') or '').strip())
    n = max(len(jobs), 1)
    return {
        'status': c.get('status'), 'complete': c.get('complete'),
        'collected_jobs': len(jobs), 'expected_total': c.get('expected_total'),
        'pages_scanned': c.get('pages_scanned'), 'pagination_exhausted': c.get('pagination_exhausted'),
        'detail_complete': c.get('detail_complete'),
        'request_budget': c.get('request_budget'),
        'published_rate': round(published / n, 3), 'deadline_rate': round(deadline / n, 3),
        'cohort_rate': round(cohort / n, 3),
        'errors': (c.get('errors') or [])[:4], 'note': c.get('note', ''),
        'sample_titles': [j.get('job_title') for j in jobs[:4]],
    }


def run_target(target):
    adapter, company, scope, slug = target
    outdir = OUT / slug
    outdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, QIUZHAO_PLATFORM_REQUEST_BUDGET=BUDGET,
               QIUZHAO_PLATFORM_REQUEST_INTERVAL=str(PER_REQUEST_SLEEP),
               PYTHONPATH=str(ROOT))
    command = [PY, '-m', 'qiuzhao.collector.p1_pipeline', '--adapter', adapter,
               '--company', company, '--scope', scope, '--output-dir', str(outdir)]
    started = time.time()
    proc = subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True)
    result_path = outdir / 'result.json'
    row = {'adapter': adapter.rsplit('.', 1)[-1], 'company': company, 'scope': scope,
           'slug': slug, 'exit': proc.returncode, 'seconds': round(time.time() - started, 1)}
    if result_path.exists():
        payload = json.loads(result_path.read_text(encoding='utf-8'))
        row.update(summarize(payload))
    else:
        row.update({'status': 'no-result', 'stderr': proc.stderr[-400:]})
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--targets', default=str(ROOT / 'pipeline-watch' / 'foreign-discovery-targets.json'))
    parser.add_argument('--only', default='', help='comma-separated adapter module suffixes')
    parser.add_argument('--out', default=DEFAULT_OUT)
    parser.add_argument('--workers', type=int, default=WORKERS)
    args = parser.parse_args()
    global OUT
    OUT = Path(args.out)
    OUT.mkdir(parents=True, exist_ok=True)
    targets = [tuple(t) for t in json.loads(Path(args.targets).read_text(encoding='utf-8'))]
    if args.only:
        keys = {k.strip() for k in args.only.split(',') if k.strip()}
        targets = [t for t in targets if t[0].rsplit('.', 1)[-1] in keys or t[3].split('-')[0] in keys]
    print('RUN %d targets, workers=%s, budget=%s' % (len(targets), args.workers, BUDGET), flush=True)
    summary = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for row in pool.map(run_target, targets):
            summary.append(row)
            (OUT / 'summary.json').write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
            time.sleep(SLEEP / max(1, args.workers))
    ok = [r for r in summary if r.get('status') in ('success', 'partial')]
    print('DONE %d/%d success|partial -> %s' % (len(ok), len(summary), OUT / 'summary.json'), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
