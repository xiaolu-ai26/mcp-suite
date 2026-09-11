"""Tencent campus recruitment public API adapter.

Endpoint: POST https://join.qq.com/api/v1/position/searchPosition
No login, no CAPTCHA, no paid content. Public campus position listing.

Standalone: python -m qiuzhao.collector.tencent --output-dir <dir>
Integration: rows = collect_tencent(collector); collector.states['tencent']
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

API_URL = 'https://join.qq.com/api/v1/position/searchPosition'
DETAIL_URL = 'https://join.qq.com/post_detail.html?postid={post_id}'
LISTING_URL = 'https://join.qq.com/post.html'
UA = 'QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'
PAGE_SIZE = 100  # API supports up to 100 per page


def fetch_page(page_index, page_size=PAGE_SIZE, delay=1.25, last_call=None):
    """Fetch a single page from Tencent public API. Returns parsed JSON.

    Note: correct parameter names are pageIndex and pageSize (camelCase),
    not page_number / page_size. Verified 2026-09-10.
    """
    if last_call is not None:
        time.sleep(max(0, delay - (time.monotonic() - last_call)))
    payload = json.dumps({'pageIndex': page_index, 'pageSize': page_size}).encode()
    headers = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'Referer': LISTING_URL,
        'Origin': 'https://join.qq.com',
    }
    with urlopen(Request(API_URL, data=payload, headers=headers), timeout=35) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'replace')), time.monotonic()


def parse_cities(work_cities_raw):
    """Parse Tencent space-separated city string into list."""
    if not work_cities_raw:
        return []
    cities = [c.strip() for c in work_cities_raw.split() if c.strip()]
    # Normalize "深圳总部" -> "深圳"
    normalized = []
    for c in cities:
        c = re.sub(r'总部$', '', c)
        normalized.append(c)
    return normalized


def parse_position_family(family_id):
    """Map Tencent positionFamily numeric ID to category name."""
    mapping = {
        1: '技术研发',
        2: '技术研发',
        3: '产品',
        4: '设计',
        5: '职能',
        6: '市场',
        7: '游戏策划',
        8: '内容运营',
    }
    return mapping.get(family_id, '')


def collect_tencent(collector, max_pages=0):
    """Collect all Tencent campus positions via public API pagination.

    Args:
        collector: Collector instance (for evidence/state/alerts).
        max_pages: If >0, stop after this many pages (for testing).

    Returns:
        List of job records conforming to base_job schema.
    """
    jobs = []
    seen_ids = set()
    expected_total = None
    total_pages = None
    page = 1
    pages_scanned = 0
    last_call = 0
    errors = []

    while True:
        try:
            response, last_call = fetch_page(page, PAGE_SIZE, collector.delay, last_call)
        except Exception as e:
            errors.append({'page': page, 'error': str(e)[:200]})
            collector.alert('tencent', f'page {page} fetch failed: {e}')
            break

        pages_scanned += 1

        if response.get('status') != 0:
            msg = response.get('message', 'unknown error')
            errors.append({'page': page, 'error': f'API status {response.get("status")}: {msg}'})
            collector.alert('tencent', f'API error on page {page}: {msg}')
            break

        data = response.get('data', {})
        position_list = data.get('positionList', [])
        count = data.get('count', 0)

        if expected_total is None:
            expected_total = count
            total_pages = max(1, math.ceil(count / PAGE_SIZE))

        checked = now()
        # Save evidence (safe fields only - no applicant data)
        safe_rows = []
        for row in position_list:
            safe_rows.append({
                'id': row.get('id'),
                'postId': row.get('postId'),
                'positionTitle': row.get('positionTitle'),
                'positionFamily': row.get('positionFamily'),
                'bgs': row.get('bgs'),
                'workCities': row.get('workCities'),
                'projectName': row.get('projectName'),
                'recruitLabelName': row.get('recruitLabelName'),
                'positionSource': row.get('positionSource'),
            })
        evidence_path = collector.evidence_file(
            f'tencent-page-{page}.json',
            json.dumps({
                'source_url': API_URL,
                'request_body': {'pageIndex': page, 'pageSize': PAGE_SIZE},
                'reviewed_at': checked,
                'count': count,
                'page': page,
                'pageSize': PAGE_SIZE,
                'positionList': safe_rows,
            }, ensure_ascii=False, indent=2)
        )

        for row in position_list:
            post_id = str(row.get('postId') or row.get('id') or '')
            if not post_id or post_id in seen_ids:
                continue
            seen_ids.add(post_id)

            title = (row.get('positionTitle') or '').strip()
            if not title:
                continue
            # Skip non-job entries
            if re.search(r'需登录|请登录|投递入口|报名入口|招聘公告', title):
                continue

            source_url = DETAIL_URL.format(post_id=post_id)
            job = base_job('tencent-' + post_id, '腾讯科技（深圳）有限公司', title, source_url, checked)

            cities = parse_cities(row.get('workCities', ''))
            family_id = row.get('positionFamily')
            bgs = (row.get('bgs') or '').strip()
            project_name = row.get('projectName') or ''
            recruit_label = row.get('recruitLabelName') or ''

            # Determine cohort from project/label
            cohort_raw = ''
            if '应届' in project_name or '应届' in recruit_label:
                cohort_raw = recruit_label or project_name

            job.update(
                recruitment_unit='腾讯科技（深圳）有限公司',
                job_category=parse_position_family(family_id),
                cities=cities,
                recruiting_unit_raw=bgs if bgs else '',
                hiring_department_raw=bgs if bgs else '',
                cohort_raw=cohort_raw,
                campaign_cohort_raw=project_name or recruit_label,
                source_name='腾讯校园招聘官方网站',
                source_record_id=post_id,
                application_url=source_url,
                job_listing_url=LISTING_URL,
                campaign_url=LISTING_URL,
                evidence_path=evidence_path,
                description_raw=f'职位族ID: {family_id}; 事业群: {bgs}; 项目: {project_name}; 招聘标签: {recruit_label}',
                record_kind='official_position_id',
                status='unverified',
                status_note='公开校招岗位列表可见；未披露截止日期，未尝试投递。',
            )
            jobs.append(job)

        logging.info('tencent page %d/%d: %d rows (total collected: %d)',
                     page, total_pages, len(position_list), len(jobs))

        if max_pages and page >= max_pages:
            break
        if page >= total_pages or not position_list:
            break
        page += 1

    # Completeness check
    complete = (expected_total is not None and len(seen_ids) == expected_total
                and not errors and not max_pages)

    collector.states['tencent'] = {
        'status': 'success' if not errors else ('partial' if jobs else 'failed'),
        'checked_at': now(),
        'expected_total': expected_total,
        'collected_jobs': len(jobs),
        'unique_source_ids': len(seen_ids),
        'total_pages': total_pages,
        'pages_scanned': pages_scanned,
        'complete': complete,
        'errors': errors,
        'api_url': API_URL,
        'listing_url': LISTING_URL,
    }
    return jobs


def main():
    parser = argparse.ArgumentParser(description='Tencent campus recruitment collector')
    parser.add_argument('--output-dir', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'data' / 'tencent_pending')
    parser.add_argument('--max-pages', type=int, default=0,
                        help='Limit pages scanned (0 = all)')
    parser.add_argument('--delay', type=float, default=1.25)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    collector = Collector(args.output_dir, max(1.0, args.delay))
    try:
        rows = collect_tencent(collector, max_pages=args.max_pages)
        write_json(args.output_dir / 'jobs.json', rows)
        write_json(args.output_dir / 'source_state.json', collector.states)
        write_json(args.output_dir / 'alerts.json',
                   {'run_finished_at': now(), 'alerts': collector.alerts})
        print(json.dumps(collector.states['tencent'], ensure_ascii=False, indent=2))
    except Exception as e:
        collector.alert('tencent', e)
        write_json(args.output_dir / 'alerts.json',
                   {'run_finished_at': now(), 'alerts': collector.alerts})
        raise SystemExit(f'Tencent collection failed: {e}')


if __name__ == '__main__':
    main()
