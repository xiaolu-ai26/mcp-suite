#!/usr/bin/env python3
"""HTTP-confirm Workday tenants for foreign employers (DNS alone is wildcard-poisoned).

``*.myworkdayjobs.com`` resolves for every name, so only a real HTTP response can
confirm a tenant. One public GET per candidate host, at most 3 hosts per company
(wd1/wd3/wd5), spaced >=1.5s per host, no login and no challenge bypass.

Usage:
    python pipeline-watch/foreign-workday-http.py --input companies.json --out confirmed.json
"""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
REGIONS = ['wd1', 'wd3', 'wd5']
STOP = {'china', 'cn', 'greaterchina', 'group', 'inc', 'ltd', 'limited', 'co', 'corp',
        'corporation', 'company', 'holdings', 'holding', 'international', 'global'}
NOT_FOUND = re.compile(r'page not found|not found|404|no longer available', re.I)
WD_MARK = re.compile(r'workday|myworkdayjobs', re.I)
_lock = threading.Lock()
_last = {}


def slugs_for(en, cn=''):
    out = []
    for raw in (en, cn):
        if not raw:
            continue
        text = re.sub(r'[（(].*?[)）]', ' ', raw)
        text = re.sub(r'[^A-Za-z0-9\s\-]', ' ', text)
        tokens = [t.lower() for t in re.split(r'[\s\-]+', t) if t]
        if not tokens:
            continue
        trimmed = [t for t in tokens if t not in STOP] or tokens
        for v in (''.join(trimmed), trimmed[0], '-'.join(trimmed)):
            v = re.sub(r'[^a-z0-9\-]', '', v)
            if 2 < len(v) <= 40 and v not in out:
                out.append(v)
    return out[:2]


def check(company, session, sleep, log):
    hits = []
    for slug in slugs_for(company.get('en', ''), company.get('company', '')):
        for region in REGIONS:
            host = f'{slug}.{region}.myworkdayjobs.com'
            with _lock:
                wait = sleep - (time.time() - _last.get(host, 0))
                _last[host] = time.time() + max(0.0, wait)
            if wait > 0:
                time.sleep(wait)
            url = f'https://{host}/'
            try:
                r = session.get(url, timeout=15, allow_redirects=True)
                with log.open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'url': url,
                                        'status': r.status_code,
                                        'note': f'workday-http {company.get("company")}'},
                                       ensure_ascii=False) + '\n')
                body = r.text[:20000]
                if r.status_code == 200 and WD_MARK.search(body) and not NOT_FOUND.search(body[:4000]):
                    title = re.search(r'<title[^>]*>(.*?)</title>', body, re.S | re.I)
                    hits.append({'company': company.get('company'), 'platform': 'Workday',
                                 'key': f'{slug}/{region}/', 'host': host, 'url': url,
                                 'status': r.status_code,
                                 'title': (title.group(1).strip()[:120] if title else '')})
                    break
            except Exception:
                pass
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--sleep', type=float, default=1.5)
    ap.add_argument('--log', default='/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/discover/request-log.jsonl')
    args = ap.parse_args()
    import requests
    companies = json.loads(Path(args.input).read_text(encoding='utf-8'))
    session = requests.Session()
    session.headers['User-Agent'] = UA
    log = Path(args.log)
    hits = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(check, c, session, args.sleep, log): c for c in companies}
        for i, fut in enumerate(concurrent.futures.as_completed(futs), 1):
            try:
                hits.extend(fut.result())
            except Exception:
                pass
            if i % 20 == 0:
                Path(args.out).write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding='utf-8')
                print(f'... {i}/{len(companies)} confirmed={len(hits)}', flush=True)
    Path(args.out).write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding='utf-8')
    print('DONE confirmed', len(hits))
    for h in hits:
        print(' ', h['company'], h['host'], h['title'][:60])


if __name__ == '__main__':
    main()
