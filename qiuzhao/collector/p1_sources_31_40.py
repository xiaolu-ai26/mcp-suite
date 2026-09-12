"""Official recruitment adapters for the ordered P1 company batch 31-40."""
from __future__ import annotations
import json,re,sys
from pathlib import Path
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor,as_completed
try:
    from . import p1_sources_01_10 as shared
except ImportError:
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

COMPANIES={'sensetime':'商汤科技','zte':'中兴通讯','dahua':'大华股份','inovance':'汇川技术','tplink':'TP-LINK普联','roborock':'石头科技','ecovacs':'科沃斯','lixiang':'理想汽车','xpeng':'小鹏汽车','nio':'蔚来汽车'}
BEISEN={'dahua':'https://dahua.zhiye.com','inovance':'https://inovance.zhiye.com','roborock':'https://roborock.zhiye.com'}
FIELDS=['LocId','Degree','Kind','OrgId','Category','PostDate','HeadCount','EndTime','YearsOfWorking','Duty','Require']

def collect_beisen(company,scope,host,output_dir,category_mapping=None):
    """Discover current PortalId; exhaust official pages and fetch every job GUID."""
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    name=COMPANIES.get(company,company);c=shared.coverage(host);jobs=[];session=shared.make_session();category={'social':'1','campus':'2','intern':'3'}[scope]
    categories={'1':'social','2':'campus','3':'intern'}
    if category_mapping:categories.update({str(k):v for k,v in category_mapping.items()})
    try:
        page=session.get(host,timeout=(10,30));page.raise_for_status();page.encoding='utf-8';(output_dir/'official-entry.html').write_text(page.text)
        ids=set(re.findall(r'"PortalId"\s*:\s*"([^"]+)"',page.text))
        if len(ids)!=1:raise ValueError('Official Beisen PortalId missing or ambiguous')
        portal=ids.pop();host=urlsplit(page.url).scheme+'://'+urlsplit(page.url).netloc;c['source_url']=host
        selected=[];seen=set();total=None
        for index in range(10000):
            body={'PortalId':portal,'PageIndex':index,'PageSize':50,'Category':[],'KeyWords':'','SpecialType':0,'DisplayFields':FIELDS}
            rr=session.post(host+'/api/Jobad/GetJobAdPageList',json=body,timeout=(10,45));rr.raise_for_status();env=rr.json();(output_dir/f'list-{index}.json').write_text(json.dumps(env,ensure_ascii=False));c['pages_scanned']+=1
            if env.get('Code')!=200:raise ValueError(str(env)[:300])
            rows=env.get('Data') or [];count=env['Count']
            if not rows and total is not None and len(seen)==total:c['last_page_evidence']=f'index={index};rows=0;prior_total={total};terminal_count={count}';break
            if total is not None and count!=total:raise ValueError('Official count changed during scan')
            total=count
            if not rows:c['last_page_evidence']=f'index={index};rows=0;count={count}';break
            for row in rows:
                ident=row['Id']
                if ident in seen:raise ValueError('Repeated Beisen pagination GUID')
                seen.add(ident);actual=str(row.get('CategoryId'))
                if actual not in categories:
                    c['errors'].append('Unknown official Beisen category '+actual+': '+str(row.get('Category')));continue
                if categories[actual]==scope:selected.append(row)
        if len(seen)!=total:raise ValueError(f'Incomplete list: {len(seen)} vs {total}')
        c['list_total']=total;c['expected_total']=len(selected);c['pagination_exhausted']=True
        def detail(row):
            ident=row['Id'];params={'jobAdId':ident,'portalId':portal,'category':str(row.get('CategoryId')),'displayFields':json.dumps(FIELDS)}
            rr=shared.http_get(host+'/api/JobAd/GetJobAdInfo',params=params,timeout=(10,45));rr.raise_for_status();env=rr.json();(output_dir/f'detail-{ident}.json').write_text(json.dumps(env,ensure_ascii=False))
            if env.get('Code')!=200:raise ValueError(str(env)[:300])
            d=env['Data']
            if d.get('Id')!=ident or str(d.get('CategoryId'))!=str(row.get('CategoryId')) or categories.get(str(d.get('CategoryId')))!=scope:raise ValueError('Beisen detail identity/category mismatch')
            duty=d.get('Duty') or '';requirements=d.get('Require') or ''
            if not duty and not requirements:raise ValueError('Official detail has no description')
            locations=d.get('LocNames') or [];loc=' / '.join(str(x) for x in locations)
            j=shared.job(name,scope,ident,d['JobAdName'],host+'/'+scope+'/detail?jobAdId='+ident,duty+'\n任职要求\n'+requirements,loc,d)
            j['recruitment_type_raw']={'CategoryId':d.get('CategoryId'),'Category':d.get('Category')};j['scope_evidence']=f'Official Beisen CategoryId={d.get("CategoryId")}; Category={d.get("Category")}; verified mapping={categories}'
            j['publication_date']=d.get('PostDate') if not str(d.get('PostDate','')).startswith('0001') else ''
            j['source_updated_at']=d.get('ChangeDate') or '';j['deadline_raw']=d.get('EndTime') if not str(d.get('EndTime','')).startswith('0001') else ''
            return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(detail,row):row['Id'] for row in selected}
            for f in as_completed(futures):
                try:
                    jobs.append(f.result())
                    if len(jobs)%100==0:shared.partial_checkpoint(jobs,c,name,scope,output_dir)
                except Exception as exc:c['errors'].append(f'detail {futures[f]}: {exc}')
        c['detail_complete']=len(jobs)==len(selected);c['evidence']=['official-entry.html']+[p.name for p in output_dir.glob('list-*.json')];c['evidence_files']=c['evidence'];c['scope_evidence']=f'Official all-category list; verified mapping={categories}; requested={scope}'
        c['scope_request']={'company':name,'scope':scope,'source_url':host,'params':body}
    except Exception as exc:c['errors'].append(str(exc))
    return shared.finish(jobs,c)

