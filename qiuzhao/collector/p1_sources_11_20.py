"""Public official-source adapters for priority companies 11–20.
No authentication; failed/unknown coverage is never a successful empty result.
"""
from __future__ import annotations
import concurrent.futures, datetime as dt, hashlib, json, re, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup

COMPANIES={'米哈游':'mihoyo','哔哩哔哩':'bilibili','蚂蚁集团':'ant','百度':'baidu','滴滴':'didi','携程':'ctrip','联想':'lenovo','海康威视':'hikvision','安克创新':'anker','影石Insta360':'insta360'}
SOURCES={'mihoyo':'https://jobs.mihoyo.com/','bilibili':'https://jobs.bilibili.com/','ant':'https://talent.antgroup.com/','baidu':'https://talent.baidu.com/jobs/list','didi':'https://talent.didiglobal.com/','ctrip':'https://careers.trip.com/','lenovo':'https://jobs.lenovo.com/en_US/careers','hikvision':'https://hr.hikvision.com/','anker':'https://career.anker.com.cn/','insta360':'https://hr.insta360.com/'}
TYPES={'campus':'校园招聘','intern':'实习招聘','social':'社会招聘'}
def clean(v):return BeautifulSoup(str(v or ''),'html.parser').get_text('\n',strip=True)
def save(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');return str(p)
def job(company,slug,ident,title,url,description,scope,evidence,**kw):
 j=dict(id=f'{slug}-{ident}',source_record_id=str(ident),recruitment_unit=company,contracting_entity='',job_title=title,job_category='',cities=[],major_requirements_raw='',major_tags=[],education_raw='',cohort_raw='',deadline=None,deadline_type='undisclosed',status='open',application_url=url,detail_url=url,source_url=url,published_at=None,reviewed_at=dt.datetime.now(dt.timezone.utc).isoformat(),source_name=company+'官方招聘',evidence_path=evidence,description_raw=description,recruitment_type=TYPES[scope]);j.update(kw);return j
class Fetcher:
 def __init__(self,out):self.out=out;self.evidence=[]
 def get(self,url,name,payload=None):
  r=requests.request('POST' if payload is not None else 'GET',url,json=payload,timeout=30,headers={'User-Agent':'QiuzhaoOfficialJobs/1.0 (public recruitment index)'})
  path=self.out/(name+'.txt');path.parent.mkdir(parents=True,exist_ok=True);text=r.content.decode('utf-8');path.write_text(text,encoding='utf-8');self.evidence.append(str(path));r.raise_for_status();return text,str(path)
 def api(self,url,name,payload):
  text,path=self.get(url,name,payload);d=json.loads(text)
  if d.get('code')!=0:raise ValueError(f'official API failure: {d.get("code")} {d.get("message")}')
  return d['data'],path

def _mihoyo(company,scope,f,cov):
 api='https://ats.openout.mihoyo.com/ats-portal';rows={};list_total=0
 # Internship positions can occur under either official hireType. Scan both.
 for typ in (1,0):
  count=0;total=None
  for page in range(1,1001):
   data,_=f.api(api+'/v1/job/list',f'list-{typ}-{page}',{'pageNo':page,'pageSize':100,'channelDetailIds':[1],'hireType':typ})
   cov['pages_scanned']+=1
   if total is None:total=int(data['total']);list_total+=total
   elif total!=int(data['total']):raise ValueError('list total changed during pagination')
   batch=data['list']
   for r in batch:
    key=(typ,str(r['id']))
    if key in rows:raise ValueError('duplicate ID across pages')
    rows[key]=r
   count+=len(batch)
   if count==total:break
   if not batch or count>total:raise ValueError('pagination count mismatch')
  else:raise ValueError('pagination limit reached')
 cov['list_total']=list_total
 selected=[]
 for (typ,ident),r in rows.items():
  actual='intern' if '实习' in r.get('jobNature','') else ('campus' if typ==1 else 'social')
  if actual==scope:selected.append((typ,ident,r))
 cov['expected_total']=len(selected);cov['scope_evidence']='官方 hireType=1 校园、0 社会；jobNature=实习优先分到实习。全量扫描两个公开频道。'
 def detail(item):
  typ,ident,r=item;data,path=f.api(api+'/v1/job/info',f'detail-{typ}-{ident}',{'id':ident,'channelDetailIds':[1],'hireType':typ})
  if str(data.get('id'))!=ident or data.get('hireType')!=typ:raise ValueError('detail identity/type mismatch')
  desc='\n\n'.join(clean(data.get(k)) for k in ('description','jobRequire','addition','deliveryInstructions') if data.get(k))
  if not clean(data.get('description')):raise ValueError('empty official job responsibilities')
  url='https://jobs.mihoyo.com/#/'+('campus/' if typ else '')+'position/'+ident
  return job(company,'mihoyo',ident,data['title'],url,desc,scope,path,cities=[x['addressDetail'] for x in data.get('addressDetailList',[])],job_category=data.get('competencyType',''),cohort_raw=data.get('objectName',''),cohort_scope='official_job_object',campaign_name=data.get('projectName',''))
 jobs=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  futures=[pool.submit(detail,x) for x in selected]
  for future in futures:
   try:jobs.append(future.result())
   except Exception as e:cov['errors'].append(str(e))
 return jobs

def _ant(company,scope,f,cov):
 route='social' if scope=='social' else 'campus'
 channel='group_official_site' if route=='social' else 'campus_group_official_site'
 jobs=[];cov['_partial_jobs']=jobs;seen=set();total=None;rows_count=0;selected=0
 for page in range(1,1001):
  text,path=f.get('https://hrcareersweb.antgroup.com/api/'+route+'/position/search',f'list-{page}',{'pageIndex':page,'pageSize':20,'channel':channel,'language':'zh_CN'})
  data=json.loads(text)
  if not data.get('success'):raise ValueError('official API '+str(data.get('errorCode')))
  cov['pages_scanned']+=1
  if total is None:total=int(data['totalCount'])
  elif int(data['totalCount'])!=total:raise ValueError('list total changed')
  rows=data['content']
  for r in rows:
   ident=str(r['id'])
   rows_count+=1
   if ident in seen:
    cov['errors'].append('duplicate source ID across pages: '+ident);continue
   seen.add(ident)
   actual='social' if route=='social' else {'graduate':'campus','trainee':'intern','talent_plan':'intern' if '实习' in (r.get('batchName') or '') else 'campus'}.get(r.get('batchType'))
   if actual is None:raise ValueError('unknown official batchType '+str(r.get('batchType')))
   if actual!=scope:continue
   selected+=1
   desc='\n\n'.join(clean(r.get(k)) for k in ('description','requirement','teamDescription') if r.get(k))
   if not clean(r.get('description')) or not clean(r.get('requirement')):
    cov['errors'].append('incomplete responsibilities/requirements '+ident);continue
   url='https://talent.antgroup.com/'+('off-campus-position' if route=='social' else 'campus-position')+'?positionId='+ident
   grad=r.get('graduationTime') or {}
   jobs.append(job(company,'ant',ident,r['name'],url,desc,scope,path,cities=r.get('workLocations') or [],education_raw=r.get('degree') or '',cohort_raw=('毕业时间 '+str(grad['from'])+' 至 '+str(grad['to'])) if grad.get('from') and grad.get('to') else '',cohort_scope='official_job_graduationTime',campaign_name=r.get('batchName') or '',published_at=r.get('publishTime'),job_category=r.get('categoryName') or ''))
  if rows_count==total:break
  if not rows or rows_count>total:raise ValueError('pagination count mismatch')
  time.sleep(.15)
 else:raise ValueError('pagination limit reached')
 cov.update(expected_total=selected,list_total=total,scope_evidence='官方campus频道 batchType graduate=应届生、trainee=实习生；social频道=社会招聘。列表返回完整description及requirement。',pagination_exhausted=True,unique_source_ids=len(jobs),last_page_evidence=path)
 return jobs

def _anker(company,scope,f,cov):
 sites={'6962795203808168199':'social','6962795203808217351':'campus','7005456241946331399':'intern','7069578816822282503':'social','7268177039772633400':'campus'}
 all_rows={};pages=0
 for site,basis in sites.items():
  token='';tokens=set();site_seen=set()
  for page in range(1,1001):
   url=f'https://rainbow-recall.anker.com.cn/api/lark/hire/v1/websites/{site}/job_posts/search?page_size=10&page_token='+requests.utils.quote(token,safe='')
   text,path=f.get(url,f'{site}-list-{page}',{'job_function_id_list':[],'city_code_list':[],'keyword':'','job_lang_list':[]})
   data=json.loads(text)
   if data.get('code')!=0:raise ValueError('Anker official API '+str(data.get('msg')))
   data=data['data'];pages+=1
   # Remove staff identity fields from the evidence; jobs remain untouched.
   for r in data['items']:r.pop('creator',None)
   Path(path).write_text(json.dumps({'code':0,'data':data},ensure_ascii=False))
   for r in data['items']:
    ident=str(r['id'])
    if ident in site_seen:raise ValueError('Anker repeated ID within site pagination')
    site_seen.add(ident)
    nature=(r.get('job_recruitment_type') or {}).get('name',{})
    actual='intern' if nature.get('zh_cn')=='实习' or nature.get('en_us')=='Intern' else basis
    key=(actual,ident)
    all_rows[key]=(r,site,path)
   if data.get('has_more') is False:break
   nxt=data.get('page_token')
   if not nxt or nxt in tokens:raise ValueError('Anker nonadvancing page token')
   tokens.add(nxt);token=nxt;time.sleep(.15)
  else:raise ValueError('Anker page limit reached')
 jobs=[];selected=[(ident,*v) for (actual,ident),v in all_rows.items() if actual==scope]
 cov.update(expected_total=len(selected),pages_scanned=pages,list_total=len(all_rows),pagination_exhausted=True,last_page_evidence=path,scope_evidence='安克官网公开JS中的5个中英文招聘websiteId；官方job_recruitment_type实习优先，其余按官网应届生/社会频道。公开列表包含完整description和requirement。')
 for ident,r,site,path in selected:
  if not clean(r.get('description')) or not clean(r.get('requirement')):cov['errors'].append('incomplete responsibilities/requirements '+ident);continue
  desc=clean(r['description'])+'\n\n'+clean(r['requirement']);url=f'https://career.anker.com.cn/larkJobDetail/?websiteId={site}&jobId={ident}'
  cities=[]
  for a in r.get('address_list') or []:
   n=(a.get('city') or {}).get('name') or {};value=n.get('zh_cn') or n.get('en_us')
   if value and value not in cities:cities.append(value)
  jobs.append(job(company,'anker',ident,r['title'],url,desc,scope,path,cities=cities,job_category=((r.get('job_function') or {}).get('name') or {}).get('zh_cn',''),cohort_raw='；'.join(re.findall(r'[^。\n]*(?:20\d{2}届|毕业)[^。\n]*',desc)),cohort_scope='official_job_description'))
 cov['unique_source_ids']=len(jobs)
 return jobs

def collect(company:str,scope:str,output_dir:Path)->dict:
 if company not in COMPANIES:raise ValueError('unknown company')
 if scope not in TYPES:raise ValueError('unknown scope')
 slug=COMPANIES[company];out=Path(output_dir).resolve()/slug/scope;f=Fetcher(out/'evidence')
 cov=dict(status='blocked',complete=False,expected_total=None,collected_jobs=0,pages_scanned=0,detail_complete=False,source_url=SOURCES[slug],errors=[],evidence=[])
 jobs=[]
 try:
  if slug=='mihoyo':jobs=_mihoyo(company,scope,f,cov)
  elif slug=='ant':jobs=_ant(company,scope,f,cov)
  elif slug=='anker':jobs=_anker(company,scope,f,cov)
  else:
   f.get(SOURCES[slug],'official-entry');raise ValueError('Official entry checked; full scoped list/detail contract not yet verified')
 except Exception as e:
  cov['errors'].append(str(e));jobs=cov.get('_partial_jobs',jobs)
 cov.pop('_partial_jobs',None)
 cov['collected_jobs']=len(jobs);cov['evidence']=f.evidence;cov['evidence_files']=f.evidence
 cov['scope_request']={'company':company,'scope':scope,'source_url':SOURCES[slug],'params':{'hireType':[1,0],'channelDetailIds':[1]} if slug=='mihoyo' else {'route':'social' if scope=='social' else 'campus','pageSize':20}}
 cov['complete']=cov['expected_total'] is not None and len(jobs)==cov['expected_total'] and not cov['errors']
 cov['detail_complete']=cov['complete'];cov['status']='success' if cov['complete'] else ('partial' if jobs else 'blocked')
 result={'jobs':jobs,'coverage':cov};save(out/'candidate.json',result);save(out/'coverage.json',cov);return result
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('company');parser.add_argument('--scope',choices=TYPES);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
 for scope in ([args.scope] if args.scope else TYPES):
  r=collect(args.company,scope,args.output_dir);print(json.dumps({'company':args.company,'scope':scope,**{k:v for k,v in r['coverage'].items() if k not in {'evidence','evidence_files'}}},ensure_ascii=False),flush=True)
