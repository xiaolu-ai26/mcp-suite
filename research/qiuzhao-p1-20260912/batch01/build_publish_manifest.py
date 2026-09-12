"""Freeze current candidates and only their inspectable, referenced source evidence."""
import pathlib,json,hashlib,shutil,importlib.util,sys,datetime
root=pathlib.Path(__file__).parent;repo=root.parents[2];dest=root/('publish_snapshot_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));dest.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('batch',repo/'qiuzhao/collector/p1_sources_01_10.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.path.insert(0,str(repo));from qiuzhao.v4_fields import graduation_of
manifest={'snapshot_created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_root':str(root.resolve()),'candidates':[]}
for key,name in m.COMPANIES.items():
 for scope in ['campus','intern','social']:
  folder=root/key/scope;source=folder/'result.json'
  if not source.exists():
   manifest['candidates'].append({'company':name,'scope':scope,'state':'running_no_result_yet','source_path':str(source.resolve())});continue
  try:r=json.loads(source.read_text())
  except (OSError,ValueError):continue
  c=r['coverage'];output=dest/key/scope;output.mkdir(parents=True,exist_ok=True);evidence=[]
  for ref in c.get('evidence_files') or []:
   origin=pathlib.Path(ref);origin=origin if origin.is_absolute() else folder/origin
   if not origin.is_file():continue
   relative=pathlib.Path('evidence')/str(ref).lstrip('/') if not pathlib.Path(ref).is_absolute() else pathlib.Path('evidence')/origin.name
   target=output/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(origin,target);evidence.append(str(relative))
  for row in r['jobs']:
   raw_id=str(row['source_record_id']);matches=list(folder.rglob('detail-'+raw_id+'.json'))
   if key in ['oppo','kuaishou'] and len(matches)>1:
    site='social-site' if 'career.oppo.com/' in row.get('detail_url','') or 'zhaopin.kuaishou.cn' in row.get('detail_url','') else 'campus-site'
    preferred=[f for f in matches if site in f.parts];matches=preferred or matches
   original=max(matches,key=lambda f:f.stat().st_mtime) if matches else None
   raw=json.loads(original.read_text()) if original else {}
   if key in ['vivo','byd','honor']:raw=raw.get('Data',raw.get('data',raw))
   if original:
    target=output/'evidence'/('detail-'+raw_id+'.json');target.parent.mkdir(exist_ok=True)
    # Recommendations and candidate form configuration are unrelated to this job's proof.
    clean={k:v for k,v in raw.items() if k not in ('positionEngineerList','positionFunctionList','positionRegionList','orgConfig','applicationForm','applyForm','fields','customBlocks')}
    target.write_text(json.dumps(clean,ensure_ascii=False));evidence.append(str(target.relative_to(output)))
   intent=folder/('intentions-'+raw_id+'.json')
   if intent.exists():target=output/'evidence'/intent.name;shutil.copy2(intent,target);evidence.append(str(target.relative_to(output)))
   facts=m.job(key,scope,raw_id,row.get('job_title') or row.get('title'),row['detail_url'],row['description_raw'],row.get('location',''),raw)
   for field in ['education_raw','major_requirements_raw','experience_raw','deadline_raw','source_fields']:
    if facts.get(field) or not row.get(field):row[field]=facts.get(field)
   if key in ('dji','catl'):
    row['cohort_raw']=''
    if row.get('campaign_scope')!='job_specific':row['campaign_cohort_raw']=(raw.get('projectFolder') or {}).get('name') or '';row['campaign_scope']='project';row['campaign_url']=row['detail_url'].split('#')[0]
   if key=='oppo' and scope!='social':row['campaign_cohort_raw']=raw.get('projectName') or row.get('campaign_cohort_raw') or row.get('cohort_raw','');row['campaign_scope']='project';row['cohort_raw']=''
   if key=='byd' and scope!='social':row['campaign_cohort_raw']=str(raw.get('batch') or '')+'届；'+str(row.get('campaign_cohort_raw') or '');row['campaign_scope']='project';row['cohort_raw']=''
   years,basis,_,_=graduation_of(row);row['graduation_years']=[y for y in years if y.startswith('20')];row['graduation_year_evidence']={y:basis[y] for y in row['graduation_years']}
   row['graduation_year_verification']='source_verified' if row['graduation_years'] and all(basis[y] in ('岗位写明','活动标题写明') for y in row['graduation_years']) else 'inferred' if row['graduation_years'] else 'unspecified'
  c['evidence_files']=list(dict.fromkeys(evidence));c['scope_request']=c.get('scope_request') or {'company':name,'scope':scope,'source_url':c.get('source_url',''),'params':{}}
  c['scope_request']['company']=name
  if r['jobs'] and not c.get('scope_evidence'):c['scope_evidence']='; '.join(dict.fromkeys(j.get('scope_evidence','') for j in r['jobs']))
  path=output/'candidate.json';path.write_text(json.dumps(r,ensure_ascii=False,indent=2))
  times=sorted(x.get('verified_at') or x.get('reviewed_at') for x in r['jobs'] if x.get('verified_at') or x.get('reviewed_at'))
  manifest['candidates'].append({'company':name,'scope':scope,'state':c['status'],'complete':c['complete'],'count':len(r['jobs']),'source_collected_from':times[0] if times else None,'source_collected_to':times[-1] if times else None,'candidate_path':str(path.resolve()),'evidence_dir':str(output.resolve()),'candidate_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'errors':c.get('errors',[])})
(root/'PUBLISH_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print(root/'PUBLISH_MANIFEST.json')
for row in manifest['candidates']:print(row['company'],row['scope'],row['state'],row.get('count'))