def collect_inovance(scope,out):
    host='https://recruit.inovance.com';c=shared.coverage(host+'/jobs');jobs=[];session=shared.make_session()
    try:
        page=session.get(host,timeout=(10,30));page.raise_for_status();page.encoding='utf-8';(out/'official-entry.html').write_text(page.text)
        assets=re.findall(r'<script[^>]+src="([^"]+)',page.text);bundle=next(u for u in assets if '/assets/index-' in u)
        js=session.get(bundle,timeout=(10,30));js.raise_for_status();request_name=re.search(r'(request-[^"`/ ]+\.js)',js.text).group(1);request_url=bundle.rsplit('/',1)[0]+'/'+request_name
        req_js=session.get(request_url,timeout=(10,30));req_js.raise_for_status();(out/'official-request.js').write_text(req_js.text)
        portal=re.search(r'X-Portal-Id`\]=`([^`]+)`',req_js.text)
        if not portal:raise ValueError('Current official X-Portal-Id contract changed')
        session.headers['X-Portal-Id']=portal.group(1);headers={'X-Portal-Id':portal.group(1)};selected=[];seen=set();total=None
        for page_no in range(1,10001):
            body={'pageNum':page_no,'pageSize':50,'keyword':'','sortBy':'recommended'};rr=session.post(host+'/prod-portal-api/position/ad/search',json=body,timeout=(10,40));rr.raise_for_status();env=rr.json();(out/f'list-{page_no}.json').write_text(json.dumps(env,ensure_ascii=False));c['pages_scanned']+=1
            if env.get('code')!=200:raise ValueError(str(env)[:300])
            d=env['data'];rows=d['records'];n=d['total']
            if total is not None and n!=total:raise ValueError('Inovance count changed')
            total=n
            for row in rows:
                ident=row['adId']
                if ident in seen:raise ValueError('Inovance repeated advertisement ID')
                seen.add(ident);kind=str(row.get('recruitType'));actual={'1':'campus','2':'social','5':'intern'}.get(kind)
                if actual is None:raise ValueError('Unclassified official Inovance recruitType='+kind)
                if actual==scope:selected.append(row)
            if d.get('hasMore') is False or not rows:c['last_page_evidence']=f'page={page_no};hasMore={d.get("hasMore")};unique={len(seen)};total={total}';break
        if len(seen)!=total:raise ValueError('Inovance incomplete list')
        c['expected_total']=len(selected);c['list_total']=total;c['pagination_exhausted']=True
        def detail(row):
            ident=row['adId'];rr=shared.http_get(host+'/prod-portal-api/position/ad/detail',params={'adId':ident},headers=headers,timeout=(10,40));rr.raise_for_status();env=rr.json();(out/f'detail-{ident}.json').write_text(json.dumps(env,ensure_ascii=False))
            if env.get('code')!=200:raise ValueError('Inovance detail failed')
            d=env['data']
            if d.get('adId')!=ident:raise ValueError('Inovance detail ID mismatch')
            desc=d.get('jobDescription') or '';req=d.get('jobRequirement') or ''
            if not desc and not req:raise ValueError('Inovance description missing')
            loc=' / '.join(x.get('name','') for x in d.get('workLocation') or row.get('workLocation') or [])
            j=shared.job('汇川技术',scope,ident,d.get('adJobName') or row['adJobName'],host+'/jobs/'+ident,desc+'\n任职要求\n'+req,loc,{**d,'qualification':req})
            j['education_raw']=d.get('degreeDesc') or row.get('degreeDesc') or j.get('education_raw');j['experience_raw']=d.get('yearsOfWorkingDesc') or row.get('yearsOfWorkingDesc') or '';j['scope_evidence']='Current official recruitType='+str(row['recruitType'])+' (1 campus, 2 social, 5 intern)';j['source_updated_at']=d.get('publishTime') or row.get('publishTime');return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(detail,row):row['adId'] for row in selected}
            for f in as_completed(futures):
                try:jobs.append(f.result())
                except Exception as exc:c['errors'].append(f'detail {futures[f]}: {exc}')
        c['detail_complete']=len(jobs)==len(selected);c['evidence']=['official-entry.html','official-request.js']+[p.name for p in out.glob('list-*.json')];c['evidence_files']=c['evidence'];c['scope_evidence']='Official current recruitType enum';c['scope_request']={'company':'汇川技术','scope':scope,'source_url':host,'params':{'pageNum':1,'pageSize':50,'sortBy':'recommended','local_recruitType':{'campus':'1','social':'2','intern':'5'}[scope]}}
    except Exception as exc:c['errors'].append(str(exc))
    return shared.finish(jobs,c)

