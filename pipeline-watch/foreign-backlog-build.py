#!/usr/bin/env python3
"""Split the foreign universe into "can add a line now" vs "needs a new adapter".

Reads ``pipeline-watch/foreign-universe.json`` and writes
``pipeline-watch/foreign-backlog-by-ats.json``: one bucket per recruiting system,
each row carrying the official entry URL, the tenant key when it is known, the
country/industry hints and where the row came from. Platforms that already have an
adapter are marked ``adapter_ready``; the rest wait for the Eightfold / Phenom /
Avature / iCIMS / ORC / tupu360 / moseeker / ajinga adapters.
"""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_READY = {'Moka', '北森', '飞书招聘', '大易', '51job', 'Workday', 'SuccessFactors',
                 '前程无忧'}
BACKLOG_PLATFORMS = ['Eightfold', 'Phenom', 'Avature', 'iCIMS', 'ORC', 'Taleo', 'SmartRecruiters',
                     'Greenhouse', 'Lever', 'tupu360', 'moseeker', 'ajinga', '智联', '牛客',
                     'BOSS直聘', '猎聘', '其他/自建', '本地招聘/未核实', '未识别']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--universe', default=str(ROOT / 'pipeline-watch' / 'foreign-universe.json'))
    ap.add_argument('--out', default=str(ROOT / 'pipeline-watch' / 'foreign-backlog-by-ats.json'))
    args = ap.parse_args()
    data = json.loads(Path(args.universe).read_text(encoding='utf-8'))
    buckets = collections.defaultdict(list)
    for c in data['companies']:
        if c['in_config']:
            continue
        platform = c['ats'] or '未识别'
        buckets[platform].append({
            'company_cn': c['company_cn'], 'company_en': c['company_en'],
            'country': c['country'], 'industry': c['industry'],
            'ats_key': c['ats_key'], 'entry_url': c['campus_url'],
            'priority': c['priority'], 'sources': c['sources'],
        })
    order = BACKLOG_PLATFORMS + sorted(set(buckets) - set(BACKLOG_PLATFORMS))
    out = {
        'generated_at': '2026-09-19',
        'description': '外企待接清单（按招聘系统分组）。adapter_ready=true 的桶已经有适配器，'
                       '按 RECEIPT-platform-adapters.md 的 SOP 加一行 + 实测即可；'
                       '其余等待对应适配器（Eightfold/Phenom/Avature/iCIMS/ORC 由另两个执行者负责）。',
        'summary': {
            'total_unconfigured': sum(len(v) for v in buckets.values()),
            'by_platform': {k: len(buckets[k]) for k in order if k in buckets},
            'adapter_ready_total': sum(len(buckets[k]) for k in buckets if k in ADAPTER_READY),
            'needs_new_adapter_total': sum(len(buckets[k]) for k in buckets if k not in ADAPTER_READY),
        },
        'platforms': [
            {'platform': k, 'adapter_ready': k in ADAPTER_READY,
             'module': {'Moka': 'qiuzhao.collector.p1_platform_moka',
                        '北森': 'qiuzhao.collector.p1_platform_beisen',
                        '飞书招聘': 'qiuzhao.collector.p1_feishu_public',
                        '大易': 'qiuzhao.collector.p1_foreign_01',
                        '51job': 'qiuzhao.collector.p1_platform_51job',
                        'Workday': 'qiuzhao.collector.p1_platform_workday',
                        'SuccessFactors': 'qiuzhao.collector.p1_platform_successfactors'}.get(k, ''),
             'count': len(buckets[k]), 'companies': buckets[k]}
            for k in order if k in buckets
        ],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print('WROTE', args.out)
    print(json.dumps(out['summary'], ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
