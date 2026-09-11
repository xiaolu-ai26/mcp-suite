"""Midea (美的) campus recruitment public API adapter.

Endpoint: POST https://careers.midea.com/backend/school/position/common/position/list
Requires projectRuleId (resolved from the public project list endpoint):
  055bb05d-1957-4ea0-bb21-873ca0164d84 -> 2027届美的星校园招聘
No login, no CAPTCHA, no paid content.
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

API_URL = 'https://careers.midea.com/backend/school/position/common/position/list'
PROJECT_URL = 'https://careers.midea.com/backend/school/position/common/project/list'
DETAIL_URL = 'https://careers.midea.com/campus/position/{position_id}'
LISTING_URL = 'https://careers.midea.com/campus'
UA = 'QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'
PAGE_SIZE = 50
CAMPUS_PROJECT_KEYWORD = '校园招聘'  # pick the campus project rule by name


def _post(url, payload, delay, last_call, referer=LISTING_URL):
    if last_call is not None:
        time.sleep(max(0, delay - (time.monotonic() - last_call)))
    body = json.dumps(payload).encode()
    headers = {'User-Agent': UA, 'Content-Type': 'application/json',
               'Accept': 'application/json, text/plain, */*', 'Referer': referer}
    with urlopen(Request(url, data=body, headers=headers), timeout=35) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'replace')), time.monotonic()


def _get(url, delay, last_call, referer=LISTING_URL):
    if last_call is not None:
        time.sleep(max(0, delay - (time.monotonic() - last_call)))
    headers = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*', 'Referer': referer}
    with urlopen(Request(url, headers=headers), timeout=35) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'replace')), time.monotonic()


def resolve_campus_project_rule_id(delay=1.25):
    """Resolve the active campus projectRuleId from the public project list."""
    data, _ = _get(PROJECT_URL, delay, 0)
    projects = data.get('data') or []
    for p in projects:
        if p.get('status') == 1 and CAMPUS_PROJECT_KEYWORD in (p.get('projectRuleName') or '') \
                and p.get('employementCategory') == 1:
            return p.get('projectRuleId'), p.get('projectRuleName'), projects
    raise ValueError('No active campus project rule found in Midea project list')


def collect_midea(collector, project_rule_id=None, max_pages=0):
    last_call = 0
    if not project_rule_id:
        try:
            project_rule_id, project_name, projects = resolve_campus_project_rule_id(collector.delay)
            collector.evidence_file('midea-projects.json',
                                    json.dumps(projects, ensure_ascii=False, indent=2))
        except Exception as e:
            collector.alert('midea', f'project resolve failed: {e}')
            collector.states['midea'] = {'status': 'failed', 'checked_at': now(),
                                          'error': str(e)[:300]}
            return []
    else:
        project_name = 'configured'

    jobs, seen_ids = [], set()
    expected_total = None
    total_pages = None
    page = 1
    pages_scanned = 0
    errors = []

    while True:
        try:
            response, last_call = _post(API_URL,
                                        {'projectRuleId': project_rule_id, 'pageIndex': page, 'pageSize': PAGE_SIZE},
                                        collector.delay, last_call)
        except Exception as e:
            errors.append({'page': page, 'error': str(e)[:200]})
            collector.alert('midea', f'page {page} fetch failed: {e}')
            break

        pages_scanned += 1
        if str(response.get('code')) != '0':
            errors.append({'page': page, 'error': f"code {response.get('code')}: {response.get('message')}"})
            collector.alert('midea', f"API error on page {page}: {response.get('message')}")
            break

        data = response.get('data', {})
        row_list = data.get('data') or []
        expected_total = data.get('total', expected_total)
        pg = data.get('info') or {}
        total_pages = pg.get('totalPage', total_pages)

        checked = now()
        safe_rows = [{
            'positionId': r.get('positionId'),
            'projectPositionName': r.get('projectPositionName'),
            'recruitCategoryName': r.get('recruitCategoryName'),
            'workPlaceCode': r.get('workPlaceCode'),
        } for r in row_list]
        evidence_path = collector.evidence_file(
            f'midea-page-{page}.json',
            json.dumps({'source_url': API_URL, 'request_body': {'projectRuleId': project_rule_id, 'pageIndex': page},
                         'reviewed_at': checked, 'total': expected_total, 'info': pg,
                         'list': safe_rows}, ensure_ascii=False, indent=2))

        for row in row_list:
            pid = str(row.get('positionId') or '')
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            inner = row.get('projectPositionDto') or {}
            title = (inner.get('positionName') or row.get('projectPositionName') or '').strip()
            if not title or re.search(r'需登录|请登录|投递入口|报名入口|招聘公告', title):
                continue

            cities = [w.get('workPlaceName') for w in (row.get('workplaceDtoList') or []) if w.get('workPlaceName')]
            if not cities and row.get('workPlaceCode'):
                cities = [row['workPlaceCode']]
            duty = inner.get('jobResponsibility') or ''
            req = inner.get('jobRequirement') or ''
            full_desc = duty + (f'\n\n【任职要求】\n{req}' if req else '')

            source_url = DETAIL_URL.format(position_id=pid)
            job = base_job('midea-' + pid, '广东美的制冷家电集团股份有限公司', title, source_url, checked)
            job.update(
                recruitment_unit='美的集团股份有限公司',
                job_category=row.get('recruitCategoryName') or inner.get('largeTypeName') or '',
                cities=cities,
                cohort_raw='2027届美的星校园招聘',
                campaign_cohort_raw=project_name,
                source_name='美的集团校园招聘官方网站',
                source_record_id=pid,
                application_url=source_url,
                job_listing_url=LISTING_URL,
                campaign_url=LISTING_URL,
                evidence_path=evidence_path,
                description_raw=full_desc[:5000],
                requirement_raw=req[:3000],
                position_code=inner.get('positionCode') or '',
                record_kind='official_position_id',
                status='unverified',
                status_note='公开校招岗位列表可见；未披露截止日期，未尝试投递。',
            )
            jobs.append(job)

        logging.info('midea page %s/%s: %d rows (collected: %d)',
                     page, total_pages, len(row_list), len(jobs))
        if max_pages and page >= max_pages:
            break
        if not row_list or (total_pages and page >= total_pages):
            break
        page += 1

    complete = (expected_total is not None and len(seen_ids) == expected_total
                and not errors and not max_pages)
    collector.states['midea'] = {
        'status': 'success' if not errors else ('partial' if jobs else 'failed'),
        'checked_at': now(), 'project_rule_id': project_rule_id, 'project_name': project_name,
        'expected_total': expected_total, 'collected_jobs': len(jobs),
        'unique_source_ids': len(seen_ids), 'total_pages': total_pages,
        'pages_scanned': pages_scanned, 'complete': complete, 'errors': errors,
        'api_url': API_URL, 'listing_url': LISTING_URL,
    }
    return jobs


def main():
    p = argparse.ArgumentParser(description='Midea campus recruitment collector')
    p.add_argument('--output-dir', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'data' / 'midea_pending')
    p.add_argument('--project-rule-id', default='')
    p.add_argument('--max-pages', type=int, default=0)
    p.add_argument('--delay', type=float, default=1.25)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    collector = Collector(args.output_dir, max(1.0, args.delay))
    try:
        rows = collect_midea(collector, project_rule_id=args.project_rule_id or None, max_pages=args.max_pages)
        write_json(args.output_dir / 'jobs.json', rows)
        write_json(args.output_dir / 'source_state.json', collector.states)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        print(json.dumps(collector.states['midea'], ensure_ascii=False, indent=2))
    except Exception as e:
        collector.alert('midea', e)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        raise SystemExit(f'Midea collection failed: {e}')


if __name__ == '__main__':
    main()