def collect_lixiang(scope,out):
    host='https://api-web.lixiang.com';entry='https://www.lixiang.com/employ/campus/list.html';c=shared.coverage(entry);jobs=[];session=shared.make_session();selected=[];seen_all=set();totals={}
    def classify(row):
        mode=str(row.get('job_mode'));hire=row.get('hire_mode')
        if mode=='202' or row.get('job_mode_name')=='实习':return 'intern'
        if mode in ('101','201') and hire==2:return 'campus'
        if mode=='101' and hire==1:return 'social'
        return None
    try:
        for channel in ['school','social']:
            seen=set();total=None
            for page in range(1,10001):
                params={'page':page,'page_size':50};rr=session.get(host+'/osd-hr-recruitment-website/v1/recruit/'+channel+'/job-page',params=params,headers={'Referer':entry,'Origin':'https://www.lixiang.com'},timeout=(10,40));rr.raise_for_status();env=rr.json();(out/f'{channel}-list-{page}.json').write_text(json.dumps(env,ensure_ascii=False));c['pages_scanned']+=1
                if env.get('code')!=0:raise ValueError(str(env)[:300])
                d=env['data'];rows=d['items'];n=d['total_count']
                if total is not None and n!=total:raise ValueError('Li Auto count changed')
                total=n
                for row in rows:
                    ident=row['id']
                    if ident in seen:raise ValueError('Li Auto repeated pagination ID')
                    seen.add(ident);actual=classify(row)
                    if actual is None:c['errors'].append('Unknown Li Auto hire/job mode '+str(row.get('hire_mode'))+'/'+str(row.get('job_mode')));continue
                    if actual==scope and ident not in seen_all:selected.append(row);seen_all.add(ident)
                if not rows or d['page']==d['total_pages']:
                    c['last_page_evidence']=f'channel={channel};page={page};official_pages={d["total_pages"]};unique={len(seen)};total={total}';break
            if len(seen)!=total:raise ValueError('Li Auto incomplete list')
            totals[channel]=total
        c['list_totals']=totals;c['expected_total']=len(selected);c['pagination_exhausted']=True
        def detail(row):
            ident=row['id'];rr=shared.http_get(host+'/osd-hr-recruitment-website/v1/recruit/job/detail',params={'job_id':ident},headers={'Referer':entry},timeout=(10,40));rr.raise_for_status();env=rr.json();(out/f'detail-{ident}.json').write_text(json.dumps(env,ensure_ascii=False))
            if env.get('code')!=0:raise ValueError('Li Auto detail failed')
            d=env['data']
            if d.get('id')!=ident or classify(d)!=scope:raise ValueError('Li Auto detail identity/scope mismatch')
            description=d.get('description') or '';requirements=d.get('requirements') or ''
            if not shared.text(description) and not shared.text(requirements):raise ValueError('Li Auto has no real description')
            j=shared.job('理想汽车',scope,ident,d['title'],'https://www.lixiang.com/employ/detail/'+str(ident)+'.html',description+'\n任职要求\n'+requirements,d.get('location_title') or row.get('location_title') or '',{**d,'qualification':requirements})
            j['scope_evidence']=f'Official hire_mode={d.get("hire_mode")};job_mode={d.get("job_mode")};job_mode_name={d.get("job_mode_name")}';j['campaign_cohort_raw']=d.get('subject_name') or '';j['campaign_scope']='project';j['campaign_url']=entry;j['recruitment_unit']='理想汽车 / '+str(d.get('department_title') or '');return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(detail,row):row['id'] for row in selected}
            for f in as_completed(futures):
                try:
                    jobs.append(f.result())
                    if len(jobs)%100==0:shared.partial_checkpoint(jobs,c,'理想汽车',scope,out)
                except Exception as exc:c['errors'].append(f'detail {futures[f]}: {exc}')
        c['detail_complete']=len(jobs)==len(selected);c['evidence']=[p.name for p in out.glob('*list*.json')];c['evidence_files']=c['evidence'];c['scope_evidence']='Official school and social lists mapped by hire_mode and job_mode';c['scope_request']={'company':'理想汽车','scope':scope,'source_url':entry,'params':{'channels':['school','social'],'page':1,'page_size':50,'local_scope_filter':scope}}
    except Exception as exc:c['errors'].append(str(exc))
    return shared.finish(jobs,c)

