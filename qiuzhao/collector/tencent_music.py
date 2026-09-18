"""Tencent Music Entertainment (腾讯音乐) campus recruitment adapter.

``join.tencentmusic.com`` runs its own Nuxt front end on a set of public JSON
endpoints (not Moka/Beisen/Feishu).  The campus channel exposes a recruitment
type dictionary and a paginated list:

* ``GET  /api/uc-job/zp-type-with-num-list``  应届生 10 / 实习生 20 / 日常实习生 30 / 技术大咖 40
* ``POST /api/uc-job/list``                   ``{page, ss, type, job_class, work_city, setid, keyword}``

Plain HTTP is sufficient -- the endpoints are public and unauthenticated.  The
adapter maps scopes onto the official type codes (``campus`` = 应届生 + 技术大咖,
``intern`` = 实习生 + 日常实习生), keeps every list row as an official position,
and never invents a deadline or a publish timestamp (``date`` is the site field
and is used verbatim as ``published_at``).

Contract is identical to ``p1_sources_*``: ``collect(company, scope, output_dir)``
returns ``{'jobs': [...], 'coverage': {...}}``; ``merged_registry()`` registers
the company with ``p1_pipeline``.

Politeness: every request sleeps ``QIUZHAO_TME_MIN_INTERVAL`` seconds (default
2.0) and stops at ``QIUZHAO_TME_REQUEST_BUDGET`` (default 40).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

MODULE_PATH = 'qiuzhao.collector.tencent_music'
COMPANY = '腾讯音乐'
API = 'https://join.tencentmusic.com'
LIST_PATH = '/api/uc-job/list'
TYPES_PATH = '/api/uc-job/zp-type-with-num-list'
SCOPES = {'campus': '校园招聘', 'intern': '实习招聘', 'social': '社会招聘'}
# Official type codes (value) observed in zp-type-with-num-list.
SCOPE_TYPES = {'campus': (10, 40), 'intern': (20, 30), 'social': ()}
PAGE_SIZE = 100
DEFAULT_REQUEST_BUDGET = 40
DEFAULT_MIN_INTERVAL = 2.0
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')


class BudgetExhausted(RuntimeError):
    """Raised when the per-run request budget is reached; callers keep partial rows."""


def merged_registry():
    return {COMPANY: MODULE_PATH}


def _budget_limit(max_requests):
    if max_requests is not None:
        return int(max_requests)
    raw = os.environ.get('QIUZHAO_TME_REQUEST_BUDGET')
    return int(raw) if raw and raw.strip() else DEFAULT_REQUEST_BUDGET


def _min_interval(delay):
    if delay is not None:
        return float(delay)
    raw = os.environ.get('QIUZHAO_TME_MIN_INTERVAL')
    return float(raw) if raw and raw.strip() else DEFAULT_MIN_INTERVAL


def _record(output_dir, name, payload):
    (Path(output_dir) / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return name


class HttpTransport:
    """Minimal polite JSON transport; injectable for offline tests."""

    def __init__(self, delay=None, max_requests=None, opener=None):
        self.delay = _min_interval(delay)
        self.limit = _budget_limit(max_requests)
        self.used = 0
        self._opener = opener or urllib.request.urlopen
        self._last = 0.0

    def _charge(self):
        if self.limit is not None and self.used >= self.limit:
            raise BudgetExhausted(f'request budget {self.limit} reached')
        self.used += 1

    def _throttle(self):
        time.sleep(max(0.0, self.delay - (time.monotonic() - self._last)))
        self._last = time.monotonic()

    def _request(self, path, data=None):
        self._charge()
        self._throttle()
        headers = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
                   'Referer': API + '/campus/post/'}
        body = None
        if data is not None:
            body = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(API + path, data=body, headers=headers)
        try:
            with self._opener(request, timeout=30) as response:
                return response.status, json.loads(response.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode('utf-8', 'replace'))
            except Exception:
                return error.code, {'_http_error': str(error)[:300]}

    def get(self, path):
        return self._request(path)

    def post(self, path, payload):
        return self._request(path, payload)

    def budget(self):
        return {'limit': self.limit, 'used': self.used}


def make_transport(max_requests=None, delay=None, opener=None):
    return HttpTransport(delay=delay, max_requests=max_requests, opener=opener)


def _cities(raw):
    cities = []
    for item in raw or []:
        if isinstance(item, dict):
            label = str(item.get('label') or '').strip()
        else:
            label = str(item or '').strip()
        if label:
            cities.append(label)
    return cities


def _row_to_job(item, checked):
    pid = str(item.get('id') or '')
    title = (item.get('name') or '').strip()
    detail = f'{API}/campus/detail/?id={pid}'
    batch_name = (item.get('job_type_descr') or '').strip()
    record = {
        'id': f'tencentmusic:{pid}',
        'source_record_id': pid,
        'title': title,
        'job_title': title,
        'recruitment_unit': '腾讯音乐娱乐（深圳）有限公司',
        'recruitment_type': SCOPES['campus'],  # overwritten by caller for intern
        'source_url': detail,
        'detail_url': detail,
        'application_url': detail,
        'job_listing_url': API + '/campus/post/',
        'campaign_url': API + '/campus/post/',
        'description_raw': (item.get('duty') or '').strip()[:20000],
        'job_category': (item.get('jobf_descr') or '').strip(),
        'cities': _cities(item.get('work_city')),
        'recruiting_unit_raw': (item.get('setid_descr') or '').strip(),
        'hiring_department_raw': (item.get('setid_descr') or '').strip(),
        'cohort_raw': '',
        'campaign_cohort_raw': batch_name,
        'campaign_scope': 'batch',
        'batch_name': batch_name,
        'position_nature_raw': (item.get('position_nbr_descr') or '').strip(),
        'source_name': '腾讯音乐娱乐集团校园招聘官方网站',
        'source': 'official_career',
        'record_kind': 'official_position_id',
        'source_fields': {key: item.get(key) for key in
                          ('id', 'job_type', 'job_type_descr', 'setid', 'setid_descr',
                           'jobf_descr', 'date', 'position_nbr_descr') if item.get(key) is not None},
        'status': 'unverified',
        'status_note': '官网公开校招岗位列表可见；未披露截止日期，未尝试投递。',
        'reviewed_at': checked,
    }
    if item.get('date'):
        record['published_at'] = item.get('date')
    return record


def _coverage():
    return {'status': 'blocked', 'complete': False, 'expected_total': None,
            'collected_jobs': 0, 'pages_scanned': 0, 'detail_complete': False,
            'source_url': API + '/campus/post/', 'errors': [],
            'evidence': [], 'evidence_files': []}


def _finalize(result, transport):
    coverage = result['coverage']
    jobs = result['jobs']
    coverage['collected_jobs'] = len(jobs)
    coverage['unique_source_ids'] = len({job['source_record_id'] for job in jobs})
    missing = sum(1 for job in jobs if not str(job.get('description_raw') or '').strip())
    coverage['detail_complete'] = missing == 0
    expected = coverage.get('expected_total')
    coverage['complete'] = bool(
        expected is not None and expected == len(jobs)
        and not coverage['errors']
        and coverage.get('pagination_exhausted') is True
        and coverage['detail_complete'])
    coverage['status'] = 'success' if coverage['complete'] else ('partial' if jobs else 'blocked')
    coverage['request_budget'] = transport.budget()
    return result


def _collect_tme(transport, scope, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage = _coverage()
    coverage['scope_request'] = {'company': COMPANY, 'scope': scope,
                                 'source_url': API + '/campus/post/',
                                 'params': {'endpoint': LIST_PATH, 'pageSize': PAGE_SIZE,
                                            'types': list(SCOPE_TYPES.get(scope, ()))}}
    result = {'jobs': [], 'coverage': coverage}
    wanted = SCOPE_TYPES.get(scope, ())
    if scope == 'social' or not wanted:
        coverage['errors'] = ['腾讯音乐社会招聘不在校园招聘接口范围（/api/uc-job/list）；本适配器不覆盖 social。']
        return _finalize(result, transport)
    try:
        status, types_response = transport.get(TYPES_PATH)
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
        coverage['errors'].append('request budget exhausted at type dictionary')
        return _finalize(result, transport)
    except Exception as error:
        coverage['errors'].append(f'type dictionary failed: {type(error).__name__}: {error}'[:300])
        return _finalize(result, transport)
    coverage['pages_scanned'] += 1
    coverage['evidence'].append(_record(output_dir, 'tme-types.json', {
        'source_url': API + TYPES_PATH, 'http_status': status, 'response': types_response}))
    if status != 200 or str((types_response or {}).get('code')) != '200':
        coverage['errors'].append(f'type dictionary http={status} code={(types_response or {}).get("code")}')
        return _finalize(result, transport)
    official_types = {}
    for entry in (types_response.get('data') or []):
        try:
            official_types[int(entry.get('value'))] = entry
        except (TypeError, ValueError):
            continue
    missing_types = [code for code in wanted if code not in official_types]
    if missing_types:
        coverage['errors'].append(f'official type codes missing from dictionary: {missing_types}')
        return _finalize(result, transport)
    expected = 0
    for code in wanted:
        try:
            expected += int(official_types[code].get('num') or 0)
        except (TypeError, ValueError):
            coverage['errors'].append(f'type {code} official count is not numeric')
    coverage['expected_total'] = expected
    coverage['pagination_exhausted'] = True

    seen = set()
    for code in wanted:
        page = 1
        while True:
            payload = {'page': page, 'ss': PAGE_SIZE, 'type': str(code), 'job_class': [],
                       'work_city': '', 'setid': '', 'keyword': ''}
            try:
                status, response = transport.post(LIST_PATH, payload)
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                coverage['pagination_exhausted'] = False
                coverage['errors'].append(f'request budget exhausted at type {code} page {page}')
                break
            except Exception as error:
                coverage['pagination_exhausted'] = False
                coverage['errors'].append(
                    f'type {code} page {page}: {type(error).__name__}: {error}'[:300])
                break
            coverage['pages_scanned'] += 1
            if status != 200 or str((response or {}).get('code')) != '200':
                coverage['pagination_exhausted'] = False
                coverage['errors'].append(
                    f'type {code} page {page}: http={status} code={(response or {}).get("code")}')
                break
            data = (response or {}).get('data') or {}
            meta = data.get('_meta') or {}
            items = data.get('items') or []
            coverage['evidence'].append(_record(
                output_dir, f'tme-type{code}-page{page}.json',
                {'source_url': API + LIST_PATH, 'request_body': payload, 'http_status': status,
                 'meta': meta,
                 'items': [{key: item.get(key) for key in
                            ('id', 'name', 'job_type', 'job_type_descr', 'setid', 'setid_descr',
                             'jobf_descr', 'date', 'work_city')} for item in items]}))
            checked = time.strftime('%Y-%m-%dT%H:%M:%S+08:00')
            for item in items:
                pid = str(item.get('id') or '')
                title = (item.get('name') or '').strip()
                if not pid or pid in seen or not title:
                    continue
                seen.add(pid)
                job = _row_to_job(item, checked)
                job['recruitment_type'] = SCOPES[scope]
                result['jobs'].append(job)
            page_count = meta.get('page_count')
            if not items or (page_count is not None and page >= int(page_count)):
                break
            page += 1

    coverage['evidence_files'] = list(coverage['evidence'])
    coverage['scope_evidence'] = (
        f"Official Tencent Music campus API {API}{LIST_PATH}; official type codes "
        f"{list(wanted)} totals={[official_types[c].get('num') for c in wanted]}; "
        f"pageSize={PAGE_SIZE}.")
    coverage['request_params'] = dict(coverage['scope_request']['params'])
    return _finalize(result, transport)


def collect(company, scope, output_dir, transport=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if company != COMPANY:
        raise ValueError('unknown Tencent Music company: ' + str(company))
    if scope not in SCOPES:
        raise ValueError('Unknown recruitment scope')
    owned = transport is None
    transport = transport or make_transport()
    try:
        result = _collect_tme(transport, scope, output_dir)
    finally:
        if owned:
            transport.close() if hasattr(transport, 'close') else None
    (output_dir / 'result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Tencent Music campus recruitment collector')
    parser.add_argument('scope', choices=list(SCOPES))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--max-requests', type=int)
    parser.add_argument('--delay', type=float)
    args = parser.parse_args()
    built = collect(COMPANY, args.scope, args.output_dir,
                    transport=make_transport(max_requests=args.max_requests, delay=args.delay))
    print(json.dumps(built['coverage'], ensure_ascii=False, indent=2))
