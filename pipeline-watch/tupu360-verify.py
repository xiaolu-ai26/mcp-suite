#!/usr/bin/env python
"""tupu360 adapter field verification (read-only, no apply, no DB write).

Runs every configured tupu360 company through all three scopes with a hard
per-tenant request budget and a >=2s spacing, validates each payload with the
production ``p1_pipeline.validate_result`` and writes a machine readable summary
plus a markdown table.

    /Users/maxzhl/Projects/mcp-suite/.venv/bin/python \
        pipeline-watch/tupu360-verify.py --out /path/to/out [--channels-probe]

Nothing here writes to the job store: it only calls the adapter and the
validator. No login, no cookies, no CAPTCHA work.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from qiuzhao.collector import p1_pipeline  # noqa: E402
from qiuzhao.collector import p1_platform_tupu360 as tupu  # noqa: E402

SCOPES = ('campus', 'intern', 'social')
# Survey read-only facts gathered by hand; kept next to the numbers so the
# receipt never has to re-derive them from a live run.
SURVEY = {
    'iqvia': {'listed_channels': 'campus 12 / intern 5 / social 12 (template A)'},
    'lilly': {'listed_channels': 'campus 17 (2 pages) / intern 0 / social 0 (template A)'},
    'schaeffler': {'listed_channels': 'campus 0 / intern 2 + TECHNOLOGYRUITMENT 2 / social 70 (5 pages, template B)'},
    'bmw': {'listed_channels': 'campus 0 / intern 0 / social 15 (2 pages, template A)'},
    'innomotics': {'listed_channels': 'campus 3 / intern 5 / social 36 (3 pages, template B)'},
    'jnj': {'listed_channels': 'campus 18 via POST /jnj/position/nextPageList (template B)'},
}


def tenant_facts(key):
    entry = tupu._entry(key)
    return {
        'name': entry.get('name') or key,
        'host': tupu.tenant_host(key),
        'slug': tupu.tenant_slug(key),
        'enabled': entry.get('enabled') is not False,
        'wechat_only': tupu.is_wechat_only(key),
        'note': entry.get('note') or '',
    }


def rate(values):
    values = list(values)
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values), 3)


def run_company_scope(key, scope, out_dir, budget, interval, extra_channels=None):
    company = tupu._entry(key).get('name') or tupu.COMPANIES.get(key) or key
    started = time.time()
    payload = tupu.collect(company, scope, out_dir / key / scope, max_requests=budget,
                           include_disabled=True)
    elapsed = time.time() - started
    validated = None
    validation_error = ''
    try:
        validated = p1_pipeline.validate_result(payload, company, scope, out_dir / key / scope)
        (out_dir / key / scope / 'validated.json').write_text(
            json.dumps(validated, ensure_ascii=False), encoding='utf-8')
    except Exception as error:  # a failing contract is itself a result
        validation_error = f'{type(error).__name__}: {error}'
    jobs = (validated or payload)['jobs']
    coverage = payload['coverage']
    china = [job for job in jobs if any(
        not str(city).strip() or not any(token in str(city) for token in ('国外', '海外'))
        for city in (job.get('cities') or [job.get('city') or '']))]
    return {
        'company_key': key,
        'company': company,
        'scope': scope,
        'status': coverage.get('status'),
        'complete': coverage.get('complete'),
        'jobs': len(jobs),
        'jobs_china': len(china),
        'expected_total': coverage.get('expected_total'),
        'detail_complete': coverage.get('detail_complete'),
        'pages_scanned': coverage.get('pages_scanned'),
        'channels_used': coverage.get('channels_used'),
        'channel_evidence': coverage.get('channel_evidence'),
        'requests_used': (coverage.get('request_budget') or {}).get('used'),
        'published_at_rate': rate(job.get('published_at') for job in jobs),
        'deadline_rate': rate(job.get('deadline_raw') for job in jobs),
        'description_rate': rate(job.get('description_raw') for job in jobs),
        'location_rate': rate(job.get('city') for job in jobs),
        'cohort_filled': sum(1 for job in jobs if job.get('cohort_raw')),
        'errors': coverage.get('errors'),
        'note': coverage.get('note'),
        'validation_error': validation_error,
        'validation_ok': validation_error == '',
        'elapsed_s': round(elapsed, 1),
        'sample_titles': [job.get('job_title') for job in jobs[:3]],
        'sample_published': [job.get('published_at') for job in jobs[:3]],
        'sample_cities': [job.get('city') for job in jobs[:3]],
    }


def channels_probe(out_dir, interval, budget):
    """Exercise the three fetch channels separately on tenants that have data."""
    probes = []
    cases = [
        ('iqvia', 'campus', 'html', {}),
        ('iqvia', 'campus', 'api', {}),
        ('iqvia', 'campus', 'headless', {}),
        ('jnj', 'campus', 'html', {}),
        ('jnj', 'campus', 'api', {}),
        ('schaeffler', 'intern', 'html', {}),
        ('schaeffler', 'intern', 'headless', {}),
    ]
    for key, scope, channel, kwargs in cases:
        company = tupu._entry(key).get('name') or tupu.COMPANIES[key]
        target = out_dir / 'channels' / key / f'{channel}-{scope}'
        started = time.time()
        record = {'company_key': key, 'company': company, 'scope': scope, 'channel': channel}
        try:
            payload = tupu.collect(company, scope, target, max_requests=budget,
                                   fetch_channel=channel, include_disabled=True)
            coverage = payload['coverage']
            record.update(status=coverage.get('status'), jobs=len(payload['jobs']),
                          requests_used=(coverage.get('request_budget') or {}).get('used'),
                          channels_used=coverage.get('channels_used'),
                          error='; '.join(coverage.get('errors') or [])[:400])
        except Exception as error:
            record.update(status='error', error=f'{type(error).__name__}: {error}'[:400])
        record['elapsed_s'] = round(time.time() - started, 1)
        record['published_at_rate'] = None
        probes.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    return probes


def mobile_probe(out_dir, interval):
    """Channel 2: the same public pages requested with a mobile/H5 User-Agent."""
    import requests
    ua = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
          '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')
    results = []
    for key in ('iqvia', 'lilly', 'schaeffler', 'innomotics'):
        url = tupu.list_url(key, tupu.channel_for(key, 'campus'))
        time.sleep(max(2.0, interval))
        try:
            response = requests.get(url, headers={**tupu.HEADERS, 'User-Agent': ua}, timeout=(10, 40))
            parsed = tupu.parse_list(response.text)
            results.append({'company_key': key, 'url': url, 'status': response.status_code,
                            'bytes': len(response.content), 'template': parsed['template'],
                            'rows': len(parsed['rows']),
                            'note': 'same server-rendered page; the mobile UA gets an identical document'})
        except Exception as error:
            results.append({'company_key': key, 'url': url, 'status': 'error',
                            'note': f'{type(error).__name__}: {error}'})
    (out_dir / 'channels' / 'mobile-probe.json').write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return results


def markdown(rows, facts):
    lines = ['| # | 公司 | tenant / host | scope | status | complete | 条数 | 期望总数 | 发布时间可用率 | 截止日可用率 | 请求数 |',
             '|---|---|---|---|---|---|---|---|---|---|---|']
    for index, row in enumerate(rows, 1):
        fact = facts[row['company_key']]
        lines.append('| {} | {} | `{}` @ {} | {} | {} | {} | {} | {} | {} | {} | {} |'.format(
            index, row['company'], fact['slug'], fact['host'], row['scope'], row['status'],
            row['complete'], row['jobs'], row['expected_total'],
            '-' if row['published_at_rate'] is None else f"{row['published_at_rate']:.0%}",
            '-' if row['deadline_rate'] is None else f"{row['deadline_rate']:.0%}",
            row['requests_used']))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--companies', default='')
    parser.add_argument('--scopes', default=','.join(SCOPES))
    parser.add_argument('--budget', type=int, default=25)
    parser.add_argument('--interval', type=float, default=2.2)
    parser.add_argument('--channels-probe', action='store_true')
    parser.add_argument('--mobile-probe', action='store_true')
    args = parser.parse_args()

    os.environ['QIUZHAO_PLATFORM_REQUEST_INTERVAL'] = str(max(2.0, args.interval))
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    all_keys = list(tupu._read_platform().keys())
    all_keys = [key for key in all_keys if not str(key).startswith('_')]
    keys = [key for key in (args.companies.split(',') if args.companies else all_keys) if key]
    scopes = [scope for scope in args.scopes.split(',') if scope]

    rows = []
    for key in keys:
        for scope in scopes:
            row = run_company_scope(key, scope, out_dir, args.budget, args.interval)
            rows.append(row)
            print(json.dumps({k: row[k] for k in
                              ('company_key', 'scope', 'status', 'complete', 'jobs',
                               'expected_total', 'requests_used', 'published_at_rate',
                               'deadline_rate', 'validation_ok')}, ensure_ascii=False), flush=True)

    facts = {key: tenant_facts(key) for key in keys}
    summary = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'budget_per_tenant_scope': args.budget,
        'min_interval_s': max(2.0, args.interval),
        'facts': facts,
        'survey': {key: SURVEY.get(key, {}) for key in keys},
        'rows': rows,
    }
    if args.channels_probe:
        summary['channels_probe'] = channels_probe(out_dir, args.interval, args.budget)
    if args.mobile_probe:
        summary['mobile_probe'] = mobile_probe(out_dir, args.interval)
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding='utf-8')
    table = markdown(rows, facts)
    (out_dir / 'summary.md').write_text(
        '# tupu360 adapter field verification\n\n' + table + '\n', encoding='utf-8')
    print(table)
    totals = {}
    for row in rows:
        totals[row['company_key']] = totals.get(row['company_key'], 0) + (row['requests_used'] or 0)
    print('\nrequests per tenant (all scopes): ' + json.dumps(totals, ensure_ascii=False))
    print('requests total: %d' % sum(totals.values()))
    if rows:
        print('median requests/unit: %s' % statistics.median([row['requests_used'] or 0 for row in rows]))


if __name__ == '__main__':
    main()
