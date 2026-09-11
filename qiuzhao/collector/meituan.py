"""Meituan (美团) campus recruitment public API adapter.

Endpoint: POST https://zhaopin.meituan.com/api/official/job/getJobList
jobType=[{"code":"1","subCode":[]}] selects campus (校招).
No login, no CAPTCHA, no paid content. Public campus position listing.

Standalone: python -m qiuzhao.collector.meituan --output-dir <dir>
Integration: rows = collect_meituan(collector); collector.states['meituan']
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import math
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

from .run import Collector, base_job, now, write_json

API_URL = 'https://zhaopin.meituan.com/api/official/job/getJobList'
DETAIL_URL = 'https://zhaopin.meituan.com/web/position?jobId={job_id}'
LISTING_URL = 'https://zhaopin.meituan.com/web/position'
UA = 'QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'
PAGE_SIZE = 20  # API caps pageSize at 20 regardless of request


def fetch_page(page_no, page_size=PAGE_SIZE, delay=1.25, last_call=None):
    if last_call is not None:
        time.sleep(max(0, delay - (time.monotonic() - last_call)))
    payload = json.dumps({
        'page': {'pageNo': page_no, 'pageSize': page_size},
        'jobShareType': '1',
        'keywords': '', 'cityList': [], 'department': [], 'jfJgList': [],
        'jobType': [{"code": "1", "subCode": []}],
        'typeCode': [], 'specialCode': [],
    }).encode()
    headers = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'Referer': LISTING_URL,
        'Origin': 'https://zhaopin.meituan.com',
    }
    with urlopen(Request(API_URL, data=payload, headers=headers), timeout=35) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'replace')), time.monotonic()


def collect_meituan(collector, max_pages=0):
    jobs = []
    seen_ids = set()
    expected_total = None
    total_pages = None
    page = 1
    pages_scanned = 0
    last_call = 0
    errors = []
    stagnant = 0  # consecutive pages yielding zero new unique ids

    while True:
        try:
            response, last_call = fetch_page(page, PAGE_SIZE, collector.delay, last_call)
        except Exception as e:
            errors.append({'page': page, 'error': str(e)[:200]})
            collector.alert('meituan', f'page {page} fetch failed: {e}')
            break

        pages_scanned += 1
        if response.get('status') not in (1, '1', 200):
            errors.append({'page': page, 'error': f"API status {response.get('status')}: {response.get('message')}"})
            collector.alert('meituan', f"API error on page {page}: {response.get('message')}")
            break

        data = response.get('data', {})
        row_list = data.get('list', []) or []
        page_meta = data.get('page', {}) or {}
        expected_total = page_meta.get('totalCount', expected_total)
        total_pages = page_meta.get('totalPage', total_pages)

        checked = now()
        safe_rows = [{
            'jobUnionId': r.get('jobUnionId'), 'name': r.get('name'),
            'jobFamily': r.get('jobFamily'), 'jobFamilyGroup': r.get('jobFamilyGroup'),
            'jobType': r.get('jobType'),
            'cityList': [c.get('name') for c in (r.get('cityList') or [])],
        } for r in row_list]
        evidence_path = collector.evidence_file(
            f'meituan-page-{page}.json',
            json.dumps({'source_url': API_URL, 'request_body': {'pageNo': page, 'pageSize': PAGE_SIZE},
                         'reviewed_at': checked, 'page': page_meta, 'list': safe_rows},
                        ensure_ascii=False, indent=2))

        new_before = len(seen_ids)
        for row in row_list:
            job_id = str(row.get('jobUnionId') or '')
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            title = (row.get('name') or '').strip()
            if not title or re.search(r'需登录|请登录|投递入口|报名入口|招聘公告', title):
                continue

            cities = [c.get('name') for c in (row.get('cityList') or []) if c.get('name')]
            duty = row.get('jobDuty') or ''
            req = row.get('jobRequirement') or ''
            desc = (row.get('desc') or '').strip()
            full_desc = '\n\n'.join(x for x in [desc and f'职位描述: {desc}', duty, req and f'岗位要求: {req}'] if x)

            source_url = DETAIL_URL.format(job_id=job_id)
            job = base_job('meituan-' + job_id, '北京三快在线科技有限公司', title, source_url, checked)
            job.update(
                recruitment_unit='北京三快在线科技有限公司',
                job_category=(row.get('jobFamilyGroup') or row.get('jobFamily') or ''),
                cities=cities,
                hiring_department_raw=(row.get('jobFamilyGroup') or ''),
                cohort_raw='2027届校园招聘',
                campaign_cohort_raw='美团2027校园招聘',
                source_name='美团校园招聘官方网站',
                source_record_id=job_id,
                application_url=source_url,
                job_listing_url=LISTING_URL,
                campaign_url=LISTING_URL,
                evidence_path=evidence_path,
                description_raw=full_desc[:5000],
                requirement_raw=req[:3000],
                record_kind='official_job_union_id',
                status='unverified',
                status_note='公开校招岗位列表可见；未披露截止日期，未尝试投递。',
            )
            jobs.append(job)

        logging.info('meituan page %s/%s: %d rows, %d new (collected: %d)',
                     page, total_pages, len(row_list), len(seen_ids) - new_before, len(jobs))

        # This public board reshuffles between pages (overlap across pageNo),
        # so page through up to 3x totalPages and stop on stagnation.
        if len(seen_ids) - new_before == 0:
            stagnant += 1
        else:
            stagnant = 0
        hard_cap = min((total_pages or 1) * 3, 60)
        if expected_total and len(seen_ids) >= expected_total:
            break
        if max_pages and page >= max_pages:
            break
        if stagnant >= 3 and len(seen_ids) >= (expected_total or 0) * 0.9:
            break
        if not row_list or page >= hard_cap:
            break
        page += 1

    complete = (expected_total is not None and len(seen_ids) == expected_total
                and not errors and not max_pages)
    collector.states['meituan'] = {
        'status': 'success' if not errors else ('partial' if jobs else 'failed'),
        'checked_at': now(), 'expected_total': expected_total,
        'collected_jobs': len(jobs), 'unique_source_ids': len(seen_ids),
        'total_pages': total_pages, 'pages_scanned': pages_scanned,
        'complete': complete, 'errors': errors,
        'api_url': API_URL, 'listing_url': LISTING_URL,
    }
    return jobs


def main():
    p = argparse.ArgumentParser(description='Meituan campus recruitment collector')
    p.add_argument('--output-dir', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'data' / 'meituan_pending')
    p.add_argument('--max-pages', type=int, default=0)
    p.add_argument('--delay', type=float, default=1.25)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    collector = Collector(args.output_dir, max(1.0, args.delay))
    try:
        rows = collect_meituan(collector, max_pages=args.max_pages)
        write_json(args.output_dir / 'jobs.json', rows)
        write_json(args.output_dir / 'source_state.json', collector.states)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        print(json.dumps(collector.states['meituan'], ensure_ascii=False, indent=2))
    except Exception as e:
        collector.alert('meituan', e)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        raise SystemExit(f'Meituan collection failed: {e}')


if __name__ == '__main__':
    main()