def collect_ecovacs(scope,out):
    moka=out/'moka';moka.mkdir(parents=True,exist_ok=True)
    sites=[('https://app.mokahr.com/campus_apply/tineco/36092','Ecovacs official group links Tineco careers; current branded Tineco campus portal orgId=tineco'),('https://app.mokahr.com/campus_apply/ecovacs/36793','Current official branded campus portal; init-data org ecovacs siteId36793 type camp'),('https://app.mokahr.com/social-recruitment/ecovacs/102402','Linked by current hr.ecovacs.cn'),('https://app.mokahr.com/apply/ecovacs/36792','Linked by current hr.ecovacs.cn')]
    result=shared.collect_moka_sites('科沃斯',scope,sites,moka)
    for j in result['jobs']:
        if '/tineco/' in j['source_url']:j['recruitment_unit']='添可智能';j['recruiting_unit_raw']='添可智能';j['parent_unit_raw']='科沃斯'
    c=result['coverage'];c['evidence_files']=['moka/'+str(x) for x in c.get('evidence',[])];jobs=result['jobs']
    def page_data(url):
        rr=shared.http_get(url,timeout=(10,35));rr.raise_for_status();rr.encoding='utf-8';match=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',rr.text,re.S)
        if not match:raise ValueError('ECOVACS public Next data missing')
        return rr.text,json.loads(match[1])['props']['pageProps']['pageData']
    try:
        raw,data=page_data('https://www.ecovacs.com/global/careers/job-list');(out/'global-list.html').write_text(raw);rows=data['list'];meta=data['page_data']
        if meta['total_page']!=1 or meta['total_count']!=len(rows):raise ValueError('ECOVACS international list requires additional pagination')
        c['pages_scanned']+=1;c['evidence_files'].append('global-list.html')
        for row in rows:
            actual='intern' if shared.is_internship(row.get('type'),row.get('title')) else 'social'
            if actual!=scope:continue
            url='https://www.ecovacs.com/global/careers/job-detail?id='+str(row['id']);raw,d=page_data(url);(out/f'global-detail-{row["id"]}.html').write_text(raw);record=d['career']
            if record['title']!=row['title']:raise ValueError('ECOVACS international title mismatch')
            desc='\n'.join(shared.text(record.get(k)) for k in ['description','responsibility','mini_qualification','preferred_qualification'] if record.get(k))
            if not desc:raise ValueError('ECOVACS international description empty')
            j=shared.job('科沃斯',scope,'ecovacs-global:'+str(row['id']),record['title'],url,desc,record.get('work_place') or '',{'qualification':record.get('mini_qualification')});j['scope_evidence']='Official global career type='+str(row['type']);j['source_namespace']='ecovacs-global';jobs.append(j);c['evidence_files'].append(f'global-detail-{row["id"]}.html')
        c['expected_total']=len(jobs);c['detail_complete']=c.get('detail_complete') and not c['errors'];c['evidence']=list(c['evidence_files']);c['scope_request']={'company':'科沃斯','scope':scope,'source_url':'https://hr.ecovacs.cn','params':{'sites':[s[0] for s in sites],'global_list':'https://www.ecovacs.com/global/careers/job-list','local_scope_filter':scope}}
    except Exception as exc:c['errors'].append(str(exc));c['detail_complete']=False
    return shared.finish(jobs,c)

