"""Public official recruitment collectors; no production writes."""
from __future__ import annotations
import base64, html, json, re, time, os, hashlib
from datetime import datetime, timezone
from pathlib import Path
import requests

def make_session():
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session=requests.Session()
    retry=Retry(total=2,connect=2,read=2,status=2,backoff_factor=1,allowed_methods={'GET','POST'},status_forcelist=[429,502,503,504],respect_retry_after_header=True)
    session.mount('https://',HTTPAdapter(max_retries=retry));return session

def http_get(url,**kwargs):
    with make_session() as session:return session.get(url,**kwargs)

def http_post(url,**kwargs):
    with make_session() as session:return session.post(url,**kwargs)

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
    if d.get('success') is False or d.get('code',0) not in (0,'0',None): raise ValueError(str(d)[:400])
    return d.get('result',d.get('data',d))

def job(company,scope,ident,title,url,description,location='',raw=None):
    record={'id':f'p1:{company}:{ident}','source_record_id':str(ident),'title':title,'job_title':title,'education_raw':'','major_requirements_raw':'','cohort_raw':'','reviewed_at':datetime.now(timezone.utc).isoformat(),'company':COMPANIES.get(company,company),'company_name':COMPANIES.get(company,company),'company_slug':company,'unit':COMPANIES.get(company,company),'recruitment_unit':COMPANIES.get(company,company),'recruitment_type':TYPES[scope],'source_url':url,'detail_url':url,'application_url':url,'description_raw':text(description),'location':location,'city':location,'cities':[x.strip() for x in re.split(r'\s*/\s*|[，,、;；]',location) if x.strip()],'source':'official_career','verified_at':datetime.now(timezone.utc).isoformat(),'source_fields':{k:v for k,v in (raw or {}).items() if k in {'id','hireMode','commitment','education','degree','major','workExperience','graduationYear','recruitType','recruitmentType','projectName','publishedAt','releaseTime','deadline','endDate'} and len(str(v))<500}}
    fields=raw or {}
    record['education_raw']=text(fields.get('education') or fields.get('degree') or fields.get('Degree') or '')
    record['major_requirements_raw']=text(fields.get('major') or fields.get('majorRequirement') or '')
    record['experience_raw']=text(fields.get('experience') or fields.get('workExperience') or fields.get('YearsOfWorking') or '')
    record['deadline_raw']=text(fields.get('deadline') or fields.get('endDate') or '')
    explicit_requirements='\n'.join(text(fields.get(k)) for k in ('serveRequirement','positionRequire','qualification','positionDemand','Require','jobRequirements','workRequire','serviceCondition') if fields.get(k))
    if fields.get('positionInfoList'):explicit_requirements+='\n'+'\n'.join(text(x.get('jobRequirements')) for x in fields['positionInfoList'])
    if not explicit_requirements:
        sections=re.split(r'任职要求|岗位要求|任职资格|招聘要求|Qualifications|Requirements',record['description_raw'],flags=re.I)
        if len(sections)>1:explicit_requirements='\n'.join(sections[1:])
    if explicit_requirements:
        sentences=[x.strip() for x in re.split(r'[\n。；;]',explicit_requirements) if x.strip()]
        if not record['education_raw']:record['education_raw']='；'.join(x for x in sentences if re.search(r'本科|硕士|博士|大专|专科|学历|中专|高中|bachelor|master|ph\.?d',x,re.I))
        if not record['major_requirements_raw']:record['major_requirements_raw']='；'.join(x for x in sentences if re.search(r'专业|major|degree in',x,re.I))
        record['requirements_field_evidence']='Verbatim explicit requirements sentences or official structured field'
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
    c=coverage(entry);jobs=[];s=make_session()
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

def partial_checkpoint(jobs,c,company,scope,output_dir):
    if not jobs:return
    cc=dict(c);cc.update(status='partial',complete=False,detail_complete=False,collected_jobs=len(jobs),expected_total=None,unique_source_ids=len(jobs))
    cc['scope_evidence']=f'Official source scope={scope}; full scan still in progress'
    cc['evidence_files']=[p.name for p in output_dir.glob('*list*.json')]
    cc['scope_request']={'company':COMPANIES.get(company,company),'scope':scope,'source_url':c.get('source_url'),'params':{'local_scope_filter':scope}}
    temp=output_dir/'result.checkpoint.tmp';temp.write_text(json.dumps({'jobs':jobs,'coverage':cc},ensure_ascii=False));temp.replace(output_dir/'result.json')

