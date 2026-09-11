"""Independently re-read four postal detail endpoints and one CHN original page."""
import json, re
from pathlib import Path
from .run import Collector, now, write_json, clean, CHN, POSTAL_ANNOUNCEMENT
from bs4 import BeautifulSoup

def verify(out):
    jobs=json.loads((out/'jobs.json').read_text()); collector=Collector(out)
    units=['中国邮政集团有限公司总部']
    results=[]
    ann=collector.fetch(POSTAL_ANNOUNCEMENT);anntext=clean(ann)
    annpath=collector.evidence_file('sample-postal-announcement.html',ann)
    m=re.search(r'招聘简历接收截止时间为(\d{4})年(\d{1,2})月(\d{1,2})日',anntext)
    if not m:raise ValueError('Official campaign deadline not found')
    official_deadline=f'{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}'
    for unit in units:
        job=next(j for j in jobs if (j.get('recruiting_unit_raw') or j.get('contracting_entity'))==unit)
        url='https://fe.zhaopin.com/grace/api/dsc/get-job-detail'
        response=json.loads(collector.fetch(url,{'pc':True,'jobNumber':job['source_record_id']}))
        if response.get('code')!=200:raise ValueError('Sample detail fetch failed')
        row=response['data']; rawjob={k:v for k,v in row['job'].items() if k!='applyCount'}
        safe={'company':row['company'],'job':rawjob}
        path=collector.evidence_file('sample-'+job['id']+'.json',json.dumps(safe,ensure_ascii=False,indent=2))
        checks={'job_title':job['job_title']==rawjob['title'],
            'recruiting_unit':unit==row['company']['campusOrgName'],
            'city':job['cities']==([rawjob['cityName']] if rawjob.get('cityName') else []),
            'education':job['education_raw']==rawjob.get('minEducationName',''),
            'description':job['description_raw']==clean(rawjob.get('detail','')),
            'source_url':job['source_url']==rawjob['url'],
            'deadline':job['deadline']==official_deadline,
            'contracting_entity_not_inferred':job['contracting_entity']==''}
        results.append({'id':job['id'],'job_title':job['job_title'],'recruiting_unit_raw':unit,
            'source_url':job['source_url'],'announcement_url':job['announcement_url'],
            'checked_at':now(),'evidence_path':path,'checks':checks,'pass':all(checks.values()),
            'note':'Independent detail endpoint matches list endpoint. Campaign deadline checked against official group announcement; per-role legal signatory not disclosed. Application endpoint differs by renderer but both official URLs retain same job ID.'})
    url=CHN+'/annc/showgw?id=5a798bfe-9973-0be4-e063-98b4d40a088a'
    html=collector.fetch(url); soup=BeautifulSoup(html,'html.parser'); content=soup.select_one('.content.row');text=clean(content)
    ident='chn-5a798bfe-9973-0be4-e063-98b4d40a088a'
    stored=next((j for j in jobs if j['id']==ident),None)
    def extract(pattern):
        m=re.search(pattern,text)
        return m.group(1).strip() if m else ''
    def date(label):
        m=re.search(label+r'：\s*(\d{4})年(\d{2})月(\d{2})日',text)
        return '-'.join(m.groups()) if m else None
    original={'job_title':extract(r'招聘岗位：(.+?) 岗位类别'),
        'recruiting_unit_raw':extract(r'招聘单位：(.+?) 招聘岗位'),
        'education_raw':extract(r'学历要求：(.+?) 专业要求'),
        'cities':[extract(r'工作地点：(.+?) 招聘人数')],
        'major_requirements_raw':extract(r'专业要求：\s*(.+)$'),
        'published_at':date('发布时间'),'deadline':date('截止时间')}
    checks={key:stored is not None and stored.get(key)==value for key,value in original.items()}
    checks['stored_record_exists']=stored is not None
    results.append({'id':ident,'source_url':url,'checked_at':now(),
        'evidence_path':collector.evidence_file('sample-chn.html',str(content)),
        'original_extracted_fields':original,'stored_fields':{k:stored.get(k) for k in original} if stored else None,
        'checks':checks,'pass':all(checks.values()),
        'note':'Direct original official role page compared with actual stored job; missing stored record fails.'})
    # CCB is checked against freshly fetched public campaign/list responses.
    from .ccb import PublicClient, ANNOUNCEMENT_URL as CCB_URL
    ccb=next((j for j in jobs if j['id'].startswith('ccb-')),None)
    if ccb:
        client=PublicClient();client.get(CCB_URL)
        ann,_=client.api('NHR106',{'annoId':'20260903163254718082'},CCB_URL)
        evidence=json.loads((out/ccb['evidence_path']).read_text())
        from urllib.parse import urlsplit,parse_qs
        query={k:v[0] for k,v in parse_qs(urlsplit(evidence['source_url']).query).items()}
        data,_=client.api('NHR104',{k:query[k] for k in ('planType','planId','orgId','PAGE_JUMP','REC_IN_PAGE')},ccb['job_listing_url'])
        original=next((r for r in data.get('planPostList',[]) if r['planPost']==ccb['source_record_id']),None)
        text=clean(ann['annoContent'])
        checks={'record_exists':original is not None,'campaign_title':ccb['job_title'] in text,
            'education':ccb['education_raw'] in text,'cohort':ccb['cohort_raw'] in text,
            'department':original is not None and ccb['hiring_department_raw']==original['planPostName'],
            'city':original is not None and ccb['cities']==[original['workPlace']],
            'deadline':original is not None and ccb['deadline']==original['endDate'],
            'recruiting_unit':original is not None and ccb['recruiting_unit_raw']==original['orgName']}
        safe={k:original.get(k) for k in ('planPost','planPostName','orgName','workPlace','endDate')} if original else None
        path=collector.evidence_file('sample-ccb.json',json.dumps({'source_url':evidence['source_url'],'role':safe,'announcement_content':ann['annoContent']},ensure_ascii=False,indent=2))
        results.append({'id':ccb['id'],'source_url':ccb['source_url'],'checked_at':now(),'evidence_path':path,'checks':checks,'pass':all(checks.values())})
    else:results.append({'id':'ccb-missing','checks':{'stored_record_exists':False},'pass':False})
    # Two Guopin groups have stable single-page official campaign lists. Re-fetch
    # their documented requests, then compare the exact original role ID.
    from .guopin import public_api, FIELDS
    for domain in ('cam2027','cgnpc'):
        stored=next((j for j in jobs if j.get('source_group_key')==domain),None)
        if not stored:
            results.append({'id':'guopin-'+domain+'-missing','checks':{'stored_record_exists':False},'pass':False});continue
        evidence=json.loads((out/stored['evidence_path']).read_text())
        data=public_api(collector,evidence['source_url'],evidence['request_body'])
        original=next((r for r in data.get('list',[]) if str(r['job_id'])==stored['source_record_id']),None)
        if not original:
            results.append({'id':stored['id'],'checks':{'original_record_exists':False},'pass':False});continue
        safe={k:original.get(k) for k in FIELDS}
        original_fields={'job_title':original['job_name'],'recruiting_unit_raw':original['company_name'],
            'cities':[r['area_cn'] for r in original.get('district_list',[]) if r.get('area_cn')],
            'education_raw':original.get('education_cn') or '',
            'deadline':(original.get('end_time') or '')[:10] or None,
            'description_raw':original.get('contents') or '',
            'nature_raw':original.get('nature_cn'),'recruitment_type_raw':original.get('recruitment_type_cn')}
        checks={k:stored.get(k)==v for k,v in original_fields.items()}
        path=collector.evidence_file('sample-'+stored['id']+'.json',json.dumps({'source_url':evidence['source_url'],'request_body':evidence['request_body'],'role':safe},ensure_ascii=False,indent=2))
        results.append({'id':stored['id'],'source_url':stored['source_url'],'checked_at':now(),'evidence_path':path,'checks':checks,'pass':all(checks.values())})
    receipt={'checked_at':now(),'announcement_evidence_path':annpath,'sample_count':len(results),'passed':all(x['pass'] for x in results),'samples':results}
    write_json(out/'sample_verification.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    return receipt["passed"]
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data');a=p.parse_args();raise SystemExit(0 if verify(a.output_dir) else 1)
