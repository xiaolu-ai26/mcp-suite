"""Anonymous official Guopin enterprise campaign APIs observed in the public UI.

No account, signatures, personal/paid search endpoints, or browser dependency.
Explicitly allowlisted current campaigns only; source placeholders are excluded.
"""
from __future__ import annotations
import argparse, datetime as dt, gzip, json, logging, math, re, time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from .run import Collector, base_job, clean, now, write_json, UA

HOST='https://gp-api.iguopin.com'
# Guarantee list only. The real campaign set is discovered daily from the official
# banner directory; these aliases are the fallback when that discovery fails.
# cgnpc (中国广核) was delisted from the directory and is no longer hardcoded; it is
# picked up again automatically if it is ever advertised.
CAMPAIGNS=(
    ('zgyd','中国移动通信集团有限公司'),
    ('ceec','中国能源建设集团有限公司'),
    ('cam2027','中国机械科学研究总院集团有限公司'),
    ('casicjob','中国航天科工集团有限公司'),
    ('zglt','中国联合网络通信集团有限公司'),
)
BANNER_ALIAS='GP_index_long_banner_rolling'
CAMPAIGN_HOST_SUFFIX='.iguopin.com'
CAMPAIGN_ALIAS_RE=re.compile(r'^[a-z0-9][a-z0-9-]*$')
YEAR_MARKER='2027'
CAMPUS_MARKERS=('校园招聘','校招','秋季招聘','秋招')
FIELDS=('job_id','job_name','company_id','company_name','recruitment_type_cn','nature_cn',
    'category_cn','education_cn','experience_cn','is_graduates','department_cn','start_time',
    'end_time','district_list','contents','status','is_apply','apply_instruction','refresh_time','update_time')
ALLOWED_PATHS={'/api/activity/exclusive/v1/info','/api/base/ads/v1/list',
    '/api/jobs/v1/list','/api/jobs/v1/project-job','/api/company/organization/v1/tree','/api/company/index/v1/project-company'}

def public_api(collector,url,payload=None):
    parts=urlsplit(url)
    if parts.scheme!='https' or parts.netloc!='gp-api.iguopin.com' or parts.path not in ALLOWED_PATHS:
        raise ValueError('Guopin request outside allowlisted public recruitment API')
    time.sleep(max(0,collector.delay-(time.monotonic()-collector.last.get(parts.netloc,0))))
    headers={'User-Agent':UA,'Device':'pc','Version':'5.0.0','Subsite':'iguopin'}
    body=None
    if payload is not None:body=json.dumps(payload).encode();headers['Content-Type']='application/json'
    try:
        with urlopen(Request(url,data=body,headers=headers),timeout=35) as response:
            raw=response.read()
            if response.headers.get('Content-Encoding')=='gzip' or raw[:2]==b'\x1f\x8b':raw=gzip.decompress(raw)
            result=json.loads(raw)
    finally:collector.last[parts.netloc]=time.monotonic()
    if result.get('code')!=200:
        raise ValueError('Guopin public API rejected request: '+str(result.get('code'))+' '+str(result.get('msg',''))[:120])
    return result['data']

def campaign_alias(row):
    """Resolve a per-campaign subdomain alias from a banner's own links, or None.

    Never guesses: only a single label directly under iguopin.com is accepted, so
    ordinary iguopin pages (www/gp-api) and unrelated hosts are rejected.
    """
    for key in ('link_url','content_url'):
        host=urlsplit(str(row.get(key) or '')).hostname or ''
        if not host.endswith(CAMPAIGN_HOST_SUFFIX):continue
        label=host[:-len(CAMPAIGN_HOST_SUFFIX)]
        if label in ('www','gp-api') or '.' in label:continue
        if CAMPAIGN_ALIAS_RE.match(label):return label
    return None

