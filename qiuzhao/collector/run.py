"""Daily public-source refresh. No login, private data, or paid APIs.
Run: python -m qiuzhao.collector.run --output-dir /var/lib/mcp-suite
"""
from __future__ import annotations
import argparse, copy, datetime as dt, gzip, hashlib, json, logging, os, re, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from qiuzhao.normalize import NORMALIZED_FIELDS, normalize_records

UA = 'QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'
TZ = dt.timezone(dt.timedelta(hours=8))
POSTAL_ANNOUNCEMENT = 'https://www.chinapost.com.cn/cn/report/2609/1176-1.htm'
POSTAL_PORTAL = 'https://chinapost2027.zhaopin.com/job/index.html'
CHN = 'https://zhaopin.chnenergy.com.cn'

def now(): return dt.datetime.now(TZ).isoformat(timespec='seconds')
def clean(value): return BeautifulSoup(str(value or ''), 'html.parser').get_text(' ', strip=True)
def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)

def base_job(identifier, group, title, source, reviewed):
    return dict(id=identifier, recruitment_unit=group, contracting_entity='', job_title=title,
        job_category='', cities=[], major_requirements_raw='', major_tags=[], education_raw='',
        cohort_raw='', deadline=None, deadline_type='undisclosed', status='unverified',
        application_url=source, source_url=source, published_at=None, reviewed_at=reviewed,
        source_name='', evidence_path='', description_raw='')

