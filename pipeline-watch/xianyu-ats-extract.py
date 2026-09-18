#!/usr/bin/env python3
"""Extract ATS tenant slugs from the full 闲鱼 company table dump (read-only).

Input: one or more lark-cli ``+record-list --format ndjson`` page files.
Output: ``pipeline-watch/xianyu-ats-slugs.json`` grouped by platform.

Platform keys: ``moka`` (app.mokahr.com), ``beisen`` (*.zhiye.com),
``feishu`` (*.jobs.feishu.cn), ``dayee`` (*.hotjob.cn), ``other``.
Each tenant entry::

    {"slug": ..., "company": <table 公司名称>, "company_names": [...], "url": <first link>, "urls": [...]}
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
from pathlib import Path

URL_RE = re.compile(r'https?://[^\s\)\]，,、；;"\'<>]+')
MOKA_RE = re.compile(r'/(?:campus|social)-recruitment/([^/]+)/(\d+)')
MOKA_ALT_RE = re.compile(
    r'/(?:campus_apply|apply|recommendation-apply|m/campus-recruitment|m/social-recruitment)/([^/]+)/(\d+)')
LIBRARY = None  # optional set of normalized library company names


def urls_in(value):
    out = []
    if isinstance(value, str):
        out += URL_RE.findall(value)
    elif isinstance(value, list):
        for item in value:
            out += urls_in(item)
    elif isinstance(value, dict):
        for item in value.values():
            out += urls_in(item)
    return out


def host_of(url):
    return re.sub(r'^https?://', '', url).split('/')[0].split(':')[0].lower()


def normalize(name):
    text = re.sub(r'\s+', '', str(name or '').strip().lower())
    text = re.sub(r'[（(].*?[)）]', '', text)
    return re.sub(r'(有限公司|股份有限公司|有限责任公司|集团|股份|公司)$', '', text)


def classify(url):
    host = host_of(url)
    if host.endswith('mokahr.com'):
        match = MOKA_RE.search(url) or MOKA_ALT_RE.search(url)
        if match:
            return 'moka', f'{match.group(1)}/{match.group(2)}'
        return None, None
    if host.endswith('zhiye.com'):
        return 'beisen', host.split('.')[0]
    if host.endswith('jobs.feishu.cn'):
        return 'feishu', host.split('.')[0]
    if host.endswith('hotjob.cn'):
        return 'dayee', host
    return 'other', host


def load_records(paths):
    records = {}
    duplicates = 0
    for path in paths:
        with open(path, encoding='utf-8') as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                rid = record.get('record_id')
                if rid in records:
                    duplicates += 1
                records[rid] = record
    return records, duplicates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pages', nargs='+', type=Path)
    parser.add_argument('--output', type=Path,
                        default=Path(__file__).with_name('xianyu-ats-slugs.json'))
    parser.add_argument('--library', type=Path,
                        help='optional JSON list of library company names for a dedup flag')
    args = parser.parse_args()

    library = set()
    if args.library and args.library.exists():
        library = {normalize(name) for name in json.loads(args.library.read_text(encoding='utf-8'))}
    global LIBRARY
    LIBRARY = library

    records, duplicates = load_records(args.pages)
    buckets = {key: {} for key in ('moka', 'beisen', 'feishu', 'dayee')}
    other = collections.defaultdict(lambda: {'companies': set(), 'urls': []})
    for record in records.values():
        company = str(record.get('公司名称') or '').strip()
        for url in sorted(set(urls_in(record))):
            platform, slug = classify(url)
            if platform == 'other':
                bucket = other[slug]
                if company:
                    bucket['companies'].add(company)
                if url not in bucket['urls']:
                    bucket['urls'].append(url)
                continue
            if slug is None or not company:
                continue
            entry = buckets[platform].setdefault(
                slug, {'slug': slug, 'company_names': set(), 'urls': []})
            entry['company_names'].add(company)
            if url not in entry['urls']:
                entry['urls'].append(url)

    def serialize(entry):
        names = sorted(entry['company_names'])
        urls = entry['urls']
        return {
            'slug': entry['slug'],
            'company': names[0] if names else '',
            'company_names': names,
            'url': urls[0] if urls else '',
            'urls': urls,
            'in_library': bool(library) and any(normalize(n) in library for n in names),
        }

    payload = {
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'source': {
            'base_token': 'REDACTED',
            'table_id': 'tblMKWxJGIPhcDbw',
            'records': len(records),
            'duplicate_rows_ignored': duplicates,
        },
        'stats': {key: len(value) for key, value in buckets.items()} | {'other_domains': len(other)},
    }
    for platform, bucket in buckets.items():
        payload[platform] = [serialize(bucket[slug]) for slug in sorted(bucket)]
    payload['other'] = [
        {'domain': domain, 'company_count': len(info['companies']),
         'companies': sorted(info['companies'])[:50],
         'examples': info['urls'][:5]}
        for domain, info in sorted(other.items(), key=lambda kv: -len(kv[1]['companies']))
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'stats': payload['stats']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
