"""Ordered P1 source batch 41-50, sharing verified public ATS protocols."""
from __future__ import annotations
import sys,json,re
from pathlib import Path
try:
 from . import p1_sources_01_10 as shared
 from .p1_sources_31_40 import collect_beisen
except ImportError:
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
 from qiuzhao.collector import p1_sources_01_10 as shared
 from qiuzhao.collector.p1_sources_31_40 import collect_beisen
COMPANIES={'geely':'吉利汽车','gwm':'长城汽车','mindray':'迈瑞医疗','hengrui':'恒瑞医药','wuxiapptec':'药明康德','xiaomi':'小米','jd':'京东','meituan':'美团','netease':'网易','dewu':'得物'}
BEISEN={'mindray':'https://career.mindray.com','wuxiapptec':'https://wuxiapptec.zhiye.com'}
MOKA={
 'geely':[('https://app.mokahr.com/campus-recruitment/geely/78436','Linked by current job.geely.com'),('https://job.geely.com/social-recruitment/geely/96123','Current official Geely holding portal'),('https://autojob.geely.com/social-recruitment/geely/102042','Current official Geely Auto portal'),('https://app.mokahr.com/social-recruitment/geely/102003','Official Geely page links Zeekr portal')],
 'hengrui':[('https://app.mokahr.com/campus-recruitment/hengrui/145997','Verified Hengrui branded campus portal'),('https://app.mokahr.com/social-recruitment/hengrui/145996','Verified Hengrui branded social portal')],
}

def collect_xiaomi_domestic(scope,out):
 host='https://hr.xiaomi.com';entry=host+'/opportunities.html';kind={'social':1,'campus':2,'intern':3}[scope];c=shared.coverage(entry);jobs=[];seen=set();session=shared.make_session();total=None
 try:
  for page in range(1,10001):
   params={'keyword':'','cityZhNames':'','pageSize':100,'pageNum':page,'type':kind};rr=session.get(host+'/website/api/agent/searchJobPage',params=params,timeout=(10,40));rr.raise_for_status();env=rr.json();(out/f'list-{page}.json').write_text(json.dumps(env,ensure_ascii=False));c['pages_scanned']+=1
   if env.get('code')!=0:raise ValueError(str(env)[:300])
   d=env['data'];rows=d['list'];n=d['total']
   if total is not None and n!=total:raise ValueError('Xiaomi proxy count changed')
   total=n
   for row in rows:
    ident=str(row.get('jobPostId') or '')
    if not ident or ident in seen:raise ValueError('Xiaomi jobPostId missing/repeated')
    if row.get('type')!=kind:raise ValueError('Xiaomi proxy scope mismatch')
    seen.add(ident);description=row.get('description') or '';requirement=row.get('requirement') or ''
    if not shared.text(description) and not shared.text(requirement):c['errors'].append('No disclosed role text for '+ident);continue
    url=row.get('url') or ''
    if not url.startswith('https://xiaomi.jobs.f.mioffice.cn/') or ident not in url:raise ValueError('Xiaomi official URL identity mismatch')
    j=shared.job('小米',scope,'feishu-xiaomi:'+ident,row['title'],url,description+'\n任职要求\n'+requirement,' / '.join(row.get('cityZhNames') or []),{**row,'qualification':requirement})
    j['official_source_id']=ident;j['source_namespace']='feishu-xiaomi';j['scope_evidence']=f'Official Xiaomi proxy type={kind}; jobPostId and returned original URL agree';j['publication_date']=row.get('publishTime');j['hiring_department_raw']=row.get('levelOneDeptName') or '';j['detail_source']='Official Xiaomi proxy supplies full description and requirement without truncation';jobs.append(j)
   if not rows or d['pageNum']==d['pageTotal']:
    c['last_page_evidence']=f'page={page};official_pages={d["pageTotal"]};unique={len(seen)};total={total}';break
  if len(seen)!=total:raise ValueError('Xiaomi incomplete proxy pagination')
  c['expected_total']=total;c['pagination_exhausted']=True;c['detail_complete']=len(jobs)==len(seen);c['evidence']=[p.name for p in out.glob('list-*.json')];c['evidence_files']=c['evidence'];c['scope_evidence']=f'Official proxy type={kind}';c['scope_request']={'company':'小米','scope':scope,'source_url':entry,'params':{'type':kind,'pageNum':1,'pageSize':100}}
  c['source_complete']=not c['errors'];c['company_scope_complete']=False
  c['errors'].append('Domestic official proxy exhausted; separate career.mi.com overseas source still being integrated')
 except Exception as exc:c['errors'].append(str(exc))
 return shared.finish(jobs,c)

