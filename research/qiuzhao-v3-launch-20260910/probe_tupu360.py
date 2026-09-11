"""Probe tupu360 candidate orgs - which resolve, and inspect structure."""
import httpx, sys, re

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'
c = httpx.Client(timeout=15, follow_redirects=True, headers={'User-Agent': UA})

ORGS = [
    # pharma
    'roche','novartis','msd','merck','gsk','sanofi','bayer','lilly','abbott',
    'boehringer','astrazeneca','pfizer','johnsonandjohnson','jansen','takeda',
    # fmcg
    'pg','p&g','unilever','nestle','pepsico','cocacola','mondelez','mars','danone',
    'ab_inbev','ab-inbev','diageo','loreal','l-oreal',
    # manufacturing
    'bosch','schneider','abb','honeywell','3m','dupont','basf','siemens','ge',
    'johnsoncontrols','emerson','parker','textron','cummins',
]

def probe(org):
    for url in [f'https://{org}.tupu360.com/', f'https://www.tupu360.com/{org}/']:
        try:
            r = c.get(url)
            if r.status_code == 200 and len(r.text) > 2000:
                title = re.search(r'<title>(.*?)</title>', r.text)
                return url, len(r.text), title.group(1) if title else ''
        except Exception:
            pass
    return None, 0, None

for org in ORGS:
    url, ln, title = probe(org)
    if url:
        print(f'[OK] {org}: {url} len={ln} title={title[:60]}')
    else:
        print(f'[--] {org}: not found', file=sys.stderr)