def discover_campaigns(collector,ads=None):
    """Every currently advertised 2027 campus campaign, from the official banners.

    Returns ``(campaigns, skipped)``: campaigns is an alias-deduplicated,
    alias-sorted list of ``(alias, title)``; skipped lists rejected banners with a
    concrete reason. Pass ``ads`` to reuse a banner list the caller already fetched.
    """
    if ads is None:
        url=HOST+'/api/base/ads/v1/list?'+urlencode({'page':1,'page_size':100,'alias':BANNER_ALIAS})
        ads=public_api(collector,url)['list']
    found={};skipped=[]
    for row in ads or []:
        title=str(row.get('title') or '').strip()
        text=title+' '+str(row.get('link_url') or '')+' '+str(row.get('content_url') or '')
        if YEAR_MARKER not in text:
            skipped.append({'id':row.get('id'),'title':title,'reason':'no 2027 marker in title/link'});continue
        if not any(marker in text for marker in CAMPUS_MARKERS):
            skipped.append({'id':row.get('id'),'title':title,'reason':'not an unambiguous campus campaign'});continue
        alias=campaign_alias(row)
        if not alias:
            skipped.append({'id':row.get('id'),'title':title,'reason':'cannot resolve a single-label iguopin campaign alias'});continue
        found.setdefault(alias,title)
    return sorted(found.items()),skipped

def merge_campaigns(discovered):
    """Guarantee list union discovered campaigns, deduplicated and alias-sorted."""
    merged=dict((alias,title) for alias,title in CAMPAIGNS)
    for alias,title in discovered:merged.setdefault(alias,title)
    return sorted(merged.items())

def campaign_pages(collector,endpoint,request,domain,config,scan):
    first=public_api(collector,endpoint,request)
    expected=int(first['total']);scan['expected']=expected
    limit=2000 if request.get('project_id') else 1000
    partitions=[('all',request.copy(),first)]
    if expected>limit:
        # The public UI exposes company selection. Query those actual selectors
        # instead of requesting pages that the upstream silently clamps/repeats.
        if request.get('project_id'):
            tree_url=HOST+'/api/company/index/v1/project-company'
            tree=public_api(collector,tree_url,{'project_ids':request['project_id'],'show_all_company':0})['list']
            nodes=[]
            def visit(node):
                if node.get('job_count',0)>0:nodes.append(node)
                for child in node.get('children',[]):visit(child)
            visit(tree)
        else:
            tree_url=HOST+'/api/company/organization/v1/tree?'+urlencode({'company_id':config['company_id'],'show_all_company':0})
            tree=public_api(collector,tree_url)['organization_tree']
            if tree.get('job_count',0):raise ValueError('Large nonproject root has direct roles; unsupported selector split')
            nodes=tree.get('children',[])
        if not nodes:raise ValueError('Public company selector tree empty')
        def safe_node(n):return {**{k:n.get(k) for k in ('company_id','name','job_count','all_job_count')},'children':[safe_node(c) for c in n.get('children',[])]}
        collector.evidence_file('guopin-'+domain+'-organization.json',json.dumps({'source_url':tree_url,'reviewed_at':now(),'tree':safe_node(tree)},ensure_ascii=False,indent=2))
        partitions=[]
        for n in nodes:
            part=request.copy();part.pop('company_id_with_sub',None)
            if request.get('project_id'):part['company_id']=[n['company_id']]
            else:part['company_id_with_sub']=n['company_id']
            partitions.append((n['company_id'],part,None))
    for key,part,initial in partitions:
        part['page']=1;data=initial or public_api(collector,endpoint,part)
        total=int(data['total']);pages=max(1,math.ceil(total/100));part_seen=set()
        if total>limit:raise ValueError('A company selector still exceeds the public pagination window')
        for page in range(1,pages+1):
            part['page']=page
            if page>1:data=public_api(collector,endpoint,part)
            if int(data['total'])!=total:raise ValueError('Company listing changed during refresh')
            safe=[{k:r.get(k) for k in FIELDS} for r in data.get('list',[])]
            checked=now();path=collector.evidence_file(f'guopin-{domain}-{key}-{page}.json',json.dumps({'source_url':endpoint,'request_body':part.copy(),'reviewed_at':checked,'total':total,'list':safe},ensure_ascii=False,indent=2))
            for row in safe:
                ident=str(row.get('job_id') or '')
                if not ident or ident in part_seen:raise ValueError('Missing/repeated role ID within public company pagination')
                part_seen.add(ident)
            logging.info('guopin %s/%s page %d/%d: %d source records',domain,key,page,pages,len(safe))
            yield safe,checked,path
        if len(part_seen)!=total:raise ValueError('Incomplete public company selector listing')

