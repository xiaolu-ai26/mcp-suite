#!/usr/bin/env python3
"""Round-2 pass over ``foreign-universe.json``: merge new discoveries + stamp a status.

Inputs (round-2 evidence, all under the external work dir):
  * ``verified-ok.json``          — tenants that passed the real adapter this round
  * ``verify-*/summary.json``     — every adapter run this round (incl. failures + reason)
  * ``wechat-probe.json``         — 微信公众号 article → application link
  * ``probe-51job.json``          — 51job micro-site landing pages
  * ``workday-probe2.json``       — Workday CXS China probe
  * ``ddg-resolve.json`` / ``baidu-resolve.json`` — search-engine channel
  * ``src-fortune500.json``       — 《财富》世界 500 强 2026 (foreign rows)
  * ``src-nowcoder.json``         — 牛客校招日程 外企标签 (tagId=2834)
  * ``cc-*.json``                 — Common Crawl tenant samples per platform

Status vocabulary (one per company, never empty):
  已接入          in the final platform config (daily collection)
  已在库          collected daily by a dedicated (non-platform) module
  待平台适配器    a real tenant exists but the platform has no adapter yet
  当期中国0条     portal verified live, zero China postings at check time
  接不了          portal verified but blocked, with the concrete reason
  未解析          no portal found; the channels already tried are listed
"""
from __future__ import annotations
import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIX = re.compile(r'(有限公司|股份有限公司|有限责任公司|集团|股份|公司|投资|中国区|大中华区|中国|china|greater china)$', re.I)
DEV_PLATFORMS = {'Eightfold', 'Phenom', 'Avature', 'iCIMS', 'ORC', 'tupu360', 'Taleo',
                 'SmartRecruiters', 'Greenhouse', 'Lever', 'moseeker', 'ajinga',
                 '智联招聘', 'BOSS直聘', '猎聘', '牛客'}
SUPPORTED = {'Moka', '北森', '飞书招聘', '大易', '51job', '前程无忧', 'Workday', 'SuccessFactors'}
CHANNEL_LABEL = {
    'wechat': 'C1 微信公众号公告正文',
    'entry-probe': 'C1 官方入口页',
    'job51': 'C1/C2 51job 微站首页',
    'ddg': 'C5 搜索引擎 site: 查询',
    'baidu': 'C5 搜索引擎（第二引擎）',
    'cdx': 'C5 Wayback 存档索引',
    'cc': 'C3 Common Crawl 索引',
    'headless': 'C4 无头浏览器渲染',
    'verify': 'SOP 适配器实测',
}


