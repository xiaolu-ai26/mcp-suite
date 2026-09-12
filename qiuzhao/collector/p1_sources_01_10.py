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
    return {'id':f'p1:{company}:{ident}','source_record_id':str(ident),'title':title,'job_title':title,'education_raw':'','major_requirements_raw':'','cohort_raw':'','reviewed_at':datetime.now(timezone.utc).isoformat(),'company':COMPANIES.get(company,company),'company_name':COMPANIES.get(company,company),'company_slug':company,'unit':COMPANIES.get(company,company),'recruitment_unit':COMPANIES.get(company,company),'recruitment_type':TYPES[scope],'source_url':url,'detail_url':url,'application_url':url,'description_raw':text(description),'location':location,'city':location,'source':'official_career','verified_at':datetime.now(timezone.utc).isoformat(),'source_fields':raw or {}}

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
    """Collect verified official Moka site URLs, full pagination and full details.

    sites is a sequence of (url, scope_basis); public response AES is decoded
    exactly as the official browser does, with key returned in that response.
    """
    jobs=[];c=coverage(sites[0][0] if sites else '');seen=set();s=requests.Session();all_done=True
    try:
        for site_url,basis in sites:
            m=re.search(r'/(?:campus|social)-recruitment/([^/]+)/(\d+)',site_url)
            if not m:raise ValueError('Unrecognized verified Moka URL')
            org,site=m.groups();host=site_url.split('/')[0]+'//'+site_url.split('/')[2]
            r=s.get(site_url,timeout=(10,45));r.raise_for_status();pagehtml=html.unescape(r.text)
            ivmatch=re.search(r'"aesIv"\s*:\s*"([^"]+)"',pagehtml);iv=ivmatch.group(1) if ivmatch else None
            listed=set();total=None;terminal=False
            for offset in range(0,200000,50):
                d=request_json(s,host+'/api/outer/ats-apply/website/jobs/v2',{'orgId':org,'siteId':int(site),'limit':50,'offset':offset,'needStat':True,'locale':'zh-CN'},iv)
                (output_dir/f'{site}-list-{offset}.json').write_text(json.dumps(d,ensure_ascii=False))
                c['pages_scanned']+=1;rows=d['jobs'];n=d.get('jobStats',{}).get('total')
                if total is not None and n!=total:raise ValueError('Moka total changed during scan')
                total=n
                if not rows:terminal=True;c['last_page_evidence']=f'site={site};offset={offset};rows=0;total={total}';break
                for row in rows:
                    ident=row['id']
                    if ident in listed:raise ValueError(f'Repeated Moka ID {ident}')
                    listed.add(ident)
                    commitment=str(row.get('commitment',''));mode=row.get('hireMode')
                    actual='intern' if '实习' in commitment or '实习' in row.get('title','') else 'campus' if mode==2 else 'social' if mode==1 else None
                    if actual!=scope:continue
                    if ident in seen:continue
                    detail=request_json(s,host+'/api/outer/ats-apply/website/job',{'orgId':org,'siteId':int(site),'jobId':ident,'locale':'zh-CN'},iv)
                    if detail.get('id')!=ident or not detail.get('jobDescription'):raise ValueError(f'Incomplete Moka detail {ident}')
                    (output_dir/f'detail-{ident}.json').write_text(json.dumps(detail,ensure_ascii=False))
                    url=site_url.split('#')[0].rstrip('/')+'#/job/'+ident
                    loc=' / '.join(x.get('cityName') or x.get('provinceName') or x.get('country','') for x in detail.get('locations',[]))
                    j=job(company,scope,ident,detail['title'],url,detail['jobDescription'],loc,detail)
                    j['scope_evidence']=f'{basis}; hireMode={mode}; commitment={commitment}; title={row.get("title","")}'
                    jobs.append(j);seen.add(ident)
                time.sleep(.08)
            if not terminal or total is not None and len(listed)!=total:raise ValueError(f'Incomplete list site={site}: observed={len(listed)}, total={total}')
            c['evidence'].extend(p.name for p in output_dir.glob(f'{site}-list-*.json'));c['scope_evidence']=f'Moka official hireMode=1 social, 2 campus; internship commitment/title; requested={scope}'
        c['pagination_exhausted']=all_done;c['detail_complete']=True;c['expected_total']=len(jobs)
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def collect_standard(company,scope,output_dir):
    from concurrent.futures import ThreadPoolExecutor
    if company=='xiaohongshu':
        host='https://job.xiaohongshu.com';entry=host+'/'+('intern' if scope=='intern' else scope)+'/position'
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
            rows=d.get('list',d.get('records'));total=int(d['total'])
            if list_total is not None and total!=list_total:raise ValueError('Total changed during scan')
            list_total=total
            if not rows:c['pagination_exhausted']=True;c['last_page_evidence']=f'page={page};rows=0;total={total}';break
            for row in rows:
                ident=row[idkey]
                if ident in seen:raise ValueError('Repeated pagination ID')
                seen.add(ident)
                if company=='oppo':actual='intern' if row.get('recruitmentType')=='Intern' else 'campus'
                elif company=='kuaishou':actual='intern' if row.get('positionNatureCode')!='fulltime' or row.get('recruitProjectCode')!='schoolr' else 'campus'
                else:actual=scope
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
                title=d['positionName'];desc=d['duty'];req=d['qualification'];loc=d.get('workplace','');url=entry+'/'+str(ident)
                cohort=d.get('projectName','');basis=f'Official API recruitType={scope}; detail.recruitType={d.get("recruitType")}'
            elif company=='oppo':
                title=d['positionName'];desc=d['positionDesc'];req=d['positionRequire'];loc=d.get('workCityName') or ' / '.join(x.get('workCityName','') for x in d.get('workCityVOList') or []);url=entry+'/'+str(ident)+'?id='+str(ident)
                cohort=d.get('projectName','');basis=f'Official recruitmentType={row.get("recruitmentType")}, project={cohort}'
            else:
                title=d['name'];desc=d['description'];req=d['positionDemand'];loc=' / '.join(x['name'] for x in d.get('workLocationDicts') or []);url=host+'/recruit/campus/e/#/campus/job-info/'+str(ident)
                cohort='';basis=f'Official recruitProjectCode={d.get("recruitProjectCode")}; positionNatureCode={d.get("positionNatureCode")}'
            if not desc or not req:raise ValueError(f'Missing full duties or requirements {ident}')
            j=job(company,scope,ident,title,url,desc+'\n任职要求\n'+req,loc)
            j['cohort_raw']=cohort;j['scope_evidence']=basis;j['education_raw']=d.get('education') or '';j['major_requirements_raw']=''
            return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            for j in pool.map(enrich,rows_all):jobs.append(j)
        c['detail_complete']=len(jobs)==len(rows_all);c['evidence']=[p.name for p in output_dir.glob('list-*.json')];c['scope_evidence']=f'Official {company} list; requested scope={scope}'
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def collect(company:str,scope:str,output_dir:Path)->dict:
    requested_company=company
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    company=next((k for k,v in COMPANIES.items() if company==v),company)
    if scope not in TYPES:raise ValueError('Unknown recruitment scope')
    if company=='pdd':result=collect_pdd(scope,output_dir)
    elif company in ('xiaohongshu','kuaishou','oppo'):result=collect_standard(company,scope,output_dir)
    elif company=='dji':
        sites=[('https://apply.careers.dji.com/campus-recruitment/dji/143359','Official campus link'),('https://apply.careers.dji.com/social-recruitment/dji/168240','Official internship link'),('https://apply.careers.dji.com/social-recruitment/dji/170070','Official social link')]
        result=collect_moka_sites(company,scope,sites,output_dir)
    else:
        c=coverage('');c['errors']=['Adapter discovery in progress'];result=finish([],c)
    result['coverage']['evidence_files']=[p.name for p in output_dir.glob('*list*.json')]
    result['coverage']['scope_request']={'company':requested_company,'scope':scope,'source_url':result['coverage']['source_url'],'params':{'recruitType':scope} if company=='xiaohongshu' else {'scope_filter':scope}}
    (output_dir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('company');p.add_argument('scope',choices=TYPES);p.add_argument('output_dir');a=p.parse_args()
    result=collect(a.company,a.scope,Path(a.output_dir));print(json.dumps(result['coverage'],ensure_ascii=False))