def collect_jd_campus(scope,out):
 from concurrent.futures import ThreadPoolExecutor,as_completed
 host='https://campus.jd.com';c=shared.coverage(host);jobs=[];session=shared.make_session()
 if scope=='social':c['errors']=['Independent JD social portal integration pending'];return shared.finish(jobs,c)
 try:
  rr=session.get(host+'/api/wx/position/getProjectList',timeout=(10,30));rr.raise_for_status();config=rr.json();(out/'official-projects.json').write_text(json.dumps(config,ensure_ascii=False))
  if config.get('success') is not True:raise ValueError('JD project metadata failed')
  groups=[]
  for project in config['body']['projectList']:
   if not project.get('release'):continue
   for group in project.get('groupList') or []:
    for plan in group.get('planMapList') or []:
     actual='intern' if project['code']=='internship' or '实习' in plan.get('planName','') else 'campus' if project['code'] in ['present','talent'] else None
     if actual is None:raise ValueError('Unknown JD official project scope')
     if actual==scope:groups.append((project['code'],plan))
  selected=[];seen_all=set();totals={}
  for code,plan in groups:
   seen=set();total=None
   for page in range(0,10000):
    body={'pageSize':50,'pageIndex':page,'parameter':{'positionName':'','planIdList':[plan['id']],'jobDirectionCodeList':[],'workCityCodeList':[],'positionDeptList':[]}}
    rr=session.post(host+'/api/wx/position/page',params={'type':code},json=body,timeout=(10,40));rr.raise_for_status();env=rr.json();(out/f'{plan["id"]}-list-{page}.json').write_text(json.dumps(env,ensure_ascii=False));c['pages_scanned']+=1
    if env.get('success') is not True:raise ValueError('JD list failed')
    data=env['body'];rows=data['items'];n=data['totalNumber']
    if total is not None and n!=total:raise ValueError('JD list count changed')
    total=n
    for row in rows:
     ident=row['publishId']
     if ident in seen:raise ValueError('JD repeated publishId across pages')
     if row.get('planId')!=plan['id']:raise ValueError('JD plan filter ignored')
     seen.add(ident)
     if ident not in seen_all:selected.append((row,plan));seen_all.add(ident)
    if len(seen)==total or not rows:c['last_page_evidence']=f'plan={plan["id"]};page={page};unique={len(seen)};official_total={total}';break
   if len(seen)!=total:raise ValueError('JD incomplete plan list')
   totals[str(plan['id'])]=total
  c['plan_totals']=totals;c['expected_total']=len(selected);c['pagination_exhausted']=True
  def detail(pair):
   row,plan=pair;ident=row['publishId'];rr=shared.http_post(host+'/api/wx/position/detail/'+str(ident),json={},timeout=(10,40));rr.raise_for_status();env=rr.json();(out/f'detail-{ident}.json').write_text(json.dumps(env,ensure_ascii=False))
   if env.get('success') is not True:raise ValueError('JD detail failed')
   d=env['body']
   if d.get('publishId')!=ident:raise ValueError('JD detail publishId mismatch')
   desc=d.get('workContent') or '';req=d.get('qualification') or ''
   if not shared.text(desc) and not shared.text(req):raise ValueError('JD role content undisclosed')
   cities=list(dict.fromkeys(x.get('workCity') for x in d.get('requirementVoList') or [] if x.get('workCity')))
   j=shared.job('京东',scope,'jd-campus:'+str(ident),d['positionName'],host+'/#/details?id='+str(ident),desc+'\n任职要求\n'+req,' / '.join(cities),d)
   j['official_source_id']=str(ident);j['source_namespace']='jd-campus';j['scope_evidence']='Current official project '+str(plan['id'])+' '+plan.get('planName','');j['campaign_cohort_raw']=plan.get('planName') or '';j['campaign_scope']='project';j['campaign_url']=host;j['education_raw']=shared.text(d.get('education')) or j.get('education_raw');return j
  with ThreadPoolExecutor(max_workers=3) as pool:
   futures={pool.submit(detail,pair):pair[0]['publishId'] for pair in selected}
   for f in as_completed(futures):
    try:jobs.append(f.result())
    except Exception as exc:c['errors'].append(f'detail {futures[f]}: {exc}')
  c['detail_complete']=len(jobs)==len(selected);c['evidence']=['official-projects.json']+[p.name for p in out.glob('*list*.json')];c['evidence_files']=c['evidence'];c['scope_evidence']='Released official JD project plan map';c['scope_request']={'company':'京东','scope':scope,'source_url':host,'params':{'plans':[{**plan,'type':code} for code,plan in groups],'pageSize':50,'pageIndex':0}}
 except Exception as exc:c['errors'].append(str(exc))
 return shared.finish(jobs,c)

