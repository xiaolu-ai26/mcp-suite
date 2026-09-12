"""Official public recruitment sources for priority companies 21–30."""
from __future__ import annotations
import json,re,time,concurrent.futures
from pathlib import Path
import requests
from qiuzhao.collector.p1_sources_11_20 import Fetcher,job,save,clean,TYPES,role_body,missing_detail
COMPANIES={'鹰角网络':'hypergryph','叠纸游戏':'papergames','莉莉丝游戏':'lilith','完美世界':'pwrd','三七互娱':'37','巨人网络':'ztgame','金山办公':'wps','用友网络':'yonyou','金蝶':'kingdee','科大讯飞':'iflytek'}
MOKA={
 'hypergryph':[('https://app.mokahr.com/campus-recruitment/hypergryph/26326','Official career.hypergryph.com links campus_apply/hypergryph/26326'),('https://app.mokahr.com/social-recruitment/hypergryph/26325','Official career.hypergryph.com links apply/hypergryph/26325')],
 'pwrd':[('https://app.mokahr.com/campus-recruitment/pwrd/'+str(i),'Official jobs.games.wanmei.com topbar.js/school.html linked project') for i in [172467,140155,144582,150080]]+[('https://app.mokahr.com/social-recruitment/pwrd/142341','Official jobs.games.wanmei.com/society.html links full social portal')],
 'ztgame':[('https://app.mokahr.com/social-recruitment/ztgame/37485','Official hr.ztgame.com/campus redirects to Moka org=ztgame/siteId37485'),('https://app.mokahr.com/campus-recruitment/ztgame/92438','Current official Moka portal identity matches ztgame; prior verified campus source')],
 '37':[('https://app.mokahr.com/campus-recruitment/37/58016','Official zhaopin.37.com recruit page campus link')],
 'wps':[('https://join.wps.cn/campus-recruitment/wps/41436','Official join.wps.cn redirect; source/referral parameters removed'),('https://app.mokahr.com/social-recruitment/wps/3471','Official www.wps.cn/learning/article/detail/id/330332 names m/apply/wps/3471; live identity rechecked')],
 'kingdee':[('https://campus.kingdee.com/campus-recruitment/kingdeehr/166565','Official campus.kingdee.com public site')],
}
# Official shared saas-career SDK mapping: g.SaasCareer -> portal_type 6.
# Verified in public 5615.cdc43769.js and anonymous automatic requests.
FEISHU={
 'papergames':[{'url':'https://career.papegames.com/campus/position/list','tenant_names':['Papergames'],'portal_type':6},{'url':'https://career.papegames.com/social/position/list','tenant_names':['Papergames'],'portal_type':6}],
 'lilith':[{'url':'https://lilithgames.jobs.feishu.cn/'+path+'/position/list','tenant_names':['莉莉丝'],'portal_type':6} for path in ['campus','career','intern']],
}

