"""Alibaba (阿里巴巴) campus recruitment headless adapter.

The campus SPA (talent.alibaba.com/campus/position-list) gates its JSON search
endpoint behind an XSRF-TOKEN cookie that JS sets on first page load. Plain
urllib POSTs get a fresh session without the token, so the first request must
be issued inside a real headless Chromium page; afterwards the same request
context carries the cookie + `_csrf` query param.

Flow:
  1. headless.open(LISTING_URL) -> JS sets XSRF-TOKEN cookie
  2. read cookie `XSRF-TOKEN`, POST /position/search?_csrf=<token>
  3. paginate until all `content.totalCount` rows seen.

No login, no CAPTCHA solving. Public listing only.

Standalone: python -m qiuzhao.collector.alibaba_headless --output-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

from .run import Collector, base_job, now, write_json
from .base_headless import HeadlessSource, HeadlessUnavailable

LISTING_URL = 'https://talent.alibaba.com/campus/position-list'
SEARCH_URL = 'https://talent.alibaba.com/position/search'
UA = 'QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'
PAGE_SIZE = 50


def _xsrf_token(h: HeadlessSource) -> str:
    for c in h.cookies():
        if c.get('name') == 'XSRF-TOKEN':
            return c.get('value') or ''
    raise RuntimeError('XSRF-TOKEN cookie not set after page load')


def _row_to_job(row, checked):
    job_id = str(row.get('id') or row.get('positionId') or row.get('jobId') or '')
    title = (row.get('name') or row.get('title') or '').strip()
    cities = row.get('regions') or row.get('cityList') or row.get('cityNames') or []
    if isinstance(cities, str):
        cities = [c.strip() for c in re.split(r'[,，、]', cities) if c.strip()]
    dept = row.get('deptName') or row.get('departmentName') or ''
    desc = row.get('description') or row.get('requirement') or ''
    source_url = f'https://talent.alibaba.com/campus/position-detail?jobId={job_id}'
    job = base_job('alibaba-' + job_id, '阿里巴巴集团控股有限公司', title, source_url, checked)
    job.update(
        recruitment_unit='阿里巴巴集团控股有限公司',
        job_category=row.get('categoryName') or row.get('categoryType') or '',
        cities=cities if isinstance(cities, list) else [],
        recruiting_unit_raw=dept,
        hiring_department_raw=dept,
        cohort_raw='2027届校园招聘',
        campaign_cohort_raw='阿里巴巴集团校园招聘',
        source_name='阿里巴巴校园招聘官方网站',
        source_record_id=job_id,
        application_url=source_url,
        job_listing_url=LISTING_URL,
        campaign_url=LISTING_URL,
        description_raw=desc[:5000],
        record_kind='official_position_id',
        status='unverified',
        status_note='公开校招岗位列表可见；未披露截止日期，未尝试投递。',
    )
    return job


def collect_alibaba(collector, max_pages=0):
    jobs, seen_ids = [], set()
    expected_total = None
    page = 1
    pages_scanned = 0
    errors = []
    try:
        h = HeadlessSource(collector, delay=collector.delay)
        h.open(LISTING_URL)
        token = _xsrf_token(h)
        while True:
            payload = {
                'channel': 'campus_group_official_site', 'language': 'zh',
                'pageSize': PAGE_SIZE, 'batchId': '', 'subCategories': '',
                'regions': '', 'customDeptCode': '', 'corpCode': '',
                'pageIndex': page, 'key': '', 'categoryType': 'freshman',
            }
            status, resp = h.post_json(f'{SEARCH_URL}?_csrf={token}', payload)
            pages_scanned += 1
            if status != 200 or not resp.get('success'):
                errors.append({'page': page, 'status': status,
                               'error': str(resp.get('errorMsg'))[:200]})
                collector.alert('alibaba', f'search failed page {page}: {resp.get("errorMsg")}')
                break
            content = resp.get('content') or {}
            row_list = content.get('datas') or []
            expected_total = content.get('totalCount', expected_total)
            checked = now()
            safe_rows = [{k: r.get(k) for k in ('id', 'name', 'categoryName', 'regions')}
                         for r in row_list]
            collector.evidence_file(
                f'alibaba-page-{page}.json',
                json.dumps({'source_url': SEARCH_URL, 'request_body': payload,
                             'reviewed_at': checked, 'totalCount': expected_total,
                             'list': safe_rows}, ensure_ascii=False, indent=2))
            for row in row_list:
                rid = str(row.get('id') or row.get('positionId') or '')
                if not rid or rid in seen_ids:
                    continue
                seen_ids.add(rid)
                title = (row.get('name') or row.get('title') or '').strip()
                if not title or re.search(r'需登录|请登录|投递入口|报名入口|招聘公告', title):
                    continue
                jobs.append(_row_to_job(row, checked))
            logging.info('alibaba page %s: %d rows, total=%s (collected %d)',
                         page, len(row_list), expected_total, len(jobs))
            if max_pages and page >= max_pages:
                break
            if not row_list or (expected_total and len(seen_ids) >= expected_total):
                break
            page += 1
        h.close()
    except HeadlessUnavailable as e:
        collector.alert('alibaba', f'headless unavailable: {e}')
        collector.states['alibaba'] = {'status': 'failed', 'checked_at': now(),
                                        'error': f'headless unavailable: {str(e)[:200]}'}
        return []
    except Exception as e:
        collector.alert('alibaba', e)
        collector.states['alibaba'] = {'status': 'failed', 'checked_at': now(),
                                        'error': str(e)[:300]}
        return []

    complete = (expected_total is not None and len(seen_ids) == expected_total
                and not errors and not max_pages)
    collector.states['alibaba'] = {
        'status': 'success' if not errors else ('partial' if jobs else 'failed'),
        'checked_at': now(), 'expected_total': expected_total,
        'collected_jobs': len(jobs), 'unique_source_ids': len(seen_ids),
        'pages_scanned': pages_scanned, 'complete': complete,
        'errors': errors, 'transport': 'headless-chromium+xsrf',
        'search_url': SEARCH_URL, 'listing_url': LISTING_URL,
    }
    return jobs


def main():
    p = argparse.ArgumentParser(description='Alibaba campus recruitment headless collector')
    p.add_argument('--output-dir', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'data' / 'alibaba_pending')
    p.add_argument('--max-pages', type=int, default=0)
    p.add_argument('--delay', type=float, default=1.5)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    collector = Collector(args.output_dir, max(1.0, args.delay))
    try:
        rows = collect_alibaba(collector, max_pages=args.max_pages)
        write_json(args.output_dir / 'jobs.json', rows)
        write_json(args.output_dir / 'source_state.json', collector.states)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        print(json.dumps(collector.states['alibaba'], ensure_ascii=False, indent=2))
    except Exception as e:
        collector.alert('alibaba', e)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        raise SystemExit(f'Alibaba collection failed: {e}')


if __name__ == '__main__':
    main()
