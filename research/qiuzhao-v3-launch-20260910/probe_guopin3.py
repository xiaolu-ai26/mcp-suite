"""Probe guopin subsites: how does {code}.iguopin.com call the list API?"""
import httpx, json, re

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
c = httpx.Client(timeout=20, headers={'User-Agent': UA}, follow_redirects=True)

# 1. Fetch a subsite homepage to find its API pattern / config
for code in ['crec', 'crrc', 'spic', 'chinamobile', 'cnnc', 'avic', 'cgnpc', 'faw', 'chd']:
    url = f'https://{code}.iguopin.com/'
    try:
        r = c.get(url)
        print(f'=== {code} -> {r.status_code} len={len(r.text)}')
        # look for api host / subsite id in HTML
        for pat in [r'gp-api[^"\']*', r'subsite["\']?\s*[:=]\s*["\']?(\d+)', r'apiHost["\']?\s*[:=]\s*["\']([^"\']+)',
                    r'window\.__\w+__\s*=\s*({.{0,300})']:
            m = re.findall(pat, r.text)
            if m:
                print('   PAT', pat[:30], '->', str(m[:2])[:200])
        # title
        t = re.search(r'<title>(.*?)</title>', r.text)
        if t:
            print('   TITLE:', t.group(1)[:80])
    except Exception as e:
        print(f'=== {code} ERR {e!r}')