def collect_yonyou(company,scope,out):
 f=Fetcher(out/'evidence');host='https://career.yonyou.com';suite='SU67ac41886202cc7916ae3029'
 c={'status':'blocked','complete':False,'expected_total':None,'collected_jobs':0,'pages_scanned':0,'detail_complete':False,'source_url':host,'errors':[],'evidence':[],'evidence_files':[],'scope_evidence':'官方Dayee JS recruitType1校招、2社会、12实习、13海外；详情同ID同类型核验。','scope_request':{'company':company,'scope':scope,'source_url':host,'params':{'suite':suite,'recruitTypes':[2,13] if scope=='social' else [1 if scope=='campus' else 12]}}}
 jobs={};expected_ids=set()
 def api(path,params,name):
  url=host+'/wecruit'+path+'?iSaJAx=isAjax&request_locale=zh_CN';r=requests.post(url,data=params,timeout=30);r.raise_for_status();d=r.json()
  if str(d.get('state'))!='200':raise ValueError('Dayee public API rejected '+str(d.get('msg')))
  return d['data']
 try:
  text,path=f.get(host+'/'+suite+'/pb/index.html','official-entry')
  for typ in c['scope_request']['params']['recruitTypes']:
   rows={};total=None;page_size=50
   for page in range(1,1001):
    params={'isFrompb':'true','recruitType':typ,'pageSize':page_size,'currentPage':page};d=api('/positionInfo/listPosition/'+suite,params,f'{typ}-list-{page}');form=d['pageForm'];batch=form.get('pageData') or [];n=int(form['dataCount']);actual_size=int(form['pageSize'])
    if page>1 and actual_size!=page_size:raise ValueError('Dayee page size changed mid-pagination')
    page_size=actual_size
    if total is None:total=n
    elif n!=total:raise ValueError('Dayee total changed')
    keep=['postId','postName','recruitType','workPlaceStr','educationStr','company','currentSuiteKey','projectName','projectId','workTypeStr','publishDate','endDate','longTermRelease']
    path=save(f.out/f'{typ}-list-{page}.json',{'request':params,'count':total,'rows':[{k:r.get(k) for k in keep} for r in batch]});f.evidence.append(path);c['pages_scanned']+=1
    for r in batch:
     ident=r['postId']
     if ident in rows:raise ValueError('Dayee repeated ID across pages')
     if str(r.get('recruitType'))!=str(typ) or r.get('currentSuiteKey')!=suite[2:]:raise ValueError('Dayee list tenant/type mismatch')
     rows[ident]=r;expected_ids.add(ident)
    if len(rows)==total:break
    if not batch or len(rows)>total:raise ValueError('Dayee pagination mismatch')
   else:raise ValueError('Dayee pagination limit')
   def detail(item):
    ident,summary=item;r=api('/positionInfo/listPositionDetail/'+suite,{'postId':ident},'detail-'+ident)
    if r.get('postId')!=ident or str(r.get('recruitType'))!=str(typ):raise ValueError('Dayee detail identity/type mismatch '+ident)
    keep=['postId','postName','recruitType','workContent','serviceCondition','workPlaceList','workPlaceStr','educationStr','company','projectName','projectId','publishDate','endDate','longTermRelease']
    path=save(f.out/('detail-'+ident+'.json'),{k:r.get(k) for k in keep});f.evidence.append(path)
    try:desc,missing=role_body(r.get('workContent'),r.get('serviceCondition'))
    except ValueError:
     missing_detail(c,ident,r.get('postName'),path);raise
    posttype={1:'campus',2:'society',12:'intern',13:'overseas'}[typ];url=host+'/'+suite+'/pb/posDetail.html?postId='+ident+'&postType='+posttype
    cohort='；'.join(re.findall(r'[^。\n]*(?:20\d{2}\s*届|毕业)[^。\n]*',desc))
    j=job(company,'yonyou',ident,r['postName'],url,desc,scope,path,source_missing_fields=missing,cities=[x['name'] for x in r.get('workPlaceList') or []],education_raw=r.get('educationStr') or summary.get('educationStr') or '',cohort_raw='',cohort_scope='official_job_description',batch_name=r.get('projectName') or '',published_at=r.get('publishDate'))
    j['recruiting_unit_raw']=r.get('company') or company
    if not r.get('longTermRelease') and r.get('endDate'):j.update(deadline=r['endDate'][:10],deadline_type='explicit')
    return j
   with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for future in [pool.submit(detail,x) for x in rows.items()]:
     try:r=future.result();jobs[r['source_record_id']]=r
     except Exception as e:c['errors'].append(str(e))
  c['expected_total']=len(expected_ids)
 except Exception as e:c['errors'].append(str(e))
 c.update(collected_jobs=len(jobs),evidence_files=f.evidence,evidence=f.evidence,detail_complete=c['expected_total'] is not None and len(jobs)==c['expected_total'] and not c['errors'])
 c['complete']=c['detail_complete'];c['status']='success' if c['complete'] else ('partial' if jobs else 'blocked');return {'jobs':list(jobs.values()),'coverage':c}

