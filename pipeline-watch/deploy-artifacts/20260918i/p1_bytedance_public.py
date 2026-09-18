"""ByteDance (字节跳动) public recruitment adapter for the daily P1 chain.

Adapter contract: ``collect(company, scope, output_dir) -> {'jobs', 'coverage'}``
(see ``p1_pipeline.validate_result``).  Anonymous public API, no login:

    POST https://jobs.bytedance.com/api/v1/search/job/posts

Scope mapping (verified live 2026-09-18 against the two official portals):

    scope    portal                     discriminator            detail URL
    campus   /campus/position            recruitment_id_list 201  /campus/position/<id>/detail
    intern   /campus/position            recruitment_id_list 202  /campus/position/<id>/detail
    social   /experienced/position       recruitment_id_list 101  /experienced/position/<id>/detail

``portal_type`` (3 = campus site, 2 = experienced site) is still accepted by the
server but **no longer changes the result set**: portal_type 1..12 all return the
experienced/mainland feed.  ``recruitment_id_list`` is the field that actually
selects the portal, so it is the only scope discriminator used here.  The
recruitment ids come from the official job detail payloads
(``recruit_type.id`` 201 正式/校招, 202 实习/校招, 101 正式/社招).

Identity: rows keep the historical ``bytedance-<job post id>`` id.  Production
already holds 4171 rows under that namespace, so publishing a fresh
``p1-<hash>`` namespace would duplicate the whole company.  The adapter declares
``coverage['stable_id_prefix'] = 'bytedance-'`` and
``p1_pipeline.validate_result`` preserves an adapter id that already carries the
declared prefix; every other adapter keeps the default hash identity.

Completeness: the search API caps ``count`` and pagination at 10000 results.
A scope whose reported total reaches that cap cannot prove it saw every posting,
so it is reported ``partial`` (never ``complete``) and therefore can never
trigger absence-based removal.  campus/intern are far below the cap and can be
complete.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path

from qiuzhao.collector.bytedance import fetch_page

COMPANY = '字节跳动'
MODULE_PATH = 'qiuzhao.collector.p1_bytedance_public'

API_URL = 'https://jobs.bytedance.com/api/v1/search/job/posts'
CAMPUS_LISTING = 'https://jobs.bytedance.com/campus/position'
EXPERIENCED_LISTING = 'https://jobs.bytedance.com/experienced/position'
RECRUITMENT_UNIT = '字节跳动'
PARENT_UNIT = '北京字节跳动科技有限公司'

SCOPES = {'campus': '校园招聘', 'intern': '实习招聘', 'social': '社会招聘'}
CAMPUS_SOURCE_NAME = '字节跳动校园招聘官方网站'
SOCIAL_SOURCE_NAME = '字节跳动社会招聘官方网站'

PROFILES = {
    'campus': {'recruitment_id': '201', 'portal_type': 3, 'listing': CAMPUS_LISTING,
               'detail': CAMPUS_LISTING + '/{job_id}/detail', 'parent_name': '校招',
               'source_name': CAMPUS_SOURCE_NAME},
    'intern': {'recruitment_id': '202', 'portal_type': 3, 'listing': CAMPUS_LISTING,
               'detail': CAMPUS_LISTING + '/{job_id}/detail', 'parent_name': '校招',
               'source_name': CAMPUS_SOURCE_NAME},
    'social': {'recruitment_id': '101', 'portal_type': 2, 'listing': EXPERIENCED_LISTING,
               'detail': EXPERIENCED_LISTING + '/{job_id}/detail', 'parent_name': '社招',
               'source_name': SOCIAL_SOURCE_NAME},
}

ID_PREFIX = 'bytedance-'
PAGE_SIZE = 100
API_CAP = 10000  # the search endpoint never returns/paginates past 10000 matches
SCOPE_EVIDENCE = ('官方公开API: POST jobs.bytedance.com/api/v1/search/job/posts '
                  '(recruitment_id_list 201=校招正式 / 202=校招实习 / 101=社招; 免登录)')
TZ = dt.timezone(dt.timedelta(hours=8))

# p1_pipeline injects QIUZHAO_PLATFORM_REQUEST_INTERVAL for same-host pacing.
REQUEST_INTERVAL = float(os.environ.get('QIUZHAO_PLATFORM_REQUEST_INTERVAL') or 0)
DEFAULT_INTERVAL = 1.1


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _interval(min_interval=None):
    if min_interval is not None:
        return max(1.0, float(min_interval))
    return max(1.0, REQUEST_INTERVAL or DEFAULT_INTERVAL)


def _published_at(value):
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return None
    try:
        return dt.datetime.fromtimestamp(ms / 1000, tz=TZ).strftime('%Y-%m-%d')
    except (OverflowError, OSError, ValueError):
        return None


def _sentences(text):
    return [part.strip() for part in re.split(r'[；;。\n]+', str(text or '')) if part.strip()]


def _education_values(text):
    return '；'.join(s for s in _sentences(text)
                     if re.search(r'学历|博士|硕士|本科|专科|大专|高中|bachelor|master|ph\.?d', s, re.I))[:200]


def _major_values(text):
    return '；'.join(s for s in _sentences(text)
                     if re.search(r'专业|计算机|软件|电子|通信|数学|统计|机械|自动化|major|degree', s, re.I))[:500]


def _cities(row):
    names = [str(c.get('name') or '').strip() for c in (row.get('city_list') or []) if isinstance(c, dict)]
    names = [name for name in names if name]
    if not names:
        info = row.get('city_info') or {}
        name = str(info.get('name') or '').strip() if isinstance(info, dict) else ''
        if name:
            names = [name]
    return list(dict.fromkeys(names))


def _addresses(row):
    info = row.get('job_post_info') or {}
    out = []
    for addr in (info.get('address_list') or []) if isinstance(info, dict) else []:
        name = str((addr or {}).get('name') or '').strip()
        if name and name not in out:
            out.append(name)
    return out


def _description(row):
    body = str(row.get('description') or '').strip()
    requirement = str(row.get('requirement') or '').strip()
    if requirement:
        body = (body + '\n\n【任职要求】\n' + requirement).strip()
    return body


def _record(row, scope, profile, reviewed, evidence_name):
    job_id = str(row.get('id') or '').strip()
    title = str(row.get('title') or '').strip()
    recruit_type = row.get('recruit_type') or {}
    parent = recruit_type.get('parent') or {}
    category = row.get('job_category') or {}
    requirement = str(row.get('requirement') or '').strip()
    detail_url = profile['detail'].format(job_id=job_id)
    return {
        'id': ID_PREFIX + job_id,
        'source_record_id': job_id,
        'job_title': title,
        'recruitment_unit': RECRUITMENT_UNIT,
        'parent_unit_raw': PARENT_UNIT,
        'recruitment_type': SCOPES[scope],
        'source_url': detail_url,
        'detail_url': detail_url,
        'application_url': detail_url,
        'job_listing_url': profile['listing'],
        'campaign_url': profile['listing'],
        'cities': _cities(row),
        'address_list': _addresses(row),
        'job_category': str(category.get('name') or ''),
        'job_code': str(row.get('code') or ''),
        'education_raw': _education_values(requirement),
        'major_requirements_raw': _major_values(requirement),
        'cohort_raw': str(recruit_type.get('name') or ''),
        'campaign_cohort_raw': str(parent.get('name') or profile['parent_name']),
        'published_at': _published_at(row.get('publish_time')),
        'published_at_scope': 'official_publish_timestamp',
        'record_kind': 'official_job_post_id',
        'source_name': profile['source_name'],
        'source_scope': SCOPES[scope],
        'source_recruitment_type_id': str(recruit_type.get('id') or ''),
        'reviewed_at': reviewed,
        'evidence_path': evidence_name,
        'description_raw': _description(row)[:5000],
        'requirement_raw': requirement[:3000],
        'status': 'open',
        'source_is_active': True,
        'source_status_raw': 'open',
        'source_list_status_raw': 'open',
        'status_note': '官方公开岗位列表当前可见；未披露截止日期，未尝试投递。',
    }


def _safe_row(row):
    """Evidence keeps identity/classification fields, not the full prose body."""
    category = row.get('job_category') or {}
    recruit_type = row.get('recruit_type') or {}
    parent = recruit_type.get('parent') or {}
    return {
        'id': row.get('id'),
        'title': row.get('title'),
        'code': row.get('code'),
        'job_category': {'id': category.get('id'), 'name': category.get('name')},
        'recruit_type': {'id': recruit_type.get('id'), 'name': recruit_type.get('name'),
                         'parent_id': parent.get('id'), 'parent_name': parent.get('name')},
        'city_info': {'name': (row.get('city_info') or {}).get('name')},
        'cities': _cities(row),
        'publish_time': row.get('publish_time'),
        'description_chars': len(str(row.get('description') or '')),
        'requirement_chars': len(str(row.get('requirement') or '')),
    }


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _default_transport(profile, offset, interval, last_call):
    return fetch_page(offset, PAGE_SIZE, interval, last_call,
                      portal_type=profile['portal_type'],
                      recruitment_id_list=[profile['recruitment_id']],
                      referer=profile['listing'])


def collect(company, scope, output_dir, transport=None, min_interval=None):
    """Collect one ByteDance scope as a validate_result-ready P1 payload."""
    if company != COMPANY:
        raise ValueError('collect supports only company=' + COMPANY)
    if scope not in SCOPES:
        raise ValueError('scope must be campus/intern/social')
    profile = PROFILES[scope]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    send = transport or _default_transport
    interval = _interval(min_interval)
    reviewed = _now()

    jobs, seen, errors, evidence = [], set(), [], []
    expected_total = None
    pagination_exhausted = False
    last_page_evidence = ''
    skipped_empty = 0
    duplicates = 0
    offset = 0
    last_call = None
    cap_limited = False

    while True:
        try:
            response, last_call = send(profile, offset, interval, last_call)
        except Exception as error:  # network/protocol failure ends this scope
            errors.append(f'offset {offset}: {type(error).__name__}: {error}'[:300])
            break
        if not isinstance(response, dict) or response.get('code') != 0:
            errors.append('offset %d: API code %r' % (offset, response.get('code') if isinstance(response, dict) else response))
            break
        data = response.get('data') or {}
        count = data.get('count')
        rows = data.get('job_post_list') or []
        if not isinstance(rows, list):
            errors.append(f'offset {offset}: job_post_list is not a list')
            break
        if isinstance(count, int):
            if expected_total is None:
                expected_total = count
                cap_limited = count >= API_CAP
            elif count != expected_total:
                errors.append(f'count drift at offset {offset}: {expected_total} -> {count}')
                break
        if not rows:
            pagination_exhausted = True
            break

        page_name = f'list-{offset}.json'
        _write_json(out / page_name, {
            'source_url': API_URL,
            'request_url': API_URL,
            'request_body': {'offset': offset, 'limit': PAGE_SIZE,
                             'recruitment_id_list': [profile['recruitment_id']],
                             'portal_type': profile['portal_type'], 'keyword': ''},
            'portal': profile['listing'],
            'scope': scope,
            'reviewed_at': reviewed,
            'offset': offset,
            'count': count,
            'returned': len(rows),
            'job_post_list': [_safe_row(row) for row in rows if isinstance(row, dict)],
        })
        evidence.append(page_name)
        last_page_evidence = page_name

        for row in rows:
            if not isinstance(row, dict):
                continue
            job_id = str(row.get('id') or '').strip()
            title = str(row.get('title') or '').strip()
            if not job_id or not title:
                errors.append(f'offset {offset}: row without id/title skipped')
                continue
            if job_id in seen:
                duplicates += 1
                errors.append(f'duplicate source_record_id={job_id} at offset {offset}')
                continue
            record = _record(row, scope, profile, reviewed, page_name)
            if not record['description_raw'].strip():
                # validate_result requires real prose; an index-only row would
                # need the pending-index contract, which cannot coexist with a
                # complete snapshot.  Refuse the row and drop completeness.
                skipped_empty += 1
                errors.append(f'source_record_id={job_id} has no description/requirement')
                continue
            seen.add(job_id)
            jobs.append(record)

        offset += PAGE_SIZE
        if expected_total is not None and len(seen) >= expected_total:
            pagination_exhausted = True
            break
        if offset >= API_CAP:
            break

    detail_complete = bool(jobs) and len(jobs) == len(seen)
    complete = bool(
        not errors
        and not cap_limited
        and not skipped_empty
        and duplicates == 0
        and expected_total is not None
        and pagination_exhausted
        and len(jobs) == expected_total
        and detail_complete
    )
    coverage = {
        'status': 'success' if complete else ('partial' if jobs else 'blocked'),
        'complete': complete,
        'detail_complete': detail_complete,
        'expected_total': expected_total,
        'collected_jobs': len(jobs),
        'pages_scanned': len(evidence),
        'source_url': API_URL,
        'scope_evidence': SCOPE_EVIDENCE,
        'scope_request': {
            'company': company,
            'scope': scope,
            'source_url': API_URL,
            'params': {
                'keyword': '',
                'limit': PAGE_SIZE,
                'recruitment_id_list': [profile['recruitment_id']],
                'portal_type': profile['portal_type'],
                'job_category_id_list': [],
                'tag_id_list': [],
                'location_code_list': [],
                'subject_id_list': [],
                'job_function_id_list': [],
            },
        },
        'evidence': list(evidence),
        'evidence_files': list(evidence),
        'unique_source_ids': len(seen),
        'pagination_exhausted': pagination_exhausted,
        'last_page_evidence': last_page_evidence,
        'api_cap': API_CAP,
        'api_cap_limited': cap_limited,
        'api_cap_note': ('接口最多返回 %d 条；达到上限即无法证明已覆盖全部在招岗位，'
                         '该 scope 只能 partial。' % API_CAP),
        'skipped_empty_body': skipped_empty,
        'duplicate_source_ids': duplicates,
        'checked_at': reviewed,
        'errors': errors,
        'stable_id_prefix': ID_PREFIX,
        'portal': profile['listing'],
        'listing_url': profile['listing'],
        'company': company,
        'scope': scope,
    }
    if cap_limited and not errors:
        coverage['status_note'] = '达到接口 10000 条上限，无法证明完整性；仅增量更新，不做缺席下线。'
    elif jobs and not complete and not errors:
        coverage['status_note'] = '本次为增量结果，不参与缺席下线。'
    result = {'jobs': jobs, 'coverage': coverage}
    _write_json(out / 'candidate.json', jobs)
    _write_json(out / 'coverage.json', coverage)
    _write_json(out / 'result.json', result)
    return result


def merged_registry():
    """Company name -> adapter module path for the pipeline REGISTRY."""
    return {COMPANY: MODULE_PATH}


def main():
    parser = argparse.ArgumentParser(description='ByteDance public recruitment adapter (p1 contract)')
    parser.add_argument('--scope', choices=sorted(SCOPES))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--min-interval', type=float, default=None)
    args = parser.parse_args()
    for scope in ([args.scope] if args.scope else sorted(SCOPES)):
        result = collect(COMPANY, scope, args.output_dir / scope, min_interval=args.min_interval)
        summary = {k: v for k, v in result['coverage'].items()
                   if k not in {'evidence', 'evidence_files', 'scope_request'}}
        print(json.dumps({'company': COMPANY, 'scope': scope, **summary}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
