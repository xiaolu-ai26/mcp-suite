"""Probe round 3: parse JSON, inspect totals; fix JD/Midea/Mindray campus."""
import json
import httpx

UA_PC = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
UA_M = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'


def post(name, url, body, headers=None, ua=UA_PC):
    h = {'User-Agent': ua, 'Accept': 'application/json, text/plain, */*',
         'Content-Type': 'application/json'}
    if headers:
        h.update(headers)
    print('=' * 60, name)
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as c:
            r = c.post(url, headers=h, json=body)
            print(r.status_code, r.headers.get('content-type'))
            try:
                j = r.json()
                print('TOP KEYS:', list(j.keys()))
                d = j.get('data')
                if isinstance(d, dict):
                    print('DATA KEYS:', list(d.keys()))
                    for k in ('total', 'totalCount', 'count', 'pageSize', 'pageNo', 'pages', 'totalPage'):
                        if k in d:
                            print('  ', k, '=', d[k])
                    lst = d.get('list') or d.get('records') or d.get('rows') or []
                    print('  list len:', len(lst))
                    if lst:
                        print('  ROW0 KEYS:', list(lst[0].keys()))
                else:
                    print(str(j)[:600])
            except Exception:
                print(r.text[:600])
    except Exception as e:
        print('ERR', repr(e))


# Meituan total
post('MEITUAN', 'https://zhaopin.meituan.com/api/official/job/getJobList',
     {'pageNo': 1, 'pageSize': 3, 'jobType': [{"code": "1", "subCode": []}]},
     {'Referer': 'https://zhaopin.meituan.com/'})

# Mindray - try to find campus. Print Count and a few JobAdName + Require snippets
with httpx.Client(timeout=20) as c:
    r = c.post('https://career.mindray.com/api/Jobad/GetJobAdPageList',
               headers={'User-Agent': UA_PC, 'Content-Type': 'application/json'},
               json={'tenantId': 106239, 'CategoryId': 2, 'PageIndex': 1, 'PageSize': 3})
    j = r.json()
    print('MINDRAY Count=', j.get('Count'))
    for row in j.get('Data', [])[:3]:
        print(' -', row.get('JobAdName'), '| LocNames=', row.get('LocNames'),
              '| CategoryId=', row.get('CategoryId'), '| Require[:40]=', (row.get('Require') or '')[:40].replace('\n', ' '))

# Midea: GET project list
with httpx.Client(timeout=20) as c:
    for path in ['/backend/school/position/common/project/list',
                 '/backend/school/position/common/projectRule/list']:
        try:
            r = c.get('https://careers.midea.com' + path,
                      headers={'User-Agent': UA_PC, 'Referer': 'https://careers.midea.com/'})
            print('MIDEA GET', path, r.status_code, r.text[:500])
        except Exception as e:
            print('MIDEA GET err', path, e)

# JD: try mobile UA + body with paging fields known to JDLive
post('JD-m', 'https://campus.jd.com/api/wx/position/page',
     {'pageNum': 1, 'pageSize': 5, 'keyword': '', 'jobType': ''},
     {'Referer': 'https://campus.jd.com/', 'x-requested-with': 'XMLHttpRequest'}, ua=UA_M)
post('JD-b', 'https://campus.jd.com/api/wx/position/page',
     {'pageIndex': 1, 'pageSize': 5},
     {'Referer': 'https://campus.jd.com/'})