def collect_kingdee_extra(company,scope,out):
 from bs4 import BeautifulSoup
 import hashlib
 f=Fetcher(out/'evidence');jobs=[];errors=[];pages=0;seen=set();api='https://www.kingdee.com/cmsadmin/recruit/queryJobList'
 def api_page(payload,name):
  response=requests.post(api,json=payload,timeout=30);response.raise_for_status();raw=response.json()
  if raw.get('code')!=200:raise ValueError('Kingdee CMS API rejected')
  # Contact-person fields are not needed for job evidence.
  for row in raw['data']['content']:
   for key in list(row):
    if key.startswith('contact'):row.pop(key)
  path=save(f.out/(name+'.json'),raw);f.evidence.append(path);return raw['data'],path
 try:
  page=1;total=None
  while True:
   data,path=api_page({'page':page,'size':50,'campus':False},f'list-{page}');pages+=1
   if total is None:total=int(data['size'])
   elif int(data['size'])!=total:raise ValueError('Kingdee CMS total changed')
   for row in data['content']:
    ident=str(row['id'])
    if ident in seen:raise ValueError('Kingdee CMS duplicate ID')
    seen.add(ident)
    if row.get('campus') is not False or '金蝶' not in row.get('companyName',''):raise ValueError('Kingdee CMS company/scope mismatch')
    actual='intern' if row.get('jobNature')=='实习' else ('social' if row.get('jobNature')=='全职' else None)
    if actual is None:errors.append('Kingdee unknown jobNature '+str(row.get('jobNature')));continue
    if actual!=scope:continue
    detail,dp=api_page({'id':ident,'campus':False,'page':1,'size':1},'detail-'+ident)
    if len(detail['content'])!=1 or str(detail['content'][0].get('id'))!=ident:raise ValueError('Kingdee detail ID mismatch')
    r=detail['content'][0];desc,missing=role_body(r.get('jobDescription'),'')
    jobs.append(job(company,'kingdee','cms-'+ident,r['jobTitle'],'https://www.kingdee.com/zpxq1?id='+ident+'&social=false',desc,scope,dp,source_missing_fields=missing,cities=[r['jobCity']] if r.get('jobCity') else [],education_raw=r.get('demandEducation',''),recruitment_unit=r['companyName'],published_at=r.get('jobStartDate'),status='unverified',source_recruitment_type=r.get('jobNature'),listing_evidence_path=path))
   if len(seen)==total:break
   if not data['content'] or len(seen)>total:raise ValueError('Kingdee CMS pagination mismatch')
   page+=1
  text,path=f.get('https://www.kingdee.com.hk/join-us/','hongkong-page');soup=BeautifulSoup(text,'html.parser')
  titles=soup.select('.elementor-tab-title')
  if not titles:raise ValueError('Kingdee HK public role accordion missing')
  for title in titles:
   body=soup.find(id=title.get('aria-controls'));name=title.get_text(' ',strip=True)
   if not body or not body.get_text(strip=True):continue
   desc=body.get_text('\n',strip=True)
   if scope=='social':
    ident='hk-'+hashlib.sha256(name.encode()).hexdigest()[:16]
    if any(j['source_record_id']==ident for j in jobs):continue
    jobs.append(job(company,'kingdee',ident,name,'https://www.kingdee.com.hk/join-us/',desc,scope,path,cities=['香港'],status='unverified',source_recruitment_type='Kingdee Hong Kong Join Us',scope_grouping_note='香港官网 Join Us 常规招聘职位；正文欢迎应届不等同校园专项。'))
  for base in ['https://www.kingdee.com/global/careers/','https://www.kingdee.com/sg/zh-hans/careers/','https://www.kingdee.com/mo/careers/']:
   queue=[base];visited=set();source_ids=set();expected_pages=None;page_numbers=set()
   while queue:
    url=queue.pop(0)
    if url in visited:continue
    visited.add(url)
    try:
     text,path=f.get(url,'global-'+hashlib.sha256(url.encode()).hexdigest()[:8]);pages+=1;soup=BeautifulSoup(text,'html.parser');items=soup.select('.accordion-item')
     plain=soup.get_text(' ',strip=True);match=re.search(r'Page\s+(\d+)\s+of\s+(\d+)',plain,re.I) or re.search(r'第\s*(\d+)\s*[页頁][，,]共\s*(\d+)\s*[页頁]',plain)
     if not match:raise ValueError('Regional official page-count evidence missing')
     page_number,page_count=map(int,match.groups())
     if expected_pages is not None and expected_pages!=page_count:raise ValueError('Regional page count changed')
     if page_number in page_numbers:raise ValueError('Regional duplicate page content')
     expected_pages=page_count;page_numbers.add(page_number)
     if not items:raise ValueError('Official regional careers accordion absent')
     for item in items:
      title=item.select_one('.accordion-header h3');body=item.select_one('.accordion-body .document');apply=item.select_one('[data-bs-target^="#ApplicationModal"]')
      if not title or not body or not apply:raise ValueError('Regional role identity/body missing')
      rawid=apply['data-bs-target'].replace('#ApplicationModal','');ident='regional-'+hashlib.sha256(base.encode()).hexdigest()[:8]+'-'+rawid
      if ident in source_ids:raise ValueError('Regional repeated ID across pages')
      source_ids.add(ident);name=title.get_text(' ',strip=True);actual='intern' if re.search(r'实习|實習|intern',name,re.I) else 'social'
      if actual!=scope:continue
      for button in body.select('a'):button.decompose()
      desc=body.get_text('\n',strip=True)
      if not desc:raise ValueError('Regional official body empty '+ident)
      info=[x.get_text(' ',strip=True) for x in item.select('.acc-info li span')]
      jobs.append(job(company,'kingdee',ident,name,url,desc,scope,path,cities=info[2:3],published_at=info[1] if len(info)>1 else None,status='unverified',source_recruitment_type='Regional careers',source_record_id_raw=rawid))
     for anchor in soup.select('.pagination a[href]'):
      href=anchor['href']
      if href.startswith(base) and href not in visited and href not in queue:queue.append(href)
    except Exception as e:errors.append(str(e)+' '+url)
   if expected_pages is None or page_numbers!=set(range(1,expected_pages+1)):errors.append('Regional pagination not exhausted '+base)

 except Exception as e:errors.append(str(e))
 complete=not errors
 c={'status':'success' if complete else ('partial' if jobs else 'blocked'),'complete':complete,'expected_total':len(jobs) if complete else None,'collected_jobs':len(jobs),'pages_scanned':pages,'detail_complete':complete,'source_url':'https://www.kingdee.com/job/social','errors':errors,'evidence':f.evidence,'evidence_files':f.evidence,'scope_evidence':'官方当前社会页面CMS campus=false，jobNature全职/实习；香港Join Us常规招聘；其他国际入口单独记录可达性。','scope_request':{'company':company,'scope':scope,'source_url':'https://www.kingdee.com/job/social','params':{'api':api,'page':1,'size':50,'campus':False}}}
 return {'jobs':jobs,'coverage':c}

