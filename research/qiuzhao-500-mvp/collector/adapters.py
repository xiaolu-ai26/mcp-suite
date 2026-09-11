"""ATS adapters. Each returns list of normalized raw jobs:
{title, cities[], description, detail_url, apply_url?, education?, cohort?, deadline?, published_at?, id?, recruitment_type?, category?}
"""
import json, re, time, random
from urllib.parse import urljoin, urlparse, quote
from .core import Client, Blocked, strip_html, clean_city

cl = Client()
MAX_JOBS = 3


def _take(jobs):
    return jobs[:MAX_JOBS]


# ---------- Workday ----------
def workday(cfg):
    host, tenant, site = cfg['host'], cfg['tenant'], cfg['site']
    base = f'https://{host}'
    r = cl.post(f'{base}/wday/cxs/{tenant}/{site}/jobs',
                json={'appliedFacets': {}, 'limit': MAX_JOBS + 5, 'offset': 0, 'searchText': ''},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                         'Referer': f'{base}/en-US/{site}'})
    if r.status_code != 200:
        raise Blocked(f'workday列表{r.status_code}')
    data = r.json()
    postings = data.get('jobPostings') or []
    if not postings:
        raise Blocked('workday无在招岗位')
    out = []
    for p in postings:
        path = p['externalPath']
        d = cl.get(f'{base}/wday/cxs/{tenant}/{site}{path}',
                   headers={'Accept': 'application/json',
                            'Referer': f'{base}/en-US/{site}{path}'})
        if d.status_code != 200:
            continue
        info = d.json().get('jobPostingInfo') or {}
        desc = strip_html(info.get('jobDescription') or '')
        if len(desc) < 50:
            continue
        loc = info.get('location') or ''
        extra = info.get('externalUrl') or ''
        out.append({
            'id': f"wd-{path.rsplit('_', 1)[-1]}",
            'title': p.get('title'),
            'cities': [clean_city(loc.split(',')[0])] if loc else [],
            'description': desc,
            'detail_url': f'{base}/en-US/{site}{path}',
            'apply_url': extra or f'{base}/en-US/{site}{path}',
            'published_at': info.get('startDate') or None,
        })
        if len(out) >= MAX_JOBS:
            break
    if not out:
        raise Blocked('workday详情无正文')
    return _take(out)


# ---------- SmartRecruiters ----------
def smartrecruiters(cfg):
    slug = cfg['slug']
    r = cl.get(f'https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit={MAX_JOBS + 5}')
    if r.status_code == 404:
        raise Blocked('smartrecruiters公司不存在')
    if r.status_code != 200:
        raise Blocked(f'smartrecruiters列表{r.status_code}')
    content = r.json().get('content') or []
    if not content:
        raise Blocked('smartrecruiters无在招岗位')
    out = []
    for p in content:
        pid = p['id']
        d = cl.get(f'https://api.smartrecruiters.com/v1/companies/{slug}/postings/{pid}')
        if d.status_code != 200:
            continue
        dj = d.json()
        secs = (dj.get('jobAd') or {}).get('sections') or {}
        desc = strip_html('\n'.join(
            (secs.get(k) or {}).get('text', '') for k in
            ('jobDescription', 'qualifications', 'responsibilities', 'aboutUs')))
        if len(desc) < 50:
            continue
        loc = dj.get('location') or {}
        out.append({
            'id': f'sr-{pid}',
            'title': (dj.get('name') or p.get('name') or '').strip(),
            'cities': [clean_city(loc.get('city'))] if loc.get('city') else [],
            'description': desc,
            'detail_url': dj.get('applyUrl') or f'https://jobs.smartrecruiters.com/{slug}/{pid}',
            'apply_url': dj.get('applyUrl'),
            'published_at': dj.get('releasedDate') or None,
        })
        if len(out) >= MAX_JOBS:
            break
    if not out:
        raise Blocked('smartrecruiters详情无正文')
    return _take(out)


