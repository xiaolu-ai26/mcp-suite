#!/usr/bin/env python3
"""Read-only first-batch verification for the foreign-company platform adapters.

Runs each (adapter, company, scope) through the real pipeline adapter path
(``python -m qiuzhao.collector.p1_pipeline --adapter ...``) so the returned
payload is validated by ``p1_pipeline.validate_result``. Per-tenant request
budget defaults to 20, every outbound request is spaced by >=2s
(``QIUZHAO_PLATFORM_REQUEST_INTERVAL``), and tenants are spaced by >=2.2s.
Nothing is deployed, nothing is written to the shared store, and every request
is a bare public GET/POST.

Usage:
    QIUZHAO_PLATFORM_REQUEST_BUDGET=20 python pipeline-watch/foreign-platforms-verify.py
Artifacts land under $FOREIGN_VERIFY_OUT (default the external scratch tree).
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
OUT = Path(os.environ.get(
    'FOREIGN_VERIFY_OUT',
    '/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-out/verify'))
BUDGET = os.environ.get('QIUZHAO_PLATFORM_REQUEST_BUDGET', '20')
SLEEP = float(os.environ.get('FOREIGN_VERIFY_SLEEP', '2.2'))
PER_REQUEST_SLEEP = float(os.environ.get('FOREIGN_VERIFY_REQUEST_INTERVAL', '2.0'))

WORKDAY = 'qiuzhao.collector.p1_platform_workday'
SF = 'qiuzhao.collector.p1_platform_successfactors'
# (adapter, company, scope, slug)
TARGETS = [
    (WORKDAY, '英伟达', 'campus', 'workday-nvidia-campus'),
    (WORKDAY, '强生', 'campus', 'workday-jnj-campus'),
    (WORKDAY, '壳牌', 'campus', 'workday-shell-campus'),
    (WORKDAY, '英国石油', 'campus', 'workday-bp-campus'),
    (WORKDAY, '美敦力', 'campus', 'workday-medtronic-campus'),
    (WORKDAY, '奥纬咨询', 'campus', 'workday-oliverwyman-campus'),
    (WORKDAY, '花旗银行', 'campus', 'workday-citi-campus'),
    (WORKDAY, '美满电子', 'campus', 'workday-marvell-campus'),
    (WORKDAY, '史密夫斐尔', 'campus', 'workday-hsf-campus'),
    (WORKDAY, '花旗银行', 'intern', 'workday-citi-intern'),
    (WORKDAY, '美满电子', 'intern', 'workday-marvell-intern'),
    (WORKDAY, '史密夫斐尔', 'intern', 'workday-hsf-intern'),
    (WORKDAY, '英伟达', 'intern', 'workday-nvidia-intern'),
    (SF, '思爱普', 'campus', 'sf-sap-campus'),
    (SF, '采埃孚', 'campus', 'sf-zf-campus'),
    (SF, '勃林格殷格翰', 'campus', 'sf-boehringer-campus'),
    (SF, '思爱普', 'intern', 'sf-sap-intern'),
    (SF, '采埃孚', 'intern', 'sf-zf-intern'),
    (SF, '勃林格殷格翰', 'intern', 'sf-boehringer-intern'),
]


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
        'location_filtered_count': c.get('location_filtered_count'),
        'request_budget': c.get('request_budget'),
        'published_rate': round(published / n, 3), 'deadline_rate': round(deadline / n, 3),
        'cohort_rate': round(cohort / n, 3),
        'errors': c.get('errors') or [], 'note': c.get('note', ''),
        'sample_titles': [j.get('job_title') for j in jobs[:4]],
    }


def main():
    env = dict(os.environ, QIUZHAO_PLATFORM_REQUEST_BUDGET=BUDGET,
               QIUZHAO_PLATFORM_REQUEST_INTERVAL=str(PER_REQUEST_SLEEP),
               PYTHONPATH=str(ROOT))
    summary = []
    for adapter, company, scope, slug in TARGETS:
        outdir = OUT / slug
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
        # Persist after every target so an interruption never loses finished results.
        (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding='utf-8')
        print(json.dumps(row, ensure_ascii=False), flush=True)
        time.sleep(SLEEP)
    print('WROTE', OUT / 'summary.json')


if __name__ == '__main__':
    main()
