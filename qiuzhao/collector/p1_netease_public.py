"""NetEase (网易) public campus/intern/social recruitment adapter.

Adapter contract: ``collect(company, scope, output_dir) -> {jobs, coverage}`` (see
``qiuzhao/collector/p1_pipeline.py``). No login, no CAPTCHA, no paid API, no cookies/signature
persisted. Reverifies the live official navigation every run instead of trusting a cached list of
historical projects.

NetEase's public recruitment surface is not one system but five independently reachable ones,
re-discovered and re-verified against the live sites (2026-09-12/13):

1. ``campus_api`` -- shared backend behind both campus.163.com and campus.game.163.com.
   GET /api/campuspc/position/getJobList?projectId=X&pageSize=N&currentPage=M
   (the real page parameter is ``currentPage``; ``pageNum``/``pageIndex`` are silently ignored by
   the server, which is why a large-enough ``pageSize`` alone looked "complete" before). The list
   response already carries the full, untruncated ``positionDescription``/``positionRequirement``
   (byte-identical to the detail endpoint); ``getJobDetails`` is still fetched per row for the two
   fields the list omits (``projectName``, ``publishTime``). Which project ids are current and
   which scope (campus vs intern) they belong to is read from the live navigation endpoint every
   run, not hardcoded. ``getIntentionInfo``/``getOtherInfo`` require login (HTTP 200, code 406,
   "当前用户未登录") and are correctly left unused rather than bypassed.
2. ``leihuo`` -- xiaozhao.leihuo.netease.com, a separate backend behind the Leihuo studio's own
   campus microsite (leihuo.163.com/campus). GET /api/apply/job/list/show?project_id=X&page_size=
   N&page_number=M, detail via /api/apply/job/detail/show?job_id=Y&project_id=X. The navigation
   endpoint only ever links project 77 ("full"); the microsite exposes further numeric project ids
   (68/73/58 observed) that are not linked from the navigation aggregator. Each candidate id is
   probed live every run and only kept if it actually returns rows; scope is decided per row from
   the official ``ehr_job_type`` field (1=全职/campus, 2=实习/intern), not from the id or route name.
3. ``hr163`` -- hr.163.com's own job board (the "日常实习"/"社会招聘" home for NetEase). POST
   /api/hr163/position/queryPage with body {currentPage, pageSize<=200, workType: "<0|1|2>"} --
   ``workType`` must be a JSON *string*; sending it as an int makes the (otherwise correct)
   ``currentPage`` parameter look broken too, which is how this was first mis-diagnosed. workType
   0=全职 and 2=派遣 are both social employment; 1=日常实习 is intern. The list rows already carry
   full ``description``/``requirement`` (byte-identical to GET /api/hr163/position/query?id=Y), so
   no per-row detail call is made for this system.
4. ``greenhouse-neteasegames`` -- boards-api.greenhouse.io/v1/boards/neteasegames, NetEase Games'
   official overseas/global board (surfaced only from the English-locale nav in hr.163.com's own
   bundle). Includes "SG Campus Recruitment" titled roles alongside regular experienced roles.
5. ``greenhouse-highdive`` -- boards-api.greenhouse.io/v1/boards/highdive, HighDive Games, a
   wholly-owned NetEase studio (confirmed via its own site's "NetEase, Inc." copyright notice).

Each system is namespaced (``netease-campus{projectId}-``, ``netease-leihuo{projectId}-``,
``netease-hr163-``, ``netease-gh-{board}-``) before dedup, since raw numeric ids are small and
collide across systems (e.g. campus project 103 and leihuo project 77 both mint ids in the low
thousands). Responsibilities and requirements are two separate fields at the source; both are
kept verbatim (never truncated) and combined into one ``description_raw`` (required by
``validate_result``) with ``source_missing_fields``/``field_completeness`` recording which half, if
any, was empty. A row whose responsibilities *and* requirements are both empty is not fabricated
into a job: it is dropped and its identifier goes into ``coverage['pending_review_index']`` /
``coverage['detail_missing_count']`` instead.
"""
from __future__ import annotations

import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

