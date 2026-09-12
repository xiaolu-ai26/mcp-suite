"""Anonymous Feishu careers SDK collector. No login, private APIs, saved cookies or signatures.

Only one browser process at a time. Use company-verified sites with tenant_names.
collect_feishu(company, scope, [{'url': ..., 'tenant_names': [...]}], output_dir)
"""
from __future__ import annotations
import datetime as dt,fcntl,json,os,re,shutil,time
from pathlib import Path
from urllib.parse import urlsplit
from .base_headless import HeadlessSource,HeadlessUnavailable
from .p1_sources_11_20 import job,clean,TYPES,role_body

INSTALL_SDK = r'''()=>{let req;const keys=Object.keys(window).filter(k=>k.startsWith('webpackChunk')&&Array.isArray(window[k]));const key=keys.find(k=>k.includes('portal'))||keys[0];if(!key)throw Error('No public careers webpack runtime');window[key].push([[Date.now()],{},r=>{req=r}]);if(!req)throw Error('Public careers runtime unavailable');const ids=Object.keys(req.m).filter(k=>String(req.m[k]).includes('website-path')&&String(req.m[k]).includes('x-csrf-token'));if(ids.length!==1)throw Error('Public careers request module ambiguous');const api=req(ids[0]);window.__qiuzhaoPublicApi={post:Object.values(api).find(f=>typeof f==='function'&&/method\s*:\s*["']post["']/.test(String(f))),get:Object.values(api).find(f=>typeof f==='function'&&/method\s*:\s*["']get["']/.test(String(f)))};if(!window.__qiuzhaoPublicApi.post||!window.__qiuzhaoPublicApi.get)throw Error('Public careers SDK methods unavailable');return true}'''
LIST_CALL="async p=>await Promise.race([window.__qiuzhaoPublicApi.post('/api/v1/search/job/posts',p,{notifyHttpError:false}),new Promise((_,reject)=>setTimeout(()=>reject(new Error('public list timeout')),45000))])"
DETAIL_CALL="""async args=>await Promise.race([Promise.all(args.ids.map(async id=>{try{return {id,data:await window.__qiuzhaoPublicApi.get('/api/v1/job/posts/'+id,{portal_type:args.portal_type},{notifyHttpError:false})}}catch(e){return {id,error:String(e.message||e)}}})),new Promise((_,reject)=>setTimeout(()=>reject(new Error('public details timeout')),60000))])"""
KEEP=('id','title','description','requirement','recruit_type','publish_time','channel_online_status','job_subject','job_function','city_list','process_type')

