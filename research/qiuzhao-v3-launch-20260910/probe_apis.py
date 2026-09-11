"""Probe candidate public APIs to inspect real response shapes. Read-only."""
import json, sys
import httpx

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'


def show(name, url, method='GET', json_body=None, headers=None, params=None):
    h = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*'}
    if headers:
        h.update(headers)
    print('=' * 70)
    print(f'[{name}] {method} {url}')
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as c:
            if method == 'GET':
                r = c.get(url, headers=h, params=params)
            else:
                r = c.post(url, headers=h, json=json_body, params=params)
            print('status', r.status_code, 'ct', r.headers.get('content-type'))
            txt = r.text
            print(txt[:1500])
    except Exception as e:
        print('ERROR', repr(e))


# 1. JD
show('JD', 'https://campus.jd.com/api/wx/position/page', 'POST',
     json_body={'pageIndex': 1, 'pageSize': 5},
     headers={'Content-Type': 'application/json', 'Referer': 'https://campus.jd.com/'})

# 2. Meituan
show('MEITUAN', 'https://zhaopin.meituan.com/api/official/job/getJobList', 'POST',
     json_body={'pageNo': 1, 'pageSize': 5, 'jobType': [{"code": "1", "subCode": []}]},
     headers={'Content-Type': 'application/json', 'Referer': 'https://zhaopin.meituan.com/'})

# 3. NetEase main
show('NETEASE-MAIN', 'https://campus.163.com/api/campuspc/position/getJobList', 'GET',
     params={'projectId': 103, 'pageIndex': 1, 'pageSize': 5},
     headers={'Referer': 'https://campus.163.com/'})

# 4. Midea
show('MIDEA', 'https://careers.midea.com/backend/school/position/common/position/list', 'POST',
     json_body={'projectRuleId': '2027届美的星', 'pageIndex': 1, 'pageSize': 5},
     headers={'Content-Type': 'application/json', 'Referer': 'https://careers.midea.com/'})

# 5. Mindray
show('MINDRAY', 'https://career.mindray.com/api/Jobad/GetJobAdPageList', 'POST',
     json_body={'tenantId': 106239, 'CategoryId': 2, 'PageIndex': 1, 'PageSize': 5},
     headers={'Content-Type': 'application/json', 'Referer': 'https://career.mindray.com/'})
