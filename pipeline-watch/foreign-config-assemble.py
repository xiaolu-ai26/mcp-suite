#!/usr/bin/env python3
"""Assemble the round-2 ``p1_platform_companies.json`` from the SOP verification runs.

A candidate is written into the config **only** when the real pipeline adapter
(``python -m qiuzhao.collector.p1_pipeline --adapter ...``) returned
``status in (success, partial)`` with at least one China posting. Everything else stays
in the receipt's failure table.

Excluded on purpose: two Beisen tenants whose own portal title says they are Chinese
firms (佰维存储 / 立信会计师事务所) — they only matched because a slug collided.
"""
from __future__ import annotations
import argparse, collections, json
from pathlib import Path

EV = Path('/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/r2')
LAYERS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'g2', 'h', 'i', 'wdc', 'wds',
          'wd3c', 'wd3s', 'wd4c', 'wd4s', 'wd5', 'wd6', 'wd7', 'wd8']
CAND_FILES = ['candidates-a.json', 'candidates-b.json', 'candidates-c.json', 'candidates-d.json',
              'candidates-e.json', 'candidates-f.json', 'candidates-g.json', 'candidates-i.json',
              'candidates-wd-campus.json', 'candidates-wd-social.json',
              'candidates-wd3-campus.json', 'candidates-wd3-social.json',
              'candidates-wd4-campus.json', 'candidates-wd4-social.json',
              'candidates-wd5.json', 'candidates-wd6.json', 'candidates-wd7.json',
              'candidates-wd8.json']
EXCLUDE = {'beisen-biwin1', 'beisen-bdochina'}  # Chinese firms (佰维存储 / 立信)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=str(EV / 'config-base.json'))
    ap.add_argument('--out', default=str(EV / 'config-final.json'))
    ap.add_argument('--report', default=str(EV / 'config-assemble-report.json'))
    args = ap.parse_args()
    stage = {}
    for f in CAND_FILES:
        p = EV / f
        if not p.exists():
            continue
        for c in json.loads(p.read_text(encoding='utf-8')):
            stage['%s-%s' % (c['platform'], c['key'].replace('/', '_'))] = c
    runs = collections.defaultdict(list)
    for layer in LAYERS:
        p = EV / ('verify-%s/summary.json' % layer)
        if not p.exists():
            continue
        for row in json.loads(p.read_text(encoding='utf-8')):
            runs[row['slug']].append(row)
    base = json.loads(Path(args.base).read_text(encoding='utf-8'))
    cfg = json.loads(json.dumps(base))
    added, kept_out = [], []
    for slug, rows in runs.items():
        if slug in EXCLUDE:
            kept_out.append({'slug': slug, 'why': '中国公司（门户标题自证）'})
            continue
        best = max(rows, key=lambda r: r.get('collected_jobs') or 0)
        if (best.get('collected_jobs') or 0) <= 0:
            continue
        c = stage.get(slug)
        if not c:
            kept_out.append({'slug': slug, 'why': '成功但无候选元数据'})
            continue
        if c['key'] in cfg.get(c['platform'], {}):
            entry = cfg[c['platform']][c['key']]
            name = entry if isinstance(entry, str) else (entry or {}).get('name', '')
            kept_out.append({'slug': slug, 'why': '配置中已存在同租户（%s）' % name})
            continue
        cfg.setdefault(c['platform'], {})[c['key']] = c.get('value') or c['name']
        added.append({'platform': c['platform'], 'key': c['key'], 'name': c['name'],
                      'scope': best.get('scope'), 'jobs': best.get('collected_jobs'),
                      'status': best.get('status')})
    # indent=2 keeps the diff against the round-1 file to the rows that actually changed
    Path(args.out).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
    before = {k: len(v) for k, v in base.items() if isinstance(v, dict)}
    after = {k: len(v) for k, v in cfg.items() if isinstance(v, dict)}
    report = {'added_count': len(added), 'added': added, 'kept_out': kept_out,
              'counts_before': before, 'counts_after': after,
              'delta': {k: after[k] - before.get(k, 0) for k in after}}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('added', len(added))
    print('delta', report['delta'])
    for a in added:
        print('  %-9s %-38s %-26s %-7s jobs=%s' % (a['platform'], a['key'], a['name'][:26],
                                                   a['scope'], a['jobs']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