def collect_jd_social(out):
 host='https://zhaopin.jd.com';entry=host+'/web/job/job_info_list/3';c=shared.coverage(entry);jobs=[];session=shared.make_session();seen=set();raw_count=0;fingerprints={};duplicates=[]
 try:
  rr=session.get(entry,timeout=(10,30));rr.raise_for_status();(out/'official-entry.html').write_text(rr.text)
  filters={'workCityJson':'[]','jobTypeJson':'[]','depTypeJson':'[]','jobSearch':''}
  rr=session.post(host+'/web/job/job_count',data=filters,timeout=(10,35));rr.raise_for_status();total=int(rr.text);(out/'official-count.json').write_text(rr.text);c['list_total']=total;c['expected_total']=total
  for page in range(1,10001):
   body={**filters,'pageIndex':page,'pageSize':50};rr=session.post(host+'/web/job/job_list',data=body,timeout=(10,35));rr.raise_for_status();rows=rr.json();(out/f'list-{page}.json').write_text(json.dumps(rows,ensure_ascii=False));c['pages_scanned']+=1
   if not isinstance(rows,list):raise ValueError('JD social list schema changed')
   raw_count+=len(rows)
   if not rows:c['last_page_evidence']=f'page={page};rows=0;official_total={total};unique={len(seen)}';break
   for row in rows:
    ident=str(row.get('requirementId') or '');position=row.get('positionId')
    if not ident or position is None:raise ValueError('JD social missing requirementId/positionId')
    if ident in seen:
     duplicates.append({'requirementId':ident,'page':page})
     if {k:v for k,v in fingerprints[ident].items() if k!='id'}!={k:v for k,v in row.items() if k!='id'}:c['errors'].append('Conflicting duplicate JD requirementId '+ident)
     for existing in jobs:
      if existing.get('official_source_id')==ident:existing['source_publication_ids']=sorted(set(existing.get('source_publication_ids',[])+[row.get('id')]))
     continue
    fingerprints[ident]=row
    seen.add(ident);desc=row.get('workContent') or '';req=row.get('qualification') or ''
    if not shared.text(desc) and not shared.text(req):
     c['errors'].append('Official inline description undisclosed: '+ident);c.setdefault('pending_details',[]).append({'source_record_id':'jd-social:'+ident,'job_title':row.get('positionNameOpen') or row.get('positionName'),'evidence_file':f'list-{page}.json','detail_fetch_status':'success','detail_content_status':'undisclosed'});continue
    j=shared.job('京东','social','jd-social:'+ident,row.get('positionNameOpen') or row['positionName'],entry,desc+'\n任职要求\n'+req,row.get('workCity') or '',row)
    j.update(official_source_id=ident,source_publication_ids=[row.get('id')],source_namespace='jd-social',recRequirementId=int(ident),positionId=position,detail_presentation='inline',application_link_type='list_entry',application_instructions='请在京东官网社会招聘列表按岗位名称查找，展开岗位后登录申请。',scope_evidence='Official JD 社会招聘 list/inline detail API',source_missing_fields=[name for name,value in [('responsibilities',desc),('requirements',req)] if not shared.text(value)],publication_date=row.get('formatPublishTime'),hiring_department_raw=row.get('positionDeptName') or '')
    jobs.append(j)
   if raw_count>=total:
    c['last_page_evidence']=f'page={page};rows={len(rows)};official_total={total};raw_rows={raw_count};unique={len(seen)}';break
   if page%10==0:
    c['collected_jobs']=len(jobs);checkpoint={'jobs':jobs,'coverage':{**c,'status':'partial','complete':False}};(out/'result.json').write_text(json.dumps(checkpoint,ensure_ascii=False))
  if raw_count!=total:raise ValueError(f'JD social incomplete official total={total};raw_rows={raw_count};unique={len(seen)}')
  c['raw_rows_collected']=raw_count;c['duplicate_source_records']=duplicates;c['expected_total']=len(seen)
  c.update(pagination_exhausted=True,unique_source_ids=len(seen),detail_complete=len(jobs)==len(seen),evidence=['official-entry.html','official-count.json']+[p.name for p in out.glob('list-*.json')],scope_evidence='Official JD social job list; full inline workContent and qualification per requirementId',scope_request={'company':'京东','scope':'social','source_url':entry,'params':{**filters,'pageIndex':1,'pageSize':50}})
  c['evidence_files']=c['evidence'];c['detail_missing_count']=len(c.get('pending_details',[]))
 except Exception as exc:c['errors'].append(str(exc))
 return shared.finish(jobs,c)