def moka_detail_cached(company,scope,row,host,org,site,iv,output_dir):
    ident=row['id'];updated=row.get('updatedAt')
    fingerprint=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    configured=os.environ.get('QIUZHAO_P1_DETAIL_CACHE_ROOT')
    cache_root=(Path(configured)/company/scope if configured else output_dir.parent/'shared'/scope);cache_root.mkdir(parents=True,exist_ok=True)
    cache=cache_root/(hashlib.sha256((org+'|'+ident).encode()).hexdigest()+'.json')
    if updated and cache.exists():
        try:
            old=json.loads(cache.read_text());detail=old['detail'];digest=hashlib.sha256(json.dumps(detail,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            if old.get('source_updated_at')==updated and old.get('list_fingerprint')==fingerprint and old.get('detail_sha256')==digest and detail.get('id')==ident and detail.get('jobDescription'):
                return detail,old['detail_checked_at'],True
        except (ValueError,KeyError,TypeError):pass
    existing=output_dir/f'detail-{ident}.json'
    if updated and existing.exists():
        try:
            previous=json.loads(existing.read_text())
            keys=tuple(row)
            if previous.get('id')==ident and previous.get('jobDescription') and previous.get('updatedAt')==updated and all(k in previous and previous[k]==row[k] for k in keys):
                checked=datetime.fromtimestamp(existing.stat().st_mtime,timezone.utc).isoformat()
                return previous,checked,True
        except (ValueError,KeyError,TypeError):pass
    with make_session() as ss:detail=request_json(ss,host+'/api/outer/ats-apply/website/job',{'orgId':org,'siteId':int(site),'jobId':ident,'locale':'zh-CN'},iv)
    if detail.get('id')!=ident or not detail.get('jobDescription'):raise ValueError(f'Incomplete Moka detail {ident}')
    checked=datetime.now(timezone.utc).isoformat()
    if updated:
        payload={'source_updated_at':updated,'list_fingerprint':fingerprint,'detail':detail,'detail_checked_at':checked,'detail_sha256':hashlib.sha256(json.dumps(detail,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
        temp=cache.with_suffix('.tmp');temp.write_text(json.dumps(payload,ensure_ascii=False));temp.replace(cache)
    return detail,checked,False

def collect_moka_sites(company,scope,sites,output_dir):
    """Full official Moka pagination with three bounded concurrent detail reads."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    jobs=[];c=coverage(sites[0][0] if sites else '');seen=set();session=make_session()
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
                detail,detail_checked,cached=moka_detail_cached(company,scope,row,host,org,site,iv,output_dir)
                if detail.get('id')!=ident or not detail.get('jobDescription'):raise ValueError(f'Incomplete Moka detail {ident}')
                (output_dir/f'detail-{ident}.json').write_text(json.dumps(detail,ensure_ascii=False))
                url=site_url.split('#')[0].rstrip('/')+'#/job/'+ident
                loc=' / '.join(x.get('cityName') or x.get('provinceName') or x.get('country','') for x in detail.get('locations',[]))
                j=job(company,scope,ident,detail['title'],url,detail['jobDescription'],loc,detail)
                j['scope_evidence']=f'{basis}; hireMode={row.get("hireMode")}; commitment={row.get("commitment","")}; title={row.get("title","")}'
                j['recruitment_type_raw']={'hireMode':detail.get('hireMode'),'commitment':detail.get('commitment')}
                j['list_checked_at']=datetime.now(timezone.utc).isoformat();j['detail_checked_at']=detail_checked;j['detail_cache_reused']=cached
                if '校园大使' in detail['title'] and scope=='social':j['recruitment_type_conflict']='Official hireMode=1 (social), title names campus ambassador; retain source classification for review'
                project=detail.get('projectFolder') or {};settings=project.get('settings') or {}
                j['cohort_raw']='';j['campaign_cohort_raw']=text(settings.get('graduateDateLimit') or project.get('name') or '');j['campaign_scope']='project';j['campaign_url']=site_url
                return j
            with ThreadPoolExecutor(max_workers=3) as pool:
                tasks={pool.submit(enrich,row):row['id'] for row in selected}
                for future in as_completed(tasks):
                    try:
                        jobs.append(future.result())
                        if len(jobs)%100==0:partial_checkpoint(jobs,c,company,scope,output_dir)
                    except Exception as exc:c['errors'].append(f'detail {tasks[future]}: {exc}')
        c['pagination_exhausted']=True;c['detail_complete']=not c['errors'];c['expected_total']=len(seen)
        c['scope_evidence']=f'Official Moka hireMode 1 social/2 campus; internship commitment/title; requested={scope}'
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def collect_standard(company,scope,output_dir,social_site=False):
    output_dir.mkdir(parents=True,exist_ok=True)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if company=='xiaohongshu':
        host='https://job.xiaohongshu.com';entry=host+'/'+('campus/intern' if scope=='intern' else scope)+'/position'
        list_url=host+'/websiterecruit/position/pageQueryPosition';detail_url=host+'/websiterecruit/position/queryPositionDetail';idkey='positionId'
    elif company=='kuaishou':
        host='https://campus.kuaishou.cn';entry=host+'/recruit/campus/e/#/campus/jobs'
        list_url=host+'/recruit/campus/e/api/v1/open/positions/simple';detail_url=host+'/recruit/campus/e/api/v1/open/positions/find';idkey='id'
    elif company=='oppo' and (scope=='social' or social_site):
        host='https://career.oppo.com';entry=host+'/recruitment/post'
        list_url=host+'/ats-candidate-api/open-api/position/queryPositionList';detail_url=host+'/ats-candidate-api/open-api/position/queryPosition';idkey='positionId'
    else:
        host='https://careers.oppo.com';entry=host+'/campus/post'
        list_url=host+'/openapi/position/pageNew';detail_url=host+'/openapi/position/detail';idkey='idRecruitPosition'
    c=coverage(entry);jobs=[];rows_all=[];seen=set();s=make_session();s.headers['Tenant-Id']='1000';list_total=None
    if company=='kuaishou' and scope=='social':
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
                if company=='oppo':actual={'Intern':'intern','Graduate':'campus','doctor':'campus','SOCIAL-RECRUITMENT':'social','OFFEN-RECRUITMENT':'intern'}.get(row.get('recruitmentType') or row.get('recruitType'))
                elif company=='kuaishou':actual={('intern','schoolr'):'intern',('fulltime','schoolr'):'campus'}.get((row.get('positionNatureCode'),row.get('recruitProjectCode')))
                else:actual=scope
                if actual is None:raise ValueError('Unknown official recruitment type enum')
                if actual==scope:rows_all.append(row)
            if len(seen)==list_total and int(d.get('pages',0))==page:
                c['pagination_exhausted']=True;c['last_page_evidence']=f'page={page};official_pages={d.get("pages")};unique={len(seen)};total={list_total}';break
            time.sleep(.08)
        if len(seen)!=list_total:raise ValueError(f'List mismatch: {len(seen)} != {list_total}')
        c['list_total']=list_total;c['expected_total']=len(rows_all)
        def enrich(row):
            ident=row[idkey];params={'positionId':ident,'recruitType':scope} if company=='xiaohongshu' else {'positionId':ident} if company=='oppo' and (scope=='social' or social_site) else {'id':ident}
            r=http_get(detail_url,params=params,headers={'Tenant-Id':'1000'},timeout=(10,45));r.raise_for_status();envelope=r.json()
            if envelope.get('success') is False or envelope.get('code',0) not in (0,'0'):raise ValueError('Detail response rejected')
            d=envelope.get('result',envelope.get('data'));(output_dir/f'detail-{ident}.json').write_text(json.dumps(d,ensure_ascii=False))
            if d[idkey]!=ident:raise ValueError('Detail ID mismatch')
            if company=='xiaohongshu':
                actual={'school_recruit':'campus','intern_recruit':'intern','club_recruit':'social'}.get(d.get('recruitType'))
                if actual is None:raise ValueError('Unknown XHS detail recruitType')
                if actual!=scope:return None
                title=d['positionName'];desc=d['duty'];req=d['qualification'];loc=d.get('workplace','');url=entry+'/'+str(ident)
                cohort=d.get('projectName','');basis=f'Official API recruitType={scope}; detail.recruitType={d.get("recruitType")}'
            elif company=='oppo' and (scope=='social' or social_site):
                title=d.get('publishName') or d['jobName'];desc=d.get('jobDuty');req=d.get('workRequire');loc=d.get('workCityName','');url=entry+'/'+str(ident)+'?id='+str(ident);cohort='';basis='Official recruitType='+str(d.get('recruitType'))
            elif company=='oppo':
                title=d['positionName'];desc=d['positionDesc'];req=d['positionRequire'];loc=d.get('workCityName') or ' / '.join(x.get('workCityName','') for x in d.get('workCityVOList') or []);url=entry+'/'+str(ident)+'?id='+str(ident)
                cohort=d.get('projectName','');basis=f'Official recruitmentType={row.get("recruitmentType")}, project={cohort}'
            else:
                title=d['name'];desc=d['description'];req=d['positionDemand'];loc=' / '.join(x['name'] for x in d.get('workLocationDicts') or []);url=host+'/recruit/campus/e/#/campus/job-info/'+str(ident)
                cohort='';basis=f'Official recruitProjectCode={d.get("recruitProjectCode")}; positionNatureCode={d.get("positionNatureCode")}'
            if not desc and not req:raise ValueError(f'Missing official description {ident}')
            desc=desc or '';req=req or ''
            j=job(company,scope,ident,title,url,desc+'\n任职要求\n'+req,loc,d)
            j['cohort_raw']='';j['campaign_cohort_raw']=cohort;j['campaign_scope']='project';j['campaign_url']=entry;j['scope_evidence']=basis;j['education_raw']=j['education_raw'] or text(d.get('education'))
            return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            for j in pool.map(enrich,rows_all):
                if j is not None:jobs.append(j)
        c['expected_total']=len(jobs);c['detail_complete']=True;c['evidence']=[p.name for p in output_dir.glob('list-*.json')];c['scope_evidence']=f'Official {company} list; requested scope={scope}'
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def collect_kuaishou_experienced(scope,output_dir):
    import hmac
    from urllib.parse import urlencode,quote_plus,urljoin
    from concurrent.futures import ThreadPoolExecutor,as_completed
    output_dir.mkdir(parents=True,exist_ok=True);entry='https://zhaopin.kuaishou.cn/recruit/e/';c=coverage(entry);jobs=[];session=make_session()
    try:
        home=session.get(entry,timeout=(10,30));home.raise_for_status();(output_dir/'official-entry.html').write_text(home.text)
        js_url=next(urljoin(entry,u) for u in re.findall(r'<script[^>]+src=["\']([^"\']+)',home.text) if '/js/main.' in u)
        js=session.get(js_url,timeout=(10,40));js.raise_for_status();(output_dir/'official-main.js').write_text(js.text)
        match=re.search(r'generateSign\)\([^,]+,"",[^,]+,"([^"]+)"\)',js.text)
        if not match:raise ValueError('Official public signature contract changed')
        public_constant=match.group(1)
        def read(path,params):
            canonical=urlencode(sorted(params.items()),quote_via=quote_plus,safe="~!*()'");stamp=str(int(time.time()*1000));sign=hmac.new(public_constant.encode(),(stamp+canonical+public_constant).encode(),hashlib.sha256).hexdigest()
            rr=http_get(entry+path,params=params,headers={'User-Agent':'Mozilla/5.0','Referer':entry,'sign':sign,'signTimestamp':stamp},timeout=(10,45));rr.raise_for_status();env=rr.json()
            if env.get('code')!=0:raise ValueError(str(env)[:300])
            return env.get('result')
        dictionary=read('api/v1/dictionary/positionNature',{});(output_dir/'scope-dictionary.json').write_text(json.dumps(dictionary,ensure_ascii=False))
        if not all(code in str(dictionary) for code in ['C001','C002']):raise ValueError('Official position nature dictionary changed')
        selected=[];seen=set();total=None
        for page in range(1,10001):
            d=read('api/v1/open/positions/simple',{'pageNum':page,'pageSize':50});(output_dir/f'list-{page}.json').write_text(json.dumps(d,ensure_ascii=False));c['pages_scanned']+=1
            rows=d['list'] or [];n=d['total']
            if total is not None and n!=total:raise ValueError('Kuaishou social total changed')
            total=n
            for row in rows:
                ident=row['id']
                if ident in seen:raise ValueError('Repeated Kuaishou social page ID')
                seen.add(ident);nature=row.get('positionNatureCode');project=row.get('recruitProjectCode')
                if project!='socialr' or nature not in ('C001','C002','C003'):raise ValueError(f'Unknown Kuaishou official type {project}/{nature}')
                actual='intern' if nature=='C002' else 'social'
                if actual==scope:selected.append(row)
            if not rows or d.get('isLastPage') is True or d.get('pages')==page:
                c['last_page_evidence']=f'page={page};official_pages={d.get("pages")};unique={len(seen)};total={total}';break
        if len(seen)!=total:raise ValueError('Kuaishou social incomplete list')
        c['expected_total']=len(selected);c['list_total']=total;c['pagination_exhausted']=True
        def enrich(row):
            ident=row['id'];d=read('api/v1/open/positions/find',{'id':ident});(output_dir/f'detail-{ident}.json').write_text(json.dumps(d,ensure_ascii=False))
            if d.get('id')!=ident or not (d.get('description') or d.get('positionDemand')):raise ValueError('Kuaishou detail invalid')
            if d.get('positionNatureCode')!=row.get('positionNatureCode'):raise ValueError('Kuaishou type changed between list and detail')
            url=entry+'#/official/'+('trainee' if scope=='intern' else 'social')+'/job-info/'+str(ident)
            loc=' / '.join(x.get('name','') for x in d.get('workLocationDicts') or [])
            j=job('kuaishou',scope,ident,d['name'],url,str(d.get('description') or '')+'\n任职要求\n'+str(d.get('positionDemand') or ''),loc,d)
            j['scope_evidence']='Official positionNature dictionary: C001 Full time, C002 Internship, C003 Part time; socialr/'+str(d.get('positionNatureCode'))
            j['recruitment_type_raw']={'recruitProjectCode':d.get('recruitProjectCode'),'positionNatureCode':d.get('positionNatureCode')};return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            tasks={pool.submit(enrich,row):row['id'] for row in selected}
            for f in as_completed(tasks):
                try:
                    jobs.append(f.result())
                    if len(jobs)%100==0:partial_checkpoint(jobs,c,'kuaishou',scope,output_dir)
                except Exception as exc:c['errors'].append(f'detail {tasks[f]}: {exc}')
        c['detail_complete']=len(jobs)==len(selected);c['evidence']=['official-entry.html','official-main.js','scope-dictionary.json']+[p.name for p in output_dir.glob('list-*.json')];c['evidence_files']=c['evidence'];c['scope_evidence']='Official position nature dictionary'
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def collect_kuaishou_intern(output_dir):
    results=[]
    for name,collector in [('campus-site',lambda d:collect_standard('kuaishou','intern',d)),('social-site',lambda d:collect_kuaishou_experienced('intern',d))]:
        folder=output_dir/name;folder.mkdir(parents=True,exist_ok=True);results.append((name,collector(folder)))
    jobs=[];seen=set();c=coverage('https://campus.kuaishou.cn/recruit/campus/e/')
    for name,r in results:
        for j in r['jobs']:
            if j['source_record_id'] not in seen:jobs.append(j);seen.add(j['source_record_id'])
        c['errors'].extend(r['coverage']['errors']);c['pages_scanned']+=r['coverage']['pages_scanned'];c['evidence'].extend(name+'/'+str(e) for e in r['coverage'].get('evidence',[]))
    c['expected_total']=len(jobs);c['pagination_exhausted']=all(r['coverage'].get('pagination_exhausted') for _,r in results);c['detail_complete']=all(r['coverage'].get('detail_complete') for _,r in results);c['last_page_evidence']=';'.join(r['coverage'].get('last_page_evidence','') for _,r in results);c['evidence_files']=c['evidence']
    return finish(jobs,c)

def collect_oppo_intern(output_dir):
    results=[]
    for name,social in [('campus-site',False),('social-site',True)]:
        results.append((name,collect_standard('oppo','intern',output_dir/name,social_site=social)))
    c=coverage('https://careers.oppo.com/campus/post');jobs=[];seen=set()
    for name,r in results:
        for j in r['jobs']:
            if j['source_record_id'] not in seen:jobs.append(j);seen.add(j['source_record_id'])
        c['errors'].extend(r['coverage']['errors']);c['pages_scanned']+=r['coverage']['pages_scanned'];c['evidence'].extend(name+'/'+str(e) for e in r['coverage'].get('evidence',[]))
    c['expected_total']=len(jobs);c['pagination_exhausted']=all(r['coverage'].get('pagination_exhausted') for _,r in results);c['detail_complete']=all(r['coverage'].get('detail_complete') for _,r in results);c['last_page_evidence']=';'.join(r['coverage'].get('last_page_evidence','') for _,r in results);c['evidence_files']=c['evidence']
    return finish(jobs,c)

def collect_vivo_byd(company,scope,output_dir):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    jobs=[];session=make_session();session.headers['lang']='zh_CN'
    entry='https://hr-campus.vivo.com' if company=='vivo' else 'https://job.byd.com/portal/pc/#/school/schoolPositionList'
    c=coverage(entry)
    if scope=='social':c['errors']=['Separate social source discovery pending'];return finish(jobs,c)
    try:
        if company=='vivo':configs=[{'PortalId':'903cbcbf-4898-46e1-817c-da522a9752b1'}]
        else:
            rr=session.get('https://job.byd.com/portal/api/portal-api/postEntryConfig/list',timeout=(10,30));rr.raise_for_status();env=rr.json()
            if env.get('code')!=0:raise ValueError(str(env)[:300])
            (output_dir/'source-config.json').write_text(json.dumps(env,ensure_ascii=False));configs=[];topics=set()
            for x in env['data']:
                actual={'008501':'campus','008502':'intern'}.get(x.get('campusNature'))
                if actual is None:raise ValueError('Unknown BYD official campusNature')
                if x.get('status')=='00111' and actual==scope and x['schoolTopic'] not in topics:configs.append(x);topics.add(x['schoolTopic'])
            if not configs:raise ValueError('No verified active BYD scope configuration')
        selected=[];global_ids=set()
        for ci,cfg in enumerate(configs):
            total=None;seen=set()
            for page in range(1,10001):
                if company=='vivo':
                    body={**cfg,'PageIndex':page-1,'PageSize':50,'KeyWords':'','SpecialType':0,'DisplayFields':['Category','LocNames','Degree','Kind','Duty','Require']}
                    url=entry+'/api/Jobad/GetJobAdPageList'
                else:
                    body={'topicCode':cfg['schoolTopic'],'batch':cfg['batch'],'campusNature':cfg['campusNature'],'pageSize':50,'pageIndex':page};url='https://job.byd.com/portal/api/portal-api/schoolPortal/queryPositionList'
                rr=session.post(url,json=body,timeout=(10,40));rr.raise_for_status();env=rr.json();(output_dir/f'{ci}-list-{page}.json').write_text(json.dumps(env,ensure_ascii=False));c['pages_scanned']+=1
                if company=='vivo':
                    if env.get('Code')!=200:raise ValueError(str(env)[:300])
                    rows=env['Data'] or [];n=env['Count']
                else:
                    if env.get('code')!=0:raise ValueError(str(env)[:300])
                    rows=env['data'] or [];n=env['page']['totalCount']
                if not rows and total is not None and len(seen)==total:c['last_page_evidence']=f'config={ci};page={page};rows=0;prior_total={total};terminal_total={n}';break
                if total is not None and total!=n:raise ValueError('List total changed')
                total=n
                if not rows:c['last_page_evidence']=f'config={ci};page={page};rows=0;total={total}';break
                for row in rows:
                    ident=row['Id'] if company=='vivo' else row['id']
                    if ident in seen:raise ValueError('Repeated page IDs')
                    seen.add(ident)
                    actual={'2':'campus','3':'intern'}.get(str(row.get('CategoryId'))) if company=='vivo' else {'008501':'campus','008502':'intern'}.get(row.get('campusNature'))
                    if actual is None:raise ValueError('Unknown official scope enum')
                    if actual==scope and ident not in global_ids:selected.append((row,cfg));global_ids.add(ident)
                if company=='byd' and len(seen)==total and env['page'].get('totalPage')==page:
                    c['last_page_evidence']=f'config={ci};page={page};official_pages={page};unique={len(seen)};total={total}';break
            if total!=len(seen):raise ValueError(f'Incomplete list {len(seen)} != {total}')
        c['expected_total']=len(selected);c['pagination_exhausted']=True
        def enrich(pair):
            row,cfg=pair;ident=row['Id'] if company=='vivo' else row['id']
            if company=='vivo':url=entry+'/api/JobAd/GetJobAdInfo';params={'jobAdId':ident,'portalId':cfg['PortalId'],'displayFields':'["LocNames","Degree","Kind","Category","Duty","Require"]'}
            else:url='https://job.byd.com/portal/api/portal-api/schoolPortal/queryPosition';params={'id':ident}
            rr=http_get(url,params=params,headers={'lang':'zh_CN'},timeout=(10,40));rr.raise_for_status();env=rr.json();(output_dir/f'detail-{ident}.json').write_text(json.dumps(env,ensure_ascii=False))
            if company=='vivo':
                if env.get('Code')!=200:raise ValueError(str(env)[:200])
                d=env['Data'];title=d['JobAdName'];desc=d.get('Duty','');req=d.get('Require','');loc=' / '.join(d.get('LocNames') or []);link=entry+'/'+scope+'/detail?jobAdId='+ident
                if d['Id']!=ident:raise ValueError('Detail ID mismatch')
                cohort='';basis=f'Official CategoryId={row.get("CategoryId")}, Category={row.get("Category")}'
            else:
                if env.get('code')!=0:raise ValueError(str(env)[:200])
                d=env['data']
                if str(d.get('id'))!=str(ident):raise ValueError('BYD detail ID mismatch')
                title=d.get('jobName') or row['jobName'];parts=d.get('positionInfoList') or []
                desc='\n\n'.join('部门：'+str(x.get('division',''))+'；方向：'+str(x.get('researchDirection',''))+'；地点：'+str(x.get('workPlace',''))+'\n'+str(x.get('jobDuty','')) for x in parts)
                req='\n\n'.join('部门：'+str(x.get('division',''))+'\n'+str(x.get('jobRequirements','')) for x in parts);loc=d.get('workPlace') or row.get('workPlace','');link='https://job.byd.com/portal/pc/#/school/schoolPositionDetail?id='+ident
                cohort=str(row.get('batch',''))+'届';basis=f'Official campusNature={row.get("campusNature")}; source entry={cfg.get("postEntryName")}'
            if not desc and not req:raise ValueError('No full official description '+str(list(d)))
            j=job(company,scope,ident,title,link,(desc or '')+'\n任职要求\n'+(req or ''),loc,d);j['cohort_raw']='';j['scope_evidence']=basis
            if company=='byd':j['campaign_cohort_raw']=cohort+'；'+str(cfg.get('content') or '');j['campaign_scope']='project';j['campaign_url']=entry;j['batch_raw']=row.get('batch')
            return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            tasks={pool.submit(enrich,row):row[0].get('Id',row[0].get('id')) for row in selected}
            for future in as_completed(tasks):
                try:jobs.append(future.result())
                except Exception as exc:c['errors'].append(f'detail {tasks[future]}: {exc}')
        c['detail_complete']=len(jobs)==len(selected);c['evidence']=[p.name for p in output_dir.glob('*list*.json')];c['scope_evidence']=f'Official {company} scope enumeration {scope}'
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def collect_vivo_byd_social(company,output_dir):
    from concurrent.futures import ThreadPoolExecutor,as_completed
    host='https://career.vivo.com' if company=='vivo' else 'https://job.byd.com'
    entry=host+'/jobs' if company=='vivo' else host+'/portal/pc/#/social/socialMainPageSocial'
    c=coverage(entry);jobs=[];selected=[];seen_all=set();session=make_session();session.headers['lang']='zh_CN'
    try:
        for channel in ([None] if company=='vivo' else ['00251','00254']):
            seen=set();total=None
            for page in range(1,10001):
                if company=='vivo':
                    body={'city_code_list':[],'company_id':1,'group_id':1,'user_id':None,'job_category_id_list':[],'keyword':'','max_results':30,'page':page,'yoe_list':[]};url=host+'/api/social/webSite/portal/page'
                else:
                    body={'positionTypeArr':[],'positionProvinceArr':[],'positionCityArr':[],'positionOrgArr':[],'vagueCondition':'','searchType':1,'zpType':channel,'pageNum':(page-1)*50,'pageSize':50};url=host+'/portal/api/portal-api/position/queryList'
                rr=session.post(url,json=body,timeout=(10,45));rr.raise_for_status();env=rr.json();(output_dir/f'{channel}-list-{page}.json').write_text(json.dumps(env,ensure_ascii=False));c['pages_scanned']+=1
                if env.get('code')!=0:raise ValueError(str(env)[:300])
                rows=env['data'] if company=='vivo' else env['data']['data'];n=env['meta']['total'] if company=='vivo' else env['data']['total']
                if not rows and total is not None and len(seen)==total:c['last_page_evidence']=f'channel={channel};page={page};rows=0;prior_total={total};terminal_total={n}';break
                if total is not None and n!=total:raise ValueError('Total changed during scan')
                total=n
                if not rows:c['last_page_evidence']=f'channel={channel};page={page};rows=0;total={n}';break
                for row in rows:
                    ident=row['job_id'] if company=='vivo' else row['id']
                    if ident in seen:raise ValueError('Repeated list ID')
                    seen.add(ident)
                    if ident not in seen_all:selected.append((row,channel));seen_all.add(ident)
                time.sleep(.08)
            if len(seen)!=total:raise ValueError('List total mismatch')
        c['pagination_exhausted']=True;c['expected_total']=len(selected)
        def enrich(pair):
            row,channel=pair;ident=row['job_id'] if company=='vivo' else row['id']
            url=host+'/api/social/webSite/portal/job/detail' if company=='vivo' else host+'/portal/api/portal-api/position/queryDetail'
            body={'job_id':ident,'company_id':1,'group_id':1} if company=='vivo' else {'id':ident,'pageSize':1}
            rr=http_post(url,json=body,headers={'lang':'zh_CN'},timeout=(10,45));rr.raise_for_status();env=rr.json();(output_dir/f'detail-{ident}.json').write_text(json.dumps(env,ensure_ascii=False))
            if env.get('code')!=0:raise ValueError('Detail unsuccessful')
            d=env['data']
            if (d.get('job_id') if company=='vivo' else d.get('id'))!=ident:raise ValueError('Detail ID mismatch')
            if company=='vivo':
                title=d['job_title'];desc=d.get('job_desc','');loc=' / '.join(x.get('city','') for x in d.get('job_location_list',[]));link=host+'/job-detail?_irji='+ident
            else:
                title=d['positionName'];desc='\n\n'.join(str(x.get('name',''))+'\n'+str(x.get('detail','')) for x in d.get('tagDetailList') or []);loc=d.get('city','');link=host+'/portal/pc/#/social/socialPositionDetails?id='+ident
            if not desc:raise ValueError('Missing official full description')
            j=job(company,'social',ident,title,link,desc,loc,d);j['scope_evidence']='Official social portal' if company=='vivo' else f'Official social/technician channel zpType={channel}'
            if company=='vivo':j['education_raw']=d.get('degree_range_name') or '';j['experience_raw']=f'yoe_min={d.get("yoe_min")};yoe_max={d.get("yoe_max")}'
            return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            tasks={pool.submit(enrich,x):x[0].get('job_id',x[0].get('id')) for x in selected}
            for f in as_completed(tasks):
                try:jobs.append(f.result())
                except Exception as exc:c['errors'].append(f'detail {tasks[f]}: {exc}')
        c['detail_complete']=len(jobs)==len(selected);c['evidence']=[p.name for p in output_dir.glob('*list*.json')];c['scope_evidence']='Official social recruitment listing'
    except Exception as exc:c['errors'].append(str(exc))
    return finish(jobs,c)

def collect_honor(scope,output_dir):
    from concurrent.futures import ThreadPoolExecutor,as_completed
    suites={'campus':['SU60eea919bef57c1023f6fe78','SU60eea1aa0dcad47a7e1ce1ed'],'intern':['SU61b9b9992f9d24431f5050a5'],'social':['SU5ff669649b0d78e6f4296c9a']}[scope]
    kind={'campus':1,'intern':12,'social':2}[scope];page_name={'campus':'school','intern':'interns','social':'social'}[scope]
    host='https://career.honor.com';c=coverage(host+'/'+suites[0]+'/pb/'+page_name+'.html');jobs=[];seen_global=set();session=make_session()
    try:
        for suite in suites:
            entry=host+'/'+suite+'/pb/'+page_name+'.html';r=session.get(entry,timeout=(10,25));r.raise_for_status();(output_dir/(suite+'-entry.html')).write_text(r.text)
            listed=set();selected=[];total=None;page_size=20
            for page in range(1,10001):
                body={'isFrompb':'true','recruitType':kind,'pageSize':page_size,'currentPage':page}
                rr=session.post(host+'/wecruit/positionInfo/listPosition/'+suite,data=body,headers={'Referer':entry},timeout=(10,40));rr.raise_for_status();env=rr.json();(output_dir/f'{suite}-list-{page}.json').write_text(json.dumps(env,ensure_ascii=False));c['pages_scanned']+=1
                if str(env.get('state'))!='200':raise ValueError(str(env)[:300])
                form=env['data']['pageForm'];rows=form['pageData'] or [];n=form['dataCount']
                if page==1 and form.get('pageSize'):page_size=int(form['pageSize'])
                if total is not None and n!=total:raise ValueError('Honor total changed')
                total=n
                for row in rows:
                    ident=row['postId']
                    if ident in listed:raise ValueError('Honor repeated pagination ID')
                    if row.get('recruitType')!=kind:raise ValueError('Honor scope conflict')
                    listed.add(ident)
                    if ident not in seen_global:selected.append(row);seen_global.add(ident)
                if not rows or form['currentPage']==form['totalPage']:
                    c['last_page_evidence']=f'suite={suite};page={page};official_pages={form["totalPage"]};unique={len(listed)};total={total}';break
            if len(listed)!=total:raise ValueError('Honor incomplete page count')
            def enrich(row):
                ident=row['postId'];rr=http_post(host+'/wecruit/positionInfo/listPositionDetail/'+suite,data={'postId':ident},headers={'Referer':entry},timeout=(10,40));rr.raise_for_status();env=rr.json();(output_dir/f'detail-{ident}.json').write_text(json.dumps(env,ensure_ascii=False))
                if str(env.get('state'))!='200':raise ValueError('Honor detail rejected')
                d=env['data']
                if d.get('postId')!=ident or d.get('recruitType')!=kind:raise ValueError('Honor detail identity/scope conflict')
                desc=d.get('workContent') or '';req=d.get('serviceCondition') or ''
                if not desc and not req:raise ValueError('Honor full description missing')
                j=job('honor',scope,ident,d['postName'],host+'/'+suite+'/pb/posDetail.html?postId='+ident,desc+'\n任职要求\n'+req,d.get('workPlaceStr') or '',d)
                j['campaign_cohort_raw']=d.get('projectName') or '';j['campaign_scope']='project';j['campaign_url']=entry;j['scope_evidence']=f'Official current HONOR portal recruitType={kind}'
                j['recruitment_unit']='荣耀 / '+str(d.get('orgName') or d.get('company') or '荣耀');return j
            with ThreadPoolExecutor(max_workers=3) as pool:
                tasks={pool.submit(enrich,row):row['postId'] for row in selected}
                for f in as_completed(tasks):
                    try:jobs.append(f.result())
                    except Exception as exc:c['errors'].append(f'detail {tasks[f]}: {exc}')
        c['expected_total']=len(seen_global);c['pagination_exhausted']=True;c['detail_complete']=len(jobs)==len(seen_global);c['evidence']=[p.name for p in output_dir.glob('*list*.json')];c['scope_evidence']=f'Official HONOR recruitType={kind}'
    except Exception as exc:c['errors'].append(str(exc))
    c['request_params']={'recruitType':kind,'currentPage':1,'pageSize':20,'sites':suites}
    return finish(jobs,c)

def collect_access_probe(company,scope,output_dir):
    session=make_session();session.headers['User-Agent']='Mozilla/5.0'
    if company=='pdd':
        entry='https://careers.pddglobalhr.com/jobs';url='https://careers.pddglobalhr.com/api/recruit/position/list';body={'job':'','page':1,'pageSize':10,'name':'','workLocationList':[]};method='post'
    elif company=='huawei':
        entry='https://career.huawei.com/reccampportal/portal5/campus-recruitment.html';url='https://career.huawei.com/reccampportal/services/portal/portalpub/getJob/newHr/page/20/1';body={'language':'zh_CN','jobType':'1' if scope=='social' else '0','jobTypes':'' if scope=='social' else '0' if scope=='intern' else '2','orderBy':'ISS_STARTDATE_DESC_AND_IS_HOT_JOB'};method='get';session.headers['x-jalor-tenantAlias']='hcm'
    elif company=='honor':
        entry='https://wecruit500.hotjob.cn/SU5fb249ec44e800c1fce8567a/pb/'+{'campus':'school','intern':'interns','social':'social'}[scope]+'.html';url='https://wecruit500.hotjob.cn/wecruit/positionInfo/listPosition/SU5fb249ec44e800c1fce8567a?iSaJAx=isAjax&request_locale=zh_CN';body={'isFrompb':'true','recruitType':{'campus':1,'intern':2,'social':0}[scope],'currentPage':1,'pageSize':20};method='form'
    elif company=='kuaishou':
        entry='https://zhaopin.kuaishou.cn/recruit/e/';url=entry+'api/v1/open/positions/simple';body={'pageNum':1,'pageSize':20};method='get'
    elif company=='oppo':
        entry='https://careers.oppo.com/';url=entry+'ats-candidate-api/open-api/position/queryPositionList';body={'pageNum':1,'pageSize':20};method='post';session.headers['Tenant-Id']='1000'
    else:raise ValueError('Unsupported probe')
    c=coverage(entry);c['request_params']=body;c['request_url']=url
    try:
        page=session.get(entry,timeout=(10,25));(output_dir/'official-entry.html').write_text(page.text)
        session.headers.update({'Referer':entry,'X-Requested-With':'XMLHttpRequest'})
        r=session.get(url,params=body,timeout=(10,30)) if method=='get' else session.post(url,data=body,timeout=(10,30)) if method=='form' else session.post(url,json=body,timeout=(10,30))
        (output_dir/'list-response.txt').write_text(r.text);c['pages_scanned']=1;c['evidence']=['official-entry.html','list-response.txt'];c['evidence_files']=c['evidence']
        try:response=r.json();summary=str(response)[:500]
        except ValueError:response={};summary=text(r.text)[:200]
        c['blocking_kind']='upstream_access' if r.status_code>=400 or response.get('success') is False or str(response.get('state',''))=='500' or response.get('code')==1 else 'adapter_discovery'
        c['errors']=[f'Official public endpoint HTTP {r.status_code}: {summary}; no verified complete job list']
        if company=='huawei' and r.status_code==200:c['blocking_kind']='adapter_discovery';c['errors'].append('Legacy list responds but current campus/intern/social project coverage and detail contract remain unverified; not an upstream access block')
    except Exception as exc:c['errors']=[str(exc)];c['blocking_kind']='upstream_access'
    return finish([],c)

def enrich_dji_campaign(result,output_dir):
    ident='093114fd-38fa-497b-ac5a-8a8f47777708'
    target=next((j for j in result['jobs'] if j['source_record_id']==ident),None)
    if target is None:return
    url='https://careers.dji.com/zh-CN/campus/digital-recruitment'
    r=http_get(url,timeout=(10,30));r.raise_for_status();r.encoding='utf-8';page=r.text
    (output_dir/'campaign-digital.html').write_text(page)
    scripts=re.findall(r'<script[^>]+src="([^"]+)',page)
    app=next((u for u in scripts if '/pages/_app-' in u),None)
    if not app:raise ValueError('DJI campaign app binding missing')
    rr=http_get(app,timeout=(10,30));rr.raise_for_status();(output_dir/'campaign-app.js').write_text(rr.text)
    if ident not in rr.text:raise ValueError('DJI campaign no longer binds verified job ID')
    meta=re.search(r'<meta name="description" content="([^"]+)"',page)
    actual=html.unescape(meta.group(1)) if meta else ''
    if not re.search(r'面向\s*2027\s*届及优秀\s*2026\s*届高校毕业生',actual):raise ValueError('DJI campaign cohort condition changed')
    target['campaign_cohort_raw']=actual[actual.index('面向'):]
    target['campaign_url']=url;target['campaign_scope']='job_specific';target['campaign_job_ids']=[ident]
    result['coverage'].setdefault('evidence_files',[]).extend(['campaign-digital.html','campaign-app.js'])

def collect(company:str,scope:str,output_dir:Path)->dict:
    requested_company=company
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    company=next((k for k,v in COMPANIES.items() if company==v),company)
    if scope not in TYPES:raise ValueError('Unknown recruitment scope')
    if company=='huawei' or scope=='social' and company=='pdd':result=collect_access_probe(company,scope,output_dir)
    elif company=='kuaishou' and scope=='social':result=collect_kuaishou_experienced(scope,output_dir)
    elif company=='kuaishou' and scope=='intern':result=collect_kuaishou_intern(output_dir)
    elif company=='honor':result=collect_honor(scope,output_dir)
    elif company=='pdd':result=collect_pdd(scope,output_dir)
    elif company in ('vivo','byd'):result=collect_vivo_byd_social(company,output_dir) if scope=='social' else collect_vivo_byd(company,scope,output_dir)
    elif company=='oppo' and scope=='intern':result=collect_oppo_intern(output_dir)
    elif company in ('xiaohongshu','kuaishou','oppo'):result=collect_standard(company,scope,output_dir)
    elif company=='catl':
        sites=[('https://talent.catl.com/'+kind+'-recruitment/catlhr/'+str(site),'Official talent.catl.com portal link') for kind,site in [('campus',148948),('campus',143035),('campus',142992),('social',96144),('social',142774),('social',98098)]]
        result=collect_moka_sites(company,scope,sites,output_dir)
    elif company=='dji':
        sites=[('https://apply.careers.dji.com/campus-recruitment/dji/143359','Official campus link'),('https://apply.careers.dji.com/social-recruitment/dji/168240','Official internship link'),('https://apply.careers.dji.com/social-recruitment/dji/170070','Official social link')]
        result=collect_moka_sites(company,scope,sites,output_dir)
    else:
        c=coverage('');c['errors']=['Adapter discovery in progress'];result=finish([],c)
    result['coverage']['evidence_files']=result['coverage'].get('evidence_files') or [p.name for p in output_dir.glob('*list*.json')]
    result['coverage']['scope_request']={'company':requested_company,'scope':scope,'source_url':result['coverage']['source_url'],'params':{'recruitType':scope,'pageNum':1,'pageSize':50} if company=='xiaohongshu' else {'endpoint':'api/recruit/position/train/list' if scope=='intern' else 'api/recruit/position/list','page':1,'pageSize':20} if company=='pdd' else {'orgId':company,'siteId':[143359,168240,170070],'limit':50,'offset':0,'needStat':True,'local_scope_filter':scope} if company=='dji' else {'orgId':'catlhr','siteId':[148948,143035,142992,96144,142774,98098],'limit':50,'offset':0,'needStat':True,'local_scope_filter':scope} if company=='catl' else {'pageNum':1,'pageSize':50,'local_scope_filter':scope}}
    if company=='vivo':
        result['coverage']['scope_request']['params']={'PortalId':'903cbcbf-4898-46e1-817c-da522a9752b1','PageIndex':0,'PageSize':50,'local_scope_filter':scope} if scope!='social' else {'company_id':1,'group_id':1,'max_results':30,'page':1}
    if company=='byd':
        cfg=output_dir/'source-config.json'
        result['coverage']['scope_request']['params']={'source_configs':json.loads(cfg.read_text())['data'],'pageSize':50,'pageIndex':1} if cfg.exists() else {'zpType':['00251','00254'],'pageNum':0,'pageSize':50}
    if result['coverage'].get('request_params') is not None:result['coverage']['scope_request']['params']=result['coverage']['request_params']
    if company=='dji' and scope=='campus':
        try:enrich_dji_campaign(result,output_dir)
        except Exception as exc:result['coverage'].setdefault('warnings',[]).append(str(exc))
    try:
        from qiuzhao.v4_fields import graduation_of
    except ModuleNotFoundError:
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]));from qiuzhao.v4_fields import graduation_of
    for row in result['jobs']:
        years,basis,_,_=graduation_of(row)
        row['graduation_years']=[y for y in years if re.fullmatch(r'20\d{2}届',y)]
        row['graduation_year_evidence']={y:basis[y] for y in row['graduation_years']}
        row['graduation_year_verification']='source_verified' if row['graduation_years'] and all(basis[y] in ('岗位写明','活动标题写明') for y in row['graduation_years']) else 'inferred' if row['graduation_years'] else 'unspecified'
    (output_dir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('company');p.add_argument('scope',choices=TYPES);p.add_argument('output_dir');a=p.parse_args()
    result=collect(a.company,a.scope,Path(a.output_dir));print(json.dumps(result['coverage'],ensure_ascii=False))
