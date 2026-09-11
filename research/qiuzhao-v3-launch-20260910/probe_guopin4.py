"""Test if list API respects subsite via Referer/Origin or subsite param."""
import httpx, json

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
c = httpx.Client(timeout=20, headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*'})

def probe(label, headers, body):
    try:
        r = c.post('https://gp-api.iguopin.com/api/jobs/v1/list',
                   headers={'Content-Type': 'application/json', **headers}, json=body)
        j = r.json()
        d = j.get('data') or {}
        lst = d.get('list') or []
        comps = set(x.get('company_name') for x in lst)
        subsites = set(x.get('subsite') for x in lst)
        print(f'{label}: total={d.get("total")} subsite_field={subsites} companies={list(comps)[:3]}')
    except Exception as e:
        print(f'{label}: ERR {e!r}')

# Baseline
probe('no-ref', {'Referer': 'https://www.iguopin.com/'}, {'pageNo':1,'pageSize':3})
# With subsite referer
for code in ['crec','crrc','spic','chinamobile','cnnc','avic']:
    probe(f'referer={code}', {'Referer': f'https://{code}.iguopin.com/'}, {'pageNo':1,'pageSize':3})
# With subsite in body
probe('subsite=crec', {'Referer':'https://crec.iguopin.com/'}, {'pageNo':1,'pageSize':3,'subsite':'crec'})
probe('subsite_id=1', {'Referer':'https://crec.iguopin.com/'}, {'pageNo':1,'pageSize':3,'subsiteId':1})
# Origin header
probe('origin=crec', {'Referer':'https://crec.iguopin.com/','Origin':'https://crec.iguopin.com'}, {'pageNo':1,'pageSize':3})
