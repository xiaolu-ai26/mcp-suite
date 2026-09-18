"""Foreign-company ATS batch A — real read-only verification runner.

Runs every configured Eightfold / Phenom tenant through the production
``p1_pipeline.collect_process`` path (one subprocess per company+scope, exactly
what the daily chain does) and reports, per tenant and scope:

* coverage status / complete / expected_total / collected_jobs / pages_scanned
* the official request count actually spent against the politeness budget
* field availability over the returned records (published_at, deadline, location,
  description length, official detail + application URLs)

Nothing is written to the production store, no ``--apply``, no network call that
logs in, signs or solves a challenge. Politeness for this run comes from
``QIUZHAO_PLATFORM_REQUEST_BUDGET`` (default 25) and
``QIUZHAO_PLATFORM_REQUEST_INTERVAL`` (default 2.0), read by both adapters.

Usage:
    python pipeline-watch/foreign-ats-a-verify.py --out <dir> [--tenant 惠普 ...]
"""
from __future__ import annotations
import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def field_rates(jobs):
    total = len(jobs)
    if not total:
        return {'jobs': 0}
    def rate(pred):
        return round(sum(1 for j in jobs if pred(j)) / total, 3)
    lengths = [len(str(j.get('description_raw') or '')) for j in jobs]
    return {
        'jobs': total,
        'published_at': rate(lambda j: bool(str(j.get('published_at') or '').strip())),
        'deadline_raw': rate(lambda j: bool(str(j.get('deadline_raw') or '').strip())),
        'location': rate(lambda j: bool(str(j.get('location') or '').strip())),
        'cities': rate(lambda j: bool(j.get('cities'))),
        'detail_url': rate(lambda j: bool(str(j.get('detail_url') or '').strip())),
        'application_url': rate(lambda j: bool(str(j.get('application_url') or '').strip())),
        'scope_evidence': rate(lambda j: bool(str(j.get('scope_evidence') or '').strip())),
        'description_median_len': int(statistics.median(lengths)) if lengths else 0,
        'description_min_len': min(lengths) if lengths else 0,
    }


def run_tenant(pipeline, company, scopes, out_dir, budget, interval):
    results = []
    for scope in scopes:
        target = out_dir / company / scope
        target.mkdir(parents=True, exist_ok=True)
        os.environ['QIUZHAO_PLATFORM_REQUEST_BUDGET'] = str(budget)
        os.environ['QIUZHAO_PLATFORM_REQUEST_INTERVAL'] = str(interval)
        os.environ['QIUZHAO_PLATFORM_MAX_PAGE_LOADS'] = str(budget)
        started = time.monotonic()
        try:
            result = pipeline.collect_process(company, scope, target, timeout=1800)
        except Exception as error:  # a broken tenant must not stop the sweep
            results.append({'scope': scope, 'status': 'error',
                            'errors': [f'{type(error).__name__}: {error}'],
                            'seconds': round(time.monotonic() - started, 1)})
            continue
        coverage = result.get('coverage') or {}
        jobs = result.get('jobs') or []
        (target / 'result.json').write_text(
            json.dumps(result, ensure_ascii=False), encoding='utf-8')
        results.append({
            'scope': scope,
            'status': coverage.get('status'),
            'complete': coverage.get('complete'),
            'detail_complete': coverage.get('detail_complete'),
            'pagination_exhausted': coverage.get('pagination_exhausted'),
            'expected_total': coverage.get('expected_total'),
            'collected_jobs': coverage.get('collected_jobs'),
            'pages_scanned': coverage.get('pages_scanned'),
            'requests_used': (coverage.get('request_budget') or {}).get('used'),
            'transport': coverage.get('mode') or (coverage.get('scope_request') or {}).get('params', {}).get('transport'),
            'note': coverage.get('note'),
            'errors': (coverage.get('errors') or [])[:4],
            'field_rates': field_rates(jobs),
            'seconds': round(time.monotonic() - started, 1),
        })
        print(f'  {company:8} {scope:7} status={str(results[-1]["status"]):8} '
              f'complete={str(results[-1]["complete"]):5} jobs={results[-1]["collected_jobs"]} '
              f'req={results[-1]["requests_used"]} {results[-1]["seconds"]}s', flush=True)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--tenant', action='append', default=None)
    parser.add_argument('--budget', type=int, default=25)
    parser.add_argument('--interval', type=float, default=2.0)
    parser.add_argument('--scopes', default='campus,intern,social')
    args = parser.parse_args()

    from qiuzhao.collector import p1_pipeline as pipeline
    from qiuzhao.collector import p1_platform_eightfold as eightfold
    from qiuzhao.collector import p1_platform_phenom as phenom

    registry = {}
    registry.update(eightfold.merged_registry())
    registry.update(phenom.merged_registry())
    companies = args.tenant or sorted(registry, key=lambda n: (registry[n], n))
    scopes = [s for s in args.scopes.split(',') if s]

    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        'started_at': datetime.now(timezone.utc).isoformat(),
        'budget_per_tenant_scope': args.budget,
        'interval_seconds': args.interval,
        'scopes': scopes,
        'tenants': {},
    }
    for company in companies:
        module = registry[company]
        print(f'== {company} ({module.rsplit(".", 1)[-1]})', flush=True)
        report['tenants'][company] = {
            'module': module,
            'host_group': pipeline.platform_group(company),
            'registry_ok': pipeline.REGISTRY.get(company) == module,
            'results': run_tenant(pipeline, company, scopes, args.out, args.budget, args.interval),
        }
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    (args.out / 'verify-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\nwrote', args.out / 'verify-report.json')


if __name__ == '__main__':
    main()