def collect_tplink(scope,out):
    host='https://hr.tp-link.com.cn';c=shared.coverage(host+'/'+{'campus':'jobList','social':'socialJobList','intern':'internship'}[scope]);jobs=[];session=shared.make_session()
    try:
        if scope=='intern':
            page=session.get(host+'/html/internship.html',timeout=(10,30));page.raise_for_status();(out/'official-entry.html').write_text(page.text)
            rr=session.get(host+'/api/v1/home/internshipdata',timeout=(10,30));rr.raise_for_status();data=rr.json();(out/'intern-list.json').write_text(json.dumps(data,ensure_ascii=False))
            if not isinstance(data.get('jobClasses'),list) or not isinstance(data.get('jobs'),list):raise ValueError('TP-LINK internship schema changed')
            class_ids={x['Id'] for x in data['jobClasses'] if not x.get('IsDeleted')};rows=[x for x in data['jobs'] if x.get('ClassId') in class_ids]
            c['scope_evidence']='Official internshipdata jobs joined to its published internship jobClasses';c['pages_scanned']=1;c['scope_class_ids']=sorted(class_ids);c['last_page_evidence']='Official unpaginated internshipdata includes complete jobClasses/jobs arrays'
        else:
            rows=[];seen=set();total=None;kind='jobsocial' if scope=='social' else 'job'
            for page in range(1,10001):
                body={'jobClassId':[],'jobDirectionIds':'0','keywords':'','limit':50,'page':page,'workPlaceId':0};rr=session.post(host+'/api/v1/'+kind+'/get',json=body,timeout=(10,35));rr.raise_for_status();env=rr.json();(out/f'list-{page}.json').write_text(json.dumps(env,ensure_ascii=False));c['pages_scanned']+=1
                if env.get('errorCode')!=0:raise ValueError(str(env)[:200])
                data=env['result'];items=data['jobs'];n=data['total']
                if not items and total is not None and len(seen)==total:c['last_page_evidence']=f'page={page};rows=0;prior_total={total};terminal_total={n}';break
                if total is not None and n!=total:raise ValueError('TP-LINK count changed')
                total=n
                if not items:c['last_page_evidence']=f'page={page};rows=0;total={total}';break
                for item in items:
                    if item['Id'] in seen:raise ValueError('TP-LINK repeated pagination ID')
                    seen.add(item['Id']);rows.append(item)
            if len(seen)!=total:raise ValueError('TP-LINK incomplete list')
            c['scope_evidence']='Official '+kind+' recruitment API / page '+c['source_url']
        c['pagination_exhausted']=True;c['expected_total']=len(rows)
        def detail(row):
            ident=row['Id'];kind='jobsocial/getbyid' if scope=='social' else 'job/detail'
            rr=shared.http_post(host+'/api/v1/'+kind,json={'id':ident,'firstJobId':0},timeout=(10,35));rr.raise_for_status();env=rr.json();(out/f'detail-{ident}.json').write_text(json.dumps(env,ensure_ascii=False))
            if env.get('errorCode')!=0:raise ValueError('TP-LINK detail failed')
            d=env['result']
            if d.get('name')!=row.get('JobName'):raise ValueError('TP-LINK detail title mismatch')
            if not d.get('duty') and not d.get('requirement'):raise ValueError('TP-LINK description missing')
            url=host+'/'+('socialJobDetail' if scope=='social' else 'jobDetail')+'/'+str(ident)
            raw={**row,'qualification':d.get('requirement')};j=shared.job('TP-LINK普联',scope,ident,d['name'],url,str(d.get('duty') or '')+'\n任职要求\n'+str(d.get('requirement') or ''),d.get('workplace') or row.get('JobAddress') or '',raw)
            j['campaign_cohort_raw']=row.get('Batch') or '';j['campaign_scope']='project';j['campaign_url']=c['source_url'];j['scope_evidence']=c['scope_evidence'];return j
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(detail,row):row['Id'] for row in rows}
            for f in as_completed(futures):
                try:jobs.append(f.result())
                except Exception as exc:c['errors'].append(f'detail {futures[f]}: {exc}')
        c['detail_complete']=len(jobs)==len(rows);c['evidence']=[p.name for p in out.glob('*list*.json')];c['evidence_files']=c['evidence'];c['scope_request']={'company':'TP-LINK普联','scope':scope,'source_url':c['source_url'],'params':{'page':1,'limit':50,'scope':scope,'intern_class_ids':c.get('scope_class_ids')}}
    except Exception as exc:c['errors'].append(str(exc))
    return shared.finish(jobs,c)