class Collector:
    def __init__(self, out, delay=1.25):
        self.out = out; self.delay = delay; self.last = {}; self.alerts = []; self.states = {}
        self.run_id = dt.datetime.now(TZ).strftime('%Y%m%dT%H%M%S')
        self.evidence = out / 'evidence' / self.run_id
        self.evidence.mkdir(parents=True, exist_ok=True)
    def fetch(self, url, payload=None, form=False):
        host = url.split('/')[2]
        time.sleep(max(0, self.delay - (time.monotonic()-self.last.get(host, 0))))
        headers = {'User-Agent': UA, 'Accept': '*/*'}
        body = None
        if payload is not None:
            body = (urlencode(payload) if form else json.dumps(payload)).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        try:
            with urlopen(Request(url, data=body, headers=headers), timeout=35) as r:
                raw = r.read()
                if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
                return raw.decode('utf-8', 'replace')
        finally: self.last[host] = time.monotonic()
    def evidence_file(self, name, content):
        p = self.evidence / name
        p.write_text(content, encoding='utf-8')
        return str(p.relative_to(self.out))
    def alert(self, source, error):
        self.alerts.append({'source':source, 'observed_at':now(), 'error':str(error)[:300]})
        logging.error('%s: %s', source, error)
    def postal(self):
        announcement = self.fetch(POSTAL_ANNOUNCEMENT)
        anntext = clean(announcement)
        # Refuse to apply stale campaign constants when the live announcement changes.
        for expected in ['2027', '2026年10月31日', '10月7日', '10月17日', 'chinapost2027.zhaopin.com']:
            if expected not in anntext: raise ValueError('Postal announcement changed: missing '+expected)
        annpath = self.evidence_file('postal-announcement.html', announcement)
        jobs=[]; expected=None; source_ids=set(); excluded=[]
        for page in range(1, 101):
            payload={'pageIndex':page,'pageSize':100,'jobSource':2,'orgNumbers':'105582','campusParentDepartmentIds':''}
            url='https://fe.zhaopin.com/grace/api/dsc/search-job-list'
            response=json.loads(self.fetch(url,payload))
            if response.get('code') != 200: raise ValueError('Postal public API did not return success')
            data=response['data']; rows=data['jobList']; pagination=data['pageInfo']
            if expected is None: expected=pagination['totalNum']
            # Evidence deliberately excludes staff profiles and applicant/behavior counts.
            safe=[{'company':r['company'],'job':{k:v for k,v in r['job'].items() if k!='applyCount'}} for r in rows]
            checked=now(); path=self.evidence_file(f'postal-page-{page}.json',json.dumps({'request_url':url,'request_body':payload,'reviewed_at':checked,'pageInfo':pagination,'jobList':safe},ensure_ascii=False,indent=2))
            for row in safe:
                j=row['job']; c=row['company']; title=j.get('title','').strip()
                source_ids.add(j['jobNumber'])
                if re.search(r'需登录|请登录|投递入口|报名入口|招聘公告',title):
                    excluded.append({'source_record_id':j['jobNumber'],'title':title,'source_url':j.get('url'),'reason':'redirect or announcement, not a named role'}); continue
                if not title or not j.get('deliveryPath'): continue
                job=base_job('postal-'+j['jobNumber'],'中国邮政集团有限公司',title,j['url'],checked)
                entity=c.get('campusOrgName','')
                deadline='2026-10-17' if '中邮人寿' in entity or '中邮保险' in entity else ('2026-10-07' if '邮政储蓄银行' in entity else '2026-10-31')
                desc=clean(j.get('detail',''))
                major=re.search(r'招聘专业要求\s*[：:]\s*(.*?)(?=其他要求\s*[：:]|岗位职责\s*[：:]|$)',desc)
                job.update(contracting_entity='', recruiting_unit_raw=entity, deadline_scope='campaign_announcement_by_recruiting_unit', cohort_scope='campaign_announcement', hiring_department_raw=(c.get('campusDepartment') or {}).get('name',''),
                    job_category=j.get('jobTypeName',''),cities=[j['cityName']] if j.get('cityName') else [],
                    major_requirements_raw=major.group(1).strip() if major else j.get('needMajor',''),
                    education_raw=j.get('minEducationName',''),cohort_raw='普通高等院校2027届应届毕业生（同时面向择业期内毕业生）；经教育部留学服务中心认证学历学位的国（境）外应届毕业留学生。',
                    deadline=deadline, deadline_type='explicit', status='expired' if deadline < now()[:10] else 'open',
                    application_url=j['deliveryPath'], source_name='中国邮政官网授权2027校招专场',
                    announcement_url=POSTAL_ANNOUNCEMENT, campaign_url=POSTAL_PORTAL, published_at='2026-09-07',
                    published_at_scope='campaign_announcement', evidence_path=path, announcement_evidence_path=annpath,
                    description_raw=desc, source_record_id=j['jobNumber'])
                jobs.append(job)
            logging.info('postal page %d/%s: %d rows',page,pagination['totalPage'],len(rows))
            if page >= pagination['totalPage']: break
        if len(source_ids) != expected: raise ValueError(f'Postal pagination changed/incomplete: unique={len(source_ids)}, expected={expected}')
        write_json(self.out/'excluded_records.json',excluded)
        self.states['postal']={'status':'success','checked_at':now(),'source_record_count':expected,'excluded_non_job_records':len(excluded),'collected_jobs':len(jobs),'complete':True,'announcement_url':POSTAL_ANNOUNCEMENT}
        return jobs
    def chnenergy(self, max_jobs=0):
        first=self.fetch(CHN+'/recTypeSerch?kinds=1&schType=1')
        soup=BeautifulSoup(first,'html.parser')
        page_match=re.search(r'共\s*(\d+)\s*条[，,]\s*共\s*(\d+)\s*页',soup.get_text(' ',strip=True))
        if not page_match: raise ValueError('CHN pagination not found')
        expected,pages=map(int,page_match.groups()); links=[]
        for page in range(pages):
            html=first if page==0 else self.fetch(CHN+'/recTypeSerch',{'kinds':'1','schType':'1','pagenum':page,'searchtype':'job'},True)
            self.evidence_file(f'chn-list-{page}.html',html)
            sp=BeautifulSoup(html,'html.parser')
            links.extend(CHN+a['href'] for a in sp.select('h3 a[href^="/annc/showgw?id="]'))
            if max_jobs and len(set(links))>=max_jobs: break
        links=list(dict.fromkeys(links)); links=links[:max_jobs] if max_jobs else links
        jobs=[]
        for idx,url in enumerate(links):
            html=self.fetch(url); checked=now(); soup=BeautifulSoup(html,'html.parser')
            content=soup.select_one('.content.row')
            if not content: raise ValueError('CHN detail content missing: '+url)
            text=content.get_text(' ',strip=True)
            def field(label):
                for el in content.select('li, div.col-md-5'):
                    if el.find(['li','div']): continue
                    t=el.get_text(' ',strip=True)
                    if t.startswith(label+'：'):return t[len(label)+1:].strip()
                return ''
            dates=content.select('blockquote strong'); pub=clean(dates[0]) if dates else ''; deadline=clean(dates[1]) if len(dates)>1 else ''
            def date(s):
                m=re.search(r'(\d{4})年(\d{2})月(\d{2})日',s)
                return '-'.join(m.groups()) if m else None
            job=base_job('chn-'+url.split('id=')[1],'国家能源投资集团有限责任公司',field('招聘岗位'),url,checked)
            major=''
            for li in content.select('li'):
                if li.get_text(strip=True).startswith('专业要求：'): major=li.get_text(' ',strip=True).removeprefix('专业要求：').strip()
            cohort=re.search(r'(20\d{2}届[^。；\n]{0,100})',text)
            # Recruitment center names may be departments: never infer the legal signing entity.
            job.update(recruiting_unit_raw=field('招聘单位'),parent_unit_raw=field('所属单位'),
                job_category=field('岗位类别'),cities=[field('工作地点')] if field('工作地点') else [],
                education_raw=field('学历要求'),major_requirements_raw=major,cohort_raw=cohort.group(1) if cohort else '',
                published_at=date(pub),deadline=date(deadline),deadline_type='explicit' if date(deadline) else 'undisclosed',
                source_name='国家能源集团官网校园招聘直招',description_raw=clean(content.select_one('#descDetail')),
                evidence_path=self.evidence_file('chn-'+url.split('id=')[1]+'.html',str(content)))
            job['status']='expired' if job['deadline'] and job['deadline']<checked[:10] else ('open' if job['deadline'] else 'unverified')
            if not job['job_title']: raise ValueError('CHN job title missing')
            jobs.append(job)
            if idx%25==0:logging.info('chn details %d/%d',idx+1,len(links))
        if not max_jobs and (len(jobs) != expected or len({j['id'] for j in jobs}) != expected):
            raise ValueError(f'CHN incomplete pagination: {len(jobs)}/{expected}')
        self.states['chnenergy']={'status':'success','checked_at':now(),'expected_jobs':expected,'collected_jobs':len(jobs),'complete':not max_jobs and len(jobs)==expected,'list_url':CHN+'/recTypeSerch?kinds=1&schType=1'}
        return jobs
    def telecom(self):
        """Refresh newest public campus page and all previously imported TELE roles."""
        from urllib.parse import urljoin, parse_qs, urlsplit
        host='https://job.chinatelecom.com.cn'
        listing=host+'/wt/TELE/web/index/campus'
        html=self.fetch(listing); soup=BeautifulSoup(html,'html.parser')
        self.evidence_file('telecom-list.html',html)
        links=[urljoin(host,a['href']) for a in soup.select('a[href*="getOnePosition"]')]
        previous=json.loads((self.out/'jobs.json').read_text()) if (self.out/'jobs.json').exists() else []
        links.extend(j['source_url'] for j in previous if str(j.get('id') or '').startswith('telecom-'))
        if not links: raise ValueError('Telecom campus listing has no role links')
        rows=[]
        for url in dict.fromkeys(links):
            raw=self.fetch(url); checked=now(); soup=BeautifulSoup(raw,'html.parser')
            fields={}
            for li in soup.select('li'):
                label=li.select_one('.position_basic_title')
                if label:
                    k=re.sub(r'\s+','',label.get_text()).rstrip('：')
                    value_node=li.select_one('font[title]')
                    fields[k]=value_node['title'].strip() if value_node else li.get_text(' ',strip=True).split('：',1)[-1].strip()
            title=soup.select_one('.position_title span')
            if not title:
                title=soup.find(['h1','h2','h3'])
            title=clean(title)
            body=soup.select_one('.position_content')
            if not body or not fields.get('所属公司') or not title: raise ValueError('Telecom detail schema changed')
            ident=parse_qs(urlsplit(url).query)['postIdEnc'][0]
            job=base_job('telecom-'+ident,'中国电信集团有限公司',title,url,checked)
            desc=body.get_text(' ',strip=True)
            req=body.select_one('.position_content_title2')
            req=clean(req.find_next_sibling('p')) if req else ''
            job.update(recruiting_unit_raw=fields['所属公司'],cities=[fields['工作地点']] if fields.get('工作地点') else [],
                education_raw=fields.get('学历',''),major_requirements_raw=req,requirements_scope='full_requirements_raw',
                published_at=fields.get('发布时间') or None,description_raw=desc,
                source_name='中国电信官方招聘网站校园招聘',campaign_url=listing,
                evidence_path=self.evidence_file('telecom-'+ident+'.html',str(soup.select_one('.position_basic') or '')+str(body)),
                status='unverified',status_note='公开校园岗位页可见；未披露截止及届别，未尝试投递。')
            rows.append(job)
        self.states['telecom']={'status':'success','checked_at':now(),'collected_jobs':len(rows),'complete':False,'coverage':'latest campus page plus all previously imported roles','list_url':listing}
        return rows
    def boc(self):
        url='https://www.boc.cn/aboutboc/bi4/202609/t20260903_25689311.html'
        raw=self.fetch(url); text=clean(raw); checked=now()
        if '2026年10月9日24点' not in text or '2027年全球校园招聘' not in text: raise ValueError('BOC campaign changed')
        path=self.evidence_file('boc-announcement.html',raw)
        section=text.split('（二）总行直属机构',1)[1].split('（三）审计分部',1)[0]
        paragraphs=re.split(r'(?<!\d)\d+\.\s*',section)
        rows=[]
        for para in paragraphs:
            m=re.match(r'(.+?)(金融综合|数据分析|信息科技|单证业务综合|集约运营业务|培训研发)(.*?)岗位，',para)
            if not m: continue
            unit=m.group(1); roles=m.group(2)+m.group(3)
            city=re.search(r'工作地点为([^。]+)',para)
            for title in roles.split('、'):
                ident=hashlib.sha256((unit+'|'+title).encode()).hexdigest()[:16]
                job=base_job('boc-'+ident,'中国银行股份有限公司',title+'岗位',url,checked)
                job.update(recruiting_unit_raw=unit,job_category=title,cities=city.group(1).split('、') if city else [],
                    cohort_raw='面向境内外院校招收应届毕业生',campaign_cohort_raw='2027年全球校园招聘',
                    deadline='2026-10-09',deadline_type='explicit',deadline_scope='campaign_announcement',
                    status='expired' if checked[:10]>'2026-10-09' else 'open',published_at='2026-09-03',
                    application_url='https://campus.chinahr.com/pages/2027-boc',source_name='中国银行官网2027校招公告',
                    description_raw=para.strip(),evidence_path=path,record_kind='announcement_explicit_role')
                rows.append(job)
        if len(rows)<10: raise ValueError('BOC explicit institutional role parser incomplete')
        self.states['boc']={'status':'success','checked_at':now(),'collected_jobs':len(rows),'complete':True,'coverage':'only explicitly named head-office affiliated institution roles; excludes unnamed branch roles','announcement_url':url}
        return rows
    def run(self, source, chn_limit):
        from .ccb import collect_ccb
        from .guopin import collect_guopin
        previous=json.loads((self.out/'jobs.json').read_text()) if (self.out/'jobs.json').exists() else []
        merged={j.get("id") or f"auto-{i}":j for i,j in enumerate(previous)}; fetched=[]
        for name,fn in [('postal',self.postal),('chnenergy',lambda:self.chnenergy(chn_limit)),('telecom',self.telecom),('boc',self.boc),('ccb',lambda:collect_ccb(self)),('guopin',lambda:collect_guopin(self))]:
            if source not in ('all',name): continue
            source_before=merged
            try:
                rows=fn()
                state=self.states[name]
                if state.get('status') not in {'success','partial'} or state.get('errors'):
                    raise ValueError('source did not return a validated successful/partial snapshot')
                if any(not isinstance(j,dict) or not j.get('id') for j in rows):
                    raise ValueError('source row missing stable identity')
                source_before=merged
                merged=copy.deepcopy(merged)
                fetched.extend(rows); seen={j['id'] for j in rows}
                if name=='guopin':
                    complete_groups={k for k,v in self.states[name].get('campaigns',{}).items() if v.get('status')=='success' and v.get('complete') and any(j.get('source_group_key') == k for j in rows)}
                    for key,old in merged.items():
                        if key.startswith('guopin-') and old.get('source_group_key') in complete_groups and key not in seen:
                            old.update(status='removed',reviewed_at=now(),removal_reason='Absent from complete current enterprise campaign listing',source_is_active=False,source_status_raw='closed',source_status_evidence={'list_status':'closed','reason':'complete_snapshot_absence','source':name,'scope':old.get('source_group_key') or name,'complete':True,'checked_at':now()})
                elif rows and self.states[name].get('status') == 'success' and self.states[name]['complete']:
                    prefix={'postal':'postal-','chnenergy':'chn-','telecom':'telecom-','boc':'boc-','ccb':'ccb-'}[name]
                    for key,old in merged.items():
                        if key.startswith(prefix) and key not in seen:
                            old.update(status='removed',reviewed_at=now(),removal_reason='Absent from complete current public listing',source_is_active=False,source_status_raw='closed',source_status_evidence={'list_status':'closed','reason':'complete_snapshot_absence','source':name,'scope':old.get('source_group_key') or name,'complete':True,'checked_at':now()})
                for row in rows:
                    old=merged.get(row['id'])
                    if old:
                        for field in NORMALIZED_FIELDS:
                            value=old.get(field)
                            if not row.get(field) and value is not None and value!='' and value!=[]:row[field]=value
                    merged[row['id']]=row
                write_json(self.out/'jobs.json',list(merged.values()))
            except Exception as error:
                merged=source_before
                self.alert(name,error); self.states[name]={'status':'failed','checked_at':now(),'error':str(error)[:300]}
        jobs=[j for j in merged.values() if not re.search(r'需登录|请登录|投递入口|报名入口|招聘公告',j['job_title'])]; today=now()[:10]
        for j in jobs:
            if j.get('deadline') and j['deadline']<today and j.get('status')!='removed':j['status']='expired'
        filled=normalize_records(jobs); logging.info('normalize_records filled: %s',filled)
        write_json(self.out/'jobs.json',jobs)
        statuses={s:sum(j.get('status')==s for j in jobs) for s in ['open','expired','unverified','removed']}
        summary={'updated_at':max((r for r in (j.get('reviewed_at') for j in jobs) if r),default=None),'run_finished_at':now(),
            'job_count':len(jobs),'status_counts':statuses,'group_count':len({j['recruitment_unit'] for j in jobs}),
            'named_recruiting_entity_count':len({j.get('recruiting_unit_raw') or j.get('contracting_entity') for j in jobs if j.get('recruiting_unit_raw') or j.get('contracting_entity')}),
            'distinct_source_urls':len({j['source_url'] for j in jobs}), 'refreshed_jobs':len(fetched),
            'added_jobs':len(set(merged)-{j.get('id') for j in previous}),'alerts_count':len(self.alerts),
            'counting_note':'One original role ID per record; no city multiplication; named recruiting entities are publisher labels, not independent legal verification.'}
        write_json(self.out/'summary.json',summary);write_json(self.out/'source_state.json',self.states)
        write_json(self.out/'alerts.json',{'run_finished_at':now(),'alerts':self.alerts})
        print(json.dumps(summary,ensure_ascii=False));return bool(self.alerts)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data')
    p.add_argument('--source',choices=['all','postal','chnenergy','telecom','boc','ccb','guopin'],default='all');p.add_argument('--chn-limit',type=int,default=0)
    p.add_argument('--delay',type=float,default=1.25);a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[logging.FileHandler(a.output_dir/'collector.log'),logging.StreamHandler()])
    raise SystemExit(1 if Collector(a.output_dir,max(1.0,a.delay)).run(a.source,a.chn_limit) else 0)
if __name__=='__main__':main()
