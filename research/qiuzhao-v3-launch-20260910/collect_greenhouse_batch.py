"""Greenhouse public API batch collector.
GET https://api.greenhouse.io/v1/boards/{slug}/jobs?content=true
"""
import json, time, re, sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'

SLUGS = [
    'cisco','adobe','stripe','airbnb','uber','dropbox','asana','notion','figma',
    'datadog','snowflake','cloudflare','atlassian','shopify','pinterest','snap',
    'reddit','etsy','wayfair','casper','glossier','warbyparker',
    'coinbase','discord','spotify','duolingo','robinhood','openai','anthropic',
    'databricks','gitlab','twilio','slack','square','block','instacart','lyft',
]

def strip_html(html):
    if not html: return ''
    t = re.sub(r'<[^>]+>', ' ', html)
    t = re.sub(r'&nbsp;', ' ', t)
    t = re.sub(r'&amp;', '&', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def board(slug):
    url = f'https://api.greenhouse.io/v1/boards/{slug}/jobs?content=true'
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def main():
    out = []; logs = []
    for slug in SLUGS:
        t0 = time.time()
        try:
            j = board(slug)
            jobs = j.get('jobs', [])
            logs.append({'slug': slug, 'total': len(jobs), 'elapsed': round(time.time()-t0,1)})
            # pick campus/new-grad first; fall back to any
            def is_campus(job):
                blob = (job.get('title','') + ' ' + strip_html(job.get('content',''))).lower()
                return bool(re.search(r'new grad|university campus|intern|graduate program|early career|campus', blob))
            campus = [x for x in jobs if is_campus(x)]
            pick = campus[:3] if campus else jobs[:2]
            for job in pick:
                content = strip_html(job.get('content',''))
                if len(content) < 50:
                    continue
                loc = (job.get('location') or {}).get('name','')
                out.append({
                    'slug': slug,
                    'company_name': j.get('name') or slug,
                    'job_id': job.get('id'),
                    'job_title': job.get('title'),
                    'cities': [loc] if loc else [],
                    'description_raw': content[:4000],
                    'recruitment_type': '实习' if 'intern' in job.get('title','').lower() else '校招',
                    'overseas_flag': True,
                    'absolute_url': job.get('absolute_url'),
                    'metadata': job.get('metadata'),
                })
            print(f"[OK] {slug}: total={len(jobs)} picked={len(pick)}", file=sys.stderr)
        except HTTPError as e:
            logs.append({'slug': slug, 'blocker': f'HTTP {e.code}'})
            print(f"[SKIP] {slug}: HTTP {e.code}", file=sys.stderr)
        except Exception as e:
            logs.append({'slug': slug, 'blocker': str(e)[:120]})
            print(f"[SKIP] {slug}: {str(e)[:80]}", file=sys.stderr)
        time.sleep(0.2)
    res = {'collected_at': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'), 'jobs': out, 'logs': logs}
    with open('/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release/_greenhouse_raw.json','w') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"\nDONE Greenhouse: {len(out)} jobs", file=sys.stderr)

if __name__ == '__main__':
    main()
