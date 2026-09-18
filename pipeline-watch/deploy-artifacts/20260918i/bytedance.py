"""ByteDance campus recruitment public API adapter.

Endpoint: POST https://jobs.bytedance.com/api/v1/search/job/posts
Offset-based pagination (limit parameter).
No login, no CAPTCHA, no paid content. Public position listing.

Standalone: python -m qiuzhao.collector.bytedance --output-dir <dir>
Integration: rows = collect_bytedance(collector); collector.states['bytedance']

SUPERSEDED for the daily chain (2026-09-18): this module stays as the shared
HTTP client, but ``collect_bytedance``/``--campus-only`` are no longer the
authoritative scope mapping.  ``portal_type`` stopped selecting the portal
server-side (it now always answers from the experienced/社招 feed), so the old
call produced 社招 rows labelled as campus.  The daily P1 chain uses
``qiuzhao.collector.p1_bytedance_public``, which selects the scope with
``recruitment_id_list`` (201 校招正式 / 202 校招实习 / 101 社招).
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

from .run import Collector, base_job, now, write_json

API_URL = 'https://jobs.bytedance.com/api/v1/search/job/posts'
DETAIL_URL = 'https://jobs.bytedance.com/campus/position/{job_id}/detail'
LISTING_URL = 'https://jobs.bytedance.com/campus/position'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36')
PAGE_SIZE = 100  # API supports up to 100 per request


def fetch_page(offset, limit=PAGE_SIZE, delay=1.25, last_call=None, portal_type=2,
               recruitment_id_list=None, referer=None):
    """Fetch a single offset page from ByteDance public API.

    ``recruitment_id_list`` is the field that actually selects the portal:
    the official job-board frontend sends ``['201']`` for 校招正式, ``['202']`` for
    校招实习 and ``['101']`` for 社招.  ``portal_type`` is still accepted by the
    server but has stopped changing the result set (2026-09: 1..12 all return the
    experienced feed), so it is only kept for compatibility.  Callers that need a
    specific scope must pass ``recruitment_id_list``; the daily chain does so via
    ``p1_bytedance_public``.
    """
    if last_call is not None:
        time.sleep(max(0, delay - (time.monotonic() - last_call)))
    payload = json.dumps({
        'keyword': '',
        'limit': limit,
        'offset': offset,
        'job_category_id_list': [],
        'tag_id_list': [],
        'location_code_list': [],
        'subject_id_list': [],
        'recruitment_id_list': list(recruitment_id_list or []),
        'portal_type': portal_type,
        'job_function_id_list': [],
    }).encode()
    headers = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'Referer': referer or LISTING_URL,
        'Origin': 'https://jobs.bytedance.com',
    }
    with urlopen(Request(API_URL, data=payload, headers=headers), timeout=35) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'replace')), time.monotonic()


def extract_cities(job):
    """Extract city names from job post city_list or city_info."""
    cities = []
    for c in (job.get('city_list') or []):
        name = c.get('name')
        if name and name not in cities:
            cities.append(name)
    if not cities:
        city_info = job.get('city_info') or {}
        name = city_info.get('name')
        if name:
            cities.append(name)
    return cities


def extract_addresses(job):
    """Extract address strings from job_post_info.address_list."""
    addresses = []
    info = job.get('job_post_info') or {}
    for addr in (info.get('address_list') or []):
        name = addr.get('name')
        if name and name not in addresses:
            addresses.append(name)
    return addresses


def is_campus_job(job):
    """Check if a job is campus recruitment (校招) based on recruit_type."""
    rt = job.get('recruit_type') or {}
    parent = rt.get('parent') or {}
    parent_name = parent.get('name', '')
    return '校招' in parent_name or '校招' in rt.get('name', '')


def collect_bytedance(collector, max_jobs=0, campus_only=False):
    """Collect ByteDance positions via public API offset pagination.

    Args:
        collector: Collector instance.
        max_jobs: If >0, stop after collecting this many jobs.
        campus_only: If True, only include jobs with recruit_type parent = 校招.

    Returns:
        List of job records conforming to base_job schema.
    """
    jobs = []
    seen_ids = set()
    expected_total = None
    offset = 0
    last_call = 0
    errors = []
    pages_scanned = 0
    campus_count = 0
    total_seen = 0

    while True:
        try:
            response, last_call = fetch_page(offset, PAGE_SIZE, collector.delay, last_call)
        except Exception as e:
            errors.append({'offset': offset, 'error': str(e)[:200]})
            collector.alert('bytedance', f'offset {offset} fetch failed: {e}')
            break

        pages_scanned += 1

        if response.get('code') != 0:
            msg = response.get('message', 'unknown error')
            errors.append({'offset': offset, 'error': f'API code {response.get("code")}: {msg}'})
            collector.alert('bytedance', f'API error at offset {offset}: {msg}')
            break

        data = response.get('data', {})
        job_list = data.get('job_post_list', [])
        count = data.get('count', 0)

        if expected_total is None:
            expected_total = count

        if not job_list:
            break

        checked = now()
        # Save evidence with safe fields (no applicant personal data)
        safe_rows = []
        for j in job_list:
            rt = j.get('recruit_type') or {}
            parent = rt.get('parent') or {}
            cat = j.get('job_category') or {}
            safe_rows.append({
                'id': j.get('id'),
                'title': j.get('title'),
                'code': j.get('code'),
                'job_category': {'name': cat.get('name'), 'id': cat.get('id')},
                'recruit_type': {'name': rt.get('name'), 'parent_name': parent.get('name')},
                'city_info': {'name': (j.get('city_info') or {}).get('name')},
                'publish_time': j.get('publish_time'),
                'city_count': len(j.get('city_list') or []),
            })
        evidence_path = collector.evidence_file(
            f'bytedance-offset-{offset}.json',
            json.dumps({
                'source_url': API_URL,
                'request_body': {'offset': offset, 'limit': PAGE_SIZE, 'portal_type': 2},
                'reviewed_at': checked,
                'count': count,
                'offset': offset,
                'returned': len(job_list),
                'job_post_list': safe_rows,
            }, ensure_ascii=False, indent=2)
        )

        for j in job_list:
            total_seen += 1
            job_id = str(j.get('id') or '')
            if not job_id or job_id in seen_ids:
                continue

            campus = is_campus_job(j)
            if campus:
                campus_count += 1
            if campus_only and not campus:
                continue

            seen_ids.add(job_id)
            title = (j.get('title') or '').strip()
            if not title:
                continue
            if re.search(r'需登录|请登录|投递入口|报名入口|招聘公告', title):
                continue

            source_url = DETAIL_URL.format(job_id=job_id)
            job = base_job('bytedance-' + job_id, '北京字节跳动科技有限公司', title, source_url, checked)

            cities = extract_cities(j)
            cat = j.get('job_category') or {}
            rt = j.get('recruit_type') or {}
            parent = rt.get('parent') or {}
            addresses = extract_addresses(j)
            description = j.get('description') or ''
            requirement = j.get('requirement') or ''
            publish_ts = j.get('publish_time')
            published_at = None
            if publish_ts:
                try:
                    import datetime as dt
                    published_at = dt.datetime.fromtimestamp(publish_ts / 1000, tz=dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d')
                except (ValueError, OSError):
                    pass

            # Extract education from requirement
            education = ''
            edu_match = re.search(r'(本科|硕士|博士|大专|学历)[^。\n]{0,30}', requirement)
            if edu_match:
                education = edu_match.group(0)[:50]

            # Extract major from requirement
            major_lines = []
            for line in (description + '\n' + requirement).splitlines():
                if re.search(r'专业|计算机|软件|电子|通信|数学|统计|机械|自动化', line):
                    major_lines.append(line.strip())
            major_raw = '\n'.join(major_lines[:5]) if major_lines else ''

            # Cohort detection
            cohort_raw = ''
            if campus:
                cohort_raw = rt.get('name', '') or parent.get('name', '')

            full_desc = description
            if requirement:
                full_desc += '\n\n【任职要求】\n' + requirement

            job.update(
                recruitment_unit='北京字节跳动科技有限公司',
                job_category=cat.get('name', ''),
                cities=cities,
                education_raw=education,
                major_requirements_raw=major_raw,
                cohort_raw=cohort_raw,
                campaign_cohort_raw=parent.get('name', '') or rt.get('name', ''),
                source_name='字节跳动校园招聘官方网站',
                source_record_id=job_id,
                application_url=source_url,
                job_listing_url=LISTING_URL,
                campaign_url=LISTING_URL,
                published_at=published_at,
                published_at_scope='official_publish_timestamp',
                evidence_path=evidence_path,
                description_raw=full_desc[:5000],
                requirement_raw=requirement[:3000],
                recruiting_unit_raw='',
                hiring_department_raw='',
                recruitment_type_raw=rt.get('name', ''),
                recruitment_type_parent_raw=parent.get('name', ''),
                address_list=addresses,
                job_code=j.get('code', ''),
                record_kind='official_job_post_id',
                status='unverified',
                status_note='公开岗位列表可见；未披露截止日期，未尝试投递。'
                           + ('（社招岗位）' if not campus else '（校招岗位）'),
            )
            jobs.append(job)

            if max_jobs and len(jobs) >= max_jobs:
                break

        logging.info('bytedance offset %d: %d rows (collected: %d, campus: %d/%d)',
                     offset, len(job_list), len(jobs), campus_count, total_seen)

        if max_jobs and len(jobs) >= max_jobs:
            break
        if offset + PAGE_SIZE >= min(expected_total, 10000):
            # API caps at 10000 results
            break
        offset += PAGE_SIZE

    complete = (expected_total is not None and len(seen_ids) >= min(expected_total, 10000)
                and not errors and not max_jobs)

    collector.states['bytedance'] = {
        'status': 'success' if not errors else ('partial' if jobs else 'failed'),
        'checked_at': now(),
        'expected_total': expected_total,
        'api_cap_note': 'API returns max 10000 results; actual total may exceed cap',
        'collected_jobs': len(jobs),
        'unique_source_ids': len(seen_ids),
        'campus_jobs_in_sample': campus_count,
        'total_jobs_scanned': total_seen,
        'pages_scanned': pages_scanned,
        'last_offset': offset,
        'complete': complete,
        'campus_only_filter': campus_only,
        'errors': errors,
        'api_url': API_URL,
        'listing_url': LISTING_URL,
    }
    return jobs


def main():
    parser = argparse.ArgumentParser(description='ByteDance campus recruitment collector')
    parser.add_argument('--output-dir', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'data' / 'bytedance_pending')
    parser.add_argument('--max-jobs', type=int, default=0,
                        help='Limit number of jobs collected (0 = all)')
    parser.add_argument('--campus-only', action='store_true',
                        help='Only collect campus (校招) jobs')
    parser.add_argument('--delay', type=float, default=1.25)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    collector = Collector(args.output_dir, max(1.0, args.delay))
    try:
        rows = collect_bytedance(collector, max_jobs=args.max_jobs, campus_only=args.campus_only)
        write_json(args.output_dir / 'jobs.json', rows)
        write_json(args.output_dir / 'source_state.json', collector.states)
        write_json(args.output_dir / 'alerts.json',
                   {'run_finished_at': now(), 'alerts': collector.alerts})
        print(json.dumps(collector.states['bytedance'], ensure_ascii=False, indent=2))
    except Exception as e:
        collector.alert('bytedance', e)
        write_json(args.output_dir / 'alerts.json',
                   {'run_finished_at': now(), 'alerts': collector.alerts})
        raise SystemExit(f'ByteDance collection failed: {e}')


if __name__ == '__main__':
    main()
