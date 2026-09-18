from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path

WORKTREE = Path('/Volumes/臭垃圾桶/生财MCP/_worktrees/platform-adapters')
OUT = Path('/Volumes/臭垃圾桶/生财MCP/_worktrees/platform-adapters-out') / 'verify'
PY = '/Users/maxzhl/Projects/mcp-suite/.venv/bin/python'
BUDGET = '20'

TARGETS = [
    ('beisen', 'qiuzhao.collector.p1_platform_beisen', '中信建投', 'csc108'),
    ('beisen', 'qiuzhao.collector.p1_platform_beisen', '中金公司', 'cicc'),
    ('beisen', 'qiuzhao.collector.p1_platform_beisen', '国信证券', 'guosen'),
    ('beisen', 'qiuzhao.collector.p1_platform_beisen', '浙江民泰商业银行', 'mintai'),
    ('moka', 'qiuzhao.collector.p1_platform_moka', '三七互娱', '37_58016'),
    ('moka', 'qiuzhao.collector.p1_platform_moka', '金山办公', 'wps_41436'),
    ('moka', 'qiuzhao.collector.p1_platform_moka', '鹰角网络', 'hypergryph_26326'),
    ('moka', 'qiuzhao.collector.p1_platform_moka', '安踏集团', 'antahr_142914'),
    ('moka', 'qiuzhao.collector.p1_platform_moka', '小天才', 'eebbk_37594'),
    ('moka', 'qiuzhao.collector.p1_platform_moka', '信也科技', 'paipaidai_168312'),
]


def main():
    summary = []
    import os
    env = dict(os.environ, QIUZHAO_PLATFORM_REQUEST_BUDGET=BUDGET, PYTHONPATH=str(WORKTREE))
    for platform, module, company, slug in TARGETS:
        target = OUT / platform / slug
        target.mkdir(parents=True, exist_ok=True)
        cmd = [PY, '-m', 'qiuzhao.collector.p1_pipeline', '--adapter', module,
               '--company', company, '--scope', 'campus', '--output-dir', str(target)]
        started = time.time()
        proc = subprocess.run(cmd, cwd=WORKTREE, env=env, capture_output=True, text=True, timeout=1800)
        record = {'platform': platform, 'company': company, 'slug': slug,
                  'returncode': proc.returncode, 'seconds': round(time.time() - started, 1)}
        result_path = target / 'result.json'
        if result_path.exists():
            payload = json.loads(result_path.read_text(encoding='utf-8'))
            coverage = payload['coverage']
            jobs = payload.get('jobs') or []
            record.update(status=coverage.get('status'), complete=coverage.get('complete'),
                          collected_jobs=coverage.get('collected_jobs'),
                          expected_total=coverage.get('expected_total'),
                          pages_scanned=coverage.get('pages_scanned'),
                          detail_complete=coverage.get('detail_complete'),
                          request_budget=coverage.get('request_budget'),
                          published_at_rate=round(sum(1 for j in jobs if str(j.get('published_at') or '').strip()) / len(jobs), 3) if jobs else None,
                          deadline_rate=round(sum(1 for j in jobs if str(j.get('deadline_raw') or '').strip()) / len(jobs), 3) if jobs else None,
                          cohort_rate=round(sum(1 for j in jobs if str(j.get('cohort_raw') or '').strip()) / len(jobs), 3) if jobs else None,
                          errors=coverage.get('errors'))
        else:
            record.update(status='no-result', errors=[proc.stderr[-300:]])
        print(json.dumps(record, ensure_ascii=False), flush=True)
        summary.append(record)
        time.sleep(2.2)   # >=2s between tenants
    (OUT.parent / 'verify-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print('SUMMARY_WRITTEN', OUT.parent / 'verify-summary.json')


if __name__ == '__main__':
    sys.exit(main())
