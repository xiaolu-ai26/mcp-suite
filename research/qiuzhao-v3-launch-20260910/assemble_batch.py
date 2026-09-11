"""Assemble batch_efficient.json from guopin + greenhouse raw captures.
Maps to production schema: id, recruitment_unit, job_title, cities,
description_raw, recruitment_type, cohort_raw, industry, source_url, reviewed_at
"""
import json, re, time
from pathlib import Path

BASE = Path('/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release')
reviewed = time.strftime('%Y-%m-%dT%H:%M:%S+08:00')

# Already-online campaigns (per task + existing collector) to flag
GUOPIN_ALREADY = {'zgyd','ceec','cgnpc','cam2027','casicjob','zglt'}

def cohort_from(text):
    for line in text.splitlines():
        m = re.search(r'(20\d{2})\s*\.{0,4}(?:届|应届|毕业)', line)
        if m: return m.group(1) + '届'
    return ''

def clean_cities(district_list):
    out = []
    for d in (district_list or []):
        a = d.get('area_cn','')
        if a: out.append(a)
    return out

jobs = []
log_companies = []

# ---- Guopin ----
g = json.load(open(BASE/'_guopin_raw.json'))
g_new = 0; g_existing = 0
for j in g['jobs']:
    contents = (j.get('contents') or '').strip()
    if len(contents) < 50: continue
    domain = j['domain']
    is_existing = domain in GUOPIN_ALREADY
    if is_existing: g_existing += 1
    else: g_new += 1
    cities = clean_cities(j.get('district_list'))
    industry = j.get('company_industry') or '国企'
    jobs.append({
        'id': f"guopin-{j['job_id']}",
        'recruitment_unit': j.get('company_name'),
        'job_title': j.get('job_name'),
        'cities': cities,
        'description_raw': contents,
        'recruitment_type': '校招',
        'cohort_raw': cohort_from(contents) or '2027届',
        'industry': industry,
        'category': j.get('category_cn'),
        'department': j.get('department_cn'),
        'education': j.get('education_cn'),
        'source_url': f"https://www.iguopin.com/job/detail?id={j['job_id']}",
        'source_group_key': domain,
        'already_online_campaign': is_existing,
        'overseas_flag': False,
        'reviewed_at': reviewed,
    })
log_companies.append({'channel':'guopin','new':g_new,'existing_campaigns':g_existing,
                      'logs':[l for l in g['logs'] if isinstance(l,dict) and 'domain' in l]})

# ---- Greenhouse ----
gh = json.load(open(BASE/'_greenhouse_raw.json'))
TECH_INDUSTRIES = {'stripe':'金融科技','airbnb':'互联网/旅游','dropbox':'互联网/云服务','asana':'SaaS/办公',
 'figma':'SaaS/设计','datadog':'云计算/监控','cloudflare':'网络安全','pinterest':'互联网/社交',
 'reddit':'互联网/社区','glossier':'消费/美妆','coinbase':'加密金融','discord':'互联网/社交',
 'duolingo':'教育科技','robinhood':'金融科技','anthropic':'AI','databricks':'云计算/大数据',
 'gitlab':'DevOps/SaaS','twilio':'通信API','block':'金融科技','instacart':'O2O/本地生活','lyft':'出行'}
gh_new = 0
for j in gh['jobs']:
    desc = (j.get('description_raw') or '').strip()
    if len(desc) < 50: continue
    gh_new += 1
    jobs.append({
        'id': f"gh-{j['slug']}-{j['job_id']}",
        'recruitment_unit': j.get('company_name') or j['slug'],
        'job_title': j.get('job_title'),
        'cities': j.get('cities') or [],
        'description_raw': desc,
        'recruitment_type': j.get('recruitment_type','校招'),
        'cohort_raw': '',
        'industry': TECH_INDUSTRIES.get(j['slug'], '海外科技'),
        'source_url': j.get('absolute_url'),
        'source_group_key': j['slug'],
        'already_online_campaign': False,
        'overseas_flag': True,
        'reviewed_at': reviewed,
    })
log_companies.append({'channel':'greenhouse','new_jobs':gh_new,
                      'logs':[l for l in gh['logs'] if isinstance(l,dict) and 'slug' in l]})

# Dedupe by id
seen=set(); final=[]
for j in jobs:
    if j['id'] in seen: continue
    seen.add(j['id']); final.append(j)

out = {
    'batch': 'efficient',
    'generated_at': reviewed,
    'agent': 'batch_efficient (MCP扩源-高效通道)',
    'summary': {
        'total_jobs': len(final),
        'guopin_jobs': sum(1 for j in final if j['id'].startswith('guopin')),
        'greenhouse_jobs': sum(1 for j in final if j['id'].startswith('gh-')),
        'new_companies_guopin': g_new,
        'overseas_jobs': sum(1 for j in final if j.get('overseas_flag')),
    },
    'jobs': final,
    'collection_log': log_companies,
    'blockers': {
        'tupu360': '全站二维码反爬墙(PC+移动UA均返回二维码页)，按零纠缠跳过；已知org: roche/sanofi/pfizer/nestle/abb/siemens/emerson/cummins',
        'zhiye_beisen': '中芯/讯飞/人保子站可达但岗位列表走内部portal-api(需PortalId+签名+Geetest)，5分钟未突破，记入口已证实待枚举；huawei/zte/lenovo/hikvision/yonyou/sangfor/银行保险等子站404',
        'guopin_inactive_domains': 'crcc/dfm/chd/cdt/spic/sinolight/salt/tobacco/chinatower/chinaunicom/chinatelecom/cec/casic/avic 返回14001活动不存在',
        'guopin_zero_campus': 'crec(中国稀土)/faw(一汽)/chinacoal(中煤)/cnnc(中核) 列表可达但无校招标签岗位',
    },
}
with open(BASE/'batch_efficient.json','w') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print('WROTE batch_efficient.json')
print('total jobs:', len(final))
print('summary:', json.dumps(out['summary'], ensure_ascii=False))
# distinct companies
comps = {}
for j in final:
    comps.setdefault(j['recruitment_unit'],0); comps[j['recruitment_unit']]+=1
print('distinct recruitment units:', len(comps))
