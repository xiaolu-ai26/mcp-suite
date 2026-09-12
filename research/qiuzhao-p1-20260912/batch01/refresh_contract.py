"""Rebuild field aliases from this run's saved complete official responses."""
import json,pathlib,re
root=pathlib.Path(__file__).parent
for company in ['pdd','dji']:
 for scope in ['campus','intern','social']:
  directory=root/company/scope;p=directory/'result.json'
  if not p.exists():continue
  r=json.loads(p.read_text());c=r['coverage']
  for j in r['jobs']:
   j['job_title']=j['title'];j['reviewed_at']=j['verified_at'];j.setdefault('education_raw','');j.setdefault('major_requirements_raw','');j.setdefault('cohort_raw',str(j.get('graduation_year_raw',''))+'届' if j.get('graduation_year_raw') else '')
   j.pop('requirements_raw',None)
   j['cities']=[x.strip() for x in re.split(r'\s*/\s*|[，,、;；]',j.get('location','')) if x.strip()]
   raw=j.get('source_fields') or {}
   if company=='dji':
    project=raw.get('projectFolder') or {};j['cohort_raw']=project.get('name') or '';j['recruitment_type_raw']={'hireMode':raw.get('hireMode'),'commitment':raw.get('commitment')}
    if '校园大使' in j['job_title'] and scope=='social':j['recruitment_type_conflict']='Official hireMode=1 (social), title names campus ambassador; retain source classification for review'
  c['scope_evidence']='; '.join(dict.fromkeys(j['scope_evidence'] for j in r['jobs']))
  c['evidence_files']=[f.name for f in directory.glob('*list*.json')]
  c['scope_request']={'company':{'pdd':'拼多多','dji':'大疆'}[company],'scope':scope,'source_url':c['source_url'],'params':{'endpoint':'api/recruit/position/train/list' if scope=='intern' else 'api/recruit/position/list','page':1,'pageSize':20} if company=='pdd' else {'orgId':'dji','siteId':[143359,168240,170070],'limit':50,'offset':0,'needStat':True,'local_scope_filter':scope}}
  p.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(p,c['status'],len(r['jobs']))
