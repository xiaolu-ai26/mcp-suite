"""Official Xiaomi overseas portals, preserving the domestic Feishu identity.

This source adapter is combined with the domestic Xiaomi adapter by its owner.
An overseas-only result must never remove domestic-only positions.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit
import requests
from .p1_feishu_public import collect_feishu,atomic

NAVIGATION=['https://career.mi.com/jobs','https://career.mi.com/career']
DOMAIN='xiaomi.jobs.f.mioffice.cn'
TENANT='小米科技'
TENANT_MD5='fb3a01fd26e4b35af8750c07263fea49'
EXPECTED={'eastasia','southeastasia','latinamerica','middleeast','africa','southasia','centralasia','global','overseacampus','overseaintern'}
PRIORITY=['global','overseacampus','overseaintern','eastasia','southeastasia','latinamerica','middleeast','africa','southasia','centralasia']

def navigation_portals(text):
    # These URLs must be present in the live official Xiaomi navigation itself.
    return set(re.findall(r'https://xiaomi\.jobs\.f\.mioffice\.cn/[a-z]+',text.replace('\\/','/')))

def align_identity(result):
    for row in [*result['jobs'],*result.get('pending_index',[])]:
        raw=str(row['source_record_id'])
        if raw.startswith('feishu-xiaomi:'):raw=raw.split(':',1)[1]
        if not re.fullmatch(r'\d+',raw):raise ValueError('Xiaomi official jobPostId is not a numeric Feishu ID')
        row['official_source_id']=raw
        row['source_namespace']='feishu-xiaomi'
        row['source_record_id']='feishu-xiaomi:'+raw
        row['id']=row['source_record_id']
    return result

def collect(company:str,scope:str,output_dir:Path)->dict:
    if company!='小米' or scope not in {'campus','intern','social'}:raise ValueError('Invalid Xiaomi overseas scope')
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    files=[];found=set();errors=[]
    for index,url in enumerate(NAVIGATION):
        try:
            response=requests.get(url,timeout=30,headers={'User-Agent':'Mozilla/5.0'})
            response.raise_for_status()
            if urlsplit(response.url).netloc!='career.mi.com':raise ValueError('Official navigation redirected outside Xiaomi careers')
            path=out/f'official-navigation-{index}.html';path.write_text(response.text);files.append(str(path))
            found.update(navigation_portals(response.text))
        except Exception as exc:errors.append('Official navigation unavailable: '+url+' '+str(exc))
    by_path={urlsplit(url).path.strip('/'):url for url in found}
    missing=EXPECTED-set(by_path)
    if missing:errors.append('Previously verified official recruitment portals missing from current navigation: '+','.join(sorted(missing)))
    ordered=[p for p in PRIORITY if p in by_path]+sorted(set(by_path)-set(PRIORITY))
    sites=[{'url':by_path[p]+'/position/list','tenant_names':[TENANT],'tenant_id_md5':TENANT_MD5,'portal_type':6} for p in ordered]
    if sites:
        result=collect_feishu(company,scope,sites,out)
    else:
        result={'jobs':[],'pending_index':[],'coverage':{'status':'blocked','complete':False,'expected_total':None,'collected_jobs':0,'pages_scanned':0,'detail_complete':False,'source_url':NAVIGATION[0],'errors':[],'evidence':[],'evidence_files':[]}}
    align_identity(result);c=result['coverage'];c['errors'].extend(errors)
    c['evidence_files'].extend(files);c['evidence']=list(c['evidence_files'])
    c['scope_evidence']=c.get('scope_evidence','')+' Official Xiaomi region/campus/intern navigation, exact Xiaomi tenant name and identifier; original recruitment types preserved.'
    c['scope_request']={'company':company,'scope':scope,'source_url':NAVIGATION[0],'params':{'official_navigation':NAVIGATION,'discovered_portals':sites,'anonymous_sdk_request':c.get('scope_request')}}
    c['source_complete']=bool(c.get('complete')) and not errors
    c['company_scope_complete']=False
    c['complete']=False
    c['status']='partial' if result['jobs'] or result.get('pending_index') or c['source_complete'] else 'blocked'
    c['coverage_boundary']='Only the officially linked overseas portals; combine with domestic Xiaomi by feishu-xiaomi:jobPostId before company-wide publication.'
    atomic(out/'result.json',result);atomic(out/'candidate.json',result);atomic(out/'coverage.json',c)
    return result

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--scope',choices=['campus','intern','social']);parser.add_argument('--output-dir',required=True,type=Path);args=parser.parse_args()
    for scope in [args.scope] if args.scope else ['campus','intern','social']:
        r=collect('小米',scope,args.output_dir/scope)
        print(json.dumps({'scope':scope,'jobs':len(r['jobs']),'pending':len(r.get('pending_index',[])),'source_complete':r['coverage']['source_complete'],'errors':r['coverage']['errors']},ensure_ascii=False),flush=True)