COMPANY = '网易'
TYPES = {'campus': '校园招聘', 'intern': '实习招聘', 'social': '社会招聘'}
UA = 'Mozilla/5.0 (QiuzhaoOfficialJobs/1.0; public recruitment index; daily low-frequency review)'
NAVIGATION_URL = 'https://campus.163.com/api/campuspc/project/navigation/list'
LEIHUO_CANDIDATE_PROJECTS = (77, 68, 73, 58)  # reverified live every run; kept only if non-empty
GREENHOUSE_BOARDS = ('neteasegames', 'highdive')
DETAIL_WORKERS = 3  # gentle per-host concurrency ceiling


def now():
    return datetime.now(timezone.utc).isoformat()


def make_session():
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=1,
                  allowed_methods={'GET', 'POST'}, status_forcelist=[429, 502, 503, 504],
                  respect_retry_after_header=True)
    session.mount('https://', HTTPAdapter(max_retries=retry))
    session.headers['User-Agent'] = UA
    return session


def clean(value):
    """Normalize a plain-text field (already-decoded JSON string, no HTML tags expected)."""
    text = html.unescape(str(value or ''))
    text = re.sub(r'\r\n', '\n', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def strip_html(value):
    """Greenhouse ``content`` is real HTML; everything else here is already plain text."""
    text = html.unescape(str(value or ''))
    return clean(BeautifulSoup(text, 'html.parser').get_text('\n', strip=True))


def cities_from(text):
    return [c.strip() for c in re.split(r'[,，、/;；]', str(text or '')) if c.strip()]


_EDU_WORDS = r'博士|硕士|研究生|本科|大专|专科|中专|高中|Bachelor|Master|Ph\.?D'
_MAJOR_WORDS = r'相关专业|专业(?:优先|不限|背景)?[：:]?|major\s+in\b|degree\s+in\b'


def extract_education(text):
    for sentence in re.split(r'[\n。；;]', str(text or '')):
        if re.search(_EDU_WORDS, sentence, re.I) and re.search(r'学历|学位|在读|以上|优先|毕业|学位|degree', sentence, re.I):
            return sentence.strip()
    return ''


def extract_major(text):
    for sentence in re.split(r'[\n。；;]', str(text or '')):
        if re.search(_MAJOR_WORDS, sentence, re.I):
            return sentence.strip()
    return ''


def combine_description(responsibility, requirement, resp_label='职位描述', req_label='任职要求'):
    """Two verbatim source fields -> one non-truncated description_raw + what, if anything, was empty."""
    resp, req = clean(responsibility), clean(requirement)
    parts, missing = [], []
    if resp:
        parts.append(f'【{resp_label}】\n{resp}')
    else:
        missing.append('responsibility')
    if req:
        parts.append(f'【{req_label}】\n{req}')
    else:
        missing.append('requirement')
    return '\n\n'.join(parts), missing


def make_job(source_record_id, scope, title, description_raw, source_url, detail_url,
             cities, education_raw='', major_requirements_raw='', cohort_raw='',
             campaign_cohort_raw='', campaign_scope='', published_at=None,
             source_missing_fields=None, extra=None):
    missing = source_missing_fields or []
    row = {
        'job_title': clean(title),
        'source_record_id': source_record_id,
        'recruitment_unit': COMPANY,
        'recruitment_type': TYPES[scope],
        'description_raw': description_raw,
        'source_url': source_url,
        'application_url': detail_url,
        'detail_url': detail_url,
        'cities': cities,
        'education_raw': education_raw,
        'major_requirements_raw': major_requirements_raw,
        'cohort_raw': cohort_raw,
        'campaign_cohort_raw': campaign_cohort_raw,
        'campaign_scope': campaign_scope,
        'published_at': published_at,
        'reviewed_at': now(),
        'source_missing_fields': missing,
        'field_completeness': 'complete' if not missing else 'partial',
        'status': 'unverified',
        'status_note': '官方公开岗位列表可见；未披露截止日期，未尝试投递。',
    }
    if extra:
        row.update(extra)
    return row


def save_json(output_dir, name, payload):
    path = Path(output_dir) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return name


def get_json(session, url, params=None, method='GET', json_body=None, timeout=(10, 40)):
    response = (session.post(url, params=params, json=json_body, timeout=timeout)
                if method == 'POST' else session.get(url, params=params, timeout=timeout))
    response.raise_for_status()
    return response.json()


class SystemResult:
    def __init__(self):
        self.jobs = []
        self.pages_scanned = 0
        self.errors = []
        self.evidence_files = []
        self.pending_review = []  # source_record_id list for both-empty rows
        self.raw_totals = {}  # system_key -> official reported total
        self.unique_seen = 0  # positions actually observed via pagination (incl. dropped ones)
        self.exhausted = {}  # system_key -> bool
        self.notes = []

    def merge_from(self, other):
        self.jobs.extend(other.jobs)
        self.pages_scanned += other.pages_scanned
        self.errors.extend(other.errors)
        self.evidence_files.extend(other.evidence_files)
        self.pending_review.extend(other.pending_review)
        self.raw_totals.update(other.raw_totals)
        self.unique_seen += other.unique_seen
        self.exhausted.update(other.exhausted)
        self.notes.extend(other.notes)


def run_with_retry(fetch_fn, session, key_args, scope, output_dir, shared, attempts=2):
    """Retry a single volatile-source fetch into an isolated attempt, keep the cleanest one.

    Live boards with thousands of items and no stable pagination cursor can drift mid-scan
    (NetEase inserts/reorders postings while we page through them); a fresh attempt often lands
    cleanly. Each attempt is isolated so a failed retry cannot double-count jobs from a prior try.
    """
    best = None
    for attempt in range(attempts):
        local = SystemResult()
        fetch_fn(session, *key_args, scope, local, output_dir)
        if best is None:
            best = local
        else:
            best_ok = not best.errors and all(best.exhausted.values() or [True])
            local_ok = not local.errors and all(local.exhausted.values() or [True])
            if local_ok and not best_ok:
                best = local
            elif len(local.jobs) > len(best.jobs) and (local_ok or not best_ok):
                best = local
        if not best.errors and all(best.exhausted.values() or [True]):
            break
    shared.merge_from(best)


# --------------------------------------------------------------------------- navigation

def fetch_navigation(session, result, output_dir):
    try:
        payload = get_json(session, NAVIGATION_URL, timeout=(10, 25))
    except Exception as error:
        result.errors.append(f'navigation fetch failed: {error}')
        return []
    result.evidence_files.append(save_json(output_dir, 'navigation.json', payload))
    if payload.get('code') != 200:
        result.errors.append(f'navigation API rejected: code={payload.get("code")} msg={payload.get("msg")}')
        return []
    return payload.get('data') or []


def group_scope(title):
    return 'intern' if '实习' in str(title or '') else 'campus'


CAMPUS_LINK = re.compile(r'https://(campus\.163\.com|campus\.game\.163\.com)/app/job/position\?id=(\d+)')
HR163_LINK = re.compile(r'hr\.163\.com/job-list\.html\?workType=(\d+)')


def parse_navigation(navigation):
    """-> (campus_projects: {project_id: scope}, notes: [str])."""
    campus_projects = {}
    notes = []
    for group in navigation:
        gscope = group_scope(group.get('title'))
        for child in group.get('children') or []:
            link = str(child.get('link') or '')
            match = CAMPUS_LINK.search(link)
            if match:
                project_id = int(match.group(2))
                if project_id in campus_projects and campus_projects[project_id] != gscope:
                    notes.append(f'nav project {project_id} appears under both scopes; kept {campus_projects[project_id]}')
                else:
                    campus_projects[project_id] = gscope
                notes.append(f'nav campus_api project={project_id} scope={gscope} title={child.get("title")}')
                continue
            if 'leihuo.163.com/campus' in link:
                notes.append(f'nav leihuo entry title={child.get("title")} scope_group={gscope} link={link}')
                continue
            if '/app/talents/' in link:
                notes.append(f'nav talents entry (informational, covered by its own campus_api project) title={child.get("title")} link={link}')
                continue
            if HR163_LINK.search(link):
                notes.append(f'nav hr163 entry workType={HR163_LINK.search(link).group(1)} title={child.get("title")} link={link}')
                continue
            notes.append(f'nav unrecognized entry title={child.get("title")} link={link}')
    return campus_projects, notes


# --------------------------------------------------------------------------- campus_api

def fetch_campus_api_project(session, project_id, scope, result, output_dir):
    key = f'campus{project_id}'
    rows, seen, total, page, had_error = [], set(), None, 1, False
    while True:
        params = {'projectId': project_id, 'pageSize': 50, 'currentPage': page}
        try:
            payload = get_json(session, 'https://campus.163.com/api/campuspc/position/getJobList', params=params)
        except Exception as error:
            result.errors.append(f'{key} list page {page} failed: {error}')
            had_error = True
            break
        result.pages_scanned += 1
        if payload.get('code') != 200:
            result.errors.append(f'{key} list page {page} rejected: {payload}')
            had_error = True
            break
        data = payload.get('data') or {}
        result.evidence_files.append(save_json(output_dir, f'{key}-list-{page}.json', payload))
        page_total = data.get('total')
        if total is not None and page_total != total:
            # A live official total can genuinely drift mid-scan; keep what pagination already
            # gathered rather than discarding it, but do not claim exhaustive coverage.
            result.errors.append(f'{key} total changed during scan: {total} -> {page_total}')
            had_error = True
            break
        total = page_total
        batch = data.get('list') or []
        for row in batch:
            ident = row.get('id')
            if ident in seen:
                result.errors.append(f'{key} repeated id {ident} across pages')
                had_error = True
                continue
            seen.add(ident)
            rows.append(row)
        if not batch or len(seen) >= (total or 0) or page >= (data.get('pages') or 1):
            break
        page += 1
        time.sleep(0.15)
    result.raw_totals[key] = total
    result.unique_seen += len(seen)
    result.exhausted[key] = (not had_error and total is not None and len(seen) == total)
    if not result.exhausted[key] and not had_error:
        result.errors.append(f'{key} pagination did not reach the official total ({len(seen)}/{total})')

    def enrich(row):
        ident = row['id']
        detail_extra = {}
        try:
            detail_payload = get_json(session, 'https://campus.163.com/api/campuspc/position/getJobDetails',
                                       params={'id': ident})
            if detail_payload.get('code') == 200:
                detail = detail_payload.get('data') or {}
                result.evidence_files.append(save_json(output_dir, f'{key}-detail-{ident}.json', detail_payload))
                if detail.get('id') == ident:
                    detail_extra['projectName'] = detail.get('projectName') or ''
                    detail_extra['publishTime'] = detail.get('publishTime') or ''
            else:
                result.errors.append(f'{key} detail {ident} rejected: code={detail_payload.get("code")}')
        except Exception as error:
            result.errors.append(f'{key} detail {ident} HTTP failure: {error}')
        return row, detail_extra

    jobs = []
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
        futures = [pool.submit(enrich, row) for row in rows]
        for future in as_completed(futures):
            row, detail_extra = future.result()
            ident = row['id']
            description_raw, missing = combine_description(row.get('positionDescription'), row.get('positionRequirement'))
            source_record_id = f'netease-{key}-{ident}'
            if not description_raw:
                result.pending_review.append(source_record_id)
                continue
            cities = cities_from(row.get('workPlaceName'))
            full_text = description_raw
            detail_url = f'https://campus.163.com/app/detail/index?id={ident}&projectId={project_id}'
            job = make_job(
                source_record_id, scope, row.get('positionName'), description_raw,
                f'https://campus.163.com/api/campuspc/position/getJobDetails?id={ident}', detail_url,
                cities, education_raw=extract_education(full_text), major_requirements_raw=extract_major(full_text),
                campaign_cohort_raw=detail_extra.get('projectName', ''), campaign_scope='project' if detail_extra.get('projectName') else '',
                published_at=detail_extra.get('publishTime') or None, source_missing_fields=missing,
                extra={'job_category': row.get('positionTypeName') or ''})
            jobs.append(job)
    result.jobs.extend(jobs)
    return jobs


# --------------------------------------------------------------------------- leihuo

LEIHUO_TYPE_SCOPE = {'1': 'campus', '2': 'intern'}


def fetch_leihuo_project(session, project_id, scope, result, output_dir):
    key = f'leihuo{project_id}'
    rows, seen, total, page, had_error = [], set(), None, 1, False
    while True:
        params = {'project_id': project_id, 'page_size': 50, 'page_number': page}
        url = 'https://xiaozhao.leihuo.netease.com/api/apply/job/list/show?' + urlencode(params)
        try:
            payload = get_json(session, url, timeout=(10, 30))
        except Exception as error:
            result.errors.append(f'{key} list page {page} failed: {error}')
            had_error = True
            break
        result.pages_scanned += 1
        if payload.get('status') != 200:
            result.errors.append(f'{key} list page {page} rejected: {payload}')
            had_error = True
            break
        data = payload.get('data') or {}
        result.evidence_files.append(save_json(output_dir, f'{key}-list-{page}.json', payload))
        page_total = data.get('count_number')
        if total is not None and page_total != total:
            # A live official total can genuinely drift mid-scan; keep what pagination already
            # gathered rather than discarding it, but do not claim exhaustive coverage.
            result.errors.append(f'{key} total changed during scan: {total} -> {page_total}')
            had_error = True
            break
        total = page_total
        batch = data.get('apply_job_list') or []
        for row in batch:
            ident = row.get('ehr_job_id')
            if ident in seen:
                result.errors.append(f'{key} repeated id {ident} across pages')
                had_error = True
                continue
            seen.add(ident)
            rows.append(row)
        if not batch or len(seen) >= (total or 0) or data.get('last_page'):
            break
        page += 1
        time.sleep(0.15)
    result.raw_totals[key] = total
    if not total:
        if not had_error:
            result.notes.append(f'{key} currently has 0 open positions (checked live)')
            result.exhausted[key] = True  # confirmed-empty on page 1 is a full proof, not a gap
        return []
    result.exhausted[key] = (not had_error and len(seen) == total)
    if not result.exhausted[key] and not had_error:
        result.errors.append(f'{key} pagination did not reach the official total ({len(seen)}/{total})')
    # This project mixes scopes (ehr_job_type varies per row); unique_source_ids must only
    # count rows relevant to the requested scope, not every row the full pagination walked.
    scope_matched = sum(1 for row in rows if LEIHUO_TYPE_SCOPE.get(str(row.get('ehr_job_type'))) == scope)
    result.unique_seen += scope_matched

    def enrich(row):
        ident = row.get('ehr_job_id')
        detail_extra = {}
        try:
            detail_url = ('https://xiaozhao.leihuo.netease.com/api/apply/job/detail/show?' +
                          urlencode({'job_id': ident, 'project_id': project_id}))
            detail_payload = get_json(session, detail_url, timeout=(10, 30))
            if detail_payload.get('status') == 200:
                detail = detail_payload.get('data') or {}
                result.evidence_files.append(save_json(output_dir, f'{key}-detail-{ident}.json', detail_payload))
                if str(detail.get('ehr_job_id')) == str(ident):
                    detail_extra['job_detail_url'] = detail.get('job_detail_url') or ''
            else:
                result.errors.append(f'{key} detail {ident} rejected: {detail_payload}')
        except Exception as error:
            result.errors.append(f'{key} detail {ident} HTTP failure: {error}')
        return row, detail_extra

    jobs = []
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
        futures = [pool.submit(enrich, row) for row in rows]
        for future in as_completed(futures):
            row, detail_extra = future.result()
            ehr_type = str(row.get('ehr_job_type') or '')
            actual_scope = LEIHUO_TYPE_SCOPE.get(ehr_type)
            if actual_scope is None:
                result.errors.append(f'{key} unknown ehr_job_type={ehr_type} for job {row.get("ehr_job_id")}')
                continue
            if actual_scope != scope:
                continue
            ident = row.get('ehr_job_id')
            description_raw, missing = combine_description(row.get('job_description'), row.get('job_requirement'))
            source_record_id = f'netease-{key}-{ident}'
            if not description_raw:
                result.pending_review.append(source_record_id)
                continue
            cities = cities_from(row.get('work_place_name'))
            detail_url = detail_extra.get('job_detail_url') or f'https://campus.163.com/app/detail/index?id={ident}&projectId={project_id}'
            job = make_job(
                source_record_id, scope, row.get('job_name'), description_raw,
                f'https://xiaozhao.leihuo.netease.com/api/apply/job/detail/show?job_id={ident}&project_id={project_id}',
                detail_url, cities, education_raw=extract_education(description_raw),
                major_requirements_raw=extract_major(description_raw),
                campaign_cohort_raw=' / '.join(row.get('department_name') or []) or (row.get('category_name') or ''),
                campaign_scope='project', source_missing_fields=missing,
                extra={'job_category': row.get('category_name') or '',
                       'scope_evidence_hint': f'leihuo ehr_job_type={ehr_type} ({row.get("type_name")}); target={row.get("job_target")}'})
            jobs.append(job)
    result.jobs.extend(jobs)
    return jobs


# --------------------------------------------------------------------------- hr163

HR163_WORKTYPE_SCOPE = {'0': 'social', '1': 'intern', '2': 'social'}
HR163_MAX_PAGE_SIZE = 200


def fetch_hr163_worktype(session, work_type, scope, result, output_dir):
    key = f'hr163-wt{work_type}'
    rows, seen, total, page, had_error = [], set(), None, 1, False
    while True:
        body = {'currentPage': page, 'pageSize': HR163_MAX_PAGE_SIZE, 'workType': str(work_type)}
        try:
            payload = get_json(session, 'https://hr.163.com/api/hr163/position/queryPage', method='POST', json_body=body)
        except Exception as error:
            result.errors.append(f'{key} list page {page} failed: {error}')
            had_error = True
            break
        result.pages_scanned += 1
        if payload.get('code') != 200:
            result.errors.append(f'{key} list page {page} rejected: {payload}')
            had_error = True
            break
        data = payload.get('data') or {}
        safe_rows = [{k: v for k, v in row.items() if k != 'description' and k != 'requirement'}
                     for row in (data.get('list') or [])]
        result.evidence_files.append(save_json(output_dir, f'{key}-list-{page}.json',
                                                {'request': body, 'total': data.get('total'), 'pages': data.get('pages'), 'rows': safe_rows}))
        page_total = data.get('total')
        if total is not None and page_total != total:
            # This is a live, frequently-updated board; a total drift mid-scan is expected on
            # the larger workType channels. Keep what was already gathered, mark it non-exhaustive.
            result.errors.append(f'{key} total changed during scan: {total} -> {page_total}')
            had_error = True
            break
        total = page_total
        batch = data.get('list') or []
        for row in batch:
            ident = row.get('id')
            if ident in seen:
                result.errors.append(f'{key} repeated id {ident} across pages')
                had_error = True
                continue
            seen.add(ident)
            rows.append(row)
        # ``pages`` (the official last-page number) is the authoritative stop condition: a sort-tie
        # at a page boundary can make the same row reappear on the next page, which makes the
        # deduped len(seen) undercount the official ``total`` even though every page was read and
        # nothing was skipped. Relying on len(seen) >= total alone would request one page past the
        # end, which this API answers with a nonsensical total=0 instead of an empty last page.
        if not batch or page >= (data.get('pages') or 1) or len(seen) >= (total or 0):
            break
        page += 1
        time.sleep(0.15)
    result.raw_totals[key] = total
    if not total:
        if not had_error:
            result.notes.append(f'{key} currently has 0 open positions (checked live)')
            result.exhausted[key] = True  # confirmed-empty on page 1 is a full proof, not a gap
        return []
    result.unique_seen += len(seen)
    result.exhausted[key] = (not had_error and len(seen) == total)
    if not result.exhausted[key] and not had_error:
        result.errors.append(f'{key} pagination did not reach the official total ({len(seen)}/{total})')

    jobs = []
    for row in rows:
        if str(row.get('workType')) != str(work_type):
            result.errors.append(f'{key} row {row.get("id")} workType mismatch: {row.get("workType")}')
            continue
        ident = row.get('id')
        description_raw, missing = combine_description(row.get('description'), row.get('requirement'))
        source_record_id = f'netease-hr163-{ident}'
        if not description_raw:
            result.pending_review.append(source_record_id)
            continue
        cities = row.get('workPlaceNameList') or cities_from(row.get('workPlace'))
        published_raw = row.get('updateTime')
        published_at = None
        if isinstance(published_raw, (int, float)):
            published_at = datetime.fromtimestamp(published_raw / 1000, tz=timezone.utc).date().isoformat()
        detail_url = f'https://hr.163.com/job-detail.html?id={ident}'
        job = make_job(
            source_record_id, scope, row.get('name'), description_raw,
            'https://hr.163.com/api/hr163/position/queryPage', detail_url, cities,
            education_raw=row.get('reqEducationName') or extract_education(description_raw),
            major_requirements_raw=extract_major(description_raw),
            campaign_cohort_raw='', campaign_scope='', published_at=published_at,
            source_missing_fields=missing,
            extra={'job_category': row.get('firstPostTypeName') or '',
                   'hiring_department_raw': row.get('productName') or '',
                   'scope_evidence_hint': f'hr163 workType={work_type} ({["全职","日常实习","派遣"][int(work_type)] if str(work_type) in ("0","1","2") else work_type})'})
        jobs.append(job)
    result.jobs.extend(jobs)
    return jobs


# --------------------------------------------------------------------------- greenhouse

def classify_greenhouse_scope(title):
    title = str(title or '')
    if re.search(r'campus recruitment', title, re.I):
        return 'intern' if re.search(r'intern', title, re.I) else 'campus'
    if re.search(r'\bintern(ship)?\b', title, re.I):
        return 'intern'
    return 'social'


def fetch_greenhouse_board(session, board, scope, result, output_dir):
    key = f'gh-{board}'
    url = f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs'
    try:
        payload = get_json(session, url, params={'content': 'true'}, timeout=(10, 30))
    except Exception as error:
        result.errors.append(f'{key} list failed: {error}')
        return []
    result.pages_scanned += 1
    jobs_data = payload.get('jobs')
    if not isinstance(jobs_data, list):
        result.errors.append(f'{key} unexpected response shape: {payload}')
        return []
    safe_rows = [{k: v for k, v in row.items() if k != 'content'} for row in jobs_data]
    result.evidence_files.append(save_json(output_dir, f'{key}-list.json', {'count': len(jobs_data), 'rows': safe_rows}))
    result.raw_totals[key] = len(jobs_data)
    result.exhausted[key] = True  # Greenhouse's board-jobs endpoint returns the full board, unpaginated

    jobs = []
    for row in jobs_data:
        ident = row.get('id')
        actual_scope = classify_greenhouse_scope(row.get('title'))
        if actual_scope != scope:
            continue
        # This board mixes scopes; unique_source_ids must only count rows relevant to scope.
        result.unique_seen += 1
        description_raw = strip_html(row.get('content'))
        source_record_id = f'netease-gh-{board}-{ident}'
        if not description_raw:
            result.pending_review.append(source_record_id)
            continue
        location = ((row.get('location') or {}).get('name')) or ''
        cities = cities_from(re.split(r';', location)[0]) if location else []
        departments = row.get('departments') or []
        published_at = None
        for candidate in (row.get('first_published'), row.get('updated_at')):
            if candidate:
                published_at = str(candidate)[:10]
                break
        job = make_job(
            source_record_id, scope, row.get('title'), description_raw,
            f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{ident}',
            row.get('absolute_url') or f'https://job-boards.greenhouse.io/{board}/jobs/{ident}',
            cities, education_raw=extract_education(description_raw), major_requirements_raw=extract_major(description_raw),
            campaign_cohort_raw='', campaign_scope='', published_at=published_at,
            source_missing_fields=[],
            extra={'job_category': departments[0].get('name') if departments else '',
                   'field_completeness': 'combined_single_field',
                   'scope_evidence_hint': f'greenhouse board={board} title={row.get("title")}'})
        jobs.append(job)
    result.jobs.extend(jobs)
    return jobs


# --------------------------------------------------------------------------- orchestration

def build_coverage(scope, result, notes, source_url):
    jobs = result.jobs
    pagination_exhausted = bool(result.exhausted) and all(result.exhausted.values())
    complete = (not result.errors and pagination_exhausted and result.unique_seen == len(jobs))
    coverage = {
        'status': 'success' if complete else ('partial' if jobs else ('blocked' if result.errors else 'partial')),
        'complete': complete,
        'detail_complete': complete,
        'expected_total': None,
        'collected_jobs': len(jobs),
        'pages_scanned': result.pages_scanned,
        'errors': result.errors,
        'evidence': result.evidence_files,
        'evidence_files': result.evidence_files,
        'source_url': source_url,
        'pagination_exhausted': pagination_exhausted,
        'unique_source_ids': result.unique_seen,
        'last_page_evidence': '; '.join(f'{k}: exhausted={v}' for k, v in result.exhausted.items()),
        'raw_totals': result.raw_totals,
        'detail_missing_count': len(result.pending_review),
        'pending_review_index': result.pending_review,
        'notes': result.notes + notes,
        'scope_evidence': scope_evidence_text(scope, result),
    }
    return coverage


def scope_evidence_text(scope, result):
    systems = ', '.join(sorted(result.raw_totals.keys())) or 'none matched this scope'
    return f'NetEase official public sources reverified live for scope={scope}: {systems}.'


def collect(company: str, scope: str, output_dir: Path) -> dict:
    if company != COMPANY:
        raise ValueError(f'unsupported company: {company}')
    if scope not in TYPES:
        raise ValueError(f'unknown recruitment scope: {scope}')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    session = make_session()
    result = SystemResult()

    def checkpoint():
        checkpoint_coverage = dict(build_coverage(scope, result, [], NAVIGATION_URL),
                                    status='partial', complete=False, detail_complete=False)
        temp = output_dir / 'result.json.tmp'
        temp.write_text(json.dumps({'jobs': result.jobs, 'coverage': checkpoint_coverage}, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        temp.replace(output_dir / 'result.json')

    navigation = fetch_navigation(session, result, output_dir)
    campus_projects, nav_notes = parse_navigation(navigation)

    if scope in ('campus', 'intern'):
        for project_id, nav_scope in sorted(campus_projects.items()):
            if nav_scope != scope:
                continue
            fetch_campus_api_project(session, project_id, scope, result, output_dir)
            checkpoint()
        for project_id in LEIHUO_CANDIDATE_PROJECTS:
            fetch_leihuo_project(session, project_id, scope, result, output_dir)
            checkpoint()

    if scope == 'intern':
        run_with_retry(fetch_hr163_worktype, session, ('1',), scope, output_dir, result)
        checkpoint()

    if scope == 'social':
        for work_type in ('0', '2'):
            run_with_retry(fetch_hr163_worktype, session, (work_type,), scope, output_dir, result)
            checkpoint()

    for board in GREENHOUSE_BOARDS:
        fetch_greenhouse_board(session, board, scope, result, output_dir)
        checkpoint()

    coverage = build_coverage(scope, result, nav_notes, NAVIGATION_URL)
    coverage['scope_request'] = {
        'company': company, 'scope': scope, 'source_url': NAVIGATION_URL,
        'params': {'campus_api_projects': sorted(campus_projects.items()),
                  'leihuo_candidates': list(LEIHUO_CANDIDATE_PROJECTS),
                  'hr163_worktypes': ['1'] if scope == 'intern' else (['0', '2'] if scope == 'social' else []),
                  'greenhouse_boards': list(GREENHOUSE_BOARDS)},
    }
    payload = {'jobs': result.jobs, 'coverage': coverage}
    (output_dir / 'result.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return payload


if __name__ == '__main__':
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='NetEase public recruitment collector')
    parser.add_argument('scope', choices=list(TYPES))
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    outcome = collect(COMPANY, args.scope, args.output_dir)
    print(json.dumps({k: v for k, v in outcome['coverage'].items() if k not in ('evidence', 'evidence_files')},
                     ensure_ascii=False, indent=2), file=sys.stderr)
