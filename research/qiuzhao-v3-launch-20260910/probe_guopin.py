"""Probe guopin API structure - discover request/response shape."""
import httpx, json

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

c = httpx.Client(timeout=20, headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*'})

# Try the main api first with a few body shapes
url = 'https://gp-api.iguopin.com/api/jobs/v1/list'
bodies = [
    {'pageNo': 1, 'pageSize': 3},
    {'pageNum': 1, 'pageSize': 3},
    {'page': 1, 'size': 3},
]
for b in bodies:
    try:
        r = c.post(url, headers={'Content-Type': 'application/json', 'Referer': 'https://www.iguopin.com/'}, json=b)
        print('POST', b, '->', r.status_code, r.headers.get('content-type'))
        print(r.text[:800])
        print('-'*50)
    except Exception as e:
        print('ERR', b, e)

# Also try GET
try:
    r = c.get(url + '?pageNo=1&pageSize=3', headers={'Referer': 'https://www.iguopin.com/'})
    print('GET ->', r.status_code, r.headers.get('content-type'))
    print(r.text[:800])
except Exception as e:
    print('GET ERR', e)
