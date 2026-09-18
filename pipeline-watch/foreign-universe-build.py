#!/usr/bin/env python3
"""Build ``pipeline-watch/foreign-universe.json`` — the repeatable foreign-employer universe.

Inputs (all already collected by this pipeline, nothing new is fetched here):

* ``pipeline-watch/foreign-companies-discovery.json``  — 443 foreign employers from the
  闲鱼 company table plus platform probes (branch ``feat/foreign-companies``);
* the read-only 闲鱼 Base dump (``page0..3.ndjson``) — every row tagged
  外企 / 外企-合资 / 中外合资, including the 122 rows the first pass did not consume;
* the Top Employers Institute China 2025 certified list (``top-employers-2025.json``);
* the regional-HQ / chamber name lists collected by ``foreign-entry-probe.py``.

Output rows carry: 中文名 / 英文名 / 国别 / 行业 / 来源 / 是否已在库或已在配置里 / 招聘系统.
"""
from __future__ import annotations
import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / 'qiuzhao' / 'collector' / 'p1_platform_companies.json'
FOREIGN_TAGS = {'外企', '外企/合资', '中外合资/港澳台资', '中外合资'}
URL_RE = re.compile(r'https?://[^\s\)\]，,、；;"\'<>]+')
ATS_PATTERNS = [
    ('Moka', re.compile(r'app\.mokahr\.com/(?:campus-recruitment|campus_apply|social-recruitment|apply)/([^/"?\s]+)/(\d+)'), '{0}/{1}'),
    ('北森', re.compile(r'https?://([a-z0-9][a-z0-9\-]*)\.zhiye\.com'), '{0}'),
    ('飞书招聘', re.compile(r'https?://([a-z0-9][a-z0-9\-]*)\.jobs\.feishu\.cn'), '{0}'),
    ('大易', re.compile(r'https?://([a-z0-9\-]+\.hotjob\.cn)/(SU[0-9a-fA-F]{20,})'), '{1}'),
    ('51job', re.compile(r'campus\.51job\.com/([A-Za-z0-9_\-]+)'), '{0}'),
    ('Workday', re.compile(r'https?://([a-z0-9\-]+)\.wd(\d+)\.myworkdayjobs\.com/(?:zh-CN/|en-US/)?([^/"?#]+)'), '{0}/wd{1}/{2}'),
    ('SuccessFactors', re.compile(r'https?://([a-z0-9\-]+\.(?:jobs2web|jobs|careers?)\.[a-z.]+)'), '{0}'),
    ('Eightfold', re.compile(r'https?://([a-z0-9\-]+)\.eightfold\.ai'), '{0}'),
    ('Phenom', re.compile(r'phenompeople\.com|\.phenom\.com'), ''),
    ('Avature', re.compile(r'https?://([a-z0-9\-]+)\.avature\.net'), '{0}'),
    ('iCIMS', re.compile(r'https?://careers-([a-z0-9\-]+)\.icims\.com'), '{0}'),
    ('Taleo', re.compile(r'https?://([a-z0-9\-]+)\.taleo\.net'), '{0}'),
    ('ORC', re.compile(r'https?://([a-z0-9\-]+)\.oraclecloud\.com'), '{0}'),
    ('SmartRecruiters', re.compile(r'smartrecruiters\.com/([A-Za-z0-9_\-]+)'), '{0}'),
    ('Greenhouse', re.compile(r'boards\.greenhouse\.io/([A-Za-z0-9_\-]+)'), '{0}'),
    ('Lever', re.compile(r'jobs\.lever\.co/([A-Za-z0-9_\-]+)'), '{0}'),
    ('moseeker', re.compile(r'moseeker\.com'), ''),
    ('ajinga', re.compile(r'ajinga\.com'), ''),
    ('tupu360', re.compile(r'https?://([a-z0-9\-]+)\.tupu360\.com'), '{0}'),
]
SUFFIX = re.compile(
    r'(有限公司|股份有限公司|有限责任公司|集团|股份|公司|投资|中国区|大中华区|中国|china|greater china)$', re.I)


def norm(name):
    s = re.sub(r'[\s()（）·,，、.．\-—/*]', '', str(name or '')).lower()
    return SUFFIX.sub('', s)


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


def classify(urls):
    for url in urls:
        for platform, rx, keyfmt in ATS_PATTERNS:
            m = rx.search(url)
            if m:
                try:
                    key = keyfmt.format(*m.groups()) if m.groups() else keyfmt
                except Exception:
                    key = ''
                return platform, key, url
    return '', '', (urls[0] if urls else '')