def collect(company,scope,output_dir):
 requested=company;key=next((k for k,v in COMPANIES.items() if v==company),company);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
 if key=='meituan':
  from .p1_meituan_public import collect as meituan_collect
  result=meituan_collect('美团',scope,out)
 elif key=='gwm':result=shared.collect_honor(scope,out,company='长城汽车',host='https://zhaopin.gwm.cn',suites_override=['SU692d3058ea11b01b6c54d0ea'])
 elif key=='jd':result=collect_jd_social(out) if scope=='social' else collect_jd_campus(scope,out)
 elif key=='xiaomi':result=collect_xiaomi_domestic(scope,out)
 elif key in BEISEN:result=collect_beisen(COMPANIES[key],scope,BEISEN[key],out,category_mapping={'4':'social','8':'intern','9':'intern','10':'intern'} if key=='mindray' else None)
 elif key in MOKA:
  result=shared.collect_moka_sites(COMPANIES[key],scope,MOKA[key],out)
  result['coverage']['scope_request']={'company':requested,'scope':scope,'source_url':MOKA[key][0][0],'params':{'orgId':key,'sites':[s[0] for s in MOKA[key]],'offset':0,'limit':50,'needStat':True,'local_scope_filter':scope}}
 else:
  c=shared.coverage('');c['errors']=['Official adapter implementation in progress'];result=shared.finish([],c)
 c=result['coverage'];c['evidence_files']=c.get('evidence_files') or [p.name for p in out.glob('*list*.json')]
 if c.get('request_params'):c['scope_request']={'company':requested,'scope':scope,'source_url':c['source_url'],'params':c['request_params']}
 if c.get('scope_request'):c['scope_request']['company']=requested
 if not result['jobs'] and c.get('complete'):
  c['source_complete']=True;c['company_scope_complete']=False;c['complete']=False;c['status']='blocked';c['blocking_kind']='coverage_discovery';c['errors'].append('Inspected source scope is empty; sole current company-wide scope not yet verified')
 from qiuzhao.v4_fields import graduation_of
 for j in result['jobs']:
  years,basis,_,_=graduation_of(j);j['graduation_years']=[y for y in years if re.fullmatch(r'20\d{2}届',y)];j['graduation_year_evidence']={y:basis[y] for y in j['graduation_years']}
 (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));return result
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('company');p.add_argument('scope',choices=['campus','intern','social']);p.add_argument('output_dir');a=p.parse_args();r=collect(a.company,a.scope,a.output_dir);print(json.dumps({k:v for k,v in r['coverage'].items() if k not in ['evidence','evidence_files','scope_evidence']},ensure_ascii=False))