def collect(company:str,scope:str,output_dir:Path)->dict:
 if company not in COMPANIES or scope not in TYPES:raise ValueError('invalid company/scope')
 slug=COMPANIES[company];out=Path(output_dir).resolve()/slug/scope;out.mkdir(parents=True,exist_ok=True)
 if slug in MOKA:
  from qiuzhao.collector.p1_sources_01_10 import collect_moka_sites
  evidence=out/'evidence';evidence.mkdir(exist_ok=True);jobs={};parts=[]
  for index,site in enumerate(MOKA[slug]):
   folder=evidence/str(index);folder.mkdir(exist_ok=True)
   part=collect_moka_sites(company,scope,[site],folder);parts.append(part['coverage'])
   for row in part['jobs']:jobs.setdefault(row['source_record_id'],row)
  complete=all(p['complete'] for p in parts);errors=[e for p in parts for e in p['errors']]
  c={'status':'success' if complete else ('partial' if jobs else 'blocked'),'complete':complete,'expected_total':len(jobs) if complete else None,'collected_jobs':len(jobs),'pages_scanned':sum(p['pages_scanned'] for p in parts),'detail_complete':complete,'source_url':MOKA[slug][0][0],'errors':errors,'scope_evidence':' ; '.join(p.get('scope_evidence','') for p in parts),'source_coverage':parts}
  result={'jobs':list(jobs.values()),'coverage':c}
  c['evidence_files']=[str(p) for p in evidence.rglob('*.json')];c['evidence']=c['evidence_files'];c['scope_request']={'company':company,'scope':scope,'source_url':MOKA[slug][0][0],'params':{'sites':[x[0] for x in MOKA[slug]],'scope':scope,'limit':50,'needStat':True}}
  c['scope_evidence']=c.get('scope_evidence') or 'Official Moka hireMode and commitment filter; verified sites listed in scope_request'
  for r in result['jobs']:
   snippets=job(company,slug,r['source_record_id'],r['job_title'],r['detail_url'],r['description_raw'],scope,r.get('evidence_path',''))
   for k in ['major_requirements_raw','education_raw']:
    if not r.get(k):r[k]=snippets[k]
 elif slug in FEISHU:
  from qiuzhao.collector.p1_feishu_public import collect_feishu
  result=collect_feishu(company,scope,FEISHU[slug],out)
 elif slug=='yonyou':
  result=collect_yonyou(company,scope,out)
 elif slug=='iflytek':
  from qiuzhao.collector.p1_sources_31_40 import collect_beisen
  result=collect_beisen(company,scope,'https://iflytek.zhiye.com',out,category_mapping={'4':'campus','5':'campus','6':'intern','7':'intern'})
  scoped_rows=[]
  for row in result['jobs']:
   source=row.get('source_fields') or {}
   row['source_recruitment_category']=source.get('Category')
   if source.get('Category')=='校园大使':row['scope_grouping_note']='官网分类为校园大使；产品归入实习/在校实践检索分组，原始分类不改写。'
   if source.get('Category')=='星火X顶尖AI人才计划' and source.get('Kind')!='实习':
    result['coverage']['errors'].append('Custom StarX category Kind changed; scope mapping requires revalidation')
    result['coverage'].update(complete=False,status='partial',detail_complete=False)
    continue
   scoped_rows.append(row)
  result['jobs']=scoped_rows;result['coverage']['collected_jobs']=len(scoped_rows)
 else:raise NotImplementedError('Source adapter is still being investigated; not an external blocker')
 if slug=='kingdee':
  extra=collect_kingdee_extra(company,scope,out/'additional');parts=[result['coverage'],extra['coverage']];merged={r['source_record_id']:r for part in [result,extra] for r in part['jobs']};complete=all(c['complete'] for c in parts)
  result={'jobs':list(merged.values()),'coverage':{'status':'success' if complete else ('partial' if merged else 'blocked'),'complete':complete,'expected_total':len(merged) if complete else None,'collected_jobs':len(merged),'pages_scanned':sum(c['pages_scanned'] for c in parts),'detail_complete':complete,'source_url':'https://www.kingdee.com/job','errors':[e for c in parts for e in c['errors']],'evidence_files':[e for c in parts for e in c['evidence_files']],'evidence':[e for c in parts for e in c['evidence_files']],'scope_evidence':'Official campus Moka plus current China CMS and Hong Kong careers. All source types preserved.','scope_request':{'company':company,'scope':scope,'source_url':'https://www.kingdee.com/job','params':{'sources':[c['scope_request'] for c in parts]}},'source_coverage':parts}}
 if slug=='37' and scope!='campus':
  from qiuzhao.collector.p1_sources_31_40 import collect_beisen
  extra=collect_beisen(company,scope,'https://37wan.zhiye.com',out/'beisen')
  for key in ['evidence_files','evidence']:
   extra['coverage'][key]=[str((out/'beisen'/p).resolve()) if not Path(p).is_absolute() else p for p in extra['coverage'].get(key,[])]
  last=extra['coverage'].get('last_page_evidence')
  if isinstance(last,str) and not Path(last).is_absolute() and (out/'beisen'/last).is_file():extra['coverage']['last_page_evidence']=str((out/'beisen'/last).resolve())
  merged={r['source_record_id']:r for part in [result,extra] for r in part['jobs']};parts=[result['coverage'],extra['coverage']];complete=all(c['complete'] for c in parts)
  result={'jobs':list(merged.values()),'coverage':{'status':'success' if complete else ('partial' if merged else 'blocked'),'complete':complete,'expected_total':len(merged) if complete else None,'collected_jobs':len(merged),'pages_scanned':sum(c['pages_scanned'] for c in parts),'detail_complete':complete,'source_url':'https://zhaopin.37.com','errors':[e for c in parts for e in c['errors']],'evidence_files':[e for c in parts for e in c['evidence_files']],'evidence':[e for c in parts for e in c['evidence_files']],'scope_evidence':'Official zhaopin.37.com campus Moka link and social role Apply link to37wan.zhiye.com; both source enums verified.','scope_request':{'company':company,'scope':scope,'source_url':'https://zhaopin.37.com','params':{'sources':[c['scope_request'] for c in parts]}},'source_coverage':parts}}
 save(out/'candidate.json',result);save(out/'coverage.json',result['coverage']);return result
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('company');p.add_argument('--scope',choices=TYPES);p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args()
 for scope in ([a.scope] if a.scope else TYPES):
  r=collect(a.company,scope,a.output_dir);c=r['coverage'];print(json.dumps({'company':a.company,'scope':scope,'jobs':len(r['jobs']),'status':c['status'],'errors':c['errors']},ensure_ascii=False),flush=True)
