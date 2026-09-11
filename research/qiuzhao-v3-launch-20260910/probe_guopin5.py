"""Find correct company filter param for guopin list API."""
import httpx, json

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
c = httpx.Client(timeout=20, headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
                                       'Content-Type': 'application/json',
                                       'Referer': 'https://crec.iguopin.com/'})
CID = '10685307842176571'  # crec 中国中铁

def try_body(label, extra):
    body = {'pageNo':1,'pageSize':3}
    body.update(extra)
    r = c.post('https://gp-api.iguopin.com/api/jobs/v1/list', json=body)
    try:
        j = r.json(); d = j.get('data') or {}
        lst = d.get('list') or []
        comps = set(x.get('company_name') for x in lst)
        print(f'{label}: total={d.get("total")} n={len(lst)} comps={list(comps)[:2]}')
    except Exception as e:
        print(f'{label}: ERR {r.status_code} {r.text[:120]}')

for extra in [
    {'company_id': CID}, {'companyId': CID}, {'enterprise_id': CID},
    {'entId': CID}, {'org_id': CID}, {'cid': CID}, {'company': CID},
    {'company_id_list': [CID]}, {'companyIds': [CID]},
    {'subsite': 'crec'}, {'domain': 'crec'},
]:
    try_body(str(list(extra.keys())[0]), extra)

# Also try GET with query params
print('--- GET variants ---')
for q in [f'company_id={CID}', f'companyId={CID}', f'company={CID}']:
    r = c.get(f'https://gp-api.iguopin.com/api/jobs/v1/list?pageNo=1&pageSize=3&{q}')
    try:
        j=r.json(); d=j.get('data') or {}; lst=d.get('list') or []
        print(f'GET {q}: total={d.get("total")} comps={list(set(x.get("company_name") for x in lst))[:2]}')
    except: print(f'GET {q}: {r.status_code} {r.text[:100]}')