# ---------- Greenhouse ----------
def greenhouse(cfg):
    board = cfg['board']
    r = cl.get(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true')
    if r.status_code == 404:
        raise Blocked('greenhouse看板不存在')
    if r.status_code != 200:
        raise Blocked(f'greenhouse列表{r.status_code}')
    jobs = r.json().get('jobs') or []
    if not jobs:
        raise Blocked('greenhouse无在招岗位')
    out = []
    for j in jobs:
        desc = strip_html(j.get('content') or '')
        if len(desc) < 50:
            continue
        loc = j.get('location') or {}
        out.append({
            'id': f"gh-{j.get('id')}",
            'title': j.get('title'),
            'cities': [clean_city(loc.get('name'))] if loc.get('name') else [],
            'description': desc,
            'detail_url': j.get('absolute_url'),
            'apply_url': j.get('absolute_url'),
            'published_at': j.get('updated_at', '')[:10] or None,
        })
        if len(out) >= MAX_JOBS:
            break
    if not out:
        raise Blocked('greenhouse详情无正文')
    return _take(out)


# ---------- Lever ----------
def lever(cfg):
    co = cfg['lever']
    r = cl.get(f'https://api.lever.co/v0/postings/{co}?mode=json')
    if r.status_code == 404:
        raise Blocked('lever看板不存在')
    if r.status_code != 200:
        raise Blocked(f'lever列表{r.status_code}')
    jobs = r.json()
    if not jobs:
        raise Blocked('lever无在招岗位')
    out = []
    for j in jobs:
        parts = [j.get('text') or '']
        for lst in (j.get('lists') or []):
            parts.append(f"{lst.get('text','')}\n" + '\n'.join(
                f"• {strip_html(x)}" for x in (lst.get('content') or [])[:12]))
        desc = strip_html('\n'.join(parts))
        if len(desc) < 50:
            continue
        cat = j.get('categories') or {}
        loc = cat.get('location') or ''
        out.append({
            'id': f"lever-{j.get('id')}",
            'title': j.get('text'),
            'cities': [clean_city(loc.split(',')[0])] if loc else [],
            'description': desc,
            'detail_url': j.get('hostedUrl'),
            'apply_url': j.get('hostedUrl'),
            'category': cat.get('team'),
        })
        if len(out) >= MAX_JOBS:
            break
    if not out:
        raise Blocked('lever详情无正文')
    return _take(out)


# ---------- 飞书 mioffice ----------
def mioffice(cfg):
    sub = cfg['sub']
    base = f'https://{sub}.jobs.f.mioffice.cn'
    r = cl.post(f'{base}/api/v1/search/job/posts',
                json={'keyword': '', 'limit': MAX_JOBS + 7, 'offset': 0,
                      'job_category_id_list': [], 'tag_id_list': [],
                      'location_code_list': [], 'subject_id_list': [],
                      'recruitment_type_id_list': [], 'meal_ticket_id_list': []},
                headers={'Content-Type': 'application/json', 'Referer': base + '/'})
    if r.status_code != 200:
        raise Blocked(f'mioffice列表{r.status_code}')
    posts = (r.json().get('data') or {}).get('job_post_list') or []
    if not posts:
        raise Blocked('mioffice无在招岗位')
    out = []
    for p in posts:
        desc = strip_html((p.get('description') or '') + '\n任职要求：\n' + (p.get('requirement') or ''))
        if len(desc) < 50:
            continue
        rtype = '校招' if '校' in (p.get('recruitment_type') or '') or '届' in (p.get('title') or '') else None
        out.append({
            'id': f"mio-{p.get('id')}",
            'title': p.get('title'),
            'cities': [clean_city(p.get('city_list') or [None])[0] if p.get('city_list') else None] or [],
            'description': desc,
            'detail_url': f"{base}/social/position/{p.get('id')}/detail",
            'apply_url': f"{base}/social/position/{p.get('id')}/detail",
            'recruitment_type': rtype,
        })
        if len(out) >= MAX_JOBS:
            break
    if not out:
        raise Blocked('mioffice详情无正文')
    return _take(out)


# ---------- Eightfold ----------
def eightfold(cfg):
    sub = cfg['sub']
    base = f'https://{sub}.eightfold.ai'
    r = cl.get(f'{base}/api/apply/v2/jobs?domain={sub}.eightfold.ai&start=0&num={MAX_JOBS + 5}')
    if r.status_code != 200:
        raise Blocked(f'eightfold列表{r.status_code}')
    positions = r.json().get('positions') or []
    if not positions:
        raise Blocked('eightfold无在招岗位')
    out = []
    for p in positions:
        desc = strip_html(p.get('description') or '')
        if len(desc) < 50:
            continue
        loc = p.get('location') or ''
        out.append({
            'id': f"ef-{p.get('id') or p.get('name')}",
            'title': p.get('name'),
            'cities': [clean_city(loc.split(',')[0])] if loc else [],
            'description': desc,
            'detail_url': p.get('canonicalPositionUrl') or f'{base}/careers',
            'apply_url': p.get('canonicalPositionUrl'),
        })
        if len(out) >= MAX_JOBS:
            break
    if not out:
        raise Blocked('eightfold详情无正文')
    return _take(out)


# ---------- Generic JSON-LD careers crawl ----------
JOB_LINK_PAT = re.compile(r'/(job|jobs|position|positions|vacancy|vacancies|career|careers|role|opening|detail|posting)s?/[A-Za-z0-9]', re.I)


def _jsonld_jobs(html):
    out = []
    for m in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                         html, re.S | re.I):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict):
                continue
            graph = it.get('@graph') if '@graph' in it else [it]
            for g in graph:
                if isinstance(g, dict) and g.get('@type') in ('JobPosting', ['JobPosting']):
                    out.append(g)
    return out


