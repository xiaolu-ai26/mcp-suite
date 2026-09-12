"""Rebuild field aliases from this run's saved complete official responses."""
import json,pathlib
root=pathlib.Path(__file__).parent
for company in ['pdd','dji']:
 for scope in ['campus','intern','social']:
  directory=root/company/scope;p=directory/'result.json'
  if not p.exists():continue
  r=json.loads(p.read_text());c=r['coverage']
  for j in r['jobs']:
   j['job_title']=j['title'];j['reviewed_at']=j['verified_at'];j.setdefault('education_raw','');j.setdefault('major_requirements_raw','');j.setdefault('cohort_raw',str(j.get('graduation_year_raw',''))+'届' if j.get('graduation_year_raw') else '')
   j.pop('requirements_raw',None)
  c['scope_evidence']='; '.join(dict.fromkeys(j['scope_evidence'] for j in r['jobs']))
  c['evidence_files']=[f.name for f in directory.glob('*list*.json')]
  c['scope_request']={'company':{'pdd':'拼多多','dji':'大疆'}[company],'scope':scope,'source_url':c['source_url'],'params':{'endpoint':'train/list' if scope=='intern' else 'list'} if company=='pdd' else {'orgId':'dji','siteId':[143359,168240,170070],'scope_filter':scope}}
  p.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(p,c['status'],len(r['jobs']))
