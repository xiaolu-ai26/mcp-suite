#!/usr/bin/env python3
"""Locate the real posting page of a 51job campus micro-site (read-only).

The 51job corporate micro-sites put their navigation on ``index.html`` and the
application anchors (``xyz.51job.com/External/Apply.aspx?CtmID=...``) on a
sub-page such as ``job.html`` / ``post.html``. ``p1_platform_51job`` fetches the
URL configured in ``p1_platform_companies.json``, so the discovery pipeline has
to find that sub-page first. This probe does exactly one GET per candidate page
(<=3 per site), nothing else.

Usage:
    python pipeline-watch/foreign-51job-entry.py --out entry.json \
        --sites '{"asml2027": "https://campus.51job.com/asml2027/"}'
"""
from __future__ import annotations
import argparse
import json
import re
import time
from pathlib import Path

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
CANDIDATE_NAMES = ['job', 'jobs', 'post', 'posts', 'position', 'positions', 'p', 'p2', 'p3',
                   'list', 'campus', 'recruit', 'xyz', 'apply', 'joblist', 'job-list']
APPLY_RE = re.compile(r'CtmID=(\d+)', re.I)
HREF_RE = re.compile(r'href="([^"#?]+\.html)"', re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sites', required=True, help='JSON file: {key: index_url}')
    ap.add_argument('--out', required=True)
    ap.add_argument('--sleep', type=float, default=2.0)
    ap.add_argument('--max-pages', type=int, default=3)
    ap.add_argument('--log', default='/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/discover/request-log.jsonl')
    args = ap.parse_args()
    import requests
    sites = json.loads(Path(args.sites).read_text(encoding='utf-8'))
    session = requests.Session()
    session.headers['User-Agent'] = UA
    session.headers['Accept-Language'] = 'zh-CN,zh;q=0.9'
    log = Path(args.log)
    out = []
    for key, index_url in sites.items():
        index_url = index_url.rstrip('/') + '/'
        rec = {'key': key, 'index_url': index_url, 'posting_url': '', 'ctm_ids': 0,
               'pages': [], 'note': ''}
        seen_pages = []

        def get(url):
            time.sleep(args.sleep)
            r = session.get(url, timeout=20)
            rec['pages'].append(url)
            with log.open('a', encoding='utf-8') as f:
                f.write(json.dumps({'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'url': url,
                                    'status': r.status_code, 'note': f'51job-entry {key}'},
                                   ensure_ascii=False) + '\n')
            return r.text if r.status_code == 200 else ''

        html = get(index_url)
        n = len(APPLY_RE.findall(html))
        if n:
            rec.update(posting_url=index_url, ctm_ids=n, note='anchors on index')
            out.append(rec)
            Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
            print(json.dumps(rec, ensure_ascii=False), flush=True)
            continue
        # follow same-site .html navigation, preferring job-ish names
        links = [l for l in dict.fromkeys(HREF_RE.findall(html))
                 if not l.lower().startswith(('http', '//', 'mailto'))]
        links.sort(key=lambda l: (0 if re.search(r'job|post|position|list|recruit', l, re.I) else 1,
                                  len(l)))
        tried = 0
        for link in links:
            if tried >= args.max_pages - 1:
                break
            url = index_url + link.lstrip('./')
            if url in seen_pages:
                continue
            seen_pages.append(url)
            body = get(url)
            tried += 1
            count = len(APPLY_RE.findall(body))
            if count:
                rec.update(posting_url=url, ctm_ids=count, note=f'anchors on {link}')
                break
        if not rec['posting_url']:
            # deterministic guesses as a last resort (still <= max-pages GETs)
            for name in CANDIDATE_NAMES:
                if tried >= args.max_pages - 1:
                    break
                url = f'{index_url}{name}.html'
                if url in seen_pages:
                    continue
                seen_pages.append(url)
                body = get(url)
                tried += 1
                count = len(APPLY_RE.findall(body))
                if count:
                    rec.update(posting_url=url, ctm_ids=count, note=f'anchors on {name}.html')
                    break
        if not rec['posting_url']:
            rec['note'] = 'no application anchor found'
        out.append(rec)
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
        print(json.dumps(rec, ensure_ascii=False), flush=True)
    print('WROTE', args.out, len(out), flush=True)


if __name__ == '__main__':
    main()
