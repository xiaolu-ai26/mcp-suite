"""Meituan official public recruitment adapter.

Scope support: campus / intern / social (jobType 1 / 2 / 3).

Input contract:
collect(company, scope, output_dir) -> dict
  with keys jobs, coverage.

All output is persisted per invocation as:
- candidate.json
- coverage.json
- result.json (checkpoint + final summary)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import datetime as dt
import gzip
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = 'https://zhaopin.meituan.com/api/official/job/getJobList'
DETAIL_URL = 'https://zhaopin.meituan.com/web/position/detail?jobUnionId={job_union_id}'
SOURCE_URL = 'https://zhaopin.meituan.com/web/position'
UA = 'QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'
# Probed 2026-09-20: the endpoint honours pageSize=100 (100 rows back, totalPage
# recomputed as ceil(totalCount/100) for every scope), so the 2501-posting social
# list costs 26 requests instead of 126 -- fewer requests is the politeness win.
PAGE_SIZE = 100
# Politely space list pages. This adapter used to sleep 0.08s between pages, and the
# 2026-09-20 run died at page 16 (social) with an SSL EOF: the fix is retry + pacing,
# not a page cap. The floor is never lowered, and p1_pipeline's
# QIUZHAO_PLATFORM_REQUEST_INTERVAL (>=1s) can only raise it.
REQUEST_INTERVAL_FLOOR = 1.0
MAX_ATTEMPTS = 4
RETRY_BACKOFF_BASE = 1.0
RETRY_BACKOFF_CAP = 8.0
# If the site's own totalPage is smaller than its own totalCount, keep asking for the
# remaining pages instead of trusting a number that would silently drop rows.
PAGE_OVERRUN_LIMIT = 20

SCOPE_TO_JOB_TYPE = {'campus': '1', 'intern': '2', 'social': '3'}
RECRUITMENT_TYPES = {'campus': '校园招聘', 'intern': '实习招聘', 'social': '社会招聘'}


def _page_interval() -> float:
    """Seconds between list pages; the environment hook can only slow us down."""
    raw = os.environ.get('QIUZHAO_PLATFORM_REQUEST_INTERVAL')
    try:
        value = float(raw) if raw not in (None, '') else REQUEST_INTERVAL_FLOOR
    except (TypeError, ValueError):
        value = REQUEST_INTERVAL_FLOOR
    return max(REQUEST_INTERVAL_FLOOR, value)



def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _is_boilerplate(text: str) -> bool:
    from qiuzhao.collector.p1_sources_11_20 import role_body
    if not re.search(r'[A-Za-z0-9\u4e00-\u9fff]', str(text or '')):
        return True
    try:
        role_body(text, '')
    except ValueError:
        return True
    return False


def _safe_fields(row: Dict[str, Any]) -> Tuple[str, str, List[str], str, str, str]:
    """Extract title, id, city names, jobDuty, jobRequirement, and project name."""
    job_id = str(row.get('jobUnionId') or '').strip()
    title = str(row.get('name') or '').strip()
    cities = [str(city.get('name') or '').strip() for city in (row.get('cityList') or [])]
    cities = [city for city in cities if city]
    duty = str(row.get('jobDuty') or '').strip()
    req = str(row.get('jobRequirement') or '').strip()
    project_name = str(row.get('projectName') or '').strip()
    return job_id, title, cities, duty, req, project_name


def _sentence_split(text: str) -> List[str]:
    return [part.strip() for part in re.split(r'[；;。;\n]+', str(text or '')) if part.strip()]


def _education_values(text: str) -> str:
    # Preserve the qualifying sentence, including lower bounds and exceptions.
    return '；'.join(sentence for sentence in _sentence_split(text)
                    if re.search(r'学历|博士|硕士|本科|专科|大专|高中|bachelor|master|ph\.?d', sentence, re.I))


def _major_values(text: str) -> str:
    # A preference for experience is not an academic major requirement.
    return '；'.join(sentence for sentence in _sentence_split(text)
                    if re.search(r'相关专业|专业(?:不限|背景|要求|方向|优先|毕业)|\bmajor(?:ing)?\s+(?:in|requirements?)\b|\bdegree in\b', sentence, re.I))


def _stable_id(company: str, scope: str, source_id: str) -> str:
    raw = f'{company}|{scope}|{source_id}'
    return 'p1-' + hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]


def _post_json(payload: Dict[str, Any], timeout: int = 30, attempts: int = MAX_ATTEMPTS,
               on_retry=None) -> Dict[str, Any]:
    """POST one page, retrying transient transport failures.

    The 2026-09-20 daily run collected only 320/2500 social postings because a single
    ``SSL: UNEXPECTED_EOF_WHILE_READING`` at page 16 aborted the whole scope. Such an
    EOF (and a truncated/empty body) is transient: retry it with backoff. A 4xx other
    than 408/429 is a real answer and is never retried.
    """
    request = Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={
            'User-Agent': UA,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'Referer': SOURCE_URL,
            'Origin': 'https://zhaopin.meituan.com',
        },
        method='POST',
    )

    attempts = max(1, int(attempts))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                if response.headers.get('Content-Encoding') == 'gzip' or body[:2] == b'\x1f\x8b':
                    body = gzip.decompress(body)
                text = body.decode('utf-8', errors='replace')
                return json.loads(text)
        except HTTPError as error:
            detail = (error.read()[:200]).decode('utf-8', errors='replace') if hasattr(error, 'read') else ''
            if error.code < 500 and error.code not in (408, 429):
                raise RuntimeError(f'HTTP {error.code} {error.reason}: {detail}') from error
            last_error = RuntimeError(f'HTTP {error.code} {error.reason}: {detail}')
        except (URLError, OSError, json.JSONDecodeError) as error:
            # URLError, ssl.SSLError, ConnectionResetError/RemoteDisconnected and a
            # truncated body all land here; all of them are worth one more attempt.
            last_error = error
        if attempt < attempts:
            if on_retry is not None:
                on_retry(attempt, last_error)
            time.sleep(min(RETRY_BACKOFF_CAP, RETRY_BACKOFF_BASE * (2 ** (attempt - 1))))

    if isinstance(last_error, json.JSONDecodeError):
        raise RuntimeError(f'Invalid JSON response: {last_error}') from last_error
    raise RuntimeError(f'Network failure: {last_error}') from last_error



def _append_trace(coverage: Dict[str, Any], page_no: int, page_total: int | None, response: Dict[str, Any], payload: Dict[str, Any], page_path: str) -> None:
    coverage.setdefault('evidence_files', []).append(page_path)
    coverage.setdefault('evidence', []).append(page_path)
    coverage.setdefault('api_calls', []).append({
        'page': page_no,
        'requested_total_page': page_total,
        'requested_status': response.get('status'),
        'page_url': API_URL,
        'payload': payload,
    })


def _is_valid_type(expected: str, observed: str) -> bool:
    return str(observed or '') == expected


def collect(company: str, scope: str, output_dir: Path) -> Dict[str, Any]:
    if company != '美团':
        raise ValueError('collect supports only company=美团')
    if scope not in SCOPE_TO_JOB_TYPE:
        raise ValueError('scope must be campus/intern/social')

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scope_code = SCOPE_TO_JOB_TYPE[scope]
    expected_type_name = RECRUITMENT_TYPES[scope]
    candidate_path = output_dir / 'candidate.json'
    coverage_path = output_dir / 'coverage.json'
    result_path = output_dir / 'result.json'

    coverage: Dict[str, Any] = {
        'status': 'partial',
        'complete': False,
        'expected_total': None,
        'collected_jobs': 0,
        'pages_scanned': 0,
        'detail_complete': False,
        'source_url': API_URL,
        'errors': [],
        'evidence': [],
        'evidence_files': [],
        'scope_evidence': '官方公开API: zhaopin.meituan.com/api/official/job/getJobList',
        'scope_request': {
            'company': company,
            'scope': scope,
            'source_url': API_URL,
            'params': {
                'page': {
                    'pageNo': 1,
                    'pageSize': PAGE_SIZE,
                },
                'jobShareType': '1',
                'jobType': [{'code': scope_code, 'subCode': []}],
                'keywords': '',
                'cityList': [],
                'department': [],
                'jfJgList': [],
                'typeCode': [],
                'specialCode': [],
            },
        },
        'scope': scope,
        'company': company,
        'collected_source_ids': [],
        'unique_source_ids': 0,
        'detail_missing_count': 0,
        'jobs_with_missing_fields': [],
        'pending_source_ids': [],
        'pagination_exhausted': False,
        'last_page_evidence': '',
        'page_size': PAGE_SIZE,
        'request_interval': None,
        'retries': 0,
        'api_calls': [],
        'reviewed_at': _now_iso(),
    }

    jobs: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    reviewed_at = _now_iso()

    expected_total = None
    observed_total_pages: int | None = None
    errors: List[str] = []
    interval = _page_interval()
    coverage['request_interval'] = interval
    retries = 0

    def _note_retry(attempt: int, error: Exception) -> None:
        nonlocal retries
        retries += 1

    try:
        for page_no in range(1, 1000000):
            payload = {
                'page': {'pageNo': page_no, 'pageSize': PAGE_SIZE},
                'jobShareType': '1',
                'keywords': '',
                'cityList': [],
                'department': [],
                'jfJgList': [],
                'jobType': [{'code': scope_code, 'subCode': []}],
                'typeCode': [],
                'specialCode': [],
            }

            response = _post_json(payload, on_retry=_note_retry)

            if str(response.get('status')) != '1':
                errors.append(f'API status={response.get("status")!r}, message={response.get("message")!r}')
                break

            data = response.get('data') or {}
            page_info = data.get('page') or {}
            current_total_count = page_info.get('totalCount')
            current_total_page = page_info.get('totalPage')
            if current_total_count is not None:
                if expected_total is None:
                    expected_total = int(current_total_count)
                    coverage['expected_total'] = expected_total
                elif int(expected_total) != int(current_total_count):
                    errors.append(
                        f'totalCount drift at page {page_no}: expected={expected_total}, observed={current_total_count}'
                    )
                    break
            if current_total_page is not None:
                current_total_page = int(current_total_page)
                if observed_total_pages is None:
                    observed_total_pages = current_total_page
                elif observed_total_pages != current_total_page:
                    errors.append(
                        f'totalPage drift at page {page_no}: expected={observed_total_pages}, observed={current_total_page}'
                    )
                    break

            rows = data.get('list') or []
            if not isinstance(rows, list):
                errors.append(f'Invalid list type at page {page_no}')
                break

            reviewed_at = _now_iso()
            page_path = output_dir / f'list-{page_no}.json'
            page_path.write_text(
                json.dumps(
                    {
                        'source_url': API_URL,
                        'request_body': payload,
                        'reviewed_at': reviewed_at,
                        'page': page_info,
                        'rows': rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding='utf-8',
            )
            _append_trace(coverage, page_no, observed_total_pages, response, payload, str(page_path))

            coverage['pages_scanned'] += 1

            for row in rows:
                if not isinstance(row, dict):
                    continue

                source_id, title, cities, duty, req, project_name = _safe_fields(row)
                if not source_id:
                    continue
                if source_id in seen_ids:
                    errors.append(f'duplicate source_record_id={source_id} at page={page_no}')
                    continue

                actual_type = str(row.get('jobType') or '')
                if not _is_valid_type(scope_code, actual_type):
                    errors.append(f'jobType mismatch for {source_id}: expected={scope_code}, observed={actual_type}')
                    continue

                has_duty = bool(duty and not _is_boilerplate(duty))
                has_req = bool(req and not _is_boilerplate(req))
                if not has_duty and not has_req:
                    coverage['detail_missing_count'] += 1
                    coverage.setdefault('pending_source_ids', []).append(source_id)
                    continue

                raw_parts = []
                if duty:
                    raw_parts.append(duty)
                if req:
                    raw_parts.append(req)
                description_raw = '\n\n'.join(raw_parts).strip()

                source_missing_fields = []
                if not has_duty:
                    source_missing_fields.append('jobDuty')
                if not has_req:
                    source_missing_fields.append('jobRequirement')

                if source_missing_fields:
                    coverage['jobs_with_missing_fields'].append(source_id)

                application_url = DETAIL_URL.format(job_union_id=source_id)
                reviewed = reviewed_at
                record = {
                    'id': _stable_id(company, scope, source_id),
                    'source_record_id': source_id,
                    'job_title': title,
                    'recruitment_unit': company,
                    'recruitment_type': expected_type_name,
                    'source_url': application_url,
                    'detail_url': application_url,
                    'application_url': application_url,
                    'cities': cities,
                    'reviewed_at': reviewed,
                    'description_raw': description_raw,
                    'education_raw': _education_values(req),
                    'major_requirements_raw': _major_values(req),
                    'cohort_raw': '',
                    'campaign_cohort_raw': project_name,
                    'campaign_scope': 'project' if project_name else '',
                    'cohort_scope': 'project' if project_name else '',
                    'evidence_path': str(page_path.resolve()),
                    'field_completeness': {'jobDuty': has_duty, 'jobRequirement': has_req},
                    'source_missing_fields': source_missing_fields,
                    'source_scope': expected_type_name,
                    'source_refresh_time': row.get('refreshTime'),
                    'source_expired_time': row.get('expiredTime'),
                }
                jobs.append(record)
                seen_ids.add(source_id)

            if rows:
                coverage['collected_source_ids'] = sorted(seen_ids)

            if not rows:
                # An empty page is the site itself saying "no more rows"; do not keep
                # hammering page N+1..N+20 just because totalCount was optimistic.
                coverage['last_page_evidence'] = str(page_path)
                if expected_total is not None and len(seen_ids) >= expected_total:
                    coverage['pagination_exhausted'] = True
                else:
                    errors.append(
                        f'list exhausted at page {page_no} with {len(seen_ids)} of '
                        f'totalCount={expected_total} postings')
                break

            if observed_total_pages is not None and page_no >= observed_total_pages:
                if expected_total is None or len(seen_ids) >= expected_total:
                    coverage['pagination_exhausted'] = True
                    coverage['last_page_evidence'] = str(page_path)
                    break
                # totalPage is short of totalCount: the site's own page count would
                # silently drop rows (the 2026-09-20 "320/2500" shape), so keep asking
                # for the remaining pages -- bounded, and recorded as evidence.
                if page_no >= observed_total_pages + PAGE_OVERRUN_LIMIT:
                    errors.append(
                        f'reported totalPage={observed_total_pages} exhausted at page '
                        f'{page_no} but only {len(seen_ids)} of totalCount={expected_total} collected')
                    break
                coverage['pages_beyond_reported_total'] = page_no + 1 - observed_total_pages
                time.sleep(interval)
                continue

            # Avoid an infinite loop in malformed responses, but still no fixed hard cap.
            if len(jobs) > (expected_total or 0) + PAGE_SIZE:
                errors.append(f'collected jobs exceeded expected_total={expected_total} without reaching final page')
                break

            if expected_total is not None and len(seen_ids) >= expected_total:
                # Continue one extra validation page only when totalPage is absent.
                if observed_total_pages is None:
                    continue
                coverage['pagination_exhausted'] = True
                coverage['last_page_evidence'] = str(page_path)
                break

            if expected_total is not None and page_no >= expected_total:
                # Defensive stop when response metadata is missing totalPage.
                break

            if page_no >= 1000000:
                errors.append('Unexpected hard guard reached')
                break

            time.sleep(interval)

            if expected_total is not None and len(seen_ids) >= expected_total:
                break

    except Exception as error:
        errors.append(str(error))

    coverage['retries'] = retries
    coverage['collected_jobs'] = len(jobs)
    coverage['unique_source_ids'] = len(seen_ids)
    coverage['errors'] = errors
    coverage['detail_complete'] = bool(jobs and all(bool((d.get('field_completeness') or {}).get('jobDuty') or
                                      (d.get('field_completeness') or {}).get('jobRequirement'))
                                 for d in jobs))
    complete_conditions = (
        expected_total is not None
        and len(seen_ids) == expected_total
        and coverage.get('pages_scanned', 0) > 0
        and coverage.get('pagination_exhausted') is True
        and not errors
        and coverage['detail_complete']
    )
    coverage['complete'] = bool(complete_conditions)
    coverage['status'] = 'success' if coverage['complete'] else ('blocked' if len(errors) >= 3 and not jobs else 'partial')
    if coverage['status'] == 'partial' and coverage['detail_missing_count']:
        coverage['status_note'] = '部分岗位岗位职责/任职要求待核索引，避免误判下架'

    candidate = jobs
    coverage['jobs_with_missing_fields'] = sorted(set(coverage['jobs_with_missing_fields']))
    coverage['pending_source_ids'] = sorted(set(coverage.get('pending_source_ids') or []))
    coverage['evidence'] = list(dict.fromkeys(coverage.get('evidence') or []))
    coverage['evidence_files'] = [str(Path(path).resolve()) for path in coverage.get('evidence_files', [])]

    candidate_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding='utf-8')
    coverage_path.write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding='utf-8')
    result_path.write_text(json.dumps({'jobs': candidate, 'coverage': coverage}, ensure_ascii=False, indent=2), encoding='utf-8')

    return {'jobs': candidate, 'coverage': coverage}


def main() -> int:
    parser = argparse.ArgumentParser(description='Collect Meituan public campus/intern/social positions')
    parser.add_argument('company')
    parser.add_argument('scope', choices=sorted(SCOPE_TO_JOB_TYPE))
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()

    result = collect(args.company, args.scope, args.output_dir)
    print(json.dumps({'company': args.company, 'scope': args.scope, **result['coverage']}, ensure_ascii=False, indent=2))
    return 0 if result['coverage']['status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
