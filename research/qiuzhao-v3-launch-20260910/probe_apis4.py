"""Probe round 4: meituan page meta; all midea projects; mindray campus; jd alt."""
import json
import httpx

UA_PC = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

c = httpx.Client(timeout=20, headers={'User-Agent': UA_PC, 'Accept': 'application/json, text/plain, */*'})

# 1. Meituan page meta
r = c.post('https://zhaopin.meituan.com/api/official/job/getJobList',
           headers={'Content-Type': 'application/json', 'Referer': 'https://zhaopin.meituan.com/'},
           json={'pageNo': 1, 'pageSize': 20, 'jobType': [{"code": "1", "subCode": []}]})
j = r.json()
print('MEITUAN page meta:', json.dumps(j['data'].get('page'), ensure_ascii=False))
print('MEITUAN status:', j.get('status'), j.get('message'))

# 2. Midea all projects
r = c.get('https://careers.midea.com/backend/school/position/common/project/list',
          headers={'Referer': 'https://careers.midea.com/'})
j = r.json()
print('\nMIDEA projects:')
for p in (j.get('data') or []):
    print('  ', p.get('projectRuleId'), '|', p.get('projectRuleName'),
          '| employementCategory=', p.get('employementCategory'),
          '| status=', p.get('status'), '| season=', p.get('season'))

# 3. Mindray campus: try keyword search / different category
print('\nMINDRAY variants:')
for body in [
    {'tenantId': 106239, 'PageIndex': 1, 'PageSize': 2},
    {'tenantId': 106239, 'CategoryId': 1, 'PageIndex': 1, 'PageSize': 2},
    {'tenantId': 106239, 'CategoryId': 3, 'PageIndex': 1, 'PageSize': 2},
]:
    r = c.post('https://career.mindray.com/api/Jobad/GetJobAdPageList',
               headers={'Content-Type': 'application/json', 'Referer': 'https://career.mindray.com/'},
               json=body)
    try:
        jj = r.json()
        rows = jj.get('Data') or []
        print(' body=', body, '-> Count=', jj.get('Count'), 'sample=',
              [x.get('JobAdName') for x in rows[:2]])
    except Exception:
        print(' body=', body, r.status_code, r.text[:200])

# 4. JD alt: try public campus API host
print('\nJD alt hosts:')
for url, body in [
    ('https://campus.jd.com/api/wx/position/list', {'pageNum': 1, 'pageSize': 5}),
    ('https://zhaopin.jd.com/api/position/list', {'pageIndex': 1, 'pageSize': 5}),
]:
    try:
        r = c.post(url, headers={'Content-Type': 'application/json', 'Referer': 'https://campus.jd.com/'}, json=body)
        print(' ', url, r.status_code, r.headers.get('content-type'), r.text[:200])
    except Exception as e:
        print(' ', url, 'ERR', e)
