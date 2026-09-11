"""NetEase (网易) campus recruitment public API adapter.

Endpoint: GET https://campus.163.com/api/campuspc/position/getJobList?projectId=...
  projectId=103 -> 网易主站校招
  projectId=102 -> 网易互娱校招
No login, no CAPTCHA, no paid content. Public campus position listing.

Standalone: python -m qiuzhao.collector.netease --output-dir <dir>
Integration: rows = collect_netease(collector, project_id=103, ...)
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .run import Collector, base_job, now, write_json

API_URL = 'https://campus.163.com/api/campuspc/position/getJobList'
DETAIL_URL = 'https://campus.163.com/position/detail?id={job_id}'
LISTING_URL = 'https://campus.163.com/campus/position'
UA = 'QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'
PAGE_SIZE = 100  # pageIndex param is ignored server-side; one large page returns all rows

# projectId -> (source_id suffix, employer label, campaign label)
PROJECTS = {
    103: ('netease', '网易（杭州）网络有限公司', '网易2027校园招聘'),
    102: ('netease-huyu', '网易互动娱乐有限公司', '网易互娱2027校园招聘'),
}


def fetch_page(project_id, page_index, page_size=PAGE_SIZE, delay=1.25, last_call=None):
    if last_call is not None:
        time.sleep(max(0, delay - (time.monotonic() - last_call)))
    qs = urlencode({'projectId': project_id, 'pageIndex': page_index, 'pageSize': page_size})
    headers = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
               'Referer': LISTING_URL}
    with urlopen(Request(f'{API_URL}?{qs}', headers=headers), timeout=35) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'replace')), time.monotonic()


def collect_netease(collector, project_id=103, max_pages=0):
    source_key, employer, campaign = PROJECTS.get(project_id, (f'netease-{project_id}', '网易', f'网易项目{project_id}校招'))
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
            response, last_call = fetch_page(project_id, page, PAGE_SIZE, collector.delay, last_call)
        except Exception as e:
            errors.append({'page': page, 'error': str(e)[:200]})
            collector.alert(source_key, f'page {page} fetch failed: {e}')
            break

        pages_scanned += 1
        if response.get('code') != 200:
            errors.append({'page': page, 'error': f"code {response.get('code')}: {response.get('msg')}"})
            collector.alert(source_key, f"API error on page {page}: {response.get('msg')}")
            break

        data = response.get('data', {})
        row_list = data.get('list', []) or []
        expected_total = data.get('total', expected_total)
        total_pages = data.get('pages', total_pages)

        checked = now()
        safe_rows = [{
            'id': r.get('id'), 'positionName': r.get('positionName'),
            'positionTypeName': r.get('positionTypeName'), 'workPlaceName': r.get('workPlaceName'),
        } for r in row_list]
        evidence_path = collector.evidence_file(
            f'{source_key}-page-{page}.json',
            json.dumps({'source_url': API_URL, 'request_query': {'projectId': project_id, 'pageIndex': page},
                         'reviewed_at': checked, 'total': expected_total, 'pages': total_pages,
                         'list': safe_rows}, ensure_ascii=False, indent=2))

        for row in row_list:
            pid = str(row.get('id') or '')
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            title = (row.get('positionName') or '').strip()
            if not title or re.search(r'需登录|请登录|投递入口|报名入口|招聘公告', title):
                continue

            cities = [c.strip() for c in (row.get('workPlaceName') or '').replace('，', ',').split(',') if c.strip()]
            desc = row.get('positionDescription') or ''
            req = row.get('positionRequirement') or ''
            full_desc = desc + (f'\n\n【职位要求】\n{req}' if req else '')

            source_url = DETAIL_URL.format(job_id=pid)
            job = base_job(f'{source_key}-{pid}', employer, title, source_url, checked)
            job.update(
                recruitment_unit=employer,
                job_category=row.get('positionTypeName') or '',
                cities=cities,
                cohort_raw='2027届校园招聘',
                campaign_cohort_raw=campaign,
                source_name='网易校园招聘官方网站',
                source_record_id=pid,
                application_url=source_url,
                job_listing_url=LISTING_URL,
                campaign_url=LISTING_URL,
                evidence_path=evidence_path,
                description_raw=full_desc[:5000],
                requirement_raw=req[:3000],
                record_kind='official_position_id',
                status='unverified',
                status_note='公开校招岗位列表可见；未披露截止日期，未尝试投递。',
            )
            jobs.append(job)

        logging.info('%s page %s/%s: %d rows (collected: %d)',
                     source_key, page, total_pages, len(row_list), len(jobs))
        if max_pages and page >= max_pages:
            break
        if not row_list or (total_pages and page >= total_pages):
            break
        page += 1

    complete = (expected_total is not None and len(seen_ids) == expected_total
                and not errors and not max_pages)
    collector.states[source_key] = {
        'status': 'success' if not errors else ('partial' if jobs else 'failed'),
        'checked_at': now(), 'project_id': project_id, 'campaign': campaign,
        'expected_total': expected_total, 'collected_jobs': len(jobs),
        'unique_source_ids': len(seen_ids), 'total_pages': total_pages,
        'pages_scanned': pages_scanned, 'complete': complete, 'errors': errors,
        'api_url': API_URL, 'listing_url': LISTING_URL,
    }
    return jobs


def collect_netease_all(collector, max_pages=0):
    """Collect all NetEase projects (main + huyu)."""
    rows = []
    for pid in (103, 102):
        try:
            rows.extend(collect_netease(collector, pid, max_pages=max_pages))
        except Exception as e:
            collector.alert(f'netease-{pid}', e)
    return rows


def main():
    p = argparse.ArgumentParser(description='NetEase campus recruitment collector')
    p.add_argument('--output-dir', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'data' / 'netease_pending')
    p.add_argument('--project-id', type=int, default=0, help='0 = all projects')
    p.add_argument('--max-pages', type=int, default=0)
    p.add_argument('--delay', type=float, default=1.25)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    collector = Collector(args.output_dir, max(1.0, args.delay))
    try:
        if args.project_id:
            rows = collect_netease(collector, args.project_id, max_pages=args.max_pages)
        else:
            rows = collect_netease_all(collector, max_pages=args.max_pages)
        write_json(args.output_dir / 'jobs.json', rows)
        write_json(args.output_dir / 'source_state.json', collector.states)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        print(json.dumps({k: v for k, v in collector.states.items() if k.startswith('netease')},
                         ensure_ascii=False, indent=2))
    except Exception as e:
        collector.alert('netease', e)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        raise SystemExit(f'NetEase collection failed: {e}')


if __name__ == '__main__':
    main()