def collect_nio_workday(scope,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);host='https://nio.wd3.myworkdayjobs.com';api=host+'/wday/cxs/nio/NIO_Careers';c=shared.coverage('https://www.nio.io/careers/jobs');jobs=[];session=shared.make_session();seen=set();rows=[]
    try:
        rr=session.get(c['source_url'],timeout=(10,30));rr.raise_for_status();(out/'official-entry.html').write_text(rr.text)
        if 'nio.wd3.myworkdayjobs.com/NIO_Careers/' not in rr.text:raise ValueError('Current official NIO entry no longer links this Workday tenant')
        total=None
        for offset in range(0,100000,20):
            rr=session.post(api+'/jobs',json={'limit':20,'offset':offset,'appliedFacets':{},'searchText':''},timeout=(10,40));rr.raise_for_status();d=rr.json();(out/f'list-{offset}.json').write_text(json.dumps(d,ensure_ascii=False));c['pages_scanned']+=1
            if total is not None and total!=d['total']:raise ValueError('NIO Workday total changed')
            total=d['total'];items=d['jobPostings']
            for row in items:
                ident=row['externalPath']
                if ident in seen:raise ValueError('NIO Workday repeated posting path')
                seen.add(ident);rows.append(row)
            if len(seen)==total or not items:c['last_page_evidence']=f'offset={offset};rows={len(items)};total={total};unique={len(seen)}';break
        if len(seen)!=total:raise ValueError('NIO Workday incomplete full list')
        c['list_total']=total;c['pagination_exhausted']=True
        selected_count=0
        for row in rows:
            path=row['externalPath'];rr=session.get(api+path,timeout=(10,40));rr.raise_for_status();env=rr.json();d=env['jobPostingInfo'];ident=d['jobReqId'];(out/('detail-'+ident+'.json')).write_text(json.dumps(env,ensure_ascii=False))
            if ident not in path or d.get('jobPostingSiteId')!='NIO_Careers':raise ValueError('NIO Workday detail ID/site mismatch')
            actual='intern' if shared.is_internship(d.get('timeType'),d.get('title')) else 'social'
            if actual!=scope:continue
            selected_count+=1;body=d.get('jobDescription') or ''
            if not shared.text(body):c['errors'].append('NIO Workday undisclosed description '+ident);continue
            url=d.get('externalUrl')
            if not url or ident not in url:raise ValueError('NIO Workday application URL missing/mismatched')
            j=shared.job('蔚来汽车',scope,'workday:nio:NIO_Careers:'+ident,d['title'],url,body,d.get('location') or row.get('locationsText') or '',d)
            j.update(official_source_id=ident,source_namespace='workday:nio:NIO_Careers',scope_evidence='Official international Workday posting; explicit Intern/Internship role title mapped internship, other experienced roles social',publication_date=d.get('startDate'),country_raw=(d.get('country') or {}).get('descriptor'),recruitment_unit='NIO',source_time_type=d.get('timeType'))
            j['source_can_apply_raw']=d.get('canApply');j['source_posted_raw']=d.get('posted')
            if d.get('canApply') is False or d.get('posted') is False:j['status']='expired';j['source_is_active']=False;j['status_note']='Official Workday posting is not currently applicable/published.'
            jobs.append(j)
        c['expected_total']=selected_count;c['detail_complete']=len(jobs)==selected_count;c['scope_evidence']='NIO official global careers links verified Workday tenant; explicit role titles and full detail';c['evidence']=['official-entry.html']+[p.name for p in out.glob('list-*.json')];c['evidence_files']=c['evidence']+[p.name for p in out.glob('detail-*.json')];c['scope_request']={'company':'蔚来汽车','scope':scope,'source_url':c['source_url'],'params':{'tenant':'nio','site':'NIO_Careers','limit':20,'offset':0,'appliedFacets':{},'searchText':'','local_scope_filter':scope}}
    except Exception as exc:c['errors'].append(str(exc))
    return shared.finish(jobs,c)

