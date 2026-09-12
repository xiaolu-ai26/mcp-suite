"""Public official recruitment collectors; no production writes."""
from __future__ import annotations
import base64, html, json, re, time
from datetime import datetime, timezone
from pathlib import Path
import requests

COMPANIES={'pdd':'拼多多','dji':'大疆','huawei':'华为','xiaohongshu':'小红书','kuaishou':'快手','oppo':'OPPO','vivo':'vivo','honor':'荣耀','byd':'比亚迪','catl':'宁德时代'}
TYPES={'campus':'校园招聘','intern':'实习招聘','social':'社会招聘'}

def text(value):
    return html.unescape(re.sub('<[^>]+>', '\n',str(value or ''))).strip()

def request_json(session,url,body,iv=None):
    r=session.post(url,json=body,timeout=(10,45));r.raise_for_status();d=r.json()
    if d.get('necromancer'):
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        d=json.loads(unpad(AES.new(d['necromancer'].encode(),AES.MODE_CBC,iv.encode()).decrypt(base64.b64decode(d['data'])),16))
    if d.get('success') is False or d.get('code',0) not in (0,None): raise ValueError(str(d)[:400])
    return d.get('result',d.get('data',d))

def job(company,scope,ident,title,url,description,location='',raw=None):
    record={'id':f'p1:{company}:{ident}','source_record_id':str(ident),'title':title,'job_title':title,'education_raw':'','major_requirements_raw':'','cohort_raw':'','reviewed_at':datetime.now(timezone.utc).isoformat(),'company':COMPANIES.get(company,company),'company_name':COMPANIES.get(company,company),'company_slug':company,'unit':COMPANIES.get(company,company),'recruitment_unit':COMPANIES.get(company,company),'recruitment_type':TYPES[scope],'source_url':url,'detail_url':url,'application_url':url,'description_raw':text(description),'location':location,'city':location,'cities':[x.strip() for x in re.split(r'\s*/\s*|[，,、;；]',location) if x.strip()],'source':'official_career','verified_at':datetime.now(timezone.utc).isoformat(),'source_fields':{k:v for k,v in (raw or {}).items() if k in {'id','hireMode','commitment','education','degree','major','workExperience','graduationYear','recruitType','recruitmentType','projectName','publishedAt','releaseTime','deadline','endDate'} and len(str(v))<500}}
    fields=raw or {}
    record['education_raw']=text(fields.get('education') or fields.get('degree') or fields.get('Degree') or '')
    record['major_requirements_raw']=text(fields.get('major') or fields.get('majorRequirement') or '')
    record['experience_raw']=text(fields.get('experience') or fields.get('workExperience') or fields.get('YearsOfWorking') or '')
    record['deadline_raw']=text(fields.get('deadline') or fields.get('endDate') or '')
    return record

def coverage(url):
    return {'status':'blocked','complete':False,'expected_total':None,'collected_jobs':0,'pages_scanned':0,'detail_complete':False,'source_url':url,'errors':[],'evidence':[]}

def finish(jobs,c):
    c['scope_evidence']='; '.join(dict.fromkeys(j.get('scope_evidence','') for j in jobs)) or c.get('scope_evidence','')
    c['collected_jobs']=len(jobs);c['unique_source_ids']=len({j['source_record_id'] for j in jobs})
    c['complete']=bool(c.get('pagination_exhausted') and c['detail_complete'] and not c['errors'] and (c['expected_total'] is None or c['expected_total']==len(jobs)))
    c['status']='success' if c['complete'] else 'partial' if jobs else 'blocked'
    return {'jobs':jobs,'coverage':c}

