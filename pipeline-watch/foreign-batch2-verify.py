#!/usr/bin/env python3
"""Read-only verification runner for the foreign-company batch-2 adapters.

Every target runs through the real pipeline adapter path
(``python -m qiuzhao.collector.p1_pipeline --adapter ...``) so the payload is
validated by ``p1_pipeline.validate_result``. Per-tenant request budget defaults
to 15 (the batch-2 politeness cap), every outbound request is spaced by >=2s
(``QIUZHAO_PLATFORM_REQUEST_INTERVAL``), and tenants are spaced by >=2.2s.
Nothing is deployed, nothing is written to the shared store, no account is used
and every request is a bare public GET/POST.

Usage:
    python pipeline-watch/foreign-batch2-verify.py [--only moka,foreign]
Artifacts land under $FOREIGN2_VERIFY_OUT (default the external scratch tree).
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
OUT = Path(os.environ.get(
    'FOREIGN2_VERIFY_OUT',
    '/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-2-out/verify2'))
BUDGET = os.environ.get('QIUZHAO_PLATFORM_REQUEST_BUDGET', '15')
SLEEP = float(os.environ.get('FOREIGN2_VERIFY_SLEEP', '2.2'))
PER_REQUEST_SLEEP = float(os.environ.get('FOREIGN2_VERIFY_REQUEST_INTERVAL', '2.0'))

MOKA = 'qiuzhao.collector.p1_platform_moka'
FOREIGN = 'qiuzhao.collector.p1_foreign_01'

# (adapter, company, scope, slug)
TARGETS = [
    # --- one-line adds: Moka foreign tenants (batch 2) ---
    (MOKA, '普华永道', 'campus', 'moka-pwc-campus'),
    (MOKA, '毕马威', 'campus', 'moka-kpmg-campus'),
    (MOKA, '高露洁', 'campus', 'moka-colpal-campus'),
    (MOKA, '德州仪器', 'campus', 'moka-ti-campus'),
    (MOKA, '拜耳', 'campus', 'moka-bayer-campus'),
    (MOKA, '特斯拉', 'campus', 'moka-tesla-campus'),
    (MOKA, '大众汽车集团(CARIAD)', 'campus', 'moka-vwa-campus'),
    (MOKA, '达能', 'campus', 'moka-danone-campus'),
    (MOKA, '达美乐中国', 'campus', 'moka-dominos-campus'),
    (MOKA, 'Shopee', 'campus', 'moka-shopee-campus'),
    (MOKA, '博西家电', 'campus', 'moka-bshg-campus'),
    (MOKA, '伊顿', 'campus', 'moka-eaton-campus'),
    (MOKA, '德莎', 'campus', 'moka-tesa-campus'),
    (MOKA, '阿特拉斯科普柯', 'campus', 'moka-atlas-campus'),
    (MOKA, '神龙汽车', 'campus', 'moka-dfmc-campus'),
]


def _extra_targets():
    """Optional JSON list of extra [adapter, company, scope, slug] rows.

    Set FOREIGN2_EXTRA_TARGETS to a JSON file path (list of 4-item lists) to run
    a different batch without editing this file.
    """
    path = os.environ.get('FOREIGN2_EXTRA_TARGETS')
    if not path:
        return []
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    return [tuple(r) for r in rows]


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', default='',
                        help='comma-separated adapter module suffixes to run')
    parser.add_argument('--out', default=str(OUT))
    args = parser.parse_args()
    out_root = Path(args.out)
    targets = _extra_targets() or TARGETS
    if args.only:
        keys = {k.strip() for k in args.only.split(',') if k.strip()}
        targets = [t for t in targets
                   if t[0].rsplit('.', 1)[-1] in keys or t[3].split('-')[0] in keys]
    env = dict(os.environ, QIUZHAO_PLATFORM_REQUEST_BUDGET=BUDGET,
               QIUZHAO_PLATFORM_REQUEST_INTERVAL=str(PER_REQUEST_SLEEP),
               PYTHONPATH=str(ROOT))
    summary = []
    for adapter, company, scope, slug in targets:
        outdir = out_root / slug
        outdir.mkdir(parents=True, exist_ok=True)
        command = [PY, '-m', 'qiuzhao.collector.p1_pipeline', '--adapter', adapter,
                   '--company', company, '--scope', scope, '--output-dir', str(outdir)]
        started = time.time()
        proc = subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True)
        result_path = outdir / 'result.json'
        if result_path.exists():
            payload = json.loads(result_path.read_text(encoding='utf-8'))
            row = {'adapter': adapter.rsplit('.', 1)[-1], 'company': company, 'scope': scope,
                   'slug': slug, 'exit': proc.returncode, 'seconds': round(time.time() - started, 1)}
            row.update(summarize(payload))
        else:
            row = {'adapter': adapter.rsplit('.', 1)[-1], 'company': company, 'scope': scope,
                   'slug': slug, 'exit': proc.returncode, 'seconds': round(time.time() - started, 1),
                   'status': 'no-result', 'stderr': proc.stderr[-400:]}
        summary.append(row)
        (out_root / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                               encoding='utf-8')
        print(json.dumps(row, ensure_ascii=False), flush=True)
        time.sleep(SLEEP)
    print('WROTE', out_root / 'summary.json')


if __name__ == '__main__':
    main()