def collect(company,scope,output_dir):
    requested=company
    if company in ('TP-LINK','TP-LINK／普联','TP-LINK/普联','普联'):company='tplink'
    company=next((key for key,name in COMPANIES.items() if name==company),company);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    if company in ('sensetime','xpeng','nio'):
        from .p1_feishu_public import collect_feishu
        if company=='sensetime':sites=[{'url':'https://hr-jobs.sensetime.com/exp/position/list','tenant_names':['商汤科技'],'portal_type':6},{'url':'https://hr-jobs.sensetime.com/edu/','tenant_names':['商汤科技'],'portal_type':6}]
        elif company=='xpeng':sites=[{'url':'https://xiaopeng.jobs.feishu.cn/index','tenant_names':['小鹏集团'],'portal_type':6},{'url':'https://xiaopeng.jobs.feishu.cn/campus','tenant_names':['小鹏集团'],'portal_type':6}]
        else:sites=[{'url':'https://nio.jobs.feishu.cn/'+path,'tenant_names':['NIO'],'portal_type':6} for path in ['campus','intern','index']]
        r=collect_feishu(COMPANIES[company],scope,sites,out)
        if company=='nio':
            import copy
            international=collect_nio_workday(scope,out/'workday');c=r['coverage'];wc=international['coverage'];c['source_coverage']=[copy.deepcopy(c),copy.deepcopy(wc)];r['jobs'].extend(international['jobs'])
            c['expected_total']=(c['expected_total']+wc['expected_total']) if isinstance(c.get('expected_total'),int) and isinstance(wc.get('expected_total'),int) else None
            c['pages_scanned']+=wc['pages_scanned'];c['errors'].extend(wc['errors']);c['evidence_files'].extend('workday/'+x for x in wc.get('evidence_files',[]));c['collected_jobs']=len(r['jobs']);c['unique_source_ids']=len({j['source_record_id'] for j in r['jobs']})
            c['company_scope_complete']=False;c['errors'].append('Official NIO global page additionally links LinkedIn roles and entries lacking application URLs; these sources remain under verification');c['complete']=False;c['status']='partial' if r['jobs'] else 'blocked'
    elif company=='ecovacs':r=collect_ecovacs(scope,out)
    elif company=='lixiang':r=collect_lixiang(scope,out)
    elif company=='inovance':r=collect_inovance(scope,out)
    elif company=='tplink':r=collect_tplink(scope,out)
    elif company in BEISEN:r=collect_beisen(company,scope,BEISEN[company],out)
    elif company=='zte':
        sites=[('https://app.mokahr.com/campus-recruitment/zte/46903','Linked by job.zte.com.cn'),('https://app.mokahr.com/social-recruitment/zte/47588','Linked by job.zte.com.cn')]
        r=shared.collect_moka_sites(COMPANIES[company],scope,sites,out)
        r['coverage']['scope_request']={'company':requested,'scope':scope,'source_url':sites[0][0],'params':{'orgId':'zte','siteId':[46903,47588],'offset':0,'limit':50,'needStat':True,'local_scope_filter':scope}}
    else:
        c=shared.coverage('');c['errors']=['Official source discovery in progress'];r=shared.finish([],c)
    c=r['coverage'];c['evidence_files']=c.get('evidence_files') or [p.name for p in out.glob('*list*.json')]
    if c.get('scope_request'):c['scope_request']['company']=requested
    if not r['jobs'] and c.get('complete'):
        c['source_complete']=True;c['company_scope_complete']=False;c['complete']=False;c['status']='blocked';c['blocking_kind']='coverage_discovery';c['errors'].append('Inspected official source has no scoped jobs; sole company-wide scope coverage not yet verified')
    from qiuzhao.v4_fields import graduation_of
    for j in r['jobs']:
        years,basis,_,_=graduation_of(j);j['graduation_years']=[y for y in years if re.fullmatch(r'20\d{2}届',y)];j['graduation_year_evidence']={y:basis[y] for y in j['graduation_years']}
    (out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));return r

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('company');p.add_argument('scope',choices=['campus','intern','social']);p.add_argument('output_dir');a=p.parse_args();r=collect(a.company,a.scope,a.output_dir);print(json.dumps({k:v for k,v in r['coverage'].items() if k not in ('evidence','evidence_files','scope_evidence')},ensure_ascii=False))
