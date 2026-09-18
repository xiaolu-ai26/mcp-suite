#!/usr/bin/env python3
"""Batch-verify 闲鱼-table ATS tenants with the real (read-only) adapters.

For every tenant slug of one platform it runs one ``campus`` collection with a
per-tenant request budget (default 15) and >=2s between tenants. No ``--apply``,
no database writes, no login. Results are appended to ``<out>/<platform>.json``
after every tenant so the run is resumable.

Company names come from the table here; the official site name is captured when
the platform discloses it (Feishu tenant_name) and is preferred by the config
writer.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INFO_RE = re.compile(r'id="js-websiteInfo"[^>]*>(.*?)</script>', re.S)
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


class TenantTimeout(Exception):
    pass


def _on_alarm(signum, frame):
    raise TenantTimeout('tenant wall-clock budget exceeded')


signal.signal(signal.SIGALRM, _on_alarm)


def slug_dir_name(slug):
    return re.sub(r'[^0-9A-Za-z._-]+', '_', slug)


def compact(slug, company, urls, result, seconds, official_name=''):
    cov = result.get('coverage') or {}
    budget = cov.get('request_budget') or {}
    return {
        'slug': slug,
        'company_table': company,
        'official_name': official_name,
        'urls': urls,
        'status': cov.get('status'),
        'complete': cov.get('complete'),
        'jobs': len(result.get('jobs') or []),
        'pending': len(result.get('pending_index') or []),
        'expected_total': cov.get('expected_total'),
        'requests': budget.get('used'),
        'seconds': round(seconds, 1),
        'errors': [str(e)[:300] for e in (cov.get('errors') or [])][:6],
        'request_budget_exhausted': bool(cov.get('request_budget_exhausted')),
    }


def run_beisen(slug, name, urls, outdir, budget):
    from qiuzhao.collector import p1_platform_beisen as B
    previous_slug = B.COMPANIES.get(slug)
    previous_name = B.NAME_TO_SLUG.get(name)
    original_host = B.host_for
    # The table link is the exact official portal path (e.g. /Campus); the bare
    # root sometimes serves a multi-portal landing or WAF page without PortalId.
    candidate = next((u.replace('&amp;', '&') for u in urls if 'zhiye.com' in u), None)
    B.COMPANIES[slug] = name
    B.NAME_TO_SLUG[name] = slug
    if candidate:
        B.host_for = lambda key: candidate
    try:
        result = B.collect(slug, 'campus', outdir, max_requests=budget)
    finally:
        B.host_for = original_host
        if previous_slug is None:
            B.COMPANIES.pop(slug, None)
        else:
            B.COMPANIES[slug] = previous_slug
        if previous_name is None:
            B.NAME_TO_SLUG.pop(name, None)
        else:
            B.NAME_TO_SLUG[name] = previous_name
    official = ''
    entry = outdir / 'official-entry.html'
    if entry.exists():
        title = re.search(r'<title[^>]*>(.*?)</title>', entry.read_text(errors='ignore'), re.S | re.I)
        if title:
            official = re.sub(r'\s+', ' ', title.group(1)).strip()[:80]
    return result, official


def run_moka(slug, name, urls, outdir, budget):
    from qiuzhao.collector import p1_platform_moka as M
    previous_slug = M.COMPANIES.get(slug)
    previous_name = M.NAME_TO_SLUG.get(name)
    original_sites = M.sites_for
    site_urls = [url for url in urls if re.search(r'/(?:campus|social)-recruitment/[^/]+/\d+', url)] or urls
    M.COMPANIES[slug] = name
    M.NAME_TO_SLUG[name] = slug
    M.sites_for = lambda key: [(url, 'xianyu table link') for url in site_urls]
    try:
        result = M.collect(slug, 'campus', outdir, max_requests=budget)
    finally:
        M.sites_for = original_sites
        if previous_slug is None:
            M.COMPANIES.pop(slug, None)
        else:
            M.COMPANIES[slug] = previous_slug
        if previous_name is None:
            M.NAME_TO_SLUG.pop(name, None)
        else:
            M.NAME_TO_SLUG[name] = previous_name
    return result, ''


def feishu_discover(slug, urls):
    import requests
    candidates = [url for url in urls if slug + '.jobs.feishu.cn' in url]
    candidates.append('https://' + slug + '.jobs.feishu.cn/')
    seen = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            response = requests.get(url, timeout=(8, 20), headers={'User-Agent': UA})
        except Exception:
            continue
        match = INFO_RE.search(response.text or '')
        if not match:
            continue
        try:
            info = json.loads(match.group(1))
        except Exception:
            continue
        tenant = str((info.get('tenant_info') or {}).get('tenant_name') or '').strip()
        if tenant:
            return url, tenant, info
    return None, '', None


def run_feishu(slug, name, urls, outdir, budget):
    from qiuzhao.collector import p1_feishu_public as F
    url, tenant, info = feishu_discover(slug, urls)
    if not url:
        return {'jobs': [], 'pending_index': [], 'coverage': {
            'status': 'blocked', 'complete': False, 'expected_total': None,
            'errors': ['official tenant discovery failed (no js-websiteInfo)'],
            'request_budget': {'limit': budget, 'used': 0}}}, ''
    site = {'url': url, 'tenant_names': [tenant], 'portal_type': 6}
    result = F.collect_feishu(tenant, 'campus', [site], outdir, max_requests=budget)
    return result, tenant


RUNNERS = {'beisen': run_beisen, 'moka': run_moka, 'feishu': run_feishu}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', required=True, choices=sorted(RUNNERS))
    parser.add_argument('--slugs-json', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-requests', type=int, default=15)
    parser.add_argument('--tenant-timeout', type=float, default=150)
    parser.add_argument('--interval', type=float, default=2.0)
    parser.add_argument('--limit', type=int, help='only the first N tenants (debug)')
    parser.add_argument('--include-library', action='store_true')
    args = parser.parse_args()

    payload = json.loads(args.slugs_json.read_text(encoding='utf-8'))
    tenants = payload.get(args.platform) or []
    args.out.mkdir(parents=True, exist_ok=True)
    results_path = args.out / (args.platform + '.json')
    results = {'platform': args.platform, 'rows': [], 'skipped': []}
    if results_path.exists():
        results = json.loads(results_path.read_text(encoding='utf-8'))
    done = {row['slug'] for row in results['rows']}
    skipped = {row['slug'] for row in results['skipped']}

    processed = 0
    for tenant in tenants:
        slug = tenant['slug']
        if slug in done or slug in skipped:
            continue
        if tenant.get('in_library') and not args.include_library:
            results['skipped'].append({
                'slug': slug, 'company_table': tenant.get('company'),
                'reason': 'already in library (company name matched)'})
            results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            continue
        if args.limit and processed >= args.limit:
            break
        start = time.monotonic()
        workdir = args.out / 'work' / (args.platform + '-' + slug_dir_name(slug))
        try:
            signal.setitimer(signal.ITIMER_REAL, args.tenant_timeout)
            result, official = RUNNERS[args.platform](
                slug, tenant.get('company') or slug, tenant.get('urls') or [], workdir, args.max_requests)
            signal.setitimer(signal.ITIMER_REAL, 0)
            row = compact(slug, tenant.get('company'), tenant.get('urls') or [], result,
                          time.monotonic() - start, official)
        except TenantTimeout:
            signal.setitimer(signal.ITIMER_REAL, 0)
            row = {'slug': slug, 'company_table': tenant.get('company'),
                   'official_name': '', 'urls': tenant.get('urls') or [],
                   'status': 'timeout', 'complete': False, 'jobs': 0, 'pending': 0,
                   'expected_total': None, 'requests': None,
                   'seconds': round(time.monotonic() - start, 1),
                   'errors': ['tenant wall-clock budget exceeded'], 'request_budget_exhausted': False}
        except Exception as error:  # one bad tenant must not stop the batch
            signal.setitimer(signal.ITIMER_REAL, 0)
            row = {'slug': slug, 'company_table': tenant.get('company'),
                   'official_name': '', 'urls': tenant.get('urls') or [],
                   'status': 'error', 'complete': False, 'jobs': 0, 'pending': 0,
                   'expected_total': None, 'requests': None,
                   'seconds': round(time.monotonic() - start, 1),
                   'errors': [f'{type(error).__name__}: {error}'[:300]],
                   'request_budget_exhausted': False}
        results['rows'].append(row)
        results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        processed += 1
        print(json.dumps({'platform': args.platform, 'n': len(results['rows']),
                          'slug': slug, 'company': row['company_table'],
                          'status': row['status'], 'jobs': row['jobs'],
                          'requests': row['requests'], 'seconds': row['seconds']},
                         ensure_ascii=False), flush=True)
        elapsed = time.monotonic() - start
        if elapsed < args.interval:
            time.sleep(args.interval - elapsed)
    print(json.dumps({'platform': args.platform, 'done': len(results['rows']),
                      'skipped': len(results['skipped'])}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
