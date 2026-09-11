import httpx, json
c = httpx.Client(timeout=15, follow_redirects=True, headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
base = 'https://iflytek.zhiye.com'
PORTAL='6e2235dc-4b88-4698-b96a-5a73c705d8db'
KEY='REDACTED'
trials = [
  ('POST','/portal-api/Job/GetJobPostList',{'PortalId':PORTAL,'pageIndex':1,'pageSize':5}),
  ('POST','/api/Job/GetJobPostList',{'PortalId':PORTAL,'Key':KEY,'pageIndex':1,'pageSize':5,'JobType':1}),
  ('POST','/api/Job/GetJobPostList',{'portalId':PORTAL,'pageIndex':1,'pageSize':5}),
  ('GET', f'/api/Job/GetJobPostList?portalId={PORTAL}&pageIndex=1&pageSize=5', None),
  ('POST','/api/JobPost/GetJobPostList',{'portalId':PORTAL,'pageIndex':1,'pageSize':5}),
]
for method,path,body in trials:
    try:
        h={'Content-Type':'application/json','Referer':base+'/campus/jobs'}
        r = c.post(base+path, json=body, headers=h) if method=='POST' else c.get(base+path, headers={'Referer':base+'/campus/jobs'})
        print(method, path, r.status_code, r.headers.get('content-type','')[:30], r.text[:160].replace(chr(10),' '))
    except Exception as e:
        print(method, path, 'ERR', str(e)[:80])
