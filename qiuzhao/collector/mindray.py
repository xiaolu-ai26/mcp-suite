"""Mindray (迈瑞医疗) recruitment public API adapter.

Endpoint: POST https://career.mindray.com/api/Jobad/GetJobAdPageList
tenantId=106239. Public position listing; no login, no CAPTCHA.

Note: the public endpoint does not expose a stable campus-only flag; it returns
the full public board (mix of campus + experienced hires). We record the full
public list and tag likely-campus roles by requirement keywords so downstream
release can decide. completeness is reported against the API Count.
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

API_URL = 'https://career.mindray.com/api/Jobad/GetJobAdPageList'
DETAIL_URL = 'https://career.mindray.com/job/{job_ad_id}'
LISTING_URL = 'https://career.mindray.com/'
UA = 'QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'
PAGE_SIZE = 100
TENANT_ID = 106239
CAMPUS_HINT = re.compile(r'应届|20\d{2}届|校招|校园招聘')


def fetch_page(page_index, page_size=PAGE_SIZE, delay=1.25, last_call=None):
    if last_call is not None:
        time.sleep(max(0, delay - (time.monotonic() - last_call)))
    body = json.dumps({'tenantId': TENANT_ID, 'PageIndex': page_index, 'PageSize': page_size}).encode()
    headers = {'User-Agent': UA, 'Content-Type': 'application/json',
               'Accept': 'application/json, text/plain, */*', 'Referer': LISTING_URL}
    with urlopen(Request(API_URL, data=body, headers=headers), timeout=35) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
    return json.loads(raw.decode('utf-8', 'replace')), time.monotonic()


def collect_mindray(collector, max_pages=0):
    jobs, seen_ids = [], set()
    expected_total = None
    total_pages = None
    page = 0  # PageIndex is 0-based on this API
    pages_scanned = 0
    last_call = 0
    errors = []
    campus_hits = 0

    while True:
        try:
            response, last_call = fetch_page(page, PAGE_SIZE, collector.delay, last_call)
        except Exception as e:
            errors.append({'page': page, 'error': str(e)[:200]})
            collector.alert('mindray', f'page {page} fetch failed: {e}')
            break

        pages_scanned += 1
        if response.get('Code') != 200:
            errors.append({'page': page, 'error': f"Code {response.get('Code')}: {response.get('Message')}"})
            collector.alert('mindray', f"API error on page {page}: {response.get('Message')}")
            break

        row_list = response.get('Data') or []
        expected_total = response.get('Count', expected_total)
        if expected_total:
            import math
            total_pages = max(1, math.ceil(expected_total / PAGE_SIZE))

        checked = now()
        safe_rows = [{
            'JobAdId': r.get('JobAdId'), 'JobAdName': r.get('JobAdName'),
            'CategoryId': r.get('CategoryId'), 'LocNames': r.get('LocNames'),
        } for r in row_list]
        evidence_path = collector.evidence_file(
            f'mindray-page-{page}.json',
            json.dumps({'source_url': API_URL, 'request_body': {'tenantId': TENANT_ID, 'PageIndex': page},
                         'reviewed_at': checked, 'Count': expected_total, 'list': safe_rows},
                        ensure_ascii=False, indent=2))

        for row in row_list:
            jid = str(row.get('JobAdId') or '')
            if not jid or jid in seen_ids:
                continue
            seen_ids.add(jid)
            title = (row.get('JobAdName') or '').strip()
            if not title or re.search(r'需登录|请登录|投递入口|报名入口|招聘公告', title):
                continue

            cities = row.get('LocNames') or []
            duty = row.get('Duty') or ''
            req = row.get('Require') or ''
            full_desc = duty + (f'\n\n【任职要求】\n{req}' if req else '')
            is_campus = bool(CAMPUS_HINT.search(req) or CAMPUS_HINT.search(title))
            if is_campus:
                campus_hits += 1

            source_url = DETAIL_URL.format(job_ad_id=jid)
            job = base_job('mindray-' + jid, '深圳迈瑞生物医疗电子股份有限公司', title, source_url, checked)
            job.update(
                recruitment_unit='深圳迈瑞生物医疗电子股份有限公司',
                job_category=row.get('Category') or '',
                cities=cities,
                cohort_raw='2027届校园招聘' if is_campus else '',
                campaign_cohort_raw='迈瑞2027校园招聘' if is_campus else '',
                source_name='迈瑞医疗招聘官方网站',
                source_record_id=jid,
                application_url=source_url,
                job_listing_url=LISTING_URL,
                campaign_url=LISTING_URL,
                evidence_path=evidence_path,
                description_raw=full_desc[:5000],
                requirement_raw=req[:3000],
                record_kind='official_job_ad_id',
                campus_guess=is_campus,
                status='unverified',
                status_note='公开岗位列表可见；公开接口未提供稳定校招过滤，按要求关键词标注疑似校招岗位，未尝试投递。',
            )
            jobs.append(job)

        logging.info('mindray page %s/%s: %d rows (collected: %d, campus-hint: %d)',
                     page, total_pages, len(row_list), len(jobs), campus_hits)
        if max_pages and page >= max_pages:
            break
        if not row_list or (total_pages and page >= total_pages):
            break
        page += 1

    complete = (expected_total is not None and len(seen_ids) == expected_total
                and not errors and not max_pages)
    collector.states['mindray'] = {
        'status': 'success' if not errors else ('partial' if jobs else 'failed'),
        'checked_at': now(), 'expected_total': expected_total,
        'collected_jobs': len(jobs), 'unique_source_ids': len(seen_ids),
        'campus_hint_jobs': campus_hits,
        'total_pages': total_pages, 'pages_scanned': pages_scanned,
        'complete': complete, 'errors': errors,
        'note': 'public board mixes campus+experienced; campus_guess by keyword',
        'api_url': API_URL, 'listing_url': LISTING_URL,
    }
    return jobs


def main():
    p = argparse.ArgumentParser(description='Mindray recruitment collector')
    p.add_argument('--output-dir', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'data' / 'mindray_pending')
    p.add_argument('--max-pages', type=int, default=0)
    p.add_argument('--delay', type=float, default=1.25)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    collector = Collector(args.output_dir, max(1.0, args.delay))
    try:
        rows = collect_mindray(collector, max_pages=args.max_pages)
        write_json(args.output_dir / 'jobs.json', rows)
        write_json(args.output_dir / 'source_state.json', collector.states)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        print(json.dumps(collector.states['mindray'], ensure_ascii=False, indent=2))
    except Exception as e:
        collector.alert('mindray', e)
        write_json(args.output_dir / 'alerts.json', {'run_finished_at': now(), 'alerts': collector.alerts})
        raise SystemExit(f'Mindray collection failed: {e}')


if __name__ == '__main__':
    main()
