"""Midea (美的集团) public recruitment adapter for the daily P1 chain.

Adapter contract: ``collect(company, scope, output_dir) -> {'jobs', 'coverage'}``.

Endpoints (anonymous public school-recruitment API, no login):

    GET  https://careers.midea.com/backend/school/position/common/project/list
    POST https://careers.midea.com/backend/school/position/common/position/list

The site publishes each hiring campaign as a *project rule*; a scope is the union
of the projects carrying that scope's ``employementCategory`` (verified live
2026-09-18: 1 = 校招 → 2027届美的星校园招聘 + 2027应届博士校园招聘,
4 = 实习 → 日常实习生招聘通道 + 校企合作实习招聘通道).  Project rules are
discovered from the official project list on every run, so a renamed or added
campaign is picked up without a code change.

Identity: rows keep the historical ``midea-<positionId>`` id (146 rows already
live under that namespace) and the same
``https://careers.midea.com/campus/position/<id>`` detail URL, published through
``coverage['stable_id_prefix']`` so ``p1_pipeline.validate_result`` preserves the
id and the merge updates those rows instead of duplicating them.

Completeness: every discovered project is paginated to its reported
``info.totalPage``.  The scope is complete only when the union of the project
totals equals the number of distinct positions collected and every row carries
prose; cross-project duplicates or an unmapped active project downgrade the
scope to ``partial`` so absence-based removal never runs on a shaky snapshot.

``social`` is intentionally ``blocked``: 美的集团's social/experienced postings
are not on the school-recruitment API this adapter is allowed to read, and an
empty result must never be mistaken for "the company has no open roles".
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

COMPANY = '美的集团'
MODULE_PATH = 'qiuzhao.collector.p1_midea_public'

PROJECT_URL = 'https://careers.midea.com/backend/school/position/common/project/list'
API_URL = 'https://careers.midea.com/backend/school/position/common/position/list'
DETAIL_URL = 'https://careers.midea.com/campus/position/{position_id}'
LISTING_URL = 'https://careers.midea.com/campus'
UA = 'QiuzhaoOfficialJobs/1.0 (public recruitment index; daily low-frequency review)'

RECRUITMENT_UNIT = '美的集团股份有限公司'
SCOPES = {'campus': '校园招聘', 'intern': '实习招聘', 'social': '社会招聘'}
SOURCE_NAMES = {'campus': '美的集团校园招聘官方网站', 'intern': '美的集团实习招聘官方网站'}
# employementCategory 1 = 校招 campaign, 4 = 实习 campaign (official project payload).
CATEGORY_BY_SCOPE = {'campus': {1}, 'intern': {4}}
# A project belonging to another scope's category is expected, not unmapped; only a
# category no scope claims means the adapter sees a campaign it cannot read.
MAPPED_CATEGORIES = frozenset().union(*CATEGORY_BY_SCOPE.values())
UNSUPPORTED_SCOPE_NOTE = ('美的集团社招岗位不在公开校招接口的可见范围内；'
                          '本适配器只读校招/实习官方通道，故 social 视为 blocked 而非空集。')
PAGE_SIZE = 50  # requested; the server caps a page at 20 rows and reports info.totalPage
MAX_PAGES = 500
ID_PREFIX = 'midea-'
TZ = dt.timezone(dt.timedelta(hours=8))

REQUEST_INTERVAL = float(os.environ.get('QIUZHAO_PLATFORM_REQUEST_INTERVAL') or 0)
DEFAULT_INTERVAL = 1.1


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _interval(min_interval=None):
    if min_interval is not None:
        return max(1.0, float(min_interval))
    return max(1.0, REQUEST_INTERVAL or DEFAULT_INTERVAL)


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _request(url, payload, interval, last_call):
    if last_call is not None:
        import time
        time.sleep(max(0.0, interval - (time.monotonic() - last_call)))
    headers = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
               'Referer': LISTING_URL}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers['Content-Type'] = 'application/json'
    with urlopen(Request(url, data=data, headers=headers, method='POST' if data else 'GET'),
                 timeout=35) as response:
        raw = response.read()
        if response.headers.get('Content-Encoding') == 'gzip' or raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
    import time
    return json.loads(raw.decode('utf-8', 'replace')), time.monotonic()


def _default_transport(url, payload, interval, last_call):
    return _request(url, payload, interval, last_call)


def _sentences(text):
    return [part.strip() for part in re.split(r'[；;。\n]+', str(text or '')) if part.strip()]


def _education_values(text):
    return '；'.join(s for s in _sentences(text)
                     if re.search(r'学历|博士|硕士|本科|专科|大专|高中|bachelor|master|ph\.?d', s, re.I))[:200]


def _major_values(text):
    return '；'.join(s for s in _sentences(text)
                     if re.search(r'专业|计算机|软件|电子|通信|数学|统计|机械|自动化|材料|major|degree', s, re.I))[:500]


def _cities(row):
    names = [str(w.get('workPlaceName') or '').strip()
             for w in (row.get('workplaceDtoList') or []) if isinstance(w, dict)]
    names = [name for name in names if name]
    if not names and row.get('workPlaceCode'):
        names = [str(row['workPlaceCode'])]
    return list(dict.fromkeys(names))


def _record(row, scope, reviewed, evidence_name, project_name):
    position_id = str(row.get('positionId') or '').strip()
    inner = row.get('projectPositionDto') or {}
    title = str(inner.get('positionName') or row.get('projectPositionName') or '').strip()
    duty = str(inner.get('jobResponsibility') or '').strip()
    requirement = str(inner.get('jobRequirement') or '').strip()
    description = duty + (('\n\n【任职要求】\n' + requirement) if requirement else '')
    detail_url = DETAIL_URL.format(position_id=position_id)
    return {
        'id': ID_PREFIX + position_id,
        'source_record_id': position_id,
        'job_title': title,
        'recruitment_unit': RECRUITMENT_UNIT,
        'recruitment_type': SCOPES[scope],
        'source_url': detail_url,
        'detail_url': detail_url,
        'application_url': detail_url,
        'job_listing_url': LISTING_URL,
        'campaign_url': LISTING_URL,
        'cities': _cities(row),
        'job_category': str(row.get('recruitCategoryName') or inner.get('largeTypeName') or ''),
        'job_code': str(inner.get('positionCode') or ''),
        'education_raw': _education_values(requirement),
        'major_requirements_raw': _major_values(requirement),
        'cohort_raw': '',
        'campaign_cohort_raw': project_name,
        'campaign_scope': 'project' if project_name else '',
        'cohort_scope': 'project' if project_name else '',
        'record_kind': 'official_job_post_id',
        'source_name': SOURCE_NAMES[scope],
        'source_scope': SCOPES[scope],
        'source_project_rule_id': str(row.get('projectRuleId') or ''),
        'reviewed_at': reviewed,
        'evidence_path': evidence_name,
        'description_raw': description[:5000],
        'requirement_raw': requirement[:3000],
        'status': 'open',
        'source_is_active': True,
        'source_status_raw': 'open',
        'source_list_status_raw': 'open',
        'status_note': '官方公开岗位列表当前可见；未披露截止日期，未尝试投递。',
    }


def _safe_row(row):
    inner = row.get('projectPositionDto') or {}
    return {
        'positionId': row.get('positionId'),
        'projectPositionName': row.get('projectPositionName'),
        'positionName': inner.get('positionName'),
        'recruitCategoryName': row.get('recruitCategoryName'),
        'projectRuleId': row.get('projectRuleId'),
        'employementCategory': row.get('employementCategory'),
        'cities': _cities(row),
        'responsibility_chars': len(str(inner.get('jobResponsibility') or '')),
        'requirement_chars': len(str(inner.get('jobRequirement') or '')),
    }


def _blocked(company, scope, reason, source_url=API_URL):
    return {'jobs': [], 'coverage': {
        'status': 'blocked', 'complete': False, 'detail_complete': False,
        'expected_total': None, 'collected_jobs': 0, 'pages_scanned': 0,
        'source_url': source_url, 'scope_evidence': UNSUPPORTED_SCOPE_NOTE if scope == 'social' else reason,
        'errors': [reason], 'evidence': [], 'evidence_files': [], 'checked_at': _now(),
        'company': company, 'scope': scope}}


def _discover_projects(scope, send, interval, last_call, out, reviewed):
    response, last_call = send(PROJECT_URL, None, interval, last_call)
    if not isinstance(response, dict) or str(response.get('code')) != '0':
        raise ValueError('project list failed: %s' % str(response)[:200])
    projects = response.get('data') or []
    wanted = CATEGORY_BY_SCOPE[scope]
    selected, unmapped = [], []
    for project in projects:
        if not isinstance(project, dict) or project.get('status') != 1:
            continue
        rule_id = str(project.get('projectRuleId') or '').strip()
        if not rule_id:
            continue
        category = project.get('employementCategory')
        entry = {'projectRuleId': rule_id,
                 'projectRuleName': str(project.get('projectRuleName') or ''),
                 'employementCategory': category}
        if category in wanted:
            selected.append(entry)
        elif category not in MAPPED_CATEGORIES:
            unmapped.append(entry)
    _write_json(out / 'projects.json', {
        'source_url': PROJECT_URL, 'reviewed_at': reviewed, 'scope': scope,
        'selected': selected, 'unmapped_active': unmapped,
        'all_projects': projects if isinstance(projects, list) else []})
    return selected, unmapped, last_call


def collect(company, scope, output_dir, transport=None, min_interval=None):
    """Collect one Midea scope (union of its official campaign projects)."""
    if company != COMPANY:
        raise ValueError('collect supports only company=' + COMPANY)
    if scope not in SCOPES:
        raise ValueError('scope must be campus/intern/social')
    if scope == 'social':
        return _blocked(company, scope, UNSUPPORTED_SCOPE_NOTE)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    send = transport or _default_transport
    interval = _interval(min_interval)
    reviewed = _now()
    evidence, errors = [], []
    jobs, seen = [], set()
    project_totals, duplicates = {}, 0
    last_call = None

    try:
        projects, unmapped, last_call = _discover_projects(scope, send, interval, last_call, out, reviewed)
    except Exception as error:
        return _blocked(company, scope,
                        'project discovery failed: %s: %s' % (type(error).__name__, error), PROJECT_URL)
    if not projects:
        return _blocked(company, scope,
                        'official project list exposes no active project for category %s'
                        % sorted(CATEGORY_BY_SCOPE[scope]), PROJECT_URL)

    for project in projects:
        rule_id = project['projectRuleId']
        project_name = project['projectRuleName']
        page = 1
        total_pages = None
        total = None
        while page <= MAX_PAGES:
            payload = {'projectRuleId': rule_id, 'pageIndex': page, 'pageSize': PAGE_SIZE}
            try:
                response, last_call = send(API_URL, payload, interval, last_call)
            except Exception as error:
                errors.append('%s page %d: %s: %s' % (project_name, page, type(error).__name__, error))
                break
            if not isinstance(response, dict) or str(response.get('code')) != '0':
                errors.append('%s page %d: code %r' % (project_name, page,
                                                       response.get('code') if isinstance(response, dict) else response))
                break
            data = response.get('data') or {}
            rows = data.get('data') or []
            info = data.get('info') or {}
            if total is None:
                total = data.get('total')
                total_pages = info.get('totalPage')
            if not isinstance(rows, list):
                errors.append('%s page %d: data.data is not a list' % (project_name, page))
                break
            page_name = 'list-%s-%d.json' % (rule_id[:8], page)
            _write_json(out / page_name, {
                'source_url': API_URL, 'request_url': API_URL, 'request_body': payload,
                'project': project, 'scope': scope, 'reviewed_at': reviewed,
                'page': page, 'total': total, 'info': info,
                'list': [_safe_row(row) for row in rows if isinstance(row, dict)]})
            evidence.append(page_name)

            for row in rows:
                if not isinstance(row, dict):
                    continue
                position_id = str(row.get('positionId') or '').strip()
                inner = row.get('projectPositionDto') or {}
                title = str(inner.get('positionName') or row.get('projectPositionName') or '').strip()
                if not position_id or not title:
                    errors.append('%s page %d: row without positionId/title skipped' % (project_name, page))
                    continue
                if position_id in seen:
                    duplicates += 1
                    continue
                record = _record(row, scope, reviewed, page_name, project_name)
                if not record['description_raw'].strip():
                    errors.append('%s: position %s has no responsibility/requirement'
                                  % (project_name, position_id))
                    continue
                seen.add(position_id)
                jobs.append(record)

            if total_pages and page >= int(total_pages):
                break
            if not rows:
                if total_pages and page < int(total_pages):
                    errors.append('%s page %d returned no rows before totalPage=%s'
                                  % (project_name, page, total_pages))
                break
            page += 1
        else:
            errors.append('%s exceeded MAX_PAGES=%d' % (project_name, MAX_PAGES))
        if total is not None:
            project_totals[rule_id] = int(total)

    expected_total = sum(project_totals.values()) if project_totals else None
    if expected_total is not None and duplicates:
        # Cross-project duplicates were observed while paginating every project in
        # full, so the provable size of the union is the sum minus those repeats.
        expected_total -= duplicates
    if unmapped:
        errors.append('active project(s) outside the mapped recruitment categories: %s'
                      % ', '.join('%s(%s)' % (p['projectRuleName'], p['employementCategory']) for p in unmapped))
    detail_complete = bool(jobs) and len(jobs) == len(seen)
    complete = bool(
        not errors
        and expected_total is not None
        and len(jobs) == expected_total
        and detail_complete
        and len(project_totals) == len(projects)
    )
    coverage = {
        'status': 'success' if complete else ('partial' if jobs else 'blocked'),
        'complete': complete,
        'detail_complete': detail_complete,
        'expected_total': expected_total,
        'collected_jobs': len(jobs),
        'pages_scanned': len(evidence),
        'source_url': API_URL,
        'scope_evidence': ('官方公开校招接口: %s + %s（employementCategory %s）'
                           % (PROJECT_URL, API_URL, sorted(CATEGORY_BY_SCOPE[scope]))),
        'scope_request': {
            'company': company, 'scope': scope, 'source_url': API_URL,
            'params': {'projectRuleId': [p['projectRuleId'] for p in projects],
                       'pageIndex': 1, 'pageSize': PAGE_SIZE},
        },
        'evidence': list(evidence),
        'evidence_files': list(evidence) + ['projects.json'],
        'unique_source_ids': len(seen),
        'project_totals': project_totals,
        'cross_project_duplicates': duplicates,
        'unmapped_active_projects': unmapped,
        'checked_at': reviewed,
        'errors': errors,
        'stable_id_prefix': ID_PREFIX,
        'portal': LISTING_URL,
        'listing_url': LISTING_URL,
        'company': company,
        'scope': scope,
    }
    result = {'jobs': jobs, 'coverage': coverage}
    _write_json(out / 'candidate.json', jobs)
    _write_json(out / 'coverage.json', coverage)
    _write_json(out / 'result.json', result)
    return result


def merged_registry():
    """Company name -> adapter module path for the pipeline REGISTRY."""
    return {COMPANY: MODULE_PATH}


def main():
    parser = argparse.ArgumentParser(description='Midea public recruitment adapter (p1 contract)')
    parser.add_argument('--scope', choices=sorted(SCOPES))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--min-interval', type=float, default=None)
    args = parser.parse_args()
    for scope in ([args.scope] if args.scope else sorted(SCOPES)):
        result = collect(COMPANY, scope, args.output_dir / scope, min_interval=args.min_interval)
        summary = {k: v for k, v in result['coverage'].items()
                   if k not in {'evidence', 'evidence_files', 'scope_request', 'unmapped_active_projects'}}
        print(json.dumps({'company': COMPANY, 'scope': scope, **summary}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
