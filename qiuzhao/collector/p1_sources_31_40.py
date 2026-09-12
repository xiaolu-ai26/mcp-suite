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

def collect_beisen(company,scope,host,output_dir):
    """Discover current PortalId; exhaust official pages and fetch every job GUID."""
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    name=COMPANIES.get(company,company);c=shared.coverage(host);jobs=[];session=shared.make_session();category={'social':'1','campus':'2','intern':'3'}[scope]
    try:
        page=session.get(host,timeout=(10,30));page.raise_for_status();page.encoding='utf-8';(output_dir/'official-entry.html').write_text(page.text)
        ids=set(re.findall(r'"PortalId"\s*:\s*"([^"]+)"',page.text))
        if len(ids)!=1:raise ValueError('Official Beisen PortalId missing or ambiguous')
        portal=ids.pop();host=urlsplit(page.url).scheme+'://'+urlsplit(page.url).netloc;c['source_url']=host
        selected=[];seen=set();total=None
        for index in range(10000):
            body={'PortalId':portal,'PageIndex':index,'PageSize':50,'Category':[category],'KeyWords':'','SpecialType':0,'DisplayFields':FIELDS}
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
                if actual not in ('1','2','3'):raise ValueError('Unknown Beisen recruitment category '+actual)
                if actual==category:selected.append(row)
        if len(seen)!=total:raise ValueError(f'Incomplete list: {len(seen)} vs {total}')
        c['list_total']=total;c['expected_total']=len(selected);c['pagination_exhausted']=True
        def detail(row):
            ident=row['Id'];params={'jobAdId':ident,'portalId':portal,'category':category,'displayFields':json.dumps(FIELDS)}
            rr=shared.http_get(host+'/api/JobAd/GetJobAdInfo',params=params,timeout=(10,45));rr.raise_for_status();env=rr.json();(output_dir/f'detail-{ident}.json').write_text(json.dumps(env,ensure_ascii=False))
            if env.get('Code')!=200:raise ValueError(str(env)[:300])
            d=env['Data']
            if d.get('Id')!=ident or str(d.get('CategoryId'))!=category:raise ValueError('Beisen detail identity/category mismatch')
            duty=d.get('Duty') or '';requirements=d.get('Require') or ''
            if not duty and not requirements:raise ValueError('Official detail has no description')
            locations=d.get('LocNames') or [];loc=' / '.join(str(x) for x in locations)
            j=shared.job(name,scope,ident,d['JobAdName'],host+'/'+scope+'/detail?jobAdId='+ident,duty+'\n任职要求\n'+requirements,loc,d)
            j['recruitment_type_raw']={'CategoryId':category,'Category':d.get('Category')};j['scope_evidence']=f'Official Beisen CategoryId={category}; Category={d.get("Category")}'
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
        c['detail_complete']=len(jobs)==len(selected);c['evidence']=['official-entry.html']+[p.name for p in output_dir.glob('list-*.json')];c['evidence_files']=c['evidence'];c['scope_evidence']=f'Official Beisen Category filter={category}'
        c['scope_request']={'company':name,'scope':scope,'source_url':host,'params':body}
    except Exception as exc:c['errors'].append(str(exc))
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

def collect(company,scope,output_dir):
    requested=company
    if company in ('TP-LINK','TP-LINK／普联','TP-LINK/普联','普联'):company='tplink'
    company=next((key for key,name in COMPANIES.items() if name==company),company);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    if company=='tplink':r=collect_tplink(scope,out)
    elif company in BEISEN:r=collect_beisen(company,scope,BEISEN[company],out)
    elif company=='zte':
        sites=[('https://app.mokahr.com/campus-recruitment/zte/46903','Linked by job.zte.com.cn'),('https://app.mokahr.com/social-recruitment/zte/47588','Linked by job.zte.com.cn')]
        r=shared.collect_moka_sites(COMPANIES[company],scope,sites,out)
        r['coverage']['scope_request']={'company':requested,'scope':scope,'source_url':sites[0][0],'params':{'orgId':'zte','siteId':[46903,47588],'offset':0,'limit':50,'needStat':True,'local_scope_filter':scope}}
    else:
        c=shared.coverage('');c['errors']=['Official source discovery in progress'];r=shared.finish([],c)
    c=r['coverage'];c['evidence_files']=c.get('evidence_files') or [p.name for p in out.glob('*list*.json')]
    if c.get('scope_request'):c['scope_request']['company']=requested
    from qiuzhao.v4_fields import graduation_of
    for j in r['jobs']:
        years,basis,_,_=graduation_of(j);j['graduation_years']=[y for y in years if re.fullmatch(r'20\d{2}届',y)];j['graduation_year_evidence']={y:basis[y] for y in j['graduation_years']}
    (out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));return r

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('company');p.add_argument('scope',choices=['campus','intern','social']);p.add_argument('output_dir');a=p.parse_args();r=collect(a.company,a.scope,a.output_dir);print(json.dumps({k:v for k,v in r['coverage'].items() if k not in ('evidence','evidence_files','scope_evidence')},ensure_ascii=False))
