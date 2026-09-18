#!/usr/bin/env python3
"""Turn batch-verification results into config lines and a rejected list.

A tenant is kept only when ``status in {success, partial}`` **and** at least one
job was collected. Everything else is written to
``pipeline-watch/xianyu-ats-rejected.json`` with a reason. Names prefer the
official site name (Feishu tenant_name / Beisen page title) and fall back to the
table name; duplicate names and names already owned by the library or the
existing config are rejected as duplicates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

SUFFIX = re.compile(r'(招聘系统|招聘官网|官方招聘|校园招聘|社会招聘|招聘网站|招聘|官网|主页)$')


def slug_dir_name(slug):
    return re.sub(r'[^0-9A-Za-z._-]+', '_', slug)


def normalize(name):
    text = re.sub(r'\s+', '', str(name or '').strip().lower())
    text = re.sub(r'[（(].*?[)）]', '', text)
    return re.sub(r'(有限公司|股份有限公司|有限责任公司|集团|股份|公司)$', '', text)


def clean_url(url):
    """Keep the official portal path only: drop HTML entities, fragment and query
    (referral/session parameters in the purchased table are not needed to collect)."""
    text = str(url or '').replace('&amp;', '&').strip()
    text = text.split('#', 1)[0].split('?', 1)[0].rstrip('/')
    return text


def load_workdir_coverage(out_root, platform, slug):
    for name in ('coverage.json', 'result.json'):
        path = out_root / 'work' / f'{platform}-{slug_dir_name(slug)}' / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if name == 'result.json':
            return payload.get('coverage') or {}
        return payload
    return {}


def name_for(platform, row, coverage):
    table = str(row.get('company_table') or '').strip()
    official = str(row.get('official_name') or '').strip()
    if platform == 'feishu' and official:
        return official
    if platform == 'beisen' and official:
        cleaned = SUFFIX.sub('', official).strip()
        if cleaned and len(cleaned) >= 2:
            return cleaned
    return table or official


def sites_for(platform, row, coverage):
    params = (coverage.get('scope_request') or {}).get('params') or {}
    sites = params.get('sites') or []
    urls = [clean_url(u) for u in (row.get('urls') or [])]
    if platform == 'feishu':
        picked = []
        for site in sites:
            if isinstance(site, dict) and site.get('url'):
                picked.append({'url': clean_url(site['url']),
                               'tenant_names': list(site.get('tenant_names') or []),
                               'portal_type': site.get('portal_type', 6)})
        if picked:
            return picked
        return [{'url': urls[0], 'tenant_names': [row.get('official_name') or row.get('company_table')]}]
    if platform == 'moka':
        picked = []
        for site in sites:
            if isinstance(site, str):
                url = clean_url(site)
                if url and url not in picked:
                    picked.append(url)
        if not picked:
            for url in urls:
                cleaned = clean_url(url)
                if cleaned and cleaned not in picked:
                    picked.append(cleaned)
        return picked
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--batch-out', type=Path, required=True)
    parser.add_argument('--library', type=Path)
    parser.add_argument('--rejected', type=Path, required=True)
    args = parser.parse_args()

    library = set()
    if args.library and args.library.exists():
        library = {normalize(n) for n in json.loads(args.library.read_text(encoding='utf-8'))}

    config = json.loads(args.config.read_text(encoding='utf-8'))
    taken = set()
    for section in ('beisen', 'moka', 'feishu'):
        for entry in (config.get(section) or {}).values():
            name = entry if isinstance(entry, str) else (entry or {}).get('name')
            if name:
                taken.add(normalize(name))

    rejected = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                'counts': {}, 'rejected': [], 'skipped_existing': []}
    added = {}
    for platform in ('beisen', 'moka', 'feishu'):
        results_path = args.batch_out / f'{platform}.json'
        if not results_path.exists():
            continue
        results = json.loads(results_path.read_text(encoding='utf-8'))
        for row in results.get('skipped') or []:
            rejected['skipped_existing'].append({
                'platform': platform, 'slug': row.get('slug'),
                'company': row.get('company_table'), 'reason': row.get('reason') or 'already in library'})
        section = config.setdefault(platform, {})
        kept = 0
        for row in results.get('rows') or []:
            slug = row.get('slug')
            jobs = int(row.get('jobs') or 0)
            status = row.get('status')
            if status not in ('success', 'partial') or jobs < 1:
                if status in ('success', 'partial'):
                    reason = 'zero campus jobs (official list returned 0 for this scope)'
                elif status == 'timeout':
                    reason = 'tenant wall-clock timeout before any verified job'
                elif status == 'error':
                    reason = 'adapter error before any verified job'
                else:
                    reason = 'blocked (WAF / missing portal identity / no usable list)'
                rejected['rejected'].append({
                    'platform': platform, 'slug': slug, 'company': row.get('company_table'),
                    'status': status, 'jobs': jobs, 'requests': row.get('requests'),
                    'reason': reason, 'errors': (row.get('errors') or [])[:4]})
                continue
            coverage = load_workdir_coverage(args.batch_out, platform, slug)
            name = name_for(platform, row, coverage)
            key = normalize(name)
            if not name or key in taken or key in library:
                rejected['rejected'].append({
                    'platform': platform, 'slug': slug, 'company': row.get('company_table'),
                    'status': status, 'jobs': jobs, 'requests': row.get('requests'),
                    'reason': 'duplicate/ambiguous company name already covered: ' + name,
                    'errors': []})
                continue
            if platform == 'feishu':
                sites = sites_for(platform, row, coverage)
                section[slug] = {'name': name, 'sites': sites}
            elif platform == 'moka':
                sites = sites_for(platform, row, coverage)
                section[slug] = {'name': name, 'sites': sites}
            else:
                section[slug] = name
            taken.add(key)
            kept += 1
            added.setdefault(platform, []).append(
                {'slug': slug, 'company': name, 'company_table': row.get('company_table'),
                 'jobs': jobs, 'status': status, 'requests': row.get('requests')})
        rejected['counts'][platform] = {'added': kept,
                                        'rejected': sum(1 for r in rejected['rejected'] if r['platform'] == platform)}

    args.config.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rejected['added'] = added
    args.rejected.write_text(json.dumps(rejected, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'counts': rejected['counts'],
                      'rejected_total': len(rejected['rejected']),
                      'skipped_existing': len(rejected['skipped_existing'])},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