def collect_guopin(collector):
    ads_url=HOST+'/api/base/ads/v1/list?'+urlencode({'page':1,'page_size':100,'alias':BANNER_ALIAS})
    discovered=[];skipped=[];fallback_used=False;directory_ok=False;adrows=[];adpath=None
    try:
        ads=public_api(collector,ads_url)
        adrows=[{k:r.get(k) for k in ('id','title','link_url','content_url')} for r in ads['list']]
        adpath=collector.evidence_file('guopin-official-campaign-directory.json',json.dumps({'source_url':ads_url,'reviewed_at':now(),'list':adrows},ensure_ascii=False,indent=2))
        directory_ok=True
        discovered,skipped=discover_campaigns(collector,ads=ads['list'])
    except Exception as error:
        # Discovery is best-effort: it must not sink the source. Keep the guarantee
        # list below and record the failure as an alert plus fallback_used.
        collector.alert('guopin:discovery',error);fallback_used=True
    alljobs=[]; excluded=[]; states={}; global_seen=set()
    for domain,group in merge_campaigns(discovered):
        try:
            ad=next((r for r in adrows if urlsplit(r['link_url'] or '').hostname==domain+'.iguopin.com' and YEAR_MARKER in str(r.get('title') or '')),None)
            if not ad:
                if directory_ok:raise ValueError('Current official directory no longer advertises this 2027 campaign')
                # Banner directory unreachable: trust the guarantee list without
                # directory proof rather than dropping the whole source.
                ad={'title':group,'link_url':''}
            config_url=HOST+'/api/activity/exclusive/v1/info?'+urlencode({'domain':domain})
            config=public_api(collector,config_url)
            parsed=json.loads(config['content'])
            # The first job navigation item is the standard campus campaign; later
            # AI/social/special tracks are not silently mixed into this scope.
            nav=next(n for n in parsed['params']['nav'] if n.get('type')=='job')
            props=nav.get('props',{});project_id=props.get('projectId')
            if not config.get('company_id') or not (config.get('company') or {}).get('name'):raise ValueError('Official enterprise identity missing')
            group=config['company']['name']
            configpath=collector.evidence_file('guopin-'+domain+'-config.json',json.dumps({
                'source_url':config_url,'reviewed_at':now(),'directory_ad':ad,
                'company_id':config['company_id'],'company':{k:(config.get('company') or {}).get(k) for k in ('id','name','show_name','nature_cn')},
                'title':config['title'],'navigation':nav},ensure_ascii=False,indent=2))
            endpoint=HOST+'/api/jobs/v1/'+('project-job' if project_id else 'list')
            request={'page':1,'page_size':100,'source':'s_job_list'}
            if props.get('nature'):request['nature']=props['nature'].split(',')
            if project_id:request['project_id']=[project_id]
            else:request.update(company_id_with_sub=config['company_id'],sort_scene=props.get('sort_scene',1))
            campaign_url='https://'+domain+'.iguopin.com'+nav['route']
            jobs=[]; seen=set(); scan={}
            for safe,checked,path in campaign_pages(collector,endpoint,request,domain,config,scan):
                for r in safe:
                    ident=str(r.get('job_id') or '');title=str(r.get('job_name') or '').strip()
                    if not ident or not title:raise ValueError('Guopin job ID/title missing')
                    if ident in seen:continue
                    seen.add(ident)
                    if re.search(r'需登录|请登录|投递入口|报名入口|招聘公告',title):
                        excluded.append({'source_record_id':ident,'title':title,'campaign':domain,'reason':'navigation/announcement, not a named role'});continue
                    if r.get('nature_cn')!='校招' or r.get('recruitment_type_cn') not in ('校园招聘','',None):
                        excluded.append({'source_record_id':ident,'title':title,'campaign':domain,'nature_cn':r.get('nature_cn'),'recruitment_type_cn':r.get('recruitment_type_cn'),'reason':'not unambiguously campus recruitment'});continue
                    source='https://www.iguopin.com/job/detail?id='+ident
                    job=base_job('guopin-'+ident,group,title,source,checked)
                    desc=str(r.get('contents') or '')
                    # Raw paragraph evidence only, never infer a cohort from the campaign.
                    cohort='\n'.join(line.strip() for line in desc.splitlines() if re.search(r'20\d{2}.{0,24}(?:届|应届|毕业)',line))
                    major='\n'.join(line.strip() for line in desc.splitlines() if '专业' in line)
                    end=str(r.get('end_time') or '')
                    deadline=end[:10] if re.match(r'20\d{2}-\d{2}-\d{2}',end) else None
                    if deadline:dt.date.fromisoformat(deadline)
                    status='expired' if deadline and deadline<checked[:10] else ('open' if r.get('status')==1 and r.get('is_apply') is True else 'unverified')
                    job.update(recruiting_unit_raw=r.get('company_name') or '',hiring_department_raw=r.get('department_cn') or '',
                        job_category=r.get('category_cn') or '',cities=[x['area_cn'] for x in (r.get('district_list') or []) if x.get('area_cn')],
                        education_raw=r.get('education_cn') or '',major_requirements_raw=major,cohort_raw=cohort,
                        campaign_cohort_raw=ad['title'],campaign_url=campaign_url,deadline=deadline,recruitment_type_raw=r.get('recruitment_type_cn'),nature_raw=r.get('nature_cn'),
                        deadline_type='explicit' if deadline else ('until_filled' if '招满即止' in desc else 'undisclosed'),
                        deadline_scope='official_role_record',status=status,source_status_raw=r.get('status'),
                        source_is_apply_raw=r.get('is_apply'),published_at=(r.get('start_time') or '')[:10] or None,
                        published_at_scope='official_role_start_time',description_raw=desc,
                        source_name='国聘官方企业校招专场：'+group,source_record_id=ident,
                        source_group_key=domain,evidence_path=path,announcement_evidence_path=configpath,
                        directory_evidence_path=adpath,record_kind='official_job_id')
                    jobs.append(job)
            expected=scan['expected']
            if len(seen)!=expected:raise ValueError(f'Guopin incomplete source listing {len(seen)}/{expected}')
            jobs=[j for j in jobs if j['source_record_id'] not in global_seen]
            global_seen.update(j['source_record_id'] for j in jobs)
            states[domain]={'status':'success','checked_at':now(),'source_record_count':expected,
                'collected_jobs':len(jobs),'complete':True,'campaign_url':campaign_url,'group_name':group}
            alljobs.extend(jobs)
        except Exception as error:
            collector.alert('guopin:'+domain,error)
            states[domain]={'status':'failed','checked_at':now(),'error':str(error)[:250]}
    write_json(collector.out/'guopin_excluded_records.json',excluded)
    complete=all(x['status']=='success' for x in states.values())
    # Per-campaign states stay in campaigns/alerts; a top-level 'errors' key or a
    # non success/partial status makes run.py reject the entire source. Partial
    # acceptance merges only campaigns whose own state is success+complete.
    # A campaign set that comes from the banner directory (auto-discovery) reports
    # the same success/partial/partial_failure semantics as the hardcoded list.
    overall='success' if complete else ('partial' if any(x['status']=='success' for x in states.values()) else 'partial_failure')
    collector.states['guopin']={'status':overall,
        'checked_at':now(),'complete':complete,
        'collected_jobs':len(alljobs),'campaigns':states,
        'discovered':[alias for alias,_ in discovered],'skipped':skipped,'fallback_used':fallback_used,
        'coverage':'guarantee list union auto-discovered 2027 campus campaigns; campus default track only'}
    return alljobs

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data'/'guopin_pending');a=p.parse_args()
    c=Collector(a.output_dir);logging.basicConfig(level=logging.INFO)
    try:
        rows=collect_guopin(c)
        if not c.alerts:write_json(a.output_dir/'jobs.json',rows)
        write_json(a.output_dir/'source_state.json',c.states)
        write_json(a.output_dir/'alerts.json',{'alerts':c.alerts,'run_finished_at':now()});print(json.dumps(c.states,ensure_ascii=False))
        raise SystemExit(1 if c.alerts else 0)
    except Exception as error:
        c.alert('guopin',error);write_json(a.output_dir/'alerts.json',{'alerts':c.alerts,'run_finished_at':now()});raise
if __name__=='__main__':main()
