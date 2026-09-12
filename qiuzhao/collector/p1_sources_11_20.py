"""Public official-source adapters for priority companies 11–20.
No authentication; failed/unknown coverage is never a successful empty result.
"""
from __future__ import annotations
import concurrent.futures, datetime as dt, hashlib, json, re, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup

COMPANIES={'米哈游':'mihoyo','哔哩哔哩':'bilibili','蚂蚁集团':'ant','百度':'baidu','滴滴':'didi','携程':'ctrip','联想':'lenovo','海康威视':'hikvision','安克创新':'anker','影石Insta360':'insta360'}
SOURCES={'mihoyo':'https://jobs.mihoyo.com/','bilibili':'https://jobs.bilibili.com/','ant':'https://talent.antgroup.com/','baidu':'https://talent.baidu.com/jobs/list','didi':'https://talent.didiglobal.com/','ctrip':'https://careers.trip.com/','lenovo':'https://jobs.lenovo.com/en_US/careers','hikvision':'https://talent.hikvision.com/','anker':'https://career.anker.com.cn/','insta360':'https://www.insta360.com/cn/jobs'}
TYPES={'campus':'校园招聘','intern':'实习招聘','social':'社会招聘'}
def clean(v):return BeautifulSoup(str(v or ''),'html.parser').get_text('\n',strip=True)
def save(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');return str(p)
def job(company,slug,ident,title,url,description,scope,evidence,**kw):
 j=dict(id=f'{slug}-{ident}',source_record_id=str(ident),recruitment_unit=company,contracting_entity='',job_title=title,job_category='',cities=[],major_requirements_raw='',major_tags=[],education_raw='',cohort_raw='',deadline=None,deadline_type='undisclosed',status='open',application_url=url,detail_url=url,source_url=url,published_at=None,reviewed_at=dt.datetime.now(dt.timezone.utc).isoformat(),source_name=company+'官方招聘',evidence_path=evidence,description_raw=description,recruitment_type=TYPES[scope]);j.update(kw)
 if j.get('campaign_name'):j['batch_name']=j['campaign_name']
 if 'source_missing_fields' in j:j['field_completeness']={name:('source_not_disclosed' if name in j['source_missing_fields'] else 'source_disclosed') for name in ['description','requirement']}
 lines=[x.strip() for x in re.split(r'[\n。；]',description) if x.strip()]
 if not j['major_requirements_raw']:
  j['major_requirements_raw']='；'.join(x for x in lines if re.search(r'相关专业|专业(?:优先|不限)|专业背景[：:]|(?:degree|major)\s+in\b',x,re.I))
 if not j['education_raw']:
  j['education_raw']='；'.join(x for x in lines if re.search(r'博士|硕士|本科|大专|专科|研究生|bachelor|master.?s|ph\.?d',x,re.I) and re.search(r'学历|学位|在读|以上|优先|毕业|degree|bachelor|master.?s|ph\.?d',x,re.I))
 return j
def role_body(description,requirement):
 d,q=clean(description),clean(requirement)
 missing=[name for name,value in [('description',d),('requirement',q)] if not value]
 if not q and re.search(r'岗位要求|任职要求|任职资格|qualification|requirements',d,re.I):missing.remove('requirement')
 if not d and re.search(r'岗位职责|工作职责|responsibilit|job description|duties',q,re.I):missing.remove('description')
 combined='\n\n'.join(x for x in [d,q] if x)
 if not combined:raise ValueError('Official responsibilities and requirements both absent')
 if re.match(r'^(?:公司简介|企业介绍|团队介绍|关于我们|免责声明|隐私政策|about us|about the company|privacy policy)',combined,re.I) and not re.search(r'岗位职责|任职|资格|负责|参与|responsibilit|requirement|qualification|you will|degree|skills',combined,re.I):
  raise ValueError('Only company/team/platform introduction, not role evidence')
 return combined,missing

def graduation_window(raw):
 if not isinstance(raw,dict) or not raw.get('from') or not raw.get('to'):return ''
 def date(value):
  parsed=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
  if parsed.tzinfo is not None:parsed=parsed.astimezone(dt.timezone(dt.timedelta(hours=8)))
  return parsed.date()
 start,end=date(raw['from']),date(raw['to'])
 if start>end:raise ValueError('Official graduation date range reversed')
 return f'毕业时间 {start.isoformat()} 至 {end.isoformat()}'

def missing_detail(cov,ident,title,path):
 pending=cov.setdefault('pending_details',[]);pending.append({'source_record_id':str(ident),'title':title,'evidence_file':path,'reason':'Official role responsibilities/requirements both absent or boilerplate'})
 cov['detail_missing_count']=len(pending)

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
  try:desc,missing=role_body(data.get('description'),data.get('jobRequire'))
  except ValueError:
   missing_detail(cov,ident,data.get('title'),path);raise
  desc+=''.join('\n\n'+clean(data[k]) for k in ('addition','deliveryInstructions') if data.get(k))
  url='https://jobs.mihoyo.com/#/'+('campus/' if typ else '')+'position/'+ident
  return job(company,'mihoyo',ident,data['title'],url,desc,scope,path,source_missing_fields=missing,cities=[x['addressDetail'] for x in data.get('addressDetailList',[])],job_category=data.get('competencyType',''),cohort_raw=data.get('objectName',''),cohort_scope='official_job_object',campaign_name=data.get('projectName',''))
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
 jobs=[];cov['_partial_jobs']=jobs;cov['scope_evidence']='官方campus批次graduate/trainee/talent_plan与social频道，实习项目按官方batchName';seen=set();total=None;rows_count=0;selected=0
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
   try:desc,missing=role_body(r.get('description'),r.get('requirement'))
   except ValueError as e:
    missing_detail(cov,ident,r.get('name'),path);cov['errors'].append(str(e)+' '+ident);continue
   if r.get('teamDescription'):desc+='\n\n'+clean(r['teamDescription'])
   url='https://talent.antgroup.com/'+('off-campus-position' if route=='social' else 'campus-position')+'?positionId='+ident
   grad=r.get('graduationTime') or {}
   jobs.append(job(company,'ant',ident,r['name'],url,desc,scope,path,source_missing_fields=missing,cities=r.get('workLocations') or [],education_raw=r.get('degree') or '',cohort_raw=graduation_window(grad),graduation_date_range_raw=grad,graduation_date_timezone='Asia/Shanghai',cohort_scope='official_job_graduationTime',campaign_name=r.get('batchName') or '',published_at=r.get('publishTime'),job_category=r.get('categoryName') or ''))
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
    actual={'101':'social','102':'social','201':'campus','202':'intern','301':'intern'}.get(str((r.get('job_recruitment_type') or {}).get('id')))
    if actual is None:raise ValueError('Unrecognized official Anker recruitment enum')
    key=(actual,ident)
    all_rows[key]=(r,site,path)
   if data.get('has_more') is False:break
   nxt=data.get('page_token')
   if not nxt or nxt in tokens:raise ValueError('Anker nonadvancing page token')
   tokens.add(nxt);token=nxt;time.sleep(.15)
  else:raise ValueError('Anker page limit reached')
 jobs=[];selected=[(ident,*v) for (actual,ident),v in all_rows.items() if actual==scope]
 cov.update(expected_total=len(selected),pages_scanned=pages,list_total=len(all_rows),pagination_exhausted=True,last_page_evidence=path,scope_evidence='安克官网公开JS中的5个中英文招聘websiteId；官方job_recruitment_type ID 101/102=全职/外包社会、201=正式校招、202/301=实习（不按所在栏目猜测）。公开列表包含完整description和requirement。')
 for ident,r,site,path in selected:
  if not clean(r.get('description')) and not clean(r.get('requirement')):
   try:
    text,path=f.get(f'https://rainbow-recall.anker.com.cn/api/lark/hire/v1/websites/{site}/job_posts/{ident}','detail-'+ident)
    envelope=json.loads(text)
    if envelope.get('code')!=0:raise ValueError('Anker detail rejected '+ident)
    detail=envelope['data']['job_post']
    if str(detail.get('id'))!=ident:raise ValueError('Anker detail identity mismatch '+ident)
    keep=['id','title','description','requirement','job_recruitment_type','job_function','address_list','subject','create_time','modify_time','job_code']
    detail={k:detail.get(k) for k in keep};Path(path).write_text(json.dumps({'code':0,'data':{'job_post':detail}},ensure_ascii=False))
    if str((detail.get('job_recruitment_type') or {}).get('id'))!=str((r.get('job_recruitment_type') or {}).get('id')):raise ValueError('Anker detail type changed '+ident)
    r=detail
   except Exception as e:cov['errors'].append(str(e));continue
  try:desc,missing=role_body(r.get('description'),r.get('requirement'))
  except ValueError as e:
   missing_detail(cov,ident,r.get('title'),path);cov['errors'].append(str(e)+' '+ident);continue
  url=f'https://career.anker.com.cn/larkJobDetail/?websiteId={site}&jobId={ident}'
  cities=[]
  for a in r.get('address_list') or []:
   n=(a.get('city') or {}).get('name') or {};value=n.get('zh_cn') or n.get('en_us')
   if value and value not in cities:cities.append(value)
  jobs.append(job(company,'anker',ident,r['title'],url,desc,scope,path,source_missing_fields=missing,cities=cities,job_category=((r.get('job_function') or {}).get('name') or {}).get('zh_cn',''),cohort_raw='',cohort_scope='official_job_description'))
 cov['unique_source_ids']=len(jobs)
 return jobs

def _bilibili(company,scope,f,cov):
 route='srs' if scope=='social' else 'campus';typ='0' if scope=='intern' else '3'
 payload={'pageSize':10,'pageNum':1,'workTypeList':[typ],'positionTypeList':[typ],'recruitType':0 if scope=='social' else 1,'onlyHotRecruit':0}
 cov['scope_request']={'company':company,'scope':scope,'source_url':SOURCES['bilibili'],'params':payload}
 text,_=f.get('https://jobs.bilibili.com/api/'+route+'/position/positionList','list-1',payload)
 data=json.loads(text)
 raise ValueError('Official Bilibili list rejected code='+str(data.get('code'))+' message='+str(data.get('message')))

def _baidu(company,scope,f,cov):
 typ={'campus':'GRADUATE','intern':'INTERN','social':'SOCIAL'}[scope]
 params={'recruitType':typ,'curPage':1,'pageSize':10,'keyWord':'','projectType':''}
 cov['scope_request']={'company':company,'scope':scope,'source_url':SOURCES['baidu'],'params':params}
 # Public frontend submits form parameters. Do not bypass no-auth responses.
 r=requests.post('https://talent.baidu.com/httservice/getPostListNew',data=params,timeout=30)
 path=f.out/'api-list.txt';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(r.content);f.evidence.append(str(path))
 r.raise_for_status();data=r.json()
 if data.get('status')!='ok':cov['errors'].append('official list API '+str(data.get('status'))+': '+str(data.get('message')))
 text,path=f.get('https://talent.baidu.com/jobs/list?recruitType='+typ,'ssr-list')
 raw=text.split('window.__INITIAL_DATA__ =',1)[1]
 raw=re.sub(r'(:|,)undefined(?=[,}])',r'\1null',raw)
 data=json.JSONDecoder().raw_decode(raw)[0]['listData']
 if data['recruitType']!=typ:raise ValueError('SSR scope mismatch')
 cov.update(pages_scanned=1,list_total=data['total'],scope_evidence='官方recruitType '+typ+'；SSR只返回首页10条，翻页接口no-auth，不声称全量。')
 jobs=[]
 for r in data['listDetailData']:
  try:desc,missing=role_body(r.get('workContent'),r.get('serviceCondition'))
  except ValueError:continue
  ident=r['postId'];url='https://talent.baidu.com/jobs/detail/'+typ+'/'+ident
  cohort=next((x.get('subtitle','') for x in data.get('listConfig',[]) if x.get('recruitType')==typ),'')
  jobs.append(job(company,'baidu',ident,r['name'],url,desc,scope,path,source_missing_fields=missing,cities=[r['workPlace']] if r.get('workPlace') else [],cohort_raw=cohort if scope!='social' else '',cohort_scope='campaign_announcement',education_raw=r.get('education',''),published_at=r.get('publishDate'),job_category=r.get('postType','')))
 cov['errors'].append('Only official SSR first page is accessible; full pagination not verified')
 return jobs

def _didi(company,scope,f,cov):
 if scope!='social':
  from qiuzhao.collector.p1_sources_01_10 import collect_moka_sites
  sites=[('https://app.mokahr.com/campus-recruitment/didiglobal/96064','Official campus.didiglobal.com init-data org=didiglobal siteId=96064'),('https://app.mokahr.com/social-recruitment/didiglobal/6222','Official talent.didiglobal.com JS internship link apply/didiglobal/6222')]
  f.out.mkdir(parents=True,exist_ok=True)
  result=collect_moka_sites(company,scope,sites,f.out);cov.update(result['coverage']);f.evidence.extend(str(p) for p in f.out.glob('*.json'))
  cov['scope_request']={'company':company,'scope':scope,'source_url':SOURCES['didi'],'params':{'sites':[x[0] for x in sites],'orgId':'didiglobal','siteIds':[96064,6222]}}
  return result['jobs']
 cov['scope_request']={'company':company,'scope':scope,'source_url':SOURCES['didi'],'params':{'recruitType':1,'size':16}}
 cov['scope_evidence']='官方人才主站social/list/1频道；逐条详情recruitType=1核验，排除未核实的其他类型。'
 rows={};total=None;api='https://talent.didiglobal.com/recruit-portal-service/api/job/front/'
 for page in range(1,1001):
  text,path=f.get(api+'list?recruitType=1&size=16&page='+str(page),f'list-{page}')
  data=json.loads(text)
  if (data.get('meta') or {}).get('code')!=0:raise ValueError('official Didi API '+str(data.get('meta')))
  d=data['data'];cov['pages_scanned']+=1
  if total is None:total=int(d['total'])
  elif total!=int(d['total']):raise ValueError('Didi total changed during pagination')
  for r in d['items']:
   ident=str(r['jdId'])
   if ident in rows:raise ValueError('Didi duplicate ID across pages')
   rows[ident]=r
  if len(rows)==total:break
  if not d['items'] or len(rows)>total:raise ValueError('Didi pagination count mismatch')
  time.sleep(.15)
 else:raise ValueError('Didi page limit reached')
 cov['expected_total']=total
 def detail(ident):
  text,path=f.get(api+'view/'+ident,'detail-'+ident);d=json.loads(text)
  if (d.get('meta') or {}).get('code')!=0:raise ValueError('Didi detail failed '+ident)
  r=d['data']
  if str(r.get('recruitType'))!='1':raise ValueError('Didi detail scope mismatch '+ident)
  if not r.get('jdNo') or r['jdNo']!=rows[ident].get('jdNo'):raise ValueError('Didi detail JD number mismatch '+ident)
  try:desc,missing=role_body(r.get('jobDesc'),r.get('qualification'))
  except ValueError:
   missing_detail(cov,ident,r.get('jobName'),path);raise
  return job(company,'didi',ident,r['jobName'],'https://talent.didiglobal.com/social/p/'+ident,desc,scope,path,source_missing_fields=missing,cities=[r['workArea']] if r.get('workArea') else [],job_category=r.get('jobType',''),published_at=r.get('publishTime'),cohort_raw='')
 jobs=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  futures=[pool.submit(detail,k) for k in rows]
  for future in futures:
   try:jobs.append(future.result())
   except Exception as e:cov['errors'].append(str(e))
 # Official home also links the separate Global Professionals backend.
 try:
  f.get('https://cdncareers.didiglobal.com:34003/icims/searchJobList','global-list',{'country':'','keyValue':'','teamId':'','typeId':''})
  cov['errors'].append('Global Professionals list accessible; its detail/type schema needs validation before full company coverage')
 except Exception as e:cov['errors'].append('Global Professionals source unavailable: '+str(e))
 return jobs

def _lenovo(company,scope,f,cov):
 def listing(kind):
  url='https://jobs.lenovo.com/en_US/careers/'+kind;seen={};visited=set();official_total=None
  while url:
   if url in visited:raise ValueError('Lenovo repeated pagination URL')
   visited.add(url);text,path=f.get(url,kind+'-'+str(len(visited)));cov['pages_scanned']+=1
   soup=BeautifulSoup(text,'html.parser')
   tally=re.search(r'\d+\s*-\s*\d+\s+of\s+([\d,+]+)\s+jobs',soup.get_text(' ',strip=True))
   if tally and '+' not in tally.group(1):
    observed=int(tally.group(1).replace(',',''))
    if official_total is not None and observed!=official_total:raise ValueError('Lenovo total changed')
    official_total=observed
   links={a['href']:a.get_text(' ',strip=True) for a in soup.select('article h3 a[href], article h2 a[href]') if '/careers/JobDetail/' in a['href']}
   if not links:
    links={a['href']:a.get_text(' ',strip=True) for a in soup.select('a[href]') if re.match(r'https://jobs.lenovo.com/[^?]+/careers/JobDetail/[^?]+/\d+$',a['href']) and a.get_text(' ',strip=True)!='Apply'}
   if not links and '0 jobs' not in soup.get_text(' ',strip=True):raise ValueError('Lenovo listing missing valid job anchors')
   for link,title in links.items():
    ident=link.rstrip('/').rsplit('/',1)[1]
    if ident in seen:raise ValueError('Lenovo duplicate across pages')
    seen[ident]=(link,title)
   nxt=next((a['href'] for a in soup.select('a[href]') if a.get_text(' ',strip=True)=='Next >>'),None)
   if nxt and not nxt.startswith('https://jobs.lenovo.com/'):raise ValueError('Lenovo pagination host drift')
   url=nxt
   if len(visited)>1000:raise ValueError('Lenovo pagination limit')
   time.sleep(.1)
  if official_total is None:cov['errors'].append('Lenovo displays capped 999+ total; complete company coverage not proven')
  elif len(seen)!=official_total:raise ValueError('Lenovo unique count differs from official total')
  cov['last_page_evidence']=path;return seen
 university=listing('SearchJobsUniversity')
 if scope=='social':allrows=listing('SearchJobs');rows={k:v for k,v in allrows.items() if k not in university}
 else:
  rows={k:v for k,v in university.items() if bool(re.search(r'\bintern(?:ship)?\b|实习|praktik|working student|werkstudent',v[1],re.I))==(scope=='intern')}
 cov.update(expected_total=len(rows),pagination_exhausted=True,scope_evidence='官方University入口链接SearchJobsUniversity全分页；其中职位标题明确Intern/实习/Working student为实习，其余为早期职业校招；社会为官方全岗位列表扣除University名单。',scope_request={'company':company,'scope':scope,'source_url':SOURCES['lenovo'],'params':{'lists':['SearchJobsUniversity']+(['SearchJobs'] if scope=='social' else [])}})
 def detail(item):
  ident,(url,title)=item;text,path=f.get(url,'detail-'+ident);soup=BeautifulSoup(text,'html.parser');heading=next((x for x in soup.select('h3') if 'Description and Requirements' in x.get_text()),None)
  if heading is None:
   alternate=next((a['href'] for a in soup.select('a[href]') if a.get_text(' ',strip=True)=='日本語' and a['href'].startswith('https://jobs.lenovo.com/ja_JP/') and a['href'].rstrip('/').endswith('/'+ident)),None)
   if alternate:
    text,path=f.get(alternate,'detail-ja-'+ident);soup=BeautifulSoup(text,'html.parser');url=alternate;heading=next((x for x in soup.select('h3') if 'Description and Requirements' in x.get_text()),None)
  if heading is None:raise ValueError('Lenovo missing detail section in official languages '+ident)
  article=heading.find_parent('article');desc=article.get_text('\n',strip=True).removeprefix('Description and Requirements').strip()
  if not desc:raise ValueError('Lenovo empty job description '+ident)
  title_el=soup.select_one('.banner__text__title');title=title_el.get_text(' ',strip=True) if title_el else title
  plain=soup.get_text(' ',strip=True);city=re.search(r'City:\s*(.+?)\s*Date:',plain)
  return job(company,'lenovo',ident,title,url,desc,scope,path,cities=[city.group(1)] if city else [],cohort_raw='',cohort_scope='official_job_description')
 jobs=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for result in [pool.submit(detail,x) for x in rows.items()]:
   try:jobs.append(result.result())
   except Exception as e:cov['errors'].append(str(e))
 return jobs

def _hikvision(company,scope,f,cov):
 jobs=[];cov['_partial_jobs']=jobs;expected=0;cov['scope_evidence']='海康官网jobNature应届生/实习生，社会官网recruitType1社会3实习'
 if scope!='social':
  nature='应届生' if scope=='campus' else '实习生';total=None;seen=set()
  url='https://campushr.hikvision.com/api/search/crsPositionSearch/getPositionByQuery'
  for page in range(1,1001):
   params={'jobNature':nature,'pageNum':page,'pageSize':50,'batchId':'','postAdSnList':'','workPlaces':'','interviewMethodList':'','keyWord':''}
   r=requests.post(url,data=params,timeout=30);r.raise_for_status();data=r.json()
   if not data.get('success'):raise ValueError('Hikvision campus API '+str(data.get('message')))
   d=data['data'];cov['pages_scanned']+=1
   if total is None:total=int(d['total']);expected+=total
   elif total!=int(d['total']):raise ValueError('Hikvision campus total changed')
   keep=['id','batchId','batchName','postAdName','postAdSn','postContent','postRequire','jobNature','workPlaceList','workPlace','mergeType','updateTime','createTime','requiireEdu']
   rows=[{k:r.get(k) for k in keep} for r in d['list']]
   path=save(f.out/f'campus-{page}.json',{'request':params,'total':total,'rows':rows});f.evidence.append(path)
   for r in rows:
    ident=r['id']
    if ident in seen:raise ValueError('Hikvision campus duplicate ID')
    seen.add(ident)
    if r.get('jobNature')!=('校招应届生' if scope=='campus' else '校招实习生'):cov['errors'].append('Hikvision source type mismatch '+ident);continue
    try:desc,missing=role_body(r.get('postContent'),r.get('postRequire'))
    except ValueError as e:
     missing_detail(cov,ident,r.get('postAdName'),path);cov['errors'].append(str(e)+' '+ident);continue
    detail=f'https://campushr.hikvision.com/JobDetails.html?id={ident}&type={r["mergeType"]}'
    cohort='；'.join(re.findall(r'[^。\n]*(?:20\d{2}届|毕业)[^。\n]*',desc))
    jobs.append(job(company,'hikvision',ident,r['postAdName'],detail,desc,scope,path,source_missing_fields=missing,cities=r.get('workPlaceList') or [],cohort_raw='',campaign_name=r.get('batchName') or '',cohort_scope='official_job_description',job_category=r.get('postAdSn') or '',education_raw=r.get('requiireEdu') or ''))
   if len(seen)==total:break
   if not rows or len(seen)>total:raise ValueError('Hikvision campus pagination mismatch')
  else:raise ValueError('Hikvision campus pagination limit')
 if scope in ('social','intern'):
  host='https://talent.hikvision.com';typ='1' if scope=='social' else '3'
  text,configpath=f.get(host+'/api/ats/official/officialConfig/rest/getConfigInfo?domainStr=talent.hikvision.com','society-config');config=json.loads(text)
  company_id=config['data']['officialSubjInfoVo']['companyId'];rows={};total=None
  for page in range(1,1001):
   text,path=f.get(host+'/api/ats/official/officialPostPosition/getPostInfoForSys','society-list-'+str(page),{'pageNum':page,'pageSize':50,'companyId':'','recruitType':typ})
   data=json.loads(text)
   if not data.get('success'):raise ValueError('Hikvision social API '+str(data.get('message')))
   d=data['data'];cov['pages_scanned']+=1
   if total is None:total=int(d['total']);expected+=total
   elif total!=int(d['total']):raise ValueError('Hikvision social total changed')
   for r in d['list']:
    ident=r['postSecureId']
    if ident in rows:raise ValueError('Hikvision repeated social ID')
    rows[ident]=r
   if len(rows)==total:break
   if not d['list'] or len(rows)>total:raise ValueError('Hikvision social pagination mismatch')
  else:raise ValueError('Hikvision social page limit')
  def detail(ident):
   url=host+'/api/ats/official/officialPostPosition/findAdDetailInfo?'+requests.compat.urlencode({'adIdStr':ident,'companyId':company_id})
   response=requests.get(url,timeout=30);response.raise_for_status();data=response.json()
   if not data.get('success'):raise ValueError('Hikvision detail rejected '+ident)
   raw=data['data']['ad'];keep=['postName','recruitType','company','department','locationDesc','workingYears','postDesc','qualifications','education','adIdStr','postIdStr','createdon','modifiedon','endTime']
   r={k:raw.get(k) for k in keep};path=save(f.out/('society-detail-'+ident+'.json'),{'request':{'adIdStr':ident,'companyId':company_id},'ad':r});f.evidence.append(path)
   if r['adIdStr']!=ident or str(r['recruitType'])!=typ:raise ValueError('Hikvision detail identity/scope mismatch '+ident)
   try:desc,missing=role_body(r.get('postDesc'),r.get('qualifications'))
   except ValueError:
    missing_detail(cov,ident,r.get('postName'),path);raise
   j=job(company,'hikvision',ident,r['postName'],host+'/society/position?postId='+ident,desc,scope,path,source_missing_fields=missing,cities=[r['locationDesc']] if r.get('locationDesc') else [],education_raw=r.get('education') or '',published_at=r.get('createdon'),cohort_raw='',cohort_scope='official_job_description')
   j['recruiting_unit_raw']=r.get('company') or company;return j
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
   futures=[pool.submit(detail,x) for x in rows]
   for result in futures:
    try:jobs.append(result.result())
    except Exception as e:cov['errors'].append(str(e))
 cov.update(expected_total=expected,scope_evidence='官方jobNature校招应届生/校招实习生；不加批次限制；另社会官网recruitType1=社会3=实习，详情逐条验证类型及adIdStr。',scope_request={'company':company,'scope':scope,'source_url':SOURCES['hikvision'],'params':{'jobNature':('应届生' if scope=='campus' else '实习生') if scope!='social' else None,'pageSize':50,'batchId':'','society_recruitType':'1' if scope=='social' else ('3' if scope=='intern' else None)}})
 return jobs

def _ctrip(company,scope,f,cov):
 sources=[('https://careers.ctrip.com','/api/hrrecruit/getJobAd',{'category':2},'campus'),('https://careers.ctrip.com','/api/hrrecruit/getJobAd',{'category':1},'social'),('https://careers.trip.com','/api/oversea/getOverseaJobAd',{},'global')]
 rows={};campus_ids=set()
 for host,endpoint,condition,route in sources:
  seen=set();total=None
  for page in range(1,1001):
   text,path=f.get(host+endpoint,route+'-list-'+str(page),{'condition':condition,'pager':{'index':page,'size':100}});data=json.loads(text)
   if str(data.get('retCode'))!='201':raise ValueError('Trip.com API '+str(data.get('retMessage')))
   d=data['retValue'];cov['pages_scanned']+=1
   if total is None:total=int(d['total'])
   elif total!=int(d['total']):raise ValueError('Trip.com list total changed')
   keep=['id','fromId','jobId','jobTitle','publishDate','city','cityName','requirements','duty','jobFamilyGroupCode','jobFamilyGroupName','buCode','buName','kind','kindName','atsApiType','category']
   batch=[{k:r.get(k) for k in keep} for r in d['recruitJobAdList']]
   Path(path).write_text(json.dumps({'request':{'condition':condition,'pager':{'index':page,'size':100}},'retCode':'201','retValue':{'total':total,'recruitJobAdList':batch}},ensure_ascii=False))
   for r in batch:
    ident=str(r.get('jobId') or r['id'])
    if ident in seen:raise ValueError('Trip.com repeated ID in pagination')
    seen.add(ident)
    if route=='campus':campus_ids.add(ident)
    # Same stable ATS job can be published on domestic and global websites.
    if ident not in rows:rows[ident]=(r,host,route,path)
   if len(seen)==total:break
   if not batch or len(seen)>total:raise ValueError('Trip.com pagination count mismatch')
  else:raise ValueError('Trip.com page limit')
 jobs=[];selected=0
 for ident,(r,host,route,path) in rows.items():
  kind=str(r.get('kind') or '')
  actual='intern' if kind in ('3','Intern_Short_Term') else ('campus' if ident in campus_ids else ('social' if kind in ('1','Regular','Contract','Temporary') else None))
  if actual is None:
   if scope!='campus':cov['errors'].append('Unspecified official recruitment type '+ident)
   continue
  if actual!=scope:continue
  selected+=1;desc='\n\n'.join(clean(r.get(k)) for k in ('duty','requirements') if r.get(k))
  if not desc:cov['errors'].append('Trip.com empty official detail '+ident);continue
  if route=='global':url=host+'/#/job-detail?'+requests.compat.urlencode({'fromId':r['fromId'],'atsApiType':r.get('atsApiType') or ''})
  else:url=host+'/#/'+('campus' if actual=='campus' else 'experienced')+'/job-detail/'+str(r['fromId'])
  cohort='；'.join(re.findall(r'[^。\n]*(?:20\d{2}届|毕业|20\d{2} Graduates)[^。\n]*',desc,re.I))
  jobs.append(job(company,'ctrip',ident,r['jobTitle'],url,desc,scope,path,cities=[r['cityName']] if r.get('cityName') else [],job_category=r.get('jobFamilyGroupName') or '',published_at=r.get('publishDate'),cohort_raw='',cohort_scope='official_job_description'))
 cov.update(expected_total=selected,list_total=len(rows),scope_evidence='携程官网condition.category2为校招、1为社会；kind3及Intern_Short_Term为实习。海外官网Regular为社会；未写类型不猜。所有列表返回完整requirements正文。',scope_request={'company':company,'scope':scope,'source_url':SOURCES['ctrip'],'params':{'sources':[{'host':h,'endpoint':e,'condition':c} for h,e,c,r in sources],'pager_size':100}})
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
  elif slug=='bilibili':jobs=_bilibili(company,scope,f,cov)
  elif slug=='baidu':jobs=_baidu(company,scope,f,cov)
  elif slug=='didi':jobs=_didi(company,scope,f,cov)
  elif slug=='lenovo':jobs=_lenovo(company,scope,f,cov)
  elif slug=='hikvision':jobs=_hikvision(company,scope,f,cov)
  elif slug=='ctrip':jobs=_ctrip(company,scope,f,cov)
  elif slug=='insta360':
   from qiuzhao.collector.p1_feishu_public import collect_feishu
   sites=[{'url':'https://arashivision.jobs.feishu.cn/'+path+'/position/list','tenant_names':['影石创新科技股份有限公司'],'portal_type':6} for path in ['campus','social']]
   result=collect_feishu(company,scope,sites,out);save(out/'candidate.json',result);return result
  else:
   f.get(SOURCES[slug],'official-entry');raise ValueError('Official entry checked; full scoped list/detail contract not yet verified')
 except Exception as e:
  cov['errors'].append(str(e));jobs=cov.get('_partial_jobs',jobs)
 cov.pop('_partial_jobs',None)
 cov['collected_jobs']=len(jobs);cov['evidence']=f.evidence;cov['evidence_files']=f.evidence
 cov.setdefault('scope_request',{'company':company,'scope':scope,'source_url':SOURCES[slug],'params':{'hireType':[1,0],'channelDetailIds':[1]} if slug=='mihoyo' else ({'websiteIds':['6962795203808168199','6962795203808217351','7005456241946331399','7069578816822282503','7268177039772633400'],'page_size':10,'job_function_id_list':[],'city_code_list':[],'keyword':'','job_lang_list':[]} if slug=='anker' else {'route':'social' if scope=='social' else 'campus','pageIndex':1,'pageSize':20,'channel':'group_official_site' if scope=='social' else 'campus_group_official_site','language':'zh_CN'} )})
 cov['source_missing_field_counts']={name:sum(name in j.get('source_missing_fields',[]) for j in jobs) for name in ['description','requirement']}
 cov['complete']=not cov['errors'] and ((cov['expected_total'] is not None and len(jobs)==cov['expected_total']) or (cov['expected_total'] is None and cov.get('pagination_exhausted') is True and cov.get('unique_source_ids')==len(jobs) and bool(cov.get('last_page_evidence'))))
 cov['detail_complete']=cov['complete'];cov['status']='success' if cov['complete'] else ('partial' if jobs else 'blocked')
 result={'jobs':jobs,'coverage':cov};save(out/'candidate.json',result);save(out/'coverage.json',cov);return result
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('company');parser.add_argument('--scope',choices=TYPES);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
 for scope in ([args.scope] if args.scope else TYPES):
  r=collect(args.company,scope,args.output_dir);print(json.dumps({'company':args.company,'scope':scope,**{k:v for k,v in r['coverage'].items() if k not in {'evidence','evidence_files'}}},ensure_ascii=False),flush=True)
