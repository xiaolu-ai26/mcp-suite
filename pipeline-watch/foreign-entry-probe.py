#!/usr/bin/env python3
"""Read-only recruitment-entry probe for foreign employers (discovery pipeline step 2).

For each company it fetches at most ``--max-requests`` public pages (default 2,
hard cap 4) and classifies the recruiting system from the HTML it actually
returned. Nothing logs in, nothing posts a form, nothing bypasses a challenge.

Politeness: >=2s between requests, and a hard cap of 15 requests per host per
run (the same "one source <=15 requests" rule used for the name lists).

Usage:
    python pipeline-watch/foreign-entry-probe.py --input companies.json --out probe.json
Input:  [{"company": ..., "url": ...}]  (url optional; when absent the probe
        stays idle for that row and reports ``no_url``).
Output: [{"company", "platform", "key", "url", "evidence", "requests", "note"}]
"""
from __future__ import annotations
import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

# (platform, regex, key-template)  -- first match wins, order matters.
PATTERNS = [
    ('Moka', re.compile(r'app\.mokahr\.com/(?:campus-recruitment|campus_apply|social-recruitment|apply|m/campus-recruitment)/([^/"\'?\s]+)/(\d+)'), '{0}/{1}'),
    ('北森', re.compile(r'https?://([a-z0-9][a-z0-9\-]*)\.zhiye\.com'), '{0}'),
    ('飞书招聘', re.compile(r'https?://([a-z0-9][a-z0-9\-]*)\.jobs\.feishu\.cn'), '{0}'),
    ('大易', re.compile(r'https?://([a-z0-9][a-z0-9\-]*)\.hotjob\.cn/(SU[0-9a-fA-F]{20,})'), '{1}'),
    ('大易', re.compile(r'(SU[0-9a-fA-F]{20,})'), '{0}'),
    ('51job', re.compile(r'campus\.51job\.com/([A-Za-z0-9_\-]+)'), '{0}'),
    ('Workday', re.compile(r'https?://([a-z0-9\-]+)\.wd(\d+)\.myworkdayjobs\.com/([^/"\'?\s]+)'), '{0}/wd{1}/{2}'),
    ('SuccessFactors', re.compile(r'https?://([a-z0-9\-]+\.(?:jobs|careers|career)[a-z0-9\-]*\.[a-z.]+)/(?:search|careers)?'), '{0}'),
    ('Eightfold', re.compile(r'https?://([a-z0-9\-]+)\.eightfold\.ai'), '{0}'),
    ('Phenom', re.compile(r'https?://([a-z0-9\-]+)\.phenompeople\.com|phenompeople\.com'), '{0}'),
    ('Avature', re.compile(r'https?://([a-z0-9\-]+)\.avature\.net'), '{0}'),
    ('iCIMS', re.compile(r'https?://careers-([a-z0-9\-]+)\.icims\.com'), '{0}'),
    ('Taleo', re.compile(r'https?://([a-z0-9\-]+)\.taleo\.net'), '{0}'),
    ('ORC', re.compile(r'https?://([a-z0-9\-]+)\.oraclecloud\.com'), '{0}'),
    ('SmartRecruiters', re.compile(r'smartrecruiters\.com/([A-Za-z0-9_\-]+)'), '{0}'),
    ('Greenhouse', re.compile(r'boards\.greenhouse\.io/([A-Za-z0-9_\-]+)'), '{0}'),
    ('Lever', re.compile(r'jobs\.lever\.co/([A-Za-z0-9_\-]+)'), '{0}'),
    ('moseeker', re.compile(r'(?:www\.)?moseeker\.com/(?:positions/index/cid|position/index/pid)/(\d+)'), '{0}'),
    ('ajinga', re.compile(r'ajinga\.com/recruiting/company/(\d+)'), '{0}'),
    ('tupu360', re.compile(r'https?://([a-z0-9\-]+)\.tupu360\.com'), '{0}'),
]


def classify(html, base_url=''):
    for platform, rx, keyfmt in PATTERNS:
        m = rx.search(html)
        if m:
            try:
                key = keyfmt.format(*m.groups())
            except Exception:
                key = m.group(0)
            return platform, key, m.group(0)[:200]
    return '自建/未识别', '', ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-requests', type=int, default=2)
    ap.add_argument('--sleep', type=float, default=2.0)
    ap.add_argument('--host-cap', type=int, default=15)
    ap.add_argument('--log', default='/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/discover/request-log.jsonl')
    args = ap.parse_args()
    max_requests = max(1, min(4, args.max_requests))
    rows = json.loads(Path(args.input).read_text(encoding='utf-8'))
    import requests
    session = requests.Session()
    session.headers['User-Agent'] = UA
    session.headers['Accept-Language'] = 'zh-CN,zh;q=0.9,en;q=0.8'
    host_used = collections.Counter()
    last_hit = {}
    out = []
    log = Path(args.log)
    for row in rows:
        company = row.get('company')
        urls = [u for u in ([row.get('url')] + list(row.get('alt_urls') or [])) if u][:max_requests]
        rec = {'company': company, 'platform': None, 'key': '', 'url': urls[0] if urls else '',
               'evidence': '', 'requests': 0, 'note': ''}
        if not urls:
            rec['note'] = 'no_url'
            out.append(rec)
            continue
        found = None
        for url in urls:
            host = urlsplit(url).netloc.lower()
            if host_used[host] >= args.host_cap:
                rec['note'] = 'host_cap_reached'
                break
            wait = args.sleep - (time.time() - last_hit.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                r = session.get(url, timeout=20, allow_redirects=True)
                last_hit[host] = time.time()
                host_used[host] += 1
                rec['requests'] += 1
                with log.open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'url': url,
                                        'status': r.status_code, 'note': f'entry-probe {company}'},
                                       ensure_ascii=False) + '\n')
                text = r.text[:400000]
                platform, key, evidence = classify(text, url)
                if platform != '自建/未识别':
                    found = (platform, key, evidence, url, r.status_code)
                    break
                rec['note'] = f'http {r.status_code}, no ats marker'
            except Exception as exc:  # network error -> try next candidate
                last_hit[host] = time.time()
                host_used[host] += 1
                rec['requests'] += 1
                rec['note'] = 'error: ' + str(exc)[:120]
        if found:
            rec.update({'platform': found[0], 'key': found[1], 'evidence': found[2],
                        'url': found[3], 'note': f'http {found[4]}'})
        out.append(rec)
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
        print(json.dumps({k: rec[k] for k in ('company', 'platform', 'key', 'requests', 'note')},
                         ensure_ascii=False), flush=True)
    print('WROTE', args.out, 'rows', len(out), flush=True)


if __name__ == '__main__':
    main()
