"""Bounded multi-pass backfill for the Moka companies left partial by the 20-request cap.

Each pass is a normal adapter subprocess with QIUZHAO_PLATFORM_REQUEST_BUDGET=20
and reuses the details already saved in the same output dir, so every pass makes
progress while never exceeding 20 network requests for the tenant.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

WORKTREE = Path('/Volumes/臭垃圾桶/生财MCP/_worktrees/platform-adapters')
OUT = Path('/Volumes/臭垃圾桶/生财MCP/_worktrees/platform-adapters-out')
PY = '/Users/maxzhl/Projects/mcp-suite/.venv/bin/python'
MODULE = 'qiuzhao.collector.p1_platform_moka'
MAX_PASSES = 25

TARGETS = [
    ('三七互娱', '37_58016'),
    ('金山办公', 'wps_41436'),
    ('鹰角网络', 'hypergryph_26326'),
    ('安踏集团', 'antahr_142914'),
]


def run_pass(company, target):
    env = dict(os.environ, QIUZHAO_PLATFORM_REQUEST_BUDGET='20', PYTHONPATH=str(WORKTREE))
    subprocess.run([PY, '-m', 'qiuzhao.collector.p1_pipeline', '--adapter', MODULE,
                    '--company', company, '--scope', 'campus', '--output-dir', str(target)],
                   cwd=WORKTREE, env=env, capture_output=True, text=True, timeout=1800)
    return json.loads((target / 'result.json').read_text(encoding='utf-8'))


def main():
    summary = []
    for company, slug in TARGETS:
        target = OUT / 'verify' / 'moka' / slug
        history = []
        stale = 0
        for attempt in range(1, MAX_PASSES + 1):
            payload = run_pass(company, target)
            coverage = payload['coverage']
            record = {'pass': attempt, 'status': coverage.get('status'),
                      'complete': coverage.get('complete'),
                      'collected': coverage.get('collected_jobs'),
                      'expected': coverage.get('expected_total'),
                      'network_requests': coverage.get('request_budget', {}).get('used'),
                      'errors': coverage.get('errors')}
            history.append(record)
            print(json.dumps({'company': company, **record}, ensure_ascii=False), flush=True)
            if coverage.get('complete') is True:
                stale = 0
                break
            if len(history) >= 2 and history[-1]['collected'] == history[-2]['collected']:
                stale += 1
                if stale >= 2:
                    print(json.dumps({'company': company, 'stop': 'no progress',
                                      'last': record}, ensure_ascii=False), flush=True)
                    break
            else:
                stale = 0
            time.sleep(2.2)
        summary.append({'company': company, 'slug': slug, 'passes': len(history),
                        'final': history[-1], 'history': history})
        time.sleep(2.2)
    (OUT / 'backfill-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                               encoding='utf-8')
    print('BACKFILL_WRITTEN', OUT / 'backfill-summary.json')


if __name__ == '__main__':
    sys.exit(main())
