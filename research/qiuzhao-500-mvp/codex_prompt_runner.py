"""Codex prompt batch runner for CODEX_PROMPT.md tasks.

Runs predefined company batches, harvests jobs, writes batch artifacts under
codex_output, and optionally publishes each batch via publish.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import re
import shutil
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from collector import adapters
from collector.core import Blocked, now_iso, build_record


WORK = Path(__file__).resolve().parent
OUT = WORK / 'codex_output'
CAND = WORK / 'candidate_batches'
FOREIGN = Path('/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign/foreign_companies.jsonl')
INTERNET = Path('/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_internet/internet_companies.jsonl')
FORTUNE = Path('/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_fortune500/fortune500_2026_full.jsonl')
PUBLISH = WORK / 'publish.py'

DDG_URL = 'https://html.duckduckgo.com/html/'
UA = 'Mozilla/5.0 (X11; Linux x86_64)'
BLOCKED_PATH = OUT / 'blocked.jsonl'
PUBLISH_LOG = OUT / 'publish_log.md'


WORKDAY_TIMEOUT = 3 * 60


@dataclass
class Target:
    cn: str
    alias: Optional[str] = None
    slug: Optional[str] = None


WORKDAY_TARGETS: List[Target] = [
    Target('埃森哲', 'accenture', 'accenture'),
    Target('阿斯利康', 'astrazeneca', 'astrazeneca'),
    Target('百事', 'pepsico', 'pepsico'),
    Target('可口可乐', 'coca-cola', 'cocacola'),
    Target('亿滋', 'mondelez', 'mondelez'),
    Target('高露洁', 'colgate', 'colgate'),
    Target('雅诗兰黛', 'esteelauder', 'esteelauder'),
    Target('强生', 'johnson', 'johnson'),
    Target('卡夫亨氏', 'kraftheinz', 'kraftheinz'),
    Target('帝亚吉欧', 'diageo', 'diageo'),
    Target('保乐力加', 'pernod', 'pernod'),
    Target('耐克', 'nike', 'nike'),
    Target('宜家', 'ikea', 'ikea'),
    Target('迪士尼', 'disney', 'disney'),
    Target('微软', 'microsoft', 'microsoft'),
    Target('思科', 'cisco', 'cisco'),
    Target('英特尔', 'intel', 'intel'),
    Target('IBM', 'ibm', 'ibm'),
    Target('戴尔', 'dell', 'dell'),
    Target('惠普', 'hp', 'hp'),
    Target('赛默飞世尔', 'thermofisher', 'thermofisher'),
    Target('嘉吉', 'cargill', 'cargill'),
    Target('摩根大通', 'jpmorgan', 'jpmorgan'),
    Target('美国银行', 'bankofamerica', 'f500-34'),
    Target('富国银行', 'wellsfargo', 'f500-80'),
    Target('卡地纳健康', 'cardinalhealth', 'cardinal'),
    Target('克罗格', 'kroger', 'f500-52'),
    Target('家得宝', 'homedepot', 'f500-46'),
    Target('塔吉特', 'target', 'f500-96'),
    Target('UPS', 'ups', 'ups'),
    Target('联邦快递', 'fedex', 'fedex'),
]


GREENHOUSE_TARGETS: List[Target] = [
    Target('英伟达', 'nvidia', 'nvidia'),
    Target('AMD', 'amd', 'amd'),
    Target('Adobe', 'adobe', 'adobe'),
]


SUCCESFACTORS_TARGETS: List[Target] = [
    Target('SAP', 'sap', 'sap'),
    Target('诺华', 'novartis', 'novartis'),
    Target('ABB', 'abb', 'abb'),
    Target('壳牌', 'shell', 'shell'),
    Target('DHL', 'dhl', 'dhl'),
]


FEISHU_TARGETS = [
    Target('商汤科技', 'sensetime', 'sensetime'),
]


SELF_BUILT_TARGETS = [
    Target('哔哩哔哩', 'bilibili', 'bilibili'),
    Target('小红书', 'xiaohongshu', 'xiaohongshu'),
    Target('米哈游', 'mihoyo', 'mihoyo'),
    Target('拼多多', 'pdd', 'pdd'),
    Target('OPPO', 'oppo', 'oppo'),
    Target('吉比特', 'g-bits', 'g-bits'),
]


FORTUNE500_CHINESE_TARGETS = [
    Target('国家电网'),
    Target('中石油'),
    Target('中石化'),
    Target('中国建筑'),
    Target('鸿海精密'),
    Target('工商银行'),
    Target('农业银行'),
    Target('中国人寿'),
    Target('中国平安'),
    Target('中国中铁'),
    Target('中国铁建'),
    Target('中信集团'),
    Target('中交建'),
    Target('华润'),
    Target('恒力'),
    Target('台积电'),
    Target('中海油'),
    Target('南方电网'),
    Target('山东能源'),
    Target('比亚迪'),
    Target('中国五矿'),
    Target('宝武钢铁'),
    Target('中国电建'),
    Target('厦门建发'),
    Target('浙江荣盛'),
    Target('中国人保'),
    Target('上汽集团'),
    Target('国药集团'),
    Target('中国电信'),
    Target('吉利'),
    Target('联想'),
    Target('物产中大'),
    Target('山东魏桥'),
    Target('中粮'),
    Target('盛虹'),
    Target('江西铜业'),
    Target('太平洋建设'),
    Target('一汽'),
    Target('交通银行'),
    Target('纬创'),
    Target('浙江恒逸'),
    Target('中国铝业'),
    Target('广达电脑'),
    Target('保利'),
    Target('金川'),
]

SELF_BUILT_HINTS = {
    '哔哩哔哩': 'https://jobs.bilibili.com/campus/positions?type=3',
    '小红书': 'https://job.xiaohongshu.com/campus/position',
    '米哈游': 'https://jobs.mihoyo.com',
    '拼多多': 'https://careers.pddglobalhr.com/campus/grad',
    'OPPO': 'https://careers.oppo.com/university/oppo/campus/post',
    '吉比特': 'https://hr.g-bits.com/web/index.html#/post-web/post-list',
}


def _read_jsonl(path: Path) -> List[dict]:
    out = []
    if not path.exists():
        return out
    for line in path.open(encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _norm(s: Optional[str]) -> str:
    return re.sub(r'\s+', '', (s or '').lower())


def _norm_ascii(s: Optional[str]) -> str:
    return re.sub(r'[^a-z0-9]+', '', (s or '').lower())


def _build_company_index() -> Tuple[List[dict], List[dict], List[dict]]:
    return _read_jsonl(FOREIGN), _read_jsonl(INTERNET), _read_jsonl(FORTUNE)


def _match_name(meta: dict, aliases: Iterable[str]) -> bool:
    values = [
        _norm(meta.get('cn_name')),
        _norm(meta.get('name')),
        _norm(meta.get('slug')),
        _norm(meta.get('canonical_name')),
        _norm(meta.get('en_name')),
    ]
    ascii_values = [
        _norm_ascii(meta.get('cn_name')),
        _norm_ascii(meta.get('name')),
        _norm_ascii(meta.get('slug')),
        _norm_ascii(meta.get('canonical_name')),
        _norm_ascii(meta.get('en_name')),
    ]
    for a in aliases:
        na = _norm(a)
        if not na:
            continue
        if any(na == v or na in v or v in na for v in values if v):
            return True
        na_ascii = _norm_ascii(a)
        if na_ascii and any(na_ascii == v or na_ascii in v or v in na_ascii for v in ascii_values if v):
            return True
    return False


def _resolve_company(target: Target) -> dict:
    foreign, internet, fortune = _build_company_index()
    aliases = [x for x in [target.cn, target.alias, target.slug] if x]
    slug_hint = _norm_ascii(target.slug or target.alias or target.cn)
    for bucket in (foreign, internet, fortune):
        for row in bucket:
            if _match_name(row, aliases):
                return {
                    'cn_name': row.get('cn_name') or row.get('name') or target.cn,
                    'slug': row.get('slug') or row.get('slug_name') or row.get('slug_name_raw') or slug_hint,
                    'entry_url': row.get('entry_url'),
                    'platform_hint': row.get('platform_hint') or row.get('platform'),
                    'platform': row.get('platform') or row.get('platform_hint'),
                    'en_name': row.get('en_name') or row.get('canonical_name') or target.alias,
                    'country': row.get('country') or '未披露',
                    'industry': row.get('industry') or row.get('industry_tags')[:1] if isinstance(row.get('industry_tags'), list) else '未披露',
                    'cn_name_raw': target.cn,
                }
    if target.cn in SELF_BUILT_HINTS:
        return {
            'cn_name': target.cn,
            'slug': slug_hint or 'fe-' + _norm_ascii(str(time.time()).replace('.', '')),
            'entry_url': SELF_BUILT_HINTS[target.cn],
            'country': '中国',
            'industry': '互联网',
            'en_name': target.alias or target.cn,
            'cn_name_raw': target.cn,
        }
    return {
        'cn_name': target.cn,
        'slug': slug_hint or hashlib.md5(target.cn.encode('utf-8')).hexdigest()[:12],
        'country': '未披露',
        'industry': '未披露',
        'en_name': target.alias,
        'cn_name_raw': target.cn,
    }


def _ddg_search_urls(query: str, limit: int = 8) -> List[str]:
    try:
        r = requests.get(
            DDG_URL,
            params={'q': query},
            headers={'User-Agent': UA},
            timeout=12,
        )
    except Exception:
        return []
    if r.status_code != 200:
        return []
    urls: List[str] = []
    for m in re.finditer(r'uddg=([^&"\']+)', r.text):
        u = urllib.parse.unquote(m.group(1))
        urls.append(u)
    dedup = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        dedup.append(u)
        if len(dedup) >= limit:
            break
    return dedup


def _parse_workday_cfg(url: str, aliases: List[str]) -> Optional[dict]:
    try:
        from urllib.parse import urlsplit

        u = urllib.parse.urlsplit(url)
        host = (u.netloc or '').lower()
        if 'myworkdayjobs.com' not in host:
            return None
        seg = [s for s in (u.path or '').split('/') if s]
        if not seg:
            return None
        site = seg[0]
        if site.lower() in {'en-us', 'en', 'zh-cn', 'zh-hans', 'zh-hant'} and len(seg) >= 2:
            site = seg[1]
        site = re.sub(r'\?.*$', '', site)
        if '/' in site:
            site = site.split('/')[0]
        tenant = host.split('.')[0]
        cfg = {'kind': 'workday', 'host': host, 'tenant': tenant, 'site': site}
        hay = f"{cfg['tenant']} {cfg['site']} {host}".lower()
        if not aliases:
            return cfg
        if any(a and a.lower() in hay for a in aliases):
            return cfg
        return cfg
    except Exception:
        return None


def _ddg_candidates(query: str, limit: int = 8, host_filter: Optional[str] = None) -> List[str]:
    urls = _ddg_search_urls(query, limit=limit * 3)
    out: List[str] = []
    seen = set()
    for u in urls:
        if u in seen:
            continue
        if host_filter and host_filter.lower() not in (urllib.parse.urlsplit(u).netloc or '').lower():
            continue
        if not host_filter and 'myworkdayjobs.com' not in u:
            continue
        seen.add(u)
        if host_filter and host_filter.lower() in (urllib.parse.urlsplit(u).netloc or '').lower():
            out.append(u)
        elif not host_filter:
            out.append(u)
        if len(out) >= limit:
            break
    return out[:limit]


def _entry_url_candidates(url: str, aliases: List[str]) -> List[dict]:
    try:
        r = requests.get(url, headers={'User-Agent': UA}, timeout=12)
    except Exception:
        return []
    out = []
    for u in re.findall(r'https?://[^\"\']+', r.text):
        cfg = _parse_workday_cfg(u, aliases)
        if cfg:
            out.append(cfg)
    uniq = []
    seen = set()
    for c in out:
        key = (c['host'], c['tenant'], c['site'])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def _normalize_record(rec: dict, company: dict) -> dict:
    now = now_iso()
    rec.setdefault('first_seen_at', now)
    rec.setdefault('verified_at', now)
    if not rec.get('country'):
        rec['country'] = company.get('country', '未披露')
    if not rec.get('industry'):
        rec['industry'] = company.get('industry', '未披露')
    if not rec.get('recruitment_unit'):
        rec['recruitment_unit'] = company.get('cn_name', '')
    return rec


def _collect_adapter(cfg: dict, timeout_sec: int = 25) -> list:
    def _alarm_handler(signum, frame):
        raise Blocked(f'API超时({timeout_sec}s)')

    if timeout_sec <= 0:
        return adapters.collect({'adapter': cfg})

    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(timeout_sec)
    try:
        return adapters.collect({'adapter': cfg})
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def _collect_workday(cfg: dict, company: dict, deadline: float, deadline_hint: str) -> Tuple[Optional[List[dict]], Optional[str]]:
    try:
        raws = _collect_adapter(cfg, timeout_sec=25)
    except Blocked as e:
        return None, str(e)
    except Exception as e:
        return None, f'workday API异常:{type(e).__name__}'
    if time.time() > deadline:
        return None, '3min内未完成'
    records: List[dict] = []
    for i, raw in enumerate(raws, 1):
        try:
            rec = build_record(company, raw, i)
            rec['source_note'] = f"workday:{cfg['tenant']}|{cfg['site']}" if cfg.get('tenant') else 'workday'
            rec['source_name'] = f"{company['cn_name']}招聘官网"
            records.append(rec)
        except Blocked as e:
            continue
    return (records, None) if records else (None, 'workday详情无正文')


def collect_workday_company(company: dict, timeout_sec: int = WORKDAY_TIMEOUT) -> Tuple[List[dict], Optional[str]]:
    deadline = time.time() + timeout_sec
    aliases = [x for x in [company.get('en_name'), company.get('slug'), company.get('cn_name_raw'), company.get('cn_name')] if x]
    normalized = [a.lower().replace(' ', '') for a in aliases if a]

    cfgs: List[dict] = []
    entry_url = company.get('entry_url')
    if isinstance(entry_url, str) and entry_url:
        cfgs.extend(_entry_url_candidates(entry_url, normalized))

    for q in set([
        f"{company.get('en_name') or ''} workday careers",
        f"{company.get('cn_name') or ''} workday careers",
        f"{company.get('slug') or ''} workday jobs",
    ]):
        if not q.strip():
            continue
        for u in _ddg_candidates(q, limit=12):
            cfg = _parse_workday_cfg(u, normalized)
            if cfg and cfg not in cfgs:
                cfgs.append(cfg)

    if not cfgs:
        for host in [
            f"{company.get('slug')}.myworkdayjobs.com",
            f"{company.get('slug')}.wd1.myworkdayjobs.com",
            f"{company.get('slug')}.wd3.myworkdayjobs.com",
            f"{company.get('slug')}.wd5.myworkdayjobs.com",
        ]:
            for site in {company.get('slug'), 'Careers', 'cocacola', 'careers', 'External', 'Workday', 'workday'}:
                if not site:
                    continue
                cfg = {'kind': 'workday', 'host': host, 'tenant': company.get('slug') or host.split('.')[0], 'site': site}
                if cfg not in cfgs:
                    cfgs.append(cfg)

    last_err = None
    for cfg in cfgs:
        if time.time() > deadline:
            return [], '3min内未完成'
        records, err = _collect_workday(cfg, company, deadline, f"{company['cn_name']}")
        if records:
            return [ _normalize_record(rec, company) for rec in records ], None
        if err:
            last_err = err
    return [], last_err or '未找到可用的Workday入口'


def collect_greenhouse_company(company: dict) -> Tuple[List[dict], Optional[str]]:
    board = company.get('slug') or _norm_ascii(company['cn_name'])
    cfg = {'kind': 'greenhouse', 'board': board}
    try:
        raws = _collect_adapter(cfg, timeout_sec=20)
    except Blocked as e:
        return [], str(e)
    out = []
    for i, raw in enumerate(raws, 1):
        try:
            rec = build_record(company, raw, i)
            rec['source_note'] = f"greenhouse:{board}"
            out.append(_normalize_record(rec, company))
        except Blocked:
            continue
    return out, None if out else '无可用Greenhouse岗位'


def collect_mioffice_company(company: dict) -> Tuple[List[dict], Optional[str]]:
    sub = company.get('slug') or _norm_ascii(company['cn_name'])
    cfg = {'kind': 'mioffice', 'sub': sub}
    try:
        raws = _collect_adapter(cfg, timeout_sec=20)
    except Blocked as e:
        return [], str(e)
    out = []
    for i, raw in enumerate(raws, 1):
        try:
            rec = build_record(company, raw, i)
            rec['source_note'] = f"mioffice:{sub}"
            out.append(_normalize_record(rec, company))
        except Blocked:
            continue
    return out, None if out else '无可用飞书岗位'


def collect_jsonld_company(company: dict, entry_url: Optional[str] = None) -> Tuple[List[dict], Optional[str]]:
    entry_url = entry_url or company.get('entry_url')
    if not entry_url:
        return [], '缺失entry_url'
    cfg = {'kind': 'jsonld', 'url': entry_url}
    try:
        raws = _collect_adapter(cfg, timeout_sec=20)
    except Blocked as e:
        return [], str(e)
    out = []
    for i, raw in enumerate(raws, 1):
        try:
            rec = build_record(company, raw, i)
            rec['source_note'] = f"jsonld:{company.get('slug') or company['cn_name']}"
            out.append(_normalize_record(rec, company))
        except Blocked:
            continue
    return out, None if out else '未命中可解析JSON-LD'


def collect_successfactors_company(company: dict) -> Tuple[List[dict], Optional[str]]:
    entries: List[str] = []
    if company.get('entry_url'):
        entries.append(company['entry_url'])
    candidates = [company.get('en_name') or company.get('cn_name')]
    for q in [q for q in candidates if q]:
        for u in _ddg_candidates(f"{q} successfactors jobs", limit=3, host_filter='successfactors'):
            entries.append(u)
    # keep deterministic and dedup
    seen = set()
    entries = [u for u in entries if not (u in seen or seen.add(u))]
    if not entries:
        return [], '未找到SuccessFactors入口'
    last_reason = '未找到可用SuccessFactors/OData API'
    # 先尝试基于入口JSON-LD提取
    for entry in entries[:4]:
        recs, reason = collect_jsonld_company(company, entry)
        if recs:
            return recs, None
        if reason:
            last_reason = reason
    # 尝试直接访问可能的 OData元数据端点（不要求鉴权）
    odata_paths = [
        '/sap/opu/odata/sap',
        '/sap/opu/odata/IWPGW/SRAPPLICATIONS',
    ]
    for entry in entries[:3]:
        try:
            u = urllib.parse.urlsplit(entry)
            base = f'{u.scheme}://{u.netloc}'
            for p in odata_paths:
                target = f'{base}{p}'
                r = requests.get(target, timeout=12, headers={'User-Agent': UA})
                if r.status_code == 200:
                    if '<html' not in r.text.lower() and 'api' in target.lower():
                        return [], 'SuccessFactors OData端点可访问但未实现岗位解析'
        except Exception:
            continue
    return [], last_reason


def append_blocked(name: str, reason: str, slug: Optional[str] = None) -> None:
    BLOCKED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BLOCKED_PATH.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'company': name, 'slug': slug, 'reason': reason, 'at': now_iso()}, ensure_ascii=False) + '\n')


def _write_batch(batch_name: str, jobs: List[dict], companies: List[dict]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f'{batch_name}.json'
    out.write_text(json.dumps({
        'batch': batch_name,
        'generated_at': now_iso(),
        'companies': companies,
        'jobs': jobs,
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    return out


def _publish(batch_name: str) -> bool:
    # keep publish target independent, only publish this batch
    for f in CAND.glob(f'{batch_name}*.json'):
        if f.name != f'{batch_name}.json':
            f.unlink()
    src = OUT / f'{batch_name}.json'
    if not src.exists():
        return False
    tmp = CAND / f'{batch_name}.json'
    shutil.copy2(src, tmp)
    proc = subprocess_run([sys.executable, str(PUBLISH), '--batch-prefix', f'{batch_name}'])
    return proc == 0


def subprocess_run(argv: list) -> int:
    try:
        p = __import__('subprocess').run(argv, cwd=str(WORK), check=False, capture_output=True, text=True)
        if p.stdout:
            sys.stdout.write(p.stdout)
        if p.returncode != 0 and p.stderr:
            sys.stderr.write(p.stderr)
        return p.returncode
    except Exception as e:
        sys.stderr.write(f'subprocess失败: {type(e).__name__} {e}\n')
        return 1


def _append_publish_log(lines: List[str]) -> None:
    if not lines:
        return
    PUBLISH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PUBLISH_LOG.open('a', encoding='utf-8') as f:
        f.write(f"## {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}\n")
        for l in lines:
            f.write(f"- {l}\n")
        f.write('\n')


def run_batch(batch_name: str, targets: List[Target], mode: str, do_publish: bool = False) -> dict:
    jobs = []
    companies = []
    blocked = 0
    ok_companies = 0

    for t in targets:
        co = _resolve_company(t)
        co['slug'] = co.get('slug') or (t.slug or hashlib.md5(t.cn.encode('utf-8')).hexdigest()[:12])
        co['cn_name'] = co.get('cn_name') or t.cn
        companies.append({'cn_name': co['cn_name'], 'slug': co['slug'], 'mode': mode})

        if mode == 'workday':
            recs, reason = collect_workday_company(co)
        elif mode == 'greenhouse':
            recs, reason = collect_greenhouse_company(co)
        elif mode == 'mioffice':
            recs, reason = collect_mioffice_company(co)
        elif mode == 'jsonld':
            recs, reason = collect_jsonld_company(co)
        elif mode == 'successfactors':
            recs, reason = collect_successfactors_company(co)
        else:
            recs, reason = [], '未知批次类型'

        if recs:
            jobs.extend(recs)
            ok_companies += 1
        else:
            blocked += 1
            append_blocked(co['cn_name'], reason or '阻塞', co.get('slug'))

    out_path = _write_batch(batch_name, jobs, companies)
    published = False
    if do_publish and jobs:
        published = _publish(batch_name)

    status = '已发布' if published else '未发布'
    line = f"{batch_name}: 企业{len(targets)} 家, 成功{ok_companies}, 阻塞{blocked}, 岗位{len(jobs)}, {status}"
    _append_publish_log([line, f"output={out_path}"])
    return {
        'batch': batch_name,
        'companies': len(targets),
        'ok_companies': ok_companies,
        'blocked_companies': blocked,
        'jobs': len(jobs),
        'path': str(out_path),
        'published': published,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--batch', default='all', choices=[
        'all',
        'workday',
        'greenhouse',
        'successfactors',
        'mioffice',
        'self_built',
        'fortune500',
    ])
    p.add_argument('--publish', action='store_true')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    results = []

    if args.batch in {'all', 'workday'}:
        print('>> run batch: workday')
        results.append(run_batch('workday_batch', WORKDAY_TARGETS, 'workday', args.publish))
    if args.batch in {'all', 'greenhouse'}:
        print('>> run batch: greenhouse')
        results.append(run_batch('greenhouse_batch', GREENHOUSE_TARGETS, 'greenhouse', args.publish))
    if args.batch in {'all', 'successfactors'}:
        print('>> run batch: successfactors')
        results.append(run_batch('successfactors_batch', SUCCESFACTORS_TARGETS, 'successfactors', args.publish))
    if args.batch in {'all', 'mioffice'}:
        print('>> run batch: mioffice')
        results.append(run_batch('mioffice_batch', FEISHU_TARGETS, 'mioffice', args.publish))
    if args.batch in {'all', 'self_built'}:
        print('>> run batch: self_built')
        results.append(run_batch('self_built_batch', SELF_BUILT_TARGETS, 'jsonld', args.publish))
    if args.batch in {'all', 'fortune500'}:
        print('>> run batch: fortune500')
        results.append(run_batch('fortune500_batch', FORTUNE500_CHINESE_TARGETS, 'successfactors', False))

    summary = {'generated_at': now_iso(), 'batches': results}
    summary_path = OUT / 'expansion_progress_report.json'
    OUT.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    print('SUMMARY', summary_path)
    for b in results:
        print(f"{b['batch']} jobs={b['jobs']} blocked={b['blocked_companies']} published={b['published']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