def _ldloc(g):
    for jl in (g.get('jobLocation') or []):
        if isinstance(jl, dict):
            addr = jl.get('address') or {}
            city = (addr.get('addressLocality') or addr.get('addressRegion')
                    or addr.get('addressCountry'))
            if city:
                return str(city)
    return None


def _ld_to_raw(g, page_url):
    desc = strip_html(g.get('description') or '')
    title = g.get('title') or ''
    if len(desc) < 50 or not title:
        return None
    valid = g.get('validThrough') or None
    return {
        'title': str(title).strip(),
        'cities': [_ldloc(g)] if _ldloc(g) else [],
        'description': desc,
        'detail_url': g.get('url') or page_url,
        'apply_url': g.get('url') or page_url,
        'deadline': valid[:10] if valid else None,
        'published_at': (g.get('datePosted') or '')[:10] or None,
    }


def jsonld_careers(cfg):
    url = cfg['url']
    r = cl.get(url)
    if r.status_code in (403, 406):
        raise Blocked(f' careers页{r.status_code}反爬')
    if r.status_code != 200:
        raise Blocked(f'careers页{r.status_code}')
    html = r.text
    # 1) list-page JSON-LD
    for g in _jsonld_jobs(html):
        raw = _ld_to_raw(g, url)
        if raw:
            return [raw]
    # 2) collect job links from page (and from sitemap if none)
    links = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html):
        href = m.group(1)
        if href.startswith(('javascript', '#', 'mailto')):
            continue
        full = urljoin(str(r.url), href)
        if JOB_LINK_PAT.search(full) and full != str(r.url):
            links.add(full.split('?')[0])
    if not links:
        sm = cl.get(urljoin(str(r.url), '/sitemap.xml'))
        if sm.status_code == 200 and '<urlset' in sm.text[:2000]:
            for m in re.finditer(r'<loc>([^<]+)</loc>', sm.text):
                u = m.group(1)
                if JOB_LINK_PAT.search(u):
                    links.add(u)
        # nested sitemaps
        if not links and '<sitemapindex' in sm.text[:2000]:
            for m in re.finditer(r'<loc>([^<]+)</loc>', sm.text)[:6] if isinstance(re.finditer(r'<loc>([^<]+)</loc>', sm.text), list) else []:
                pass
    if not links:
        raise Blocked('未找到岗位链接(SPA渲染?)')
    out = []
    for link in list(links)[:6]:
        try:
            rd = cl.get(link)
        except Blocked:
            continue
        if rd.status_code != 200:
            continue
        for g in _jsonld_jobs(rd.text):
            raw = _ld_to_raw(g, link)
            if raw:
                out.append(raw)
                break
        if len(out) >= MAX_JOBS:
            break
    if not out:
        raise Blocked('岗位详情无JSON-LD正文')
    return _take(out)


# ---------- Amazon.jobs ----------
def amazonjobs(cfg):
    r = cl.get('https://www.amazon.jobs/en/search.json',
               params={'result_limit': MAX_JOBS + 5, 'offset': 0, 'base_query': ''})
    if r.status_code != 200:
        raise Blocked(f'amazonjobs列表{r.status_code}')
    jobs = r.json().get('jobs') or []
    if not jobs:
        raise Blocked('amazonjobs无在招岗位')
    out = []
    for j in jobs:
        desc = strip_html(j.get('description') or '')
        if len(desc) < 50:
            continue
        loc = j.get('normalized_location') or ''
        out.append({
            'id': f"amzn-{j.get('job_path', '').split('/')[-2] if j.get('job_path') else j.get('id_icims')}",
            'title': j.get('title'),
            'cities': [clean_city(loc.split(',')[0])] if loc else [],
            'description': desc,
            'detail_url': 'https://www.amazon.jobs' + j['job_path'],
            'apply_url': 'https://www.amazon.jobs' + j['job_path'],
            'published_at': j.get('posted_date'),
        })
        if len(out) >= MAX_JOBS:
            break
    if not out:
        raise Blocked('amazonjobs正文过短')
    return _take(out)


ADAPTERS = {
    'workday': workday,
    'smartrecruiters': smartrecruiters,
    'greenhouse': greenhouse,
    'lever': lever,
    'mioffice': mioffice,
    'eightfold': eightfold,
    'amazonjobs': amazonjobs,
    'jsonld': jsonld_careers,
}


def collect(co):
    cfg = co.get('adapter') or {}
    kind = cfg.get('kind')
    fn = ADAPTERS.get(kind)
    if not fn:
        raise Blocked(f'未知适配器{kind}')
    return fn(cfg)
