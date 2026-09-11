import httpx, json
c = httpx.Client(timeout=15, follow_redirects=True, headers={'User-Agent':'Mozilla/5.0', 'Accept':'application/json'})
base = 'https://iflytek.zhiye.com'
candidates = [
    ('POST', '/api/Job/GetJobPostList', {'pageIndex':1,'pageSize':5}),
    ('POST', '/api/Job/GetJobList', {'pageIndex':1,'pageSize':5}),
    ('POST', '/api/Job/SearchJobPost', {'pageIndex':1,'pageSize':5}),
    ('GET',  '/api/Job/GetJobPostList?pageIndex=1&pageSize=5', None),
    ('GET',  '/api/Job/GetJobList?pageIndex=1&pageSize=5', None),
    ('POST', '/WebApi/Job/GetJobList', {'pageIndex':1,'pageSize':5}),
    ('POST', '/api/job/GetJobPostList', {'pageIndex':1,'pageSize':5}),
]
for method, path, body in candidates:
    try:
        if method=='POST':
            r = c.post(base+path, json=body, headers={'Content-Type':'application/json','Referer':base+'/campus/jobs'})
        else:
            r = c.get(base+path, headers={'Referer':base+'/campus/jobs'})
        ct = r.headers.get('content-type','')
        print(method, path, r.status_code, ct[:40], r.text[:200].replace(chr(10),' '))
    except Exception as e:
        print(method, path, 'ERR', str(e)[:80])
