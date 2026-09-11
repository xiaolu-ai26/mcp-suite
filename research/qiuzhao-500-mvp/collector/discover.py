"""Multi-engine careers endpoint discovery -> adapter cfg candidates, with
identity-level name-affinity validation.

Engines: Brave Search (primary), DDG html, Bing. Engine health tracked with
temporary bans to keep per-company discovery fast.
"""
import re, time, base64, random, urllib.parse
from .core import Client, Blocked

cl = Client()
_last = [0.0]
_banned_until = {}  # engine name -> timestamp

GENERIC_TOKENS = {'group', 'inc', 'corp', 'corporation', 'company', 'the', 'co',
                  'ltd', 'plc', 'sa', 'ag', 'holdings', 'holding', 'international',
                  'china', 'global', 'companies', 'limited'}

WORKDAY_LOCALE = re.compile(r'^[a-z]{2,3}(?:[-_][A-Za-z]{2,4})?$')


def name_tokens(co):
    en = co.get('en_name') or ''
    cn = co.get('cn_name') or ''
    en_ascii = re.sub(r'[^\x00-\x7f]', ' ', en + ' ' + cn)
    toks = re.split(r'[^A-Za-z0-9]+', en_ascii.lower())
    toks = [t for t in toks if len(t) >= 4 and t not in GENERIC_TOKENS]
    return toks


def affinity(url_or_cfg, co):
    """Identity-level affinity: tokens must appear in hostname/tenant/site/
    board/slug/careers-host — never in job-title path segments."""
    if isinstance(url_or_cfg, dict):
        cfg = url_or_cfg
        if cfg.get('kind') == 'jsonld':
            parts = [urllib.parse.urlsplit(cfg.get('url', '')).netloc]
        else:
            parts = [str(cfg.get(k, '')) for k in
                     ('host', 'tenant', 'site', 'slug', 'board', 'lever', 'sub')]
        s = ' '.join(parts).lower()
    else:
        s = str(url_or_cfg).lower()
        s = urllib.parse.urlsplit(s if s.startswith('http') else 'http://' + s).netloc
    toks = name_tokens(co)
    if not toks:
        return True
    return any(t in s for t in toks)


def _throttle():
    wait = 1.6 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait + random.random() * 0.5)
    _last[0] = time.time()


def _brave(q):
    now = time.time()
    if _banned_until.get('brave', 0) > now:
        return None
    r = cl.get('https://search.brave.com/search', params={'q': q})
    if r.status_code != 200:
        _banned_until['brave'] = now + 300
        return None
    urls = []
    for m in re.finditer(r'href="(https?://[^"]+)"', r.text):
        u = m.group(1)
        if 'brave.com' in u:
            continue
        urls.append(u)
    return urls


def _ddg(q):
    now = time.time()
    if _banned_until.get('ddg', 0) > now:
        return None
    r = cl.get('https://html.duckduckgo.com/html/', params={'q': q})
    if r.status_code != 200 or len(r.text) < 500:
        _banned_until['ddg'] = now + 300
        return None
    urls = []
    for m in re.finditer(r'uddg=([^&"]+)', r.text):
        u = urllib.parse.unquote(m.group(1))
        if u.startswith('http'):
            urls.append(u)
    return urls


def _bing(q):
    now = time.time()
    if _banned_until.get('bing', 0) > now:
        return None
    r = cl.get('https://www.bing.com/search', params={'q': q, 'count': 20})
    if r.status_code != 200:
        _banned_until['bing'] = now + 300
        return None
    urls = []
    for m in re.finditer(r'href="(https?://www\.bing\.com/ck/a[^"]*)"', r.text):
        raw = m.group(1)
        um = re.search(r'[?&]u=a1([^&"]+)', raw)
        if um:
            b = um.group(1)
            b += '=' * (-len(b) % 4)
            try:
                u = base64.urlsafe_b64decode(b).decode('utf-8', 'ignore')
                if u.startswith('http'):
                    urls.append(u)
            except Exception:
                pass
    return urls


def search(query, deadline=None):
    """Return result URLs from first working engine; None results (banned/err) fall through."""
    for eng in (_brave, _ddg, _bing):
        for i in range(2):
            if deadline and time.time() > deadline:
                return []
            _throttle()
            try:
                urls = eng(query)
            except Exception:
                urls = None
            if urls:
                return urls
            if urls is None:
                break  # engine banned -> next engine
            time.sleep(1.5 + i)
    return []


def route_url(url):
    u = urllib.parse.urlsplit(url)
    host = u.netloc.lower()
    path = u.path
    if 'myworkdayjobs.com' in host:
        tenant = host.split('.')[0]
        segs = [s for s in path.split('/') if s]
        site = tenant
        for sg in segs:
            if WORKDAY_LOCALE.match(sg):
                continue
            if sg.lower().startswith(('job', 'search', 'r[')):
                continue
            site = sg
            break
        return {'kind': 'workday', 'host': host, 'tenant': tenant, 'site': site}
    if host.endswith('smartrecruiters.com'):
        m = re.match(r'/([A-Za-z0-9_\-]+)', path)
        if m:
            return {'kind': 'smartrecruiters', 'slug': m.group(1)}
    if 'greenhouse.io' in host:
        m = re.match(r'/([A-Za-z0-9_\-]+)', path)
        if m:
            return {'kind': 'greenhouse', 'board': m.group(1)}
    if host.endswith('lever.co'):
        m = re.match(r'/([A-Za-z0-9_\-]+)', path)
        if m:
            return {'kind': 'lever', 'lever': m.group(1)}
    if host.endswith('jobs.f.mioffice.cn'):
        return {'kind': 'mioffice', 'sub': host.split('.')[0]}
    if host.endswith('eightfold.ai'):
        return {'kind': 'eightfold', 'sub': host.split('.')[0]}
    if host in ('amazon.jobs', 'www.amazon.jobs'):
        return {'kind': 'amazonjobs'}
    return None


def discover_all(co, deadline_s=100):
    """Return list of (cfg, found_url) candidates, affinity-checked via cfg identity."""
    name = (co.get('en_name') or co['cn_name']).strip()
    cn = co.get('cn_name') or ''
    queries = [
        f'{name} careers site myworkdayjobs.com',
        f'{name} jobs smartrecruiters',
        f'{name} jobs greenhouse board',
        f'{name} jobs lever.co',
        f'{name} eightfold careers',
        f'{name} {cn} careers official jobs apply',
    ]
    ats_cands, generic = [], []
    seen = set()
    deadline = time.time() + deadline_s
    for query in queries:
        if ats_cands or time.time() > deadline:
            break
        urls = search(query, deadline)
        for u in urls[:10]:
            if u in seen:
                continue
            seen.add(u)
            cfg = route_url(u)
            if cfg:
                if affinity(cfg, co):
                    ats_cands.append((cfg, u))
            else:
                generic.append(u)
    if not ats_cands:
        for u in generic:
            host = urllib.parse.urlsplit(u).netloc.lower()
            if (any(k in host for k in ['career', 'jobs', 'talent', 'recruit', 'join'])
                    or any(k in u.lower() for k in ['/career', '/jobs', '/joinus', '/work-with-us'])):
                if affinity({'kind': 'jsonld', 'url': u}, co):
                    return [({'kind': 'jsonld', 'url': u}, u)]
    return ats_cands
