"""Rebuild schema fields from saved official details; does not claim a new crawl."""
import importlib.util,json,pathlib,sys
root=pathlib.Path(__file__).parent;repo=root.parents[2]
spec=importlib.util.spec_from_file_location('batch',repo/'qiuzhao/collector/p1_sources_01_10.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.path.insert(0,str(repo));from qiuzhao.v4_fields import graduation_of
for company in m.COMPANIES:
 for p in (root/company).glob('*/result.json'):
  r=json.loads(p.read_text());c=r['coverage'];scope=p.parent.name
  if not c.get('complete'):continue
  for j in r['jobs']:
   f=p.parent/('detail-'+j['source_record_id']+'.json')
   raw=json.loads(f.read_text()) if f.exists() else {}
   if company in ('vivo','byd'):raw=raw.get('Data',raw.get('data',raw))
   update=m.job(company,scope,j['source_record_id'],j['job_title'],j['detail_url'],j['description_raw'],j.get('location',''),raw)
   for key in ['cities','education_raw','major_requirements_raw','experience_raw','deadline_raw','source_fields']:
    if update.get(key) or not j.get(key):j[key]=update.get(key)
   if company in ('dji','catl'):
    j['cohort_raw']=''
    if j.get('campaign_scope')!='job_specific':j['campaign_cohort_raw']=(raw.get('projectFolder') or {}).get('name') or '';j['campaign_scope']='project';j['campaign_url']=j['detail_url'].split('#')[0]
   if company=='oppo' and scope!='social':j['campaign_cohort_raw']=raw.get('projectName') or j.get('cohort_raw','');j['campaign_scope']='project';j['cohort_raw']=''
   if company=='vivo' and scope!='social':
    link='https://hr-campus.vivo.com/'+scope+'/detail?jobAdId='+j['source_record_id']
    for key in ['source_url','application_url','detail_url']:j[key]=link
   ys,basis,_,_=graduation_of(j);j['graduation_years']=[y for y in ys if y[:2]=='20'];j['graduation_year_evidence']={y:basis[y] for y in j['graduation_years']};j['graduation_year_verification']='source_verified' if j['graduation_years'] and all(basis[y] in ['岗位写明','活动标题写明'] for y in j['graduation_years']) else 'inferred' if j['graduation_years'] else 'unspecified'
  if company=='vivo':params={'PortalId':'903cbcbf-4898-46e1-817c-da522a9752b1','PageIndex':0,'PageSize':50,'local_scope_filter':scope} if scope!='social' else {'company_id':1,'group_id':1,'max_results':30,'page':1}
  elif company=='byd':
   cfgfile=p.parent/'source-config.json';cfg=json.loads(cfgfile.read_text())['data'] if cfgfile.exists() else []
   params={'source_configs':cfg,'pageSize':50,'pageIndex':1} if scope!='social' else {'zpType':['00251','00254'],'pageNum':0,'pageSize':50}
  elif company in ('dji','catl'):params={'orgId':'catlhr' if company=='catl' else 'dji','siteId':[148948,143035,142992,96144,142774,98098] if company=='catl' else [143359,168240,170070],'limit':50,'offset':0,'needStat':True,'local_scope_filter':scope}
  elif company=='pdd':params={'endpoint':'api/recruit/position/train/list' if scope=='intern' else 'api/recruit/position/list','page':1,'pageSize':20}
  else:params={'pageNum':1,'pageSize':50,**({'recruitType':scope} if company=='xiaohongshu' else {'local_scope_filter':scope})}
  c['scope_request']={'company':m.COMPANIES[company],'scope':scope,'source_url':c['source_url'],'params':params}
  p.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(company,scope,len(r['jobs']),'education',sum(bool(x.get('education_raw')) for x in r['jobs']),'major',sum(bool(x.get('major_requirements_raw')) for x in r['jobs']))