def collect_pdd(scope,output_dir):
    page_type='intern' if scope=='intern' else 'grad';entry=f'https://careers.pddglobalhr.com/campus/{page_type}'
    c=coverage(entry);jobs=[];s=requests.Session()
    if scope=='social':c['errors']=['Official social recruitment endpoint not verified'];return finish(jobs,c)
    endpoint='train/list' if scope=='intern' else 'list'
    try:
        seen=set();expected=None
        for page in range(1,10001):
            d=request_json(s,'https://careers.pddglobalhr.com/api/careers/api/recruit/position/'+endpoint,{'page':page,'pageSize':20})
            (output_dir/f'list-{page}.json').write_text(json.dumps(d,ensure_ascii=False))
            c['pages_scanned']+=1;total=int(d['total']);rows=d['list'] or []
            if not rows and expected is not None and len(seen)==expected:
                c['pagination_exhausted']=True;c['last_page_evidence']=f'page={page};rows=0;prior_total={expected};terminal_total={total}';break
            if expected is not None and total!=expected:raise ValueError('List total changed during scan')
            expected=total;c['expected_total']=total
            if not rows:
                c['pagination_exhausted']=True;c['last_page_evidence']=f'page={page};rows=0;total={total}';break
            for row in rows:
                ident=row['id']
                if ident in seen:raise ValueError('Repeated job ID across pages')
                seen.add(ident)
                detail=request_json(s,'https://careers.pddglobalhr.com/api/careers/api/recruit/position/detail',{'id':ident})
                if detail.get('id')!=ident or not detail.get('normal') or not detail.get('serveRequirement') or not detail.get('jobDuty'):raise ValueError(f'Incomplete detail: {ident}')
                (output_dir/f'detail-{ident}.json').write_text(json.dumps(detail,ensure_ascii=False))
                url=f'{entry}/detail?positionId={ident}'
                j=job('pdd',scope,ident,detail['name'],url,detail['jobDuty']+'\n任职要求\n'+detail['serveRequirement'],detail.get('workLocationName',''),detail)
                if row.get('graduationYear'):j['cohort_raw']=str(row['graduationYear'])+'届';j['graduation_year_raw']=str(row['graduationYear']);j['graduation_evidence']='official API graduationYear'
                j['scope_evidence']=f'Official {entry}, API {endpoint}'
                jobs.append(j)
            time.sleep(.08)
        c['detail_complete']=len(jobs)==expected
        c['evidence']=[p.name for p in output_dir.glob('list-*.json')];c['scope_evidence']=f'Official {entry}, API {endpoint}'
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def collect_moka_sites(company,scope,sites,output_dir):
    """Full official Moka pagination with three bounded concurrent detail reads."""
    from concurrent.futures import ThreadPoolExecutor
    jobs=[];c=coverage(sites[0][0] if sites else '');seen=set();session=requests.Session()
    try:
        for site_url,basis in sites:
            m=re.search(r'/(?:campus|social)-recruitment/([^/]+)/(\d+)',site_url)
            if not m:raise ValueError('Unrecognized verified Moka URL')
            org,site=m.groups();host=site_url.split('/')[0]+'//'+site_url.split('/')[2]
            r=session.get(site_url,timeout=(10,45));r.raise_for_status();pagehtml=html.unescape(r.text)
            ivmatch=re.search(r'"aesIv"\s*:\s*"([^"]+)"',pagehtml);iv=ivmatch.group(1) if ivmatch else None
            listed=set();total=None;terminal=False;selected=[]
            for offset in range(0,200000,50):
                d=request_json(session,host+'/api/outer/ats-apply/website/jobs/v2',{'orgId':org,'siteId':int(site),'limit':50,'offset':offset,'needStat':True,'locale':'zh-CN'},iv)
                (output_dir/f'{site}-list-{offset}.json').write_text(json.dumps(d,ensure_ascii=False));c['pages_scanned']+=1
                rows=d['jobs'];n=d.get('jobStats',{}).get('total')
                if not rows and total is not None and len(listed)==total:
                    terminal=True;c['last_page_evidence']=f'site={site};offset={offset};rows=0;prior_total={total};terminal_total={n}';break
                if total is not None and n!=total:raise ValueError('Moka total changed during scan')
                total=n
                if not rows:terminal=True;c['last_page_evidence']=f'site={site};offset={offset};rows=0;total={total}';break
                for row in rows:
                    ident=row['id']
                    if ident in listed:raise ValueError(f'Repeated Moka ID {ident}')
                    listed.add(ident);commitment=str(row.get('commitment',''));mode=row.get('hireMode')
                    if mode not in (1,2):raise ValueError(f'Unknown official hireMode={mode}; job={ident}')
                    actual='intern' if '实习' in commitment or '实习' in row.get('title','') else 'campus' if mode==2 else 'social'
                    if actual==scope and ident not in seen:selected.append(row);seen.add(ident)
                time.sleep(.08)
            if not terminal or total is not None and len(listed)!=total:raise ValueError(f'Incomplete list site={site}: observed={len(listed)}, total={total}')
            c['evidence'].extend(p.name for p in output_dir.glob(f'{site}-list-*.json'))
            def enrich(row):
                ident=row['id']
                with requests.Session() as ss:detail=request_json(ss,host+'/api/outer/ats-apply/website/job',{'orgId':org,'siteId':int(site),'jobId':ident,'locale':'zh-CN'},iv)
                if detail.get('id')!=ident or not detail.get('jobDescription'):raise ValueError(f'Incomplete Moka detail {ident}')
                (output_dir/f'detail-{ident}.json').write_text(json.dumps(detail,ensure_ascii=False))
                url=site_url.split('#')[0].rstrip('/')+'#/job/'+ident
                loc=' / '.join(x.get('cityName') or x.get('provinceName') or x.get('country','') for x in detail.get('locations',[]))
                j=job(company,scope,ident,detail['title'],url,detail['jobDescription'],loc,detail)
                j['scope_evidence']=f'{basis}; hireMode={row.get("hireMode")}; commitment={row.get("commitment","")}; title={row.get("title","")}'
                j['recruitment_type_raw']={'hireMode':detail.get('hireMode'),'commitment':detail.get('commitment')}
                if '校园大使' in detail['title'] and scope=='social':j['recruitment_type_conflict']='Official hireMode=1 (social), title names campus ambassador; retain source classification for review'
                project=detail.get('projectFolder') or {};settings=project.get('settings') or {}
                j['cohort_raw']=text(settings.get('graduateDateLimit') or project.get('name') or '')
                return j
            with ThreadPoolExecutor(max_workers=3) as pool:
                for j in pool.map(enrich,selected):jobs.append(j)
        c['pagination_exhausted']=True;c['detail_complete']=True;c['expected_total']=len(jobs)
        c['scope_evidence']=f'Official Moka hireMode 1 social/2 campus; internship commitment/title; requested={scope}'
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def collect_standard(company,scope,output_dir):
    from concurrent.futures import ThreadPoolExecutor
    if company=='xiaohongshu':
        host='https://job.xiaohongshu.com';entry=host+'/'+('campus/intern' if scope=='intern' else scope)+'/position'
        list_url=host+'/websiterecruit/position/pageQueryPosition';detail_url=host+'/websiterecruit/position/queryPositionDetail';idkey='positionId'
    elif company=='kuaishou':
        host='https://campus.kuaishou.cn';entry=host+'/recruit/campus/e/#/campus/jobs'
        list_url=host+'/recruit/campus/e/api/v1/open/positions/simple';detail_url=host+'/recruit/campus/e/api/v1/open/positions/find';idkey='id'
    else:
        host='https://careers.oppo.com';entry=host+'/campus/post'
        list_url=host+'/openapi/position/pageNew';detail_url=host+'/openapi/position/detail';idkey='idRecruitPosition'
    c=coverage(entry);jobs=[];rows_all=[];seen=set();s=requests.Session();s.headers['Tenant-Id']='1000';list_total=None
    if company in ('oppo','kuaishou') and scope=='social':
        c['errors']=['Separate official social endpoint not yet verified'];return finish([],c)
    try:
        for page in range(1,10001):
            params={'pageNum':page,'pageSize':50}
            if company=='xiaohongshu':params['recruitType']=scope
            if company=='oppo':params['current']=page
            d=request_json(s,list_url,params);(output_dir/f'list-{page}.json').write_text(json.dumps(d,ensure_ascii=False));c['pages_scanned']+=1
            rows=d.get('list',d.get('records')) or [];total=int(d['total'])
            if not rows and list_total is not None and len(seen)==list_total:
                c['pagination_exhausted']=True;c['last_page_evidence']=f'page={page};rows=0;prior_total={list_total};terminal_total={total}';break
            if list_total is not None and total!=list_total:raise ValueError('Total changed during scan')
            list_total=total
            if not rows:c['pagination_exhausted']=True;c['last_page_evidence']=f'page={page};rows=0;total={total}';break
            for row in rows:
                ident=row[idkey]
                if ident in seen:raise ValueError('Repeated pagination ID')
                seen.add(ident)
                if company=='oppo':actual={'Intern':'intern','Graduate':'campus','doctor':'campus'}.get(row.get('recruitmentType'))
                elif company=='kuaishou':actual={('intern','schoolr'):'intern',('fulltime','schoolr'):'campus'}.get((row.get('positionNatureCode'),row.get('recruitProjectCode')))
                else:actual=scope
                if actual is None:raise ValueError('Unknown official recruitment type enum')
                if actual==scope:rows_all.append(row)
            time.sleep(.08)
        if len(seen)!=list_total:raise ValueError(f'List mismatch: {len(seen)} != {list_total}')
        c['list_total']=list_total;c['expected_total']=len(rows_all)
        def enrich(row):
            ident=row[idkey];params={'positionId':ident,'recruitType':scope} if company=='xiaohongshu' else {'id':ident}
            r=requests.get(detail_url,params=params,headers={'Tenant-Id':'1000'},timeout=(10,45));r.raise_for_status();envelope=r.json()
            if envelope.get('success') is False or envelope.get('code',0)!=0:raise ValueError('Detail response rejected')
            d=envelope.get('result',envelope.get('data'));(output_dir/f'detail-{ident}.json').write_text(json.dumps(d,ensure_ascii=False))
            if d[idkey]!=ident:raise ValueError('Detail ID mismatch')
            if company=='xiaohongshu':
                actual={'school_recruit':'campus','intern_recruit':'intern','club_recruit':'social'}.get(d.get('recruitType'))
                if actual is None:raise ValueError('Unknown XHS detail recruitType')
                if actual!=scope:return None
                title=d['positionName'];desc=d['duty'];req=d['qualification'];loc=d.get('workplace','');url=entry+'/'+str(ident)
                cohort=d.get('projectName','');basis=f'Official API recruitType={scope}; detail.recruitType={d.get("recruitType")}'
            elif company=='oppo':
                title=d['positionName'];desc=d['positionDesc'];req=d['positionRequire'];loc=d.get('workCityName') or ' / '.join(x.get('workCityName','') for x in d.get('workCityVOList') or []);url=entry+'/'+str(ident)+'?id='+str(ident)
                cohort=d.get('projectName','');basis=f'Official recruitmentType={row.get("recruitmentType")}, project={cohort}'
            else:
                title=d['name'];desc=d['description'];req=d['positionDemand'];loc=' / '.join(x['name'] for x in d.get('workLocationDicts') or []);url=host+'/recruit/campus/e/#/campus/job-info/'+str(ident)
                cohort='';basis=f'Official recruitProjectCode={d.get("recruitProjectCode")}; positionNatureCode={d.get("positionNatureCode")}'
            if not desc and not req:raise ValueError(f'Missing official description {ident}')
            desc=desc or '';req=req or ''
            j=job(company,scope,ident,title,url,desc+'\n任职要求\n'+req,loc,d)
            j['cohort_raw']=cohort;j['scope_evidence']=basis;j['education_raw']=d.get('education') or '';j['major_requirements_raw']=''
            return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            for j in pool.map(enrich,rows_all):
                if j is not None:jobs.append(j)
        c['expected_total']=len(jobs);c['detail_complete']=True;c['evidence']=[p.name for p in output_dir.glob('list-*.json')];c['scope_evidence']=f'Official {company} list; requested scope={scope}'
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def enrich_dji_campaign(result,output_dir):
    ident='093114fd-38fa-497b-ac5a-8a8f47777708'
    target=next((j for j in result['jobs'] if j['source_record_id']==ident),None)
    if target is None:return
    url='https://careers.dji.com/zh-CN/campus/digital-recruitment'
    r=requests.get(url,timeout=(10,30));r.raise_for_status();r.encoding='utf-8';page=r.text
    (output_dir/'campaign-digital.html').write_text(page)
    scripts=re.findall(r'<script[^>]+src="([^"]+)',page)
    app=next((u for u in scripts if '/pages/_app-' in u),None)
    if not app:raise ValueError('DJI campaign app binding missing')
    rr=requests.get(app,timeout=(10,30));rr.raise_for_status();(output_dir/'campaign-app.js').write_text(rr.text)
    if ident not in rr.text:raise ValueError('DJI campaign no longer binds verified job ID')
    meta=re.search(r'<meta name="description" content="([^"]+)"',page)
    actual=html.unescape(meta.group(1)) if meta else ''
    if not re.search(r'面向\s*2027\s*届及优秀\s*2026\s*届高校毕业生',actual):raise ValueError('DJI campaign cohort condition changed')
    target['campaign_cohort_raw']=actual[actual.index('面向'):]
    target['campaign_url']=url
    result['coverage'].setdefault('evidence_files',[]).extend(['campaign-digital.html','campaign-app.js'])

