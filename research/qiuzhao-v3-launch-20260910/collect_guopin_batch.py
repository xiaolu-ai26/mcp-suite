"""Efficient guopin batch collector - breadth first, 1-5 campus jobs per company.

Uses the verified public API:
  - headers: Device:pc, Version:5.0.0, Subsite:iguopin
  - config: GET /api/activity/exclusive/v1/info?domain=CODE
  - list:   POST /api/jobs/v1/list  {page,page_size,source:s_job_list, company_id_with_sub:CID, sort_scene:1}
        or  POST /api/jobs/v1/project-job {..., project_id:[PID]}
"""
from __future__ import annotations
import json, time, re, gzip, sys
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

HOST = 'https://gp-api.iguopin.com'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
HDR = {'User-Agent': UA, 'Device': 'pc', 'Version': '5.0.0', 'Subsite': 'iguopin',
       'Accept': 'application/json, text/plain, */*'}

# Candidate domains from the task + known aliases
CANDIDATE_DOMAINS = [
    'crec','crcc','ccccltd','ceec','crrc','faw','dfm','chd','cdt','spic',
    'chinacoal','sinomach','cam2027','sinolight','salt','tobacco','chinatower',
    'chinamobile','zgyd','chinaunicom','zglt','chinatelecom','ctc','cec',
    'spacechina','casic','casicjob','avic','cnnc','cgnpc',
]

CITY_MAP = {}  # we just pass through area_cn strings

def api(path, payload=None):
    url = HOST + path
    body = None
    h = dict(HDR)
    if payload is not None:
        body = json.dumps(payload).encode(); h['Content-Type'] = 'application/json'
    req = Request(url, data=body, headers=h)
    with urlopen(req, timeout=25) as r:
        raw = r.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
    res = json.loads(raw)
    if res.get('code') != 200:
        raise ValueError(f"code={res.get('code')} msg={str(res.get('msg'))[:100]}")
    return res['data']

def get_config(domain):
    d = api('/api/activity/exclusive/v1/info?' + urlencode({'domain': domain}))
    return d

def pull_campus_jobs(domain, max_per_company=5):
    """Return (jobs_list, log_entry). jobs_list has full row contents."""
    log = {'domain': domain}
    cfg = get_config(domain)
    cid = cfg.get('company_id')
    cname = (cfg.get('company') or {}).get('name') or cfg.get('title') or domain
    log['company_id'] = cid
    log['company_name'] = cname
    if not cid:
        log['blocker'] = 'no company_id'; return [], log

    # parse project_id from nav
    project_id = None; nature = None
    try:
        parsed = json.loads(cfg['content'])
        navs = [n for n in (parsed.get('params', {}).get('nav') or []) if n.get('type') == 'job']
        if navs:
            props = navs[0].get('props', {})
            project_id = props.get('projectId')
            if props.get('nature'):
                nature = props['nature'].split(',')
    except Exception as e:
        log['config_parse_warn'] = str(e)[:80]

    if project_id:
        endpoint = '/api/jobs/v1/project-job'
        req = {'page': 1, 'page_size': 100, 'source': 's_job_list', 'project_id': [project_id]}
        if nature: req['nature'] = nature
    else:
        endpoint = '/api/jobs/v1/list'
        req = {'page': 1, 'page_size': 100, 'source': 's_job_list',
               'company_id_with_sub': cid, 'sort_scene': 1}

    data = api(endpoint, req)
    rows = data.get('list') or []
    log['total_listed'] = data.get('total')
    log['endpoint'] = endpoint

    # campus filter
    campus = []
    for r in rows:
        nc = r.get('nature_cn')
        rt = r.get('recruitment_type_cn')
        if nc != '校招':
            continue
        if rt not in ('校园招聘', '', None):
            continue
        contents = str(r.get('contents') or '')
        if len(contents) < 50:
            continue
        campus.append(r)
        if len(campus) >= max_per_company:
            break
    log['campus_qualified'] = len(campus)
    return campus, log

def main():
    out_jobs = []
    logs = []
    # Also pull official ads directory to discover valid domains
    try:
        ads = api('/api/base/ads/v1/list?page=1&page_size=100&alias=GP_index_long_banner_rolling')
        ad_domains = set()
        for a in ads.get('list', []):
            host = urlsplit(a.get('link_url') or '').hostname or ''
            if host.endswith('.iguopin.com'):
                code = host.split('.')[0]
                if code and code not in ('www', 'gp-api', 'api4', 'c', 'b', 'live'):
                    ad_domains.add(code)
        logs.append({'note': 'ads_directory_discovered', 'domains': sorted(ad_domains)})
        print('ADS discovered domains:', sorted(ad_domains), file=sys.stderr)
    except Exception as e:
        ad_domains = set()
        logs.append({'note': 'ads_dir_failed', 'err': str(e)[:120]})

    # merge: candidate list + ad-discovered, dedupe preserve order
    seen = set(); ordered = []
    for d in list(CANDIDATE_DOMAINS) + sorted(ad_domains):
        if d not in seen:
            seen.add(d); ordered.append(d)

    for domain in ordered:
        t0 = time.time()
        try:
            jobs, log = pull_campus_jobs(domain, max_per_company=5)
            log['elapsed_s'] = round(time.time() - t0, 1)
            for r in jobs:
                out_jobs.append({
                    'domain': domain,
                    'company_name': r.get('company_name'),
                    'job_name': r.get('job_name'),
                    'job_id': r.get('job_id'),
                    'department_cn': r.get('department_cn'),
                    'category_cn': r.get('category_cn'),
                    'nature_cn': r.get('nature_cn'),
                    'recruitment_type_cn': r.get('recruitment_type_cn'),
                    'education_cn': r.get('education_cn'),
                    'major_cn': r.get('major_cn'),
                    'district_list': r.get('district_list'),
                    'start_time': r.get('start_time'),
                    'end_time': r.get('end_time'),
                    'contents': r.get('contents'),
                    'company_industry': (r.get('company_info') or {}).get('industry_cn'),
                })
            logs.append(log)
            print(f"[OK] {domain}: {log.get('company_name','?')[:20]} listed={log.get('total_listed')} campus={log.get('campus_qualified')} ({log['elapsed_s']}s)", file=sys.stderr)
        except Exception as e:
            logs.append({'domain': domain, 'blocker': str(e)[:150], 'elapsed_s': round(time.time()-t0, 1)})
            print(f"[SKIP] {domain}: {str(e)[:100]}", file=sys.stderr)
        time.sleep(0.3)

    result = {'collected_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
              'jobs': out_jobs, 'logs': logs}
    with open('/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release/_guopin_raw.json', 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"\nDONE: {len(out_jobs)} jobs from {len([l for l in logs if l.get('campus_qualified')])} companies", file=sys.stderr)

if __name__ == '__main__':
    main()