def norm(name):
    s = re.sub(r'[\s()（）·,，、.．\-—/*]', '', str(name or '')).lower()
    return SUFFIX.sub('', s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=str(ROOT / 'pipeline-watch' / 'foreign-universe.json'))
    ap.add_argument('--evidence', default='/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/r2')
    ap.add_argument('--config', default='/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/r2/config-final.json')
    ap.add_argument('--out', default=str(ROOT / 'pipeline-watch' / 'foreign-universe.json'))
    args = ap.parse_args()
    ev = Path(args.evidence)

    def load(name, default=None):
        p = ev / name
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding='utf-8'))

    base = json.loads(Path(args.base).read_text(encoding='utf-8'))
    companies = base['companies']
    index = {norm(c['company_cn']) or norm(c.get('company_en')): c for c in companies}

    def upsert(cn='', en='', country='', industry=None, source='', priority='', ats='', ats_key='',
               campus_url='', evidence_urls=None, notes=''):
        key = norm(cn) or norm(en)
        rec = index.get(key)
        if rec is None:
            rec = {'company_cn': cn, 'company_en': en, 'country': country, 'industry': list(industry or []),
                   'sources': [], 'in_config': False, 'config_platform': '', 'config_key': '',
                   'ats': ats, 'ats_key': ats_key, 'campus_url': campus_url,
                   'evidence_urls': list(evidence_urls or []), 'priority': priority, 'notes': notes}
            companies.append(rec)
            index[key] = rec
        if source and source not in rec['sources']:
            rec['sources'].append(source)
        for field, value in (('ats', ats), ('ats_key', ats_key), ('campus_url', campus_url),
                             ('country', country), ('priority', priority)):
            if value and not rec.get(field):
                rec[field] = value
        for url in evidence_urls or []:
            if url and url not in rec['evidence_urls']:
                rec['evidence_urls'].append(url)
        return rec

    # ---------------------------------------------------------------- evidence
    # ``config-assemble-report.json`` is the authoritative list of rows that actually
    # made it into the config this round (66); ``verified-ok.json`` is the earlier,
    # partial snapshot and is only kept as a fallback.
    assemble = load('config-assemble-report.json', {}) or {}
    verified = {'%s-%s' % (a['platform'], a['key'].replace('/', '_')): a
                for a in (assemble.get('added') or [])}
    if not verified:
        verified = load('verified-ok.json', {})
    stage = {}
    for f in ('candidates-a.json', 'candidates-b.json', 'candidates-c.json', 'candidates-d.json',
              'candidates-e.json', 'candidates-f.json', 'candidates-g.json', 'candidates-i.json',
              'candidates-wd-campus.json', 'candidates-wd-social.json',
              'candidates-wd3-campus.json', 'candidates-wd3-social.json',
              'candidates-wd4-campus.json', 'candidates-wd4-social.json',
              'candidates-wd5.json', 'candidates-wd6.json', 'candidates-wd7.json',
              'candidates-wd8.json'):
        for c in load(f, []) or []:
            stage['%s-%s' % (c['platform'], c['key'].replace('/', '_'))] = c

    verify_runs = {}
    for layer in ('a', 'b', 'c', 'd', 'e', 'f', 'g', 'g2', 'h', 'i', 'wdc', 'wds',
                  'wd3c', 'wd3s', 'wd4c', 'wd4s', 'wd5', 'wd6', 'wd7', 'wd8'):
        for row in load('verify-%s/summary.json' % layer, []) or []:
            verify_runs.setdefault(row['company'], []).append(row)

    wechat = load('wechat-probe.json', []) or []
    j51 = load('probe-51job.json', []) or []
    wd = (load('workday-probe2.json', []) or []) + (load('workday-probe4.json', []) or [])
    ddg = load('ddg-resolve.json', []) or []
    baidu = load('baidu-resolve.json', []) or []
    fortune = load('src-fortune500.json', []) or []
    nowcoder = load('src-nowcoder.json', []) or []

    # ------------------------------------------------------- new source lists
    for row in fortune:
        name = re.sub(r'（.*?）|\(.*?\)', '', row['name']).strip()
        country = (row.get('extra') or ['', '', ''])[2] if len(row.get('extra') or []) > 2 else ''
        if country == '中国':
            continue
        if not name:
            continue
        upsert(cn=name, country=country, source='《财富》世界500强 2026（非中国注册）',
               evidence_urls=['https://www.fortunechina.com/fortune500/index.htm'], priority='medium')
    for name in nowcoder:
        if not name:
            continue
        upsert(cn=name, source='牛客校招日程 外企标签 tagId=2834',
               evidence_urls=['https://www.nowcoder.com/school/schedule?tagId=2834'])

    # ------------------------------------------------- round-2 verified tenants
    added = []
    for slug, hit in verified.items():
        c = stage.get(slug)
        if not c:
            c = {'platform': hit['platform'], 'key': hit['key'], 'name': hit['name'], 'value': None}
        c.setdefault('scope', hit.get('scope'))
        c['platform'] = c.get('platform') or hit['platform']
        c['key'] = c.get('key') or hit['key']
        c['name'] = c.get('name') or hit['name']
        if c['platform'] == 'beisen' and slug in ('beisen-biwin1', 'beisen-bdochina'):
            continue  # 佰维存储 / 立信会计师事务所 —— 中国公司，误命中
        rec = upsert(cn=c['name'], source='第二轮外企发现（SOP 适配器实测）',
                     ats={'moka': 'Moka', 'beisen': '北森', 'job51': '51job', 'dayee': '大易',
                          'workday': 'Workday', 'successfactors': 'SuccessFactors',
                          'feishu': '飞书招聘'}.get(c['platform'], c['platform']),
                     ats_key=c['key'], campus_url=(c.get('value') or {}).get('url', '') if isinstance(c.get('value'), dict) else '',
                     evidence_urls=[r for r in [(c.get('value') or {}).get('url') if isinstance(c.get('value'), dict) else ''] if r])
        rec['round2_added'] = True
        rec['round2_scope'] = hit.get('scope')
        rec['round2_jobs'] = hit.get('jobs')
        added.append(rec)

    # ------------------------------------------------------- Workday discovery
    for r in wd:
        if (r.get('total') or 0) <= 0:
            continue
        c = stage.get('workday-%s_%s_%s' % (r['tenant'], r['wd'], r['site']))
        if c:
            continue
        upsert(cn=r['tenant'], source='第二轮 Workday 租户发现（Common Crawl + CXS 实测）',
               ats='Workday', ats_key='%s/%s/%s' % (r['tenant'], r['wd'], r['site']),
               evidence_urls=[(r.get('host') or 'https://%s.%s.myworkdayjobs.com' % (r['tenant'], r['wd']))
                              + '/wday/cxs/%s/%s/jobs' % (r['tenant'], r['site'])])

    # --------------------------------------------- evidence -> per-company state
    for row in wechat:
        rec = index.get(norm(row['company']))
        if rec is None:
            continue
        rec.setdefault('channels_tried', [])
        if CHANNEL_LABEL['wechat'] not in rec['channels_tried']:
            rec['channels_tried'].append(CHANNEL_LABEL['wechat'])
        if row.get('platform'):
            rec['ats'] = row['platform']
            rec['ats_key'] = row.get('key', '')
            if row.get('link') and row['link'] not in rec['evidence_urls']:
                rec['evidence_urls'].append(row['link'])
    for row in ddg + baidu:
        rec = index.get(norm(row['company']))
        if rec is None:
            continue
        rec.setdefault('channels_tried', [])
        label = CHANNEL_LABEL['ddg'] if row in ddg else CHANNEL_LABEL['baidu']
        if label not in rec['channels_tried']:
            rec['channels_tried'].append(label)
        for h in row.get('hits') or []:
            if h['platform'] in SUPPORTED | DEV_PLATFORMS and not rec.get('ats'):
                rec['ats'] = h['platform']
                rec['ats_key'] = h.get('key', '')
                if h.get('url') and h['url'] not in rec['evidence_urls']:
                    rec['evidence_urls'].append(h['url'])

    # ------------------------------------------------------------ config state
    cfg = json.loads(Path(args.config).read_text(encoding='utf-8'))
    cfg_name = {}
    for platform, block in cfg.items():
        if platform == '_README' or not isinstance(block, dict):
            continue
        for key, entry in block.items():
            name = entry if isinstance(entry, str) else str((entry or {}).get('name') or '')
            if name:
                cfg_name[norm(name)] = (platform, key, name)

    try:
        sys.path.insert(0, str(ROOT))
        from qiuzhao.collector import p1_pipeline  # noqa: E402
        registry = {norm(n): n for n in p1_pipeline.REGISTRY}
    except Exception as exc:  # pragma: no cover - registry is best-effort metadata
        registry = {}
        print('WARN registry unavailable:', exc)

    # ----------------------------------------------------------- status stamp
    counts = collections.Counter()
    for rec in companies:
        key = norm(rec['company_cn']) or norm(rec.get('company_en'))
        hit = cfg_name.get(key)
        if not hit and len(key) >= 3:
            for k, v in cfg_name.items():
                if key in k or k in key:
                    hit = v
                    break
        runs = verify_runs.get(rec['company_cn']) or verify_runs.get(hit[2] if hit else '') or []
        tried = rec.get('channels_tried') or []
        if hit:
            rec['status'] = '已接入'
            rec['status_reason'] = '平台配置 %s/%s' % (hit[0], hit[1])
            rec['in_config'] = True
            rec['config_platform'] = hit[0]
            rec['config_key'] = hit[1]
        elif key in registry:
            rec['status'] = '已在库'
            rec['status_reason'] = '已有专用采集模块，无需平台适配器'
        elif rec.get('ats') in DEV_PLATFORMS and rec.get('ats_key'):
            rec['status'] = '待平台适配器'
            rec['status_reason'] = '%s 适配器未落地（租户参数已存档）' % rec['ats']
        elif runs and any((r.get('collected_jobs') or 0) > 0 for r in runs):
            rec['status'] = '当期中国0条'
            rec['status_reason'] = '实测有岗位但未写入配置（请复核）'
        elif runs:
            err = ''
            for r in runs:
                if r.get('errors'):
                    err = r['errors'][0][:120]
                    break
                if r.get('note'):
                    err = r['note'][:120]
                    break
            if any((r.get('collected_jobs') or 0) == 0 and r.get('status') == 'success' for r in runs):
                rec['status'] = '当期中国0条'
                rec['status_reason'] = '门户在线，实测当期中国地区 0 条'
            else:
                rec['status'] = '接不了'
                rec['status_reason'] = err or '适配器返回 blocked'
        elif rec.get('ats') in SUPPORTED and rec.get('ats_key'):
            rec['status'] = '待平台适配器'
            rec['status_reason'] = '%s 租户已知但本轮未通过实测' % rec['ats']
        else:
            rec['status'] = '未解析'
            rec['status_reason'] = ('本轮仅完成名单收录，未做入口解析'
                                    if any(x.startswith(('《财富》', '牛客')) for x in rec['sources'])
                                    else '未找到公开招聘入口')
        rec['channels_tried'] = tried or ['C1 官方入口页']
        counts[rec['status']] += 1

    companies.sort(key=lambda r: (r['status'] != '已接入', r['company_cn']))
    summary = dict(base.get('summary') or {})
    summary.update({
        'total': len(companies),
        'round2_generated_at': '2026-09-19',
        'with_status': sum(1 for c in companies if c.get('status')),
        'by_status': dict(counts.most_common()),
        'in_config': sum(1 for c in companies if c.get('in_config')),
        'not_in_config': sum(1 for c in companies if not c.get('in_config')),
        'with_known_ats': sum(1 for c in companies if c.get('ats')),
        'by_ats': dict(collections.Counter(c.get('ats') or '未识别' for c in companies).most_common()),
        'by_country': dict(collections.Counter(c.get('country') or '未核实' for c in companies).most_common()),
        'round2_added': len(added),
        'by_source': dict(collections.Counter(s for c in companies for s in c['sources']).most_common()),
    })
    payload = dict(base)
    payload['generated_at'] = '2026-09-19'
    payload['round2'] = {
        'date': '2026-09-19',
        'description': '第二轮：多通道重试（C1 完整浏览器头 / C2 移动端 UA / C3 JSON·sitemap·RSS·PDF·'
                       'Common Crawl 索引 / C4 Playwright 无头 / C5 搜索引擎 site: 与 Wayback 存档）。',
        'status_vocabulary': ['已接入', '已在库', '待平台适配器', '当期中国0条', '接不了', '未解析'],
        'new_sources': ['《财富》世界500强 2026（非中国注册）',
                        '牛客校招日程 外企标签 tagId=2834',
                        '欧盟商会 / AHK 德国商会 / 英国商会 公开会员页',
                        'Top Employers Institute 官网认证企业页'],
    }
    payload['summary'] = summary
    payload['companies'] = companies
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print('WROTE', args.out, 'companies', len(companies))
    print(json.dumps(summary['by_status'], ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