def collect(company:str,scope:str,output_dir:Path)->dict:
    requested_company=company
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    company=next((k for k,v in COMPANIES.items() if company==v),company)
    if scope not in TYPES:raise ValueError('Unknown recruitment scope')
    if company=='pdd':result=collect_pdd(scope,output_dir)
    elif company in ('xiaohongshu','kuaishou','oppo'):result=collect_standard(company,scope,output_dir)
    elif company=='catl':
        sites=[('https://talent.catl.com/'+kind+'-recruitment/catlhr/'+str(site),'Official talent.catl.com portal link') for kind,site in [('campus',148948),('campus',143035),('campus',142992),('social',96144),('social',142774),('social',98098)]]
        result=collect_moka_sites(company,scope,sites,output_dir)
    elif company=='dji':
        sites=[('https://apply.careers.dji.com/campus-recruitment/dji/143359','Official campus link'),('https://apply.careers.dji.com/social-recruitment/dji/168240','Official internship link'),('https://apply.careers.dji.com/social-recruitment/dji/170070','Official social link')]
        result=collect_moka_sites(company,scope,sites,output_dir)
    else:
        c=coverage('');c['errors']=['Adapter discovery in progress'];result=finish([],c)
    result['coverage']['evidence_files']=[p.name for p in output_dir.glob('*list*.json')]
    result['coverage']['scope_request']={'company':requested_company,'scope':scope,'source_url':result['coverage']['source_url'],'params':{'recruitType':scope,'pageNum':1,'pageSize':50} if company=='xiaohongshu' else {'endpoint':'api/recruit/position/train/list' if scope=='intern' else 'api/recruit/position/list','page':1,'pageSize':20} if company=='pdd' else {'orgId':company,'siteId':[143359,168240,170070],'limit':50,'offset':0,'needStat':True,'local_scope_filter':scope} if company=='dji' else {'orgId':'catlhr','siteId':[148948,143035,142992,96144,142774,98098],'limit':50,'offset':0,'needStat':True,'local_scope_filter':scope} if company=='catl' else {'pageNum':1,'pageSize':50,'local_scope_filter':scope}}
    if company=='dji' and scope=='campus':
        try:enrich_dji_campaign(result,output_dir)
        except Exception as exc:result['coverage'].setdefault('warnings',[]).append(str(exc))
    (output_dir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('company');p.add_argument('scope',choices=TYPES);p.add_argument('output_dir');a=p.parse_args()
    result=collect(a.company,a.scope,Path(a.output_dir));print(json.dumps(result['coverage'],ensure_ascii=False))
