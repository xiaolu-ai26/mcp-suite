"""Build unified company queue from candidate pools, minus already-online units."""
import json, re
from pathlib import Path
from .core import WORK

V3 = WORK.parent / 'qiuzhao-v3-launch-20260910'
EXP = WORK.parent / 'qiuzhao-expansion-20260910'

PROD_UNITS = set()  # filled at runtime


def load_prod_units(path=None):
    """Download production units list (ssh) or use cached file."""
    cache = WORK / 'state' / 'prod_units.json'
    if path is None:
        if cache.exists():
            return set(json.loads(cache.read_text()))
        return None
    units = json.loads(Path(path).read_text())
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(sorted(units), ensure_ascii=False))
    return set(units)


def latin_of(name):
    return re.sub(r'[^A-Za-z0-9]', '', re.sub(r'[\u4e00-\u9fff]', '', name or '')).lower()


def build_queue(prod_units):
    queue = []
    seen = set()

    def add(slug, cn, en, country, industry, prio, fortune_rank=None,
            adapter=None, hint=None):
        key = latin_of(en) or slug
        if not key or key in seen:
            return
        cnk = re.sub(r'\s', '', cn or '')
        for u in prod_units:
            if cnk and (cnk in re.sub(r'\s|（.*?）|\(.*?\)', '', u) or
                        re.sub(r'\s|（.*?）|\(.*?\)', '', u) in cnk):
                return
        seen.add(key)
        co = {'slug': slug, 'cn_name': cn, 'en_name': en, 'country': country,
              'industry': industry, 'priority': prio}
        if fortune_rank:
            co['fortune_rank'] = fortune_rank
        if adapter:
            co['adapter'] = adapter
        if hint:
            co['platform_hint'] = hint
        queue.append(co)

    # merged_companies for industry enrichment
    industry_map, rank_map, alias_map = {}, {}, {}
    for line in open(V3 / 'expansion_fortune500' / 'merged_companies.jsonl'):
        r = json.loads(line)
        ind = r.get('industry_tags') or []
        if ind:
            industry_map[re.sub(r'\s', '', r['canonical_name'])] = ind[0]
        for a in (r.get('aliases') or []):
            for m in r.get('ranking_memberships') or []:
                if m.get('list_id') == 'fortune_global_500_2026':
                    rank_map[latin_of(a)] = m.get('rank')

    def ind_of(cn):
        return industry_map.get(re.sub(r'\s', '', cn or ''))

    # 1) internet pool (entry_url known)
    for line in open(V3 / 'expansion_internet' / 'internet_companies.jsonl'):
        r = json.loads(line)
        add(r['slug'], r['name'], r['slug'].title(), '中国', ind_of(r['name']) or '互联网',
            prio=1, adapter=None, hint={'platform': r.get('platform'),
                                        'entry_url': r.get('entry_url')})

    # 2) fortune 500 (all countries)
    for line in open(V3 / 'expansion_fortune500' / 'fortune500_2026_full.jsonl'):
        r = json.loads(line)
        en = (r.get('en_name') or '').title()
        rank = rank_map.get(latin_of(en)) or r.get('rank')
        add(f"f500-{r['rank']}", r['cn_name'], en, r['country'],
            ind_of(r['cn_name']) or '综合', prio=2 if r['country'] != '中国' else 3,
            fortune_rank=r['rank'])

    # 3) foreign pool
    for line in open(V3 / 'expansion_foreign' / 'foreign_companies.jsonl'):
        r = json.loads(line)
        en = latin_of(r['cn_name']) or r['slug']
        add(f"fc-{r['slug']}", r['cn_name'], r['slug'].title(), r['country'],
            r.get('industry') or '综合', prio=4, hint=r.get('platform_hint'))

    # 4) ranking memberships (forbes/gptw)
    p = EXP / 'ranking_memberships.jsonl'
    if p.exists():
        for line in open(p):
            r = json.loads(line)
            nm = r.get('canonical_name') or r.get('name') or ''
            if not nm:
                continue
            add(f"rm-{latin_of(nm)[:24]}", nm, nm if nm.isascii() else '',
                r.get('country') or '未披露', ind_of(nm) or '综合', prio=5)

    queue.sort(key=lambda c: c['priority'])
    out = WORK / 'state' / 'queue.json'
    out.write_text(json.dumps(queue, ensure_ascii=False, indent=1))
    return queue
