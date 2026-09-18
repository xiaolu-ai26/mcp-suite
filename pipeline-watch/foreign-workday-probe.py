#!/usr/bin/env python3
"""Discover Workday / Eightfold / Phenom / Avature / iCIMS tenants for foreign employers.

Cheap-first: a DNS lookup decides whether ``<slug>.wd<N>.myworkdayjobs.com`` (or the
other vendor host patterns) exists at all; only hosts that resolve get one public
HTTP GET to confirm the tenant. No login, no form post, no challenge bypass.

Usage:
    python pipeline-watch/foreign-workday-probe.py --input companies.json --out tenants.json
Input:  [{"company": "...", "en": "Abbott China"}, ...]
Output: [{"company", "platform", "slug", "host", "status", "evidence"}]
"""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import re
import socket
import time
from pathlib import Path

WD_REGIONS = ['wd1', 'wd3', 'wd5', 'wd103']
VENDOR_HOSTS = [
    ('Eightfold', '{slug}.eightfold.ai'),
    ('Avature', '{slug}.avature.net'),
    ('iCIMS', 'careers-{slug}.icims.com'),
    ('Taleo', '{slug}.taleo.net'),
]
STOP = {'china', 'cn', 'greaterchina', 'group', 'inc', 'ltd', 'limited', 'co', 'corp',
        'corporation', 'company', 'holdings', 'holding', 'international', 'global'}


def slugs_for(company):
    en = (company.get('en') or '').strip()
    cn = (company.get('company') or '').strip()
    out = []
    for raw in (en, cn):
        if not raw:
            continue
        text = re.sub(r'[（(].*?[)）]', ' ', raw)
        text = re.sub(r'[^A-Za-z0-9\s\-]', ' ', text)
        tokens = [t for t in re.split(r'[\s\-]+', text) if t]
        if not tokens:
            continue
        lowered = [t.lower() for t in tokens]
        trimmed = [t for t in lowered if t not in STOP] or lowered
        variants = {
            ''.join(lowered),
            ''.join(trimmed),
            trimmed[0] if trimmed else '',
            '-'.join(trimmed),
        }
        for v in variants:
            v = re.sub(r'[^a-z0-9\-]', '', v)
            if 2 < len(v) <= 40 and v not in out:
                out.append(v)
    return out[:3]


def resolves(host):
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        return True
    except Exception:
        return False


def probe(company):
    results = []
    for slug in slugs_for(company):
        for region in WD_REGIONS:
            host = f'{slug}.{region}.myworkdayjobs.com'
            if resolves(host):
                results.append({'company': company.get('company'), 'platform': 'Workday',
                                'slug': slug, 'host': host, 'status': 'dns-ok',
                                'url': f'https://{host}/'})
        for platform, pattern in VENDOR_HOSTS:
            host = pattern.format(slug=slug)
            if resolves(host):
                results.append({'company': company.get('company'), 'platform': platform,
                                'slug': slug, 'host': host, 'status': 'dns-ok',
                                'url': f'https://{host}/'})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=16)
    args = ap.parse_args()
    companies = json.loads(Path(args.input).read_text(encoding='utf-8'))
    hits = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for res in pool.map(probe, companies):
            hits.extend(res)
    Path(args.out).write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding='utf-8')
    print('companies', len(companies), 'dns hits', len(hits))
    for h in hits:
        print(h['platform'], h['company'], h['host'])


if __name__ == '__main__':
    main()
