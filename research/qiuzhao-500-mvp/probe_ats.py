import json, httpx
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
c=httpx.Client(timeout=20, headers={'User-Agent':UA,'Accept':'application/json'}, follow_redirects=True)

def show(name,r):
    try:
        j=r.json()
        s=json.dumps(j,ensure_ascii=False)
        print(f'{name}: {r.status_code} len={len(s)} head={s[:200]}')
        return j
    except Exception as e:
        print(f'{name}: {r.status_code} NON-JSON {r.text[:120]}')
        return None

# Greenhouse public boards
for board in ['mckesson','cargill','chevrontexaco','generalmills']:
    r=c.get(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs')
    show(f'GH {board}',r)

# Lever
for co in ['netflix','palantir','plaid']:
    r=c.get(f'https://api.lever.co/v0/postings/{co}?mode=json')
    show(f'LEVER {co}',r)

# SmartRecruiters
for co in ['Visa','Boeing','NVIDIA','Continental']:
    r=c.get(f'https://api.smartrecruiters.com/v1/companies/{co}/postings?limit=3')
    show(f'SR {co}',r)

# Workday CXS
for tenant,site,host in [('nvidia','nvidiaExternalJob','nvidia.wd1.myworkdayjobs.com'),('schneider','SchneiderElectricCareers','schneider.wd3.myworkdayjobs.com')]:
    r=c.post(f'https://{host}/wday/cxs/{tenant}/{site}/jobs', json={'appliedFacets':{},'limit':3,'offset':0,'searchText':''},
             headers={'Content-Type':'application/json','Accept':'application/json'})
    show(f'WD {tenant}',r)

# Feishu mioffice
r=c.post('https://xiaomi.jobs.f.mioffice.cn/api/v1/search/job/posts',
    json={'keyword':'','limit':3,'offset':'','job_category_id_list':[],'tag_id_list':[],'location_code_list':[],'subject_id_list':[],'recruitment_type_id_list':[],'meal_ticket_id_list':[]},
    headers={'Content-Type':'application/json','Referer':'https://xiaomi.jobs.f.mioffice.cn/'})
show('MIOFFICE xiaomi',r)
