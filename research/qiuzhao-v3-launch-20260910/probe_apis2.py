"""Probe round 2: fix JD, Midea, Mindray campus; inspect pagination totals."""
import json
import httpx

UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
UA_PC = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'


def show(name, url, method='GET', json_body=None, form=None, headers=None, params=None):
    h = {'User-Agent': UA_PC, 'Accept': 'application/json, text/plain, */*'}
    if headers:
        h.update(headers)
    print('=' * 70)
    print(f'[{name}] {method} {url}')
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as c:
            if method == 'GET':
                r = c.get(url, headers=h, params=params)
            elif form is not None:
                r = c.post(url, headers=h, data=form, params=params)
            else:
                r = c.post(url, headers=h, json=json_body, params=params)
            print('status', r.status_code, 'ct', r.headers.get('content-type'))
            print(r.text[:1200])
    except Exception as e:
        print('ERROR', repr(e))


# JD: try alternate body shapes
show('JD-v2', 'https://campus.jd.com/api/wx/position/page', 'POST',
     json_body={'pageNum': 1, 'pageSize': 5, 'keyword': ''},
     headers={'Content-Type': 'application/json', 'Referer': 'https://campus.jd.com/'})
show('JD-v3', 'https://campus.jd.com/api/wx/position/page', 'POST',
     form={'pageNum': 1, 'pageSize': 5},
     headers={'Content-Type': 'application/x-www-form-urlencoded',
              'Referer': 'https://campus.jd.com/'})

# Meituan: inspect total / pagination keys
show('MEITUAN-total', 'https://zhaopin.meituan.com/api/official/job/getJobList', 'POST',
     json_body={'pageNo': 1, 'pageSize': 3, 'jobType': [{"code": "1", "subCode": []}]},
     headers={'Content-Type': 'application/json', 'Referer': 'https://zhaopin.meituan.com/'})

# NetEase: confirm pagination param name
show('NETEASE-p2', 'https://campus.163.com/api/campuspc/position/getJobList', 'GET',
     params={'projectId': 103, 'pageIndex': 2, 'pageSize': 3},
     headers={'Referer': 'https://campus.163.com/'})

# Midea: try list projects / no filter
show('MIDEA-nofilter', 'https://careers.midea.com/backend/school/position/common/position/list', 'POST',
     json_body={'pageIndex': 1, 'pageSize': 5},
     headers={'Content-Type': 'application/json', 'Referer': 'https://careers.midea.com/'})
show('MIDEA-projects', 'https://careers.midea.com/backend/school/position/common/project/list', 'POST',
     json_body={'pageIndex': 1, 'pageSize': 20},
     headers={'Content-Type': 'application/json', 'Referer': 'https://careers.midea.com/'})

# Mindray: try campus category variants
show('MINDRAY-cat2', 'https://career.mindray.com/api/Jobad/GetJobAdPageList', 'POST',
     json_body={'tenantId': 106239, 'CategoryId': 2, 'PageIndex': 1, 'PageSize': 2},
     headers={'Content-Type': 'application/json', 'Referer': 'https://career.mindray.com/'})
