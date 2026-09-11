"""Collect P&G (Procter & Gamble) Chinese Mainland campus recruiting jobs.
Source: pgcareers.com (Phenom), detail pages have JSON-LD.
"""
import gzip
import html as htmlmod
import json
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0'
TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ).isoformat(timespec='seconds')
OUT = '/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/job_mvp'

# Candidate Chinese-Mainland campus job IDs (from探源 report + sitemap)
CANDIDATES = [
    ('CNC003184', '-Chinese-Mainland-Campus-Recruiting-Research-Development-Scientist'),
    ('CNC003221', '-Chinese-Mainland-Campus-Recruiting-Manager-of-One-Brand-Function-Brand-Management-BRM'),
    ('CNC003185', '-Chinese-Mainland-Campus-Recruiting-Finance-Accounting-Manager'),
    ('CNC003200', '-Chinese-Mainland-Campus-Recruiting-Customer-Business-Development-Manager'),
    ('CNC003210', '-Chinese-Mainland-Campus-Recruiting-Human-Resources-Manager'),
    ('CNC003172', '-Chinese-Mainland-Campus-Recruiting-Product-Supply-Manager-Operation-Management-Digital-Engineer'),
    ('CNC003222', '-Chinese-Mainland-Campus-Recruiting-Manager-of-One-Brand-Function-Consumer-Market-Knowledge-CMK'),
    ('CNC003215', '-Chinese-Mainland-Campus-Recruiting-Information-Technology-Manager'),
]


def fetch(url):
    req = Request(url, headers={'User-Agent': UA, 'Accept': 'text/html'})
    with urlopen(req, timeout=25) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        return r.status, raw.decode('utf-8', 'replace')


def strip_html(s):
    s = htmlmod.unescape(s or '')
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def main():
    accepted, rejected = [], []
    for cid, slug in CANDIDATES:
        url = f'https://www.pgcareers.com/global/en/job/{cid}/{slug}'
        try:
            status, h = fetch(url)
        except HTTPError as e:
            rejected.append({'id': cid, 'url': url, 'reason': f'HTTP {e.code}'})
            continue
        except Exception as e:
            rejected.append({'id': cid, 'url': url, 'reason': str(e)[:100]})
            continue

        ld = None
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            try:
                j = json.loads(m.group(1))
                if j.get('@type') == 'JobPosting':
                    ld = j
                    break
            except Exception:
                pass
        if not ld:
            rejected.append({'id': cid, 'url': url, 'reason': 'no JSON-LD JobPosting'})
            continue

        title = ld.get('title', '')
        locs = ld.get('jobLocation') or []
        cities = []
        for l in locs if isinstance(locs, list) else [locs]:
            ad = (l or {}).get('address', {}) or {}
            city = ad.get('addressLocality') or ''
            if city and city not in cities:
                cities.append(city)
        desc = strip_html(ld.get('description', ''))
        date_posted = ld.get('datePosted')

        # Extract graduation period / major requirement from desc
        grad = re.search(r'(Required Graduation Period[^.]*\.?)', desc)
        grad_raw = grad.group(1) if grad else ''
        edu = re.search(r'(Bachelor[^.]*?|Master[^.]*?|PhD[^.]*?)(?=[.;]|$)', desc)

        cities_cn = []
        cn_map = {'Beijing': '北京', 'Shanghai': '上海', 'Guangzhou': '广州',
                  'Tianjin': '天津', 'Taicang': '太仓', 'Chengdu': '成都',
                  'Multi-cities': '多地'}
        for c in cities:
            cities_cn.append(cn_map.get(c, c))

        rec = {
            'id': f'pg-{cid}',
            'recruitment_unit': 'Procter & Gamble (宝洁)',
            'contracting_entity': '',
            'job_title': title,
            'job_category': ld.get('occupationalCategory', ''),
            'cities': cities_cn,
            'major_requirements_raw': grad_raw,
            'major_tags': [],
            'education_raw': edu.group(1)[:60] if edu else '',
            'cohort_raw': 'Required Graduation Period: 2025.6.1 - 2027.8.31',
            'deadline': None,
            'deadline_type': 'undisclosed',
            'status': 'open',
            'application_url': url,
            'source_url': url,
            'published_at': date_posted,
            'reviewed_at': NOW,
            'source_name': '宝洁全球招聘官网 (Phenom)',
            'description_raw': desc[:5000],
            'recruiting_unit_raw': '',
            'hiring_department_raw': '',
            'campaign_cohort_raw': '2027秋季校园招聘',
            'source_record_id': cid,
            'recruitment_type_raw': '校招',
            'recruitment_scope_note': 'campus_recruiting_chinese_mainland',
            'region': 'mainland',
            'overseas_flag': False,
            'record_kind': 'official_job_post_id',
        }
        accepted.append(rec)
        time.sleep(1.0)

    out = {'accepted': accepted, 'rejected': rejected,
           'summary': {'candidates': len(CANDIDATES), 'accepted': len(accepted),
                       'rejected': len(rejected), 'checked_at': NOW}}
    with open(f'{OUT}/pg_staging.json', 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out['summary'], ensure_ascii=False))
    for a in accepted:
        print('  OK', a['id'], a['job_title'][:50], '|', a['cities'])
    for rj in rejected:
        print('  REJ', rj)


if __name__ == '__main__':
    main()
