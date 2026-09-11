"""Probe guopin: full row, detail endpoint, company filter."""
import httpx, json

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
c = httpx.Client(timeout=20, headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*'})
H = {'Content-Type': 'application/json', 'Referer': 'https://www.iguopin.com/'}

# 1. Full row structure
r = c.post('https://gp-api.iguopin.com/api/jobs/v1/list', headers=H, json={'pageNo': 1, 'pageSize': 2})
j = r.json()
row = j['data']['list'][0]
print('=== ROW KEYS ===')
print(json.dumps(row, ensure_ascii=False, indent=1)[:2500])

# 2. Detail endpoint guesses
jid = row['job_id']
print('\n=== DETAIL PROBES for job_id=', jid)
for url, body in [
    (f'https://gp-api.iguopin.com/api/jobs/v1/detail', {'job_id': jid}),
    (f'https://gp-api.iguopin.com/api/jobs/v1/detail', {'id': jid}),
    (f'https://gp-api.iguopin.com/api/jobs/v1/info', {'job_id': jid}),
]:
    try:
        rr = c.post(url, headers=H, json=body)
        print('POST', url, body, '->', rr.status_code, rr.text[:400])
    except Exception as e:
        print('ERR', url, e)

# 3. Try filter by company_name / keyword
print('\n=== FILTER PROBES ===')
for body in [
    {'pageNo': 1, 'pageSize': 3, 'keyword': '中国中铁'},
    {'pageNo': 1, 'pageSize': 3, 'job_name': ''},
    {'pageNo': 1, 'pageSize': 3, 'company_name': '中国中铁'},
    {'pageNo': 1, 'pageSize': 3, 'companyId': row['company_id']},
    {'pageNo': 1, 'pageSize': 3, 'company_id': row['company_id']},
]:
    try:
        rr = c.post('https://gp-api.iguopin.com/api/jobs/v1/list', headers=H, json=body)
        jj = rr.json()
        d = jj.get('data', {})
        lst = d.get('list', [])
        names = [x.get('company_name') for x in lst[:3]]
        print('body keys=', list(body.keys()), 'total=', d.get('total'), 'companies=', names)
    except Exception as e:
        print('ERR', body, e)