def atomic(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
def public_row(row):
 result={k:row.get(k) for k in KEEP};info=row.get('job_post_info') or {};result['required_degree']=info.get('required_degree',row.get('required_degree'));result['target_major_list']=info.get('target_major_list',row.get('target_major_list')) or [];return result
def public_label(value):
 """Use only supplied human labels; numeric enum IDs remain raw evidence."""
 if isinstance(value,str):return value.strip() if value.strip() and not value.strip().isdigit() else ''
 if isinstance(value,list):return '；'.join(dict.fromkeys(filter(None,(public_label(x) for x in value))))
 if isinstance(value,dict):
  for key in ['zh_cn','zh_CN','name','display_name','label','descriptor','i18n_name','en_us','en_US','en_name']:
   text=public_label(value.get(key))
   if text:return text
 return ''

def public_error(error):
 message=str(error).split('\n')[0]
 return re.sub(r'([?&](?:_signature|token|csrf|csrf_token)=)[^&\s]+',r'\1[redacted]',message,flags=re.I)[:1200]

def pending_record(row,url,listing_path,detail_path=None,error=None):
 failed=error is not None
 result={'source_record_id':str(row['id']),'job_title':row['title'],'detail_url':url,'source_url':url,'application_url':url,
         'last_attempt_at':dt.datetime.now(dt.timezone.utc).isoformat(),'listing_evidence_path':listing_path,
         'pending_reason':'fetch_failed' if failed else 'source_empty_body','detail_request_status':'failed' if failed else 'success',
         'source_missing_fields':[] if failed else ['responsibilities','requirements']}
 if detail_path:result['detail_evidence_path']=detail_path
 if failed:result.update(unretrieved_fields=['responsibilities','requirements'],fetch_error=public_error(error))
 return result

def actual_scope(row):
 typ=row.get('recruit_type') or {};identifier=str(typ.get('id') or '')
 if identifier in ('202','301'):return 'intern'
 if identifier=='201':return 'campus'
 if identifier in ('101','102','103'):return 'social'
 name=str(typ.get('name') or typ.get('i18n_name') or '');parent=typ.get('parent') or {}
 if '实习' in name:return 'intern'
 if parent.get('name')=='校招' and name=='正式':return 'campus'
 return None

def response_data(envelope):
 if not isinstance(envelope,dict):raise ValueError('Invalid public careers response')
 if envelope.get('code')!=0:raise ValueError('Official careers SDK response rejected: '+str(envelope.get('code')))
 return envelope['data']

class AnonymousBrowser(HeadlessSource):
 def _ensure(self):
  if self.page is not None:return
  from playwright.sync_api import sync_playwright
  self._pw=sync_playwright().start()
  executable=os.environ.get('QIUZHAO_CHROME_PATH') or shutil.which('google-chrome')
  options={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--renderer-process-limit=1']}
  if executable:options['executable_path']=executable
  else:options['channel']='chrome'
  try:
   self._browser=self._pw.chromium.launch(**options)
   self._context=self._browser.new_context(locale='zh-CN')
   self._context.set_default_timeout(self.timeout_ms)
   self._context.route('**/*',lambda route:route.abort() if route.request.resource_type in ('image','media','font') else route.continue_())
   self.page=self._context.new_page()
  except Exception:
   self.close();raise

 def close(self):
  # One failed cleanup must not skip the remaining browser/driver resources.
  self.page=None
  for name,method in [('_context','close'),('_browser','close'),('_pw','stop')]:
   resource=getattr(self,name,None)
   try:
    if resource is not None:getattr(resource,method)()
   except Exception:pass
   finally:setattr(self,name,None)

def collect_feishu(company:str,scope:str,sites:list,output_dir:Path)->dict:
 if scope not in TYPES:raise ValueError('unknown scope')
 if not sites or any(not s.get('url') or not s.get('tenant_names') for s in sites):raise ValueError('verified URLs and expected tenant_names are required')
 out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
 c={'status':'blocked','complete':False,'expected_total':None,'collected_jobs':0,'pages_scanned':0,'detail_complete':False,'source_url':sites[0]['url'],'errors':[],'evidence':[],'evidence_files':[],
    'scope_evidence':'Official anonymous Feishu SDK; recruit_type201=campus,202/301=intern,101/102/103=social; unknown enums are not guessed.',
    'scope_request':{'company':company,'scope':scope,'source_url':sites[0]['url'],'params':{'sites':sites,'anonymous':True}},'source_coverage':[],'detail_missing_count':0,'pending_details':[]}
 jobs={};pending={};verified_list_rows={};selected_ids=set();all_sites_done=True
 def evidence(name,obj):
  path=out/name;atomic(path,obj);c['evidence_files'].append(str(path));c['evidence']=list(c['evidence_files']);return str(path)
 def checkpoint():
  cc=dict(c);cc.update(status='partial',complete=False,detail_complete=False,collected_jobs=len(jobs),unique_source_ids=len(jobs)+len(pending),expected_total=None)
  atomic(out/'result.json',{'jobs':list(jobs.values()),'pending_index':list(pending.values()),'coverage':cc})
 lock_path=Path(os.environ.get('QIUZHAO_BROWSER_LOCK','/tmp/qiuzhao-public-careers-browser.lock'))
 with lock_path.open('a') as lock:
  deadline=time.monotonic()+120
  while True:
   try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
   except BlockingIOError:
    if time.monotonic()>deadline:raise TimeoutError('single public careers browser is busy')
    time.sleep(1)
  try:
   with AnonymousBrowser(None,timeout_ms=45000) as browser:
    browser._ensure();page=browser.page
    for site_index,site in enumerate(sites):
     site_state={'url':site['url'],'complete':False,'list_total':None,'listed':0,'pages':0};c['source_coverage'].append(site_state)
     captured=[];errors_before=len(c['errors']);seen={};listing_paths={};website=None;verified_site=False
     def observe(request):
      if '/api/v1/search/job/posts' in request.url and request.method=='POST':
       try:
        data=request.post_data_json
        if isinstance(data,dict):captured.append(data)
       except Exception:pass
     page.on('request',observe)
     try:
      page.goto(site['url'],wait_until='domcontentloaded',timeout=45000)
      page.wait_for_function("document.querySelector('#js-websiteInfo') && Object.keys(window).some(k=>k.startsWith('webpackChunk'))",timeout=30000)
      page.wait_for_timeout(1200)
      info=page.evaluate("JSON.parse(document.querySelector('#js-websiteInfo').textContent)")
      tenant=info['tenant_info']['tenant_name'];website=info['website_info']
      if tenant not in site['tenant_names']:raise ValueError('Official tenant identity drift: '+tenant)
      if site.get('tenant_id_md5') and info['tenant_info'].get('tenant_id_md5')!=site['tenant_id_md5']:raise ValueError('Official tenant identifier drift')
      verified_site=True
      evidence(f'{site_index}-identity.json',{'entry':site['url'],'tenant_name':tenant,'website_id':website['id'],'website_path':website['path'],'process_type':website.get('process_type')})
      page.evaluate(INSTALL_SDK)
      portal_type=(captured[0].get('portal_type') if captured else None) or site.get('portal_type')
      if not portal_type:raise ValueError('No observed or explicitly verified portal_type; refusing guessed request')
      payload={'keyword':'','limit':50,'offset':0,'job_category_id_list':[],'tag_id_list':[],'location_code_list':[],'subject_id_list':[],'recruitment_id_list':[],'portal_type':portal_type,'job_function_id_list':[],'storefront_id_list':[]}
      seen={};total=None;last_path=None
      for offset in range(0,100000,50):
       payload['offset']=offset;data=response_data(page.evaluate(LIST_CALL,payload));rows=data.get('job_post_list')
       if not isinstance(rows,list):raise ValueError('Missing public job list')
       observed=int(data['count'])
       if total is None:total=observed;site_state['list_total']=total
       elif observed!=total:raise ValueError('Official total changed during pagination')
       last_path=evidence(f'{site_index}-list-{offset}.json',{'request':dict(payload),'count':total,'jobs':[public_row(r) for r in rows]})
       c['pages_scanned']+=1;site_state['pages']+=1
       for row in rows:
        ident=str(row.get('id') or '')
        if not ident or ident in seen:raise ValueError('Missing/repeated official job ID')
        seen[ident]=row;listing_paths[ident]=last_path
       if len(seen)==total:break
       if not rows or len(seen)>total:raise ValueError('Official pagination count mismatch')
      else:raise ValueError('Public pagination bound exceeded')
      site_state['listed']=len(seen);site_state['last_page_evidence']=last_path
      selected=[]
      for ident,row in seen.items():
       actual=actual_scope(row)
       if actual is None:c['errors'].append('Unknown official recruit_type for '+ident);continue
       if actual==scope:
        selected_ids.add(ident)
        if ident not in jobs or verified_list_rows.get(ident)!=public_row(row):selected.append(ident)
      for start in range(0,len(selected),3):
       details=page.evaluate(DETAIL_CALL,{'ids':selected[start:start+3],'portal_type':portal_type})
       for result in details:
        ident=result['id'];url=urlsplit(site['url']).scheme+'://'+urlsplit(site['url']).netloc+'/'+website['path'].strip('/')+'/position/'+ident+'/detail'
        try:
         if result.get('error'):raise ValueError(result['error'])
         raw=response_data(result['data']).get('job_post_detail')
         if not raw or str(raw.get('id'))!=ident or actual_scope(raw)!=scope:raise ValueError('Official role identity/scope mismatch')
         detail=public_row(raw);path=evidence(f'{site_index}-detail-{ident}.json',{'request':{'job_id':ident,'portal_type':portal_type},'job':detail})
         try:desc,missing=role_body(detail.get('description'),detail.get('requirement'))
         except ValueError:
          if ident in jobs:
           c['errors'].append('Cross-site empty detail after verified body for '+ident)
           jobs[ident].setdefault('source_conflicts',[]).append({'reason':'cross_site_empty_detail','evidence_file':path})
          else:pending[ident]=pending_record(detail,url,listing_paths[ident],path)
          continue
         url=urlsplit(site['url']).scheme+'://'+urlsplit(site['url']).netloc+'/'+website['path'].strip('/')+'/position/'+ident+'/detail'
         subject=(detail.get('job_subject') or {}).get('name') or {};batch=(subject.get('zh_cn') or subject.get('i18n') or subject.get('en_us') or '') if isinstance(subject,dict) else str(subject)
         cities=[r.get('name') or r.get('i18n_name') or r.get('en_name') for r in detail.get('city_list') or []]
         cohort='；'.join(re.findall(r'[^。\n]*(?:20\d{2}\s*届|毕业|graduat)[^。\n]*',desc,re.I))
         j=job(company,'feishu-'+str(website['id']),ident,detail['title'],url,desc,scope,path,education_raw=public_label(detail.get('required_degree')),major_requirements_raw=public_label(detail.get('target_major_list')),education_source_raw=detail.get('required_degree'),major_source_raw=detail.get('target_major_list'),source_channel_online_status=detail.get('channel_online_status'),cities=[x for x in cities if x],cohort_raw='',cohort_scope='official_job_description',batch_name=batch,job_category=public_label((detail.get('job_function') or {}).get('name')))
         j['source_recruitment_type']=(detail.get('recruit_type') or {}).get('name') or '';j['source_missing_fields']=missing;j['field_completeness']={name:('source_not_disclosed' if name in missing else 'source_disclosed') for name in ['description','requirement']}
         if detail.get('channel_online_status') not in (None,1):j.update(status='unverified',status_note='官方频道状态值为'+str(detail.get('channel_online_status'))+'，可投性需按官网状态说明核验。')
         if ident in jobs and any(j.get(k)!=jobs[ident].get(k) for k in ['job_title','description_raw','cities','education_raw','major_requirements_raw','education_source_raw','major_source_raw','source_channel_online_status']):c['errors'].append('Conflicting cross-site detail for '+ident)
         jobs.setdefault(ident,j);verified_list_rows[ident]=public_row(seen[ident]);pending.pop(ident,None)
        except Exception as exc:
         c['errors'].append('detail '+ident+': '+public_error(exc))
         if ident not in jobs:pending[ident]=pending_record(public_row(seen[ident]),url,listing_paths[ident],error=exc)
       if jobs and len(jobs)%30==0:checkpoint()
      site_state['list_complete']=True;site_state['complete']=len(c['errors'])==errors_before
      checkpoint()
     except Exception as exc:
      all_sites_done=False;c['errors'].append('site '+site['url']+': '+public_error(exc))
      if verified_site and website:
       for ident,row in seen.items():
        if ident not in jobs and ident not in pending and actual_scope(row)==scope:
         url=urlsplit(site['url']).scheme+'://'+urlsplit(site['url']).netloc+'/'+website['path'].strip('/')+'/position/'+ident+'/detail'
         pending[ident]=pending_record(public_row(row),url,listing_paths[ident],error='Scope interrupted before verified detail: '+public_error(exc));pending[ident]['detail_request_status']='blocked'
      checkpoint()
     finally:page.remove_listener('request',observe)
  finally:fcntl.flock(lock,fcntl.LOCK_UN)
 c.update(collected_jobs=len(jobs),unique_source_ids=len(jobs)+len(pending),expected_total=len(selected_ids) if all_sites_done else None,detail_complete=all_sites_done and len(jobs)+len(pending)==len(selected_ids) and not c['errors'])
 c['pending_count']=len(pending);c['detail_missing_count']=sum(r['pending_reason']=='source_empty_body' for r in pending.values());c['pending_details']=list(pending.values())
 c['source_missing_field_counts']={name:sum(name in j.get('source_missing_fields',[]) for j in jobs.values()) for name in ['description','requirement']}
 c['complete']=c['detail_complete'];c['status']='success' if c['complete'] else ('partial' if jobs or pending else 'blocked')
 result={'jobs':list(jobs.values()),'pending_index':list(pending.values()),'coverage':c};atomic(out/'result.json',result);atomic(out/'coverage.json',c);return result
