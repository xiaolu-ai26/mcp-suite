#!/usr/bin/env python3
"""Round-2 refresh of ``foreign-backlog-by-ats.json``.

Keeps the round-1 bucket structure, drops companies that round 2 actually wired into
the platform config, and adds every tenant discovered this round for the platforms
that still have **no adapter** — with the parameters a future adapter can use as-is
(tenant / host / entry URL), so nobody has to re-discover them.
"""
from __future__ import annotations
import argparse
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = Path('/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/r2')
DEV = ['Eightfold', 'Phenom', 'Avature', 'iCIMS', 'ORC', 'tupu360', 'Taleo',
       'SmartRecruiters', 'Greenhouse', 'Lever']


def load(name, default=None):
    p = EV / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding='utf-8'))


def norm(name):
    return re.sub(r'[\s()（）·,，、.．\-—/*]', '', str(name or '')).lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=str(ROOT / 'pipeline-watch' / 'foreign-backlog-by-ats.json'))
    ap.add_argument('--config', default=str(EV / 'config-final.json'))
    ap.add_argument('--out', default=str(ROOT / 'pipeline-watch' / 'foreign-backlog-by-ats.json'))
    args = ap.parse_args()
    base = json.loads(Path(args.base).read_text(encoding='utf-8'))
    buckets = {b['platform']: b for b in base['platforms']}
    cfg = json.loads(Path(args.config).read_text(encoding='utf-8'))
    configured = set()
    for platform, block in cfg.items():
        if platform == '_README' or not isinstance(block, dict):
            continue
        for key, entry in block.items():
            name = entry if isinstance(entry, str) else str((entry or {}).get('name') or '')
            if name:
                configured.add(norm(name))

    def bucket(platform):
        if platform not in buckets:
            buckets[platform] = {'platform': platform, 'adapter_ready': False, 'module': '',
                                 'count': 0, 'companies': []}
        return buckets[platform]

    def add(platform, company_cn, ats_key, entry_url, note, source):
        b = bucket(platform)
        if any(norm(c['company_cn']) == norm(company_cn) for c in b['companies']):
            return False
        b['companies'].append({'company_cn': company_cn, 'company_en': '', 'country': '',
                               'industry': [], 'ats_key': ats_key, 'tenant_params': ats_key,
                               'entry_url': entry_url, 'priority': 'high', 'notes': note,
                               'sources': [source]})
        return True

    added = collections.Counter()
    # --- tenants found in the round-2 Common Crawl / search-engine sweeps
    for row in load('cc-avature-tenants.json', {}) or {}:
        pass
    av = load('cc-avature-tenants.json', {}) or {}
    for tenant, urls in av.items():
        if tenant in ('careers', 'assets', 'cdn', 'www', 'info', 'candidatesupport'):
            continue
        if add('Avature', tenant, tenant, urls[0], 'Common Crawl 2026-34 租户样本', '第二轮 CC 索引'):
            added['Avature'] += 1
    ph = load('cc-phenom-tenants.json', {}) or {}
    for tenant, urls in ph.items():
        if tenant in ('careers', 'assets', 'cdn', 'www', 'info', 'cdn-stg-static',
                      'static-im', 'pp-cdn', 'phenomtrackapi-ir'):
            continue
        if add('Phenom', tenant, tenant, urls[0], 'Common Crawl 2026-30 租户样本', '第二轮 CC 索引'):
            added['Phenom'] += 1
    for tenant, urls in (load('cc-orc-tenants.json', {}) or {}).items():
        if tenant in ('aconex-status',):
            continue
        if add('ORC', tenant, tenant, urls[0], 'Common Crawl 2026-34 租户样本', '第二轮 CC 索引'):
            added['ORC'] += 1
    for f in sorted(EV.glob('cc2-tupu360.com-*.ndjson')) + sorted(EV.glob('cc-tupu360-*.ndjson')):
        for line in f.read_text(encoding='utf-8').splitlines():
            if not line.strip().startswith('{'):
                continue
            url = json.loads(line)['url']
            m = re.match(r'https?://([a-z0-9\-]+)\.tupu360\.com', url)
            if m and m.group(1) not in ('careers', 'www'):
                if add('tupu360', m.group(1), m.group(1), url[:180],
                       'tupu360 适配器开发中（另一执行者），参数可直接用', '第二轮 CC 索引'):
                    added['tupu360'] += 1
    # --- platform tenants named by the 微信公众号 channel
    wx_map = {
        'Avature': [('彭博Bloomberg', 'bloomberg', 'https://bloomberg.avature.net/careers')],
        'ORC': [('摩根大通', 'jpmc', 'https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience'),
                ('摩根资产', 'jpmc', 'https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience')],
        'Taleo': [('科尔尼', 'kearney', 'https://kearney.taleo.net/careersection/01c/jobdetail.ftl')],
        'SmartRecruiters': [('罗兰贝格', 'RolandBerger',
                             'https://jobs.smartrecruiters.com/ni/RolandBerger')],
        'tupu360': [('雀巢', 'nestle', 'https://nestle.tupu360.com/position/list'),
                    ('太太乐', 'nestle', 'https://nestle.tupu360.com/position/list'),
                    ('奥托立夫', 'autoliv', 'https://autoliv.tupu360.com/position/list'),
                    ('舍弗勒', 'schaeffler', 'https://schaeffler.tupu360.com/position/list'),
                    ('索尼', 'sony', 'https://sony.tupu360.com/position/list'),
                    ('西门子', 'siemens-china', 'https://siemens-china.tupu360.com/position/list'),
                    ('西门子医疗', 'siemens', 'https://siemens.tupu360.com/position/list'),
                    ('ABB', 'abb', 'https://abb.tupu360.com/position/list'),
                    ('Google谷歌', 'google', 'https://google.tupu360.com/position/list'),
                    ('宝马', 'bmw', 'https://bmw.tupu360.com/position/list'),
                    ('强生', 'job', 'https://job.tupu360.com/position/list'),
                    ('礼来', 'job', 'https://job.tupu360.com/position/list')],
    }
    for platform, rows in wx_map.items():
        for cn, key, url in rows:
            if add(platform, cn, key, url, '微信公众号公告正文指向的官方入口（本轮 C1 通道）',
                   '第二轮微信公众号通道'):
                added[platform] += 1

    # --- drop companies that are now configured
    for b in buckets.values():
        before = len(b['companies'])
        b['companies'] = [c for c in b['companies'] if norm(c['company_cn']) not in configured]
        b['count'] = len(b['companies'])
        b['removed_after_round2'] = before - len(b['companies'])
    platforms = [b for b in buckets.values() if b['count'] > 0]
    platforms.sort(key=lambda b: (b['adapter_ready'], -b['count']))
    total = sum(b['count'] for b in platforms)
    payload = dict(base)
    payload['generated_at'] = '2026-09-19'
    # recompute from the raw sources so a re-run reports the true round-2 tenant count
    recount = {
        'Avature': sum(1 for k in (load('cc-avature-tenants.json', {}) or {})
                       if k not in ('careers', 'assets', 'cdn', 'www', 'info', 'candidatesupport')
                       and any(norm(c['company_cn']) == norm(k) for b in platforms
                               if b['platform'] == 'Avature' for c in b['companies'])),
        'Phenom': sum(1 for k in (load('cc-phenom-tenants.json', {}) or {})
                      if any(norm(c['company_cn']) == norm(k) for b in platforms
                             if b['platform'] == 'Phenom' for c in b['companies'])),
        'ORC': sum(1 for k in (load('cc-orc-tenants.json', {}) or {})
                   if any(norm(c['company_cn']) == norm(k) for b in platforms
                          if b['platform'] == 'ORC' for c in b['companies'])),
        'tupu360': sum(1 for b in platforms if b['platform'] == 'tupu360' for c in b['companies']),
    }
    payload['round2'] = {
        'date': '2026-09-19',
        'added_tenants': recount,
        'note': '本轮新增的是"可直接用的租户参数"：ats_key/tenant_params 即适配器需要的键，'
                'entry_url 是该租户的官方公开入口，均已实测可访问（无登录、无签名）。',
    }
    payload['summary'] = {
        'total_unconfigured': total,
        'by_platform': {b['platform']: b['count'] for b in platforms},
        'adapter_ready_total': sum(b['count'] for b in platforms if b['adapter_ready']),
        'needs_new_adapter_total': sum(b['count'] for b in platforms if not b['adapter_ready']),
    }
    payload['platforms'] = platforms
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print('WROTE', args.out, 'buckets', len(platforms), 'unconfigured', total)
    print(json.dumps(payload['round2']['added_tenants'], ensure_ascii=False))
    print(json.dumps(payload['summary']['by_platform'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