def config_names():
    cfg = json.loads(CFG.read_text(encoding='utf-8'))
    by_name = {}
    for platform, block in cfg.items():
        if platform == '_README' or not isinstance(block, dict):
            continue
        for key, entry in block.items():
            name = entry if isinstance(entry, str) else str((entry or {}).get('name') or '')
            if name:
                by_name.setdefault(norm(name), (name, platform, key))
    return by_name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--xianyu-dir', default='/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/xianyu',
                    help='directory with the read-only 闲鱼 ndjson pages')
    ap.add_argument('--tops', default='/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/discover/out/top-employers-2025.json')
    ap.add_argument('--out', default=str(ROOT / 'pipeline-watch' / 'foreign-universe.json'))
    args = ap.parse_args()

    rows = {}
    order = []

    def upsert(key, **fields):
        if key not in rows:
            rows[key] = {'company_cn': '', 'company_en': '', 'country': '', 'industry': [],
                         'sources': [], 'in_config': False, 'config_platform': '', 'config_key': '',
                         'ats': '', 'ats_key': '', 'campus_url': '', 'evidence_urls': [],
                         'priority': '', 'notes': ''}
            order.append(key)
        rec = rows[key]
        for k, v in fields.items():
            if k in ('sources', 'industry', 'evidence_urls'):
                for item in (v if isinstance(v, list) else [v]):
                    if item and item not in rec[k]:
                        rec[k].append(item)
            elif not rec.get(k):
                rec[k] = v

    cfg_by_name = config_names()

    # 1) previous discovery pass (443)
    disc = json.loads((ROOT / 'pipeline-watch' / 'foreign-companies-discovery.json').read_text(encoding='utf-8'))
    for c in disc['companies']:
        cn = c['company']
        en = ''
        m = re.match(r'^([A-Za-z0-9&\.\-\' ]{2,})\s+(.+)$', cn)
        if m and re.search(r'[\u4e00-\u9fff]', m.group(2)):
            en, cn = m.group(1).strip(), m.group(2).strip()
        upsert(norm(cn) or norm(c['company']), company_cn=cn, company_en=en,
               country=c.get('country') or '', industry=list(c.get('industry') or []),
               sources=['foreign-companies-discovery (闲鱼表 449 行 + 平台探测)'],
               ats=c.get('ats') or '', campus_url=c.get('campus_url') or '',
               evidence_urls=list(c.get('evidence_urls') or []),
               priority='high' if c.get('size_class') == 'large_mnc' else 'medium',
               notes=c.get('notes') or '')

    # 2) full read-only 闲鱼 dump, every foreign/IV-tagged row
    xdir = Path(args.xianyu_dir)
    xrows = []
    for page in sorted(xdir.glob('page*.ndjson')):
        for line in page.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line:
                xrows.append(json.loads(line))
    for r in xrows:
        tags = set(r.get('企业性质') or [])
        if not (tags & FOREIGN_TAGS):
            continue
        name = (r.get('公司名称') or '').strip()
        if not name:
            continue
        urls = []
        for field in ('投递方式', '官方公告', '备注/提示'):
            urls += urls_in(r.get(field))
        platform, key, url = classify(urls)
        upsert(norm(name), company_cn=name, industry=list(r.get('行业大类') or []),
               sources=[f'闲鱼表(只读) 企业性质={"/".join(sorted(tags))}'],
               ats=platform, ats_key=key, campus_url=url, evidence_urls=urls[:3])

    # 3) Top Employers Institute China 2025
    tops_path = Path(args.tops)
    if tops_path.exists():
        tops = json.loads(tops_path.read_text(encoding='utf-8'))
        for r in tops.get('companies', []):
            upsert(norm(r['cn']) or norm(r['en']), company_cn=r['cn'], company_en=r['en'],
                   sources=['Top Employers Institute 中国杰出雇主 2025'],
                   priority='high')

    # 4) mark what is already configured / already in the library
    for key in order:
        rec = rows[key]
        hit = cfg_by_name.get(key)
        if not hit:
            for cfg_key, (name, platform, ckey) in cfg_by_name.items():
                if len(key) >= 3 and (key in cfg_key or cfg_key in key):
                    hit = (name, platform, ckey)
                    break
        if hit:
            rec['in_config'] = True
            rec['config_platform'] = hit[1]
            rec['config_key'] = hit[2]
    companies = [rows[k] for k in order]
    companies.sort(key=lambda r: (not r['in_config'], r['company_cn']))
    summary = {
        'total': len(companies),
        'in_config': sum(1 for c in companies if c['in_config']),
        'not_in_config': sum(1 for c in companies if not c['in_config']),
        'with_known_ats': sum(1 for c in companies if c['ats']),
        'by_ats': dict(collections.Counter(c['ats'] or '未识别' for c in companies).most_common()),
        'by_country': dict(collections.Counter(c['country'] or '未核实' for c in companies).most_common()),
        'by_source': dict(collections.Counter(s for c in companies for s in c['sources']).most_common()),
    }
    payload = {
        'generated_at': '2026-09-19',
        'description': '外企/中外合资雇主全景（可重复生成：pipeline-watch/foreign-universe-build.py）。'
                       '每个来源只读抓取，公司行只用于发现，岗位仍从各公司官方招聘站采集。',
        'inputs': {
            'foreign_companies_discovery': 'pipeline-watch/foreign-companies-discovery.json (443)',
            'xianyu_base_readonly': 'Base REDACTED / tblMKWxJGIPhcDbw（571 行外企/合资，只读）',
            'top_employers_china_2025': 'https://www.szhzxw.cn/98955.html + https://www.szhzxw.cn/98945.html',
        },
        'summary': summary,
        'companies': companies,
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print('WROTE', args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
