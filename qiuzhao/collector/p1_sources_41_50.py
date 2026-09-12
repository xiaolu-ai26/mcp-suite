"""Ordered P1 source batch 41-50, sharing verified public ATS protocols."""
from __future__ import annotations
import sys,json,re
from pathlib import Path
try:
 from . import p1_sources_01_10 as shared
 from .p1_sources_31_40 import collect_beisen
except ImportError:
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
 from qiuzhao.collector import p1_sources_01_10 as shared
 from qiuzhao.collector.p1_sources_31_40 import collect_beisen
COMPANIES={'geely':'吉利汽车','gwm':'长城汽车','mindray':'迈瑞医疗','hengrui':'恒瑞医药','wuxiapptec':'药明康德','xiaomi':'小米','jd':'京东','meituan':'美团','netease':'网易','dewu':'得物'}
BEISEN={'mindray':'https://career.mindray.com','wuxiapptec':'https://wuxiapptec.zhiye.com'}
MOKA={
 'geely':[('https://app.mokahr.com/campus-recruitment/geely/78436','Linked by current job.geely.com'),('https://job.geely.com/social-recruitment/geely/96123','Current official Geely holding portal'),('https://autojob.geely.com/social-recruitment/geely/102042','Current official Geely Auto portal'),('https://app.mokahr.com/social-recruitment/geely/102003','Official Geely page links Zeekr portal')],
 'hengrui':[('https://app.mokahr.com/campus-recruitment/hengrui/145997','Verified Hengrui branded campus portal'),('https://app.mokahr.com/social-recruitment/hengrui/145996','Verified Hengrui branded social portal')],
}

def collect(company,scope,output_dir):
 requested=company;key=next((k for k,v in COMPANIES.items() if v==company),company);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
 if key in BEISEN:result=collect_beisen(COMPANIES[key],scope,BEISEN[key],out)
 elif key in MOKA:
  result=shared.collect_moka_sites(COMPANIES[key],scope,MOKA[key],out)
  result['coverage']['scope_request']={'company':requested,'scope':scope,'source_url':MOKA[key][0][0],'params':{'orgId':key,'sites':[s[0] for s in MOKA[key]],'offset':0,'limit':50,'needStat':True,'local_scope_filter':scope}}
 else:
  c=shared.coverage('');c['errors']=['Official adapter implementation in progress'];result=shared.finish([],c)
 c=result['coverage'];c['evidence_files']=c.get('evidence_files') or [p.name for p in out.glob('*list*.json')]
 if c.get('scope_request'):c['scope_request']['company']=requested
 from qiuzhao.v4_fields import graduation_of
 for j in result['jobs']:
  years,basis,_,_=graduation_of(j);j['graduation_years']=[y for y in years if re.fullmatch(r'20\d{2}届',y)];j['graduation_year_evidence']={y:basis[y] for y in j['graduation_years']}
 (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));return result
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('company');p.add_argument('scope',choices=['campus','intern','social']);p.add_argument('output_dir');a=p.parse_args();r=collect(a.company,a.scope,a.output_dir);print(json.dumps({k:v for k,v in r['coverage'].items() if k not in ['evidence','evidence_files','scope_evidence']},ensure_ascii=False))
