"""Normalize already completed source snapshots without additional network calls."""
import json,pathlib,re
root=pathlib.Path(__file__).parent
names={'xiaohongshu':'小红书','oppo':'OPPO','kuaishou':'快手'}
for company in names:
 for p in (root/company).glob('*/result.json'):
  r=json.loads(p.read_text());scope=p.parent.name;c=r['coverage']
  if not c.get('complete'):continue
  kept=[]
  for j in r['jobs']:
   raw=json.loads((p.parent/('detail-'+j['source_record_id']+'.json')).read_text())
   if company=='xiaohongshu':
    actual={'school_recruit':'campus','intern_recruit':'intern','social_recruit':'social'}.get(raw.get('recruitType'))
    if actual is None:raise ValueError('Unknown XHS type')
    if actual!=scope:continue
    j['recruitment_type_raw']=raw.get('recruitType')
    if scope=='intern':
     url='https://job.xiaohongshu.com/campus/intern/position/'+j['source_record_id']
     for key in ['source_url','application_url','detail_url']:j[key]=url
   j['cities']=[x.strip() for x in re.split(r'\s*/\s*|[，,、;；]',j.get('location','')) if x.strip()]
   j['job_title']=j['title'];j['reviewed_at']=j['verified_at'];kept.append(j)
  r['jobs']=kept;c['collected_jobs']=len(kept);c['expected_total']=len(kept);c['unique_source_ids']=len(kept)
  c['scope_evidence']='; '.join(dict.fromkeys(j['scope_evidence'] for j in kept))
  c['evidence_files']=[f.name for f in p.parent.glob('list-*.json')]
  c['scope_request']={'company':names[company],'scope':scope,'source_url':c['source_url'],'params':{'pageNum':1,'pageSize':50,**({'recruitType':scope} if company=='xiaohongshu' else {'local_scope_filter':scope})}}
  p.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(company,scope,len(kept))
