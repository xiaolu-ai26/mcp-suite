"""Bank-specific official recruitment adapters, batch 1.

Five large banks each run their own bespoke portal, so unlike the platform
adapters (Beisen / Moka) this module keeps one parser per bank. The contract is
identical to ``p1_sources_*``: a ``COMPANIES`` slug map, ``collect(company,
scope, output_dir)`` returning ``{'jobs': [...], 'coverage': {...}}``, and the
same on-disk evidence plus ``result.json``.

Banks and their public channels:

* ``citic`` 中信银行   JSON ``POST /recruitportal/portal/recruitQuery``
* ``cmb``   招商银行   JSON ``/api/campusRecruitmentWebsite/job/*``
* ``bocom`` 交通银行   JSON ``POST /api/GTMS.GTMS-PORTAL.V-1.0/querySocietyRecruitInfo.do``
* ``icbc``  中国工商银行  岗位列表接口要求登录态 token -> blocked
* ``abc``   中国农业银行  请求体 AES+RSA 加密签名 -> blocked

Registration is config-free: ``merged_registry()`` returns every name in
``COMPANIES`` so ``p1_pipeline`` can append them after the hardcoded 50 without
touching any ordinal.

Politeness: every external request goes through :func:`_request`, which sleeps
``QIUZHAO_BANK_MIN_INTERVAL`` seconds (default 2.0) and honours
``QIUZHAO_BANK_REQUEST_BUDGET`` / ``max_requests`` when set. Production defaults
to no request cap; the read-only verification runs pass 30 on purpose.
"""
from __future__ import annotations
import json
import os
import re
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

MODULE_PATH = 'qiuzhao.collector.p1_banks_01'
COMPANIES = {
    'icbc': '中国工商银行',
    'abc': '中国农业银行',
    'bocom': '交通银行',
    'cmb': '招商银行',
    'citic': '中信银行',
}
TYPES = shared.TYPES
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
# Production default: no cap. The verification runs set 30 explicitly.
DEFAULT_REQUEST_BUDGET = None
DEFAULT_MIN_INTERVAL = 2.0

# CMB hard-codes one recruitment-type GUID per public channel in its bundle.
CMB_CAMPUS_TYPE = '96574F8D-C7ED-4772-AE7C-BAC896D190C1'
CMB_SOCIAL_TYPE = 'DF94FD6D-26D3-4A19-9E69-577C4BA1DE82'
# CITIC channel codes observed in schoolRecruit.html (02) and socialRecruit.html (01).
CITIC_CHANNELS = {'campus': '02', 'social': '01'}


class BudgetExhausted(RuntimeError):
    """Raised when the per-run request budget is reached; callers keep partial rows."""


def merged_registry():
    """Company name -> adapter module path for the pipeline REGISTRY."""
    return {name: MODULE_PATH for name in COMPANIES.values()}


def _slug(company):
    if company in COMPANIES:
        return company
    reverse = {name: slug for slug, name in COMPANIES.items()}
    if company in reverse:
        return reverse[company]
    raise ValueError('unknown bank company: ' + str(company))


def _budget_limit(max_requests):
    if max_requests is not None:
        return int(max_requests)
    raw = os.environ.get('QIUZHAO_BANK_REQUEST_BUDGET')
    return int(raw) if raw and raw.strip() else DEFAULT_REQUEST_BUDGET


def _min_interval():
    raw = os.environ.get('QIUZHAO_BANK_MIN_INTERVAL')
    return float(raw) if raw and raw.strip() else DEFAULT_MIN_INTERVAL


def _legacy_ssl_context():
    context = ssl.create_default_context()
    # Several bank hosts still negotiate without RFC 5746 secure renegotiation;
    # browsers accept them, OpenSSL 3 refuses unless this is re-enabled.
    if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
        context.options |= ssl.OP_LEGACY_SERVER_CONNECT
    return context


def _make_session(legacy_tls=False):
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    session.headers['User-Agent'] = UA
    retry = Retry(total=1, connect=1, read=1, status=1, backoff_factor=1,
                  allowed_methods={'GET', 'POST'}, status_forcelist=[429, 502, 503, 504])
    if legacy_tls:
        context = _legacy_ssl_context()

        class LegacyTLSAdapter(HTTPAdapter):
            def build_connection_pool_key_attributes(self, request, verify, cert=None):
                host, pool = super().build_connection_pool_key_attributes(request, verify, cert)
                pool['ssl_context'] = context
                return host, pool

        session.mount('https://', LegacyTLSAdapter(max_retries=retry))
    else:
        session.mount('https://', HTTPAdapter(max_retries=retry))
    return session


def make_client(legacy_tls=False, max_requests=None, interval=None, session=None, transport=None):
    """Build the per-run request context shared by one collect() invocation."""
    return {
        'session': session if session is not None else _make_session(legacy_tls),
        'budget': {'limit': _budget_limit(max_requests), 'used': 0},
        'interval': _min_interval() if interval is None else float(interval),
        'transport': transport,
    }


def _request(client, method, url, **kwargs):
    budget = client['budget']
    if budget['limit'] is not None and budget['used'] >= budget['limit']:
        raise BudgetExhausted('per-run request budget reached')
    if client.get('interval'):
        time.sleep(client['interval'])
    budget['used'] += 1
    if client.get('transport') is not None:
        response = client['transport'](method, url, **kwargs)
    else:
        response = client['session'].request(method, url, timeout=(10, 45), **kwargs)
    response.raise_for_status()
    return response


def _get(client, url, **kwargs):
    return _request(client, 'GET', url, **kwargs)


def _post(client, url, **kwargs):
    return _request(client, 'POST', url, **kwargs)


def _date10(value):
    text = str(value or '').strip()
    match = re.match(r'(\d{4}-\d{2}-\d{2})', text)
    return match.group(1) if match else ''


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _job(company, scope, ident, title, url, description, location='', raw=None,
         requirements='', education='', cohort=''):
    name = COMPANIES.get(company, company)
    stamp = _now_iso()
    plain = shared.text(description)
    cities = [part.strip() for part in re.split(r'\s*[/、,，;；]\s*', shared.text(location)) if part.strip()]
    record = {
        'id': f'p1:{company}:{ident}',
        'source_record_id': str(ident),
        'title': title,
        'job_title': title,
        'company': name,
        'company_name': name,
        'company_slug': company,
        'unit': name,
        'recruitment_unit': name,
        'recruitment_type': TYPES[scope],
        'source_url': url,
        'detail_url': url,
        'application_url': url,
        'description_raw': plain,
        'location': shared.text(location),
        'city': shared.text(location),
        'cities': cities,
        'education_raw': shared.text(education),
        'major_requirements_raw': '',
        'cohort_raw': cohort,
        'experience_raw': '',
        'source': 'official_career',
        'verified_at': stamp,
        'reviewed_at': stamp,
        'source_fields': {k: v for k, v in (raw or {}).items()
                          if isinstance(v, (str, int, float, bool)) and len(str(v)) < 500},
    }
    if requirements:
        record['requirements_field_evidence'] = 'Verbatim official detail field'
    return record


def _record(output_dir, name, payload):
    (Path(output_dir) / name).write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8')


def _blocked(url, reason, client=None, evidence=None):
    coverage = shared.coverage(url)
    coverage['errors'] = [reason]
    if evidence is not None:
        coverage['blocking_kind'] = 'upstream_access'
        coverage['blocking_evidence'] = evidence
    if client is not None:
        coverage['request_budget'] = client['budget']
    return shared.finish([], coverage)


# --------------------------------------------------------------------------- CITIC

def collect_citic(company, scope, output_dir, client=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    entry = 'https://job.citicbank.com/CustStyle/zpmhys/schoolRecruit.html'
    coverage = shared.coverage(entry)
    if scope not in CITIC_CHANNELS:
        return _blocked(entry, '中信银行站点公开频道仅校招(02)/社招(01)，无独立实习频道', client)
    client = client or make_client(legacy_tls=False)
    jobs = []
    code = CITIC_CHANNELS[scope]
    list_url = 'https://job.citicbank.com/recruitportal/portal/recruitQuery'
    try:
        expected = None
        page = 1
        while page <= 200:
            body = {'RELEASENAME': '', 'recruitmentType': code, 'workAddr': [],
                    'deptCode': [], 'page': page}
            response = _post(client, list_url, json=body,
                             headers={'Referer': entry, 'X-Requested-With': 'XMLHttpRequest'})
            payload = response.json()
            _record(output_dir, f'list-{page}.json', payload)
            coverage['pages_scanned'] += 1
            if payload.get('IsSuc') is not True:
                raise ValueError(str(payload.get('Msg') or payload)[:300])
            table = payload.get('tableData') or {}
            rows = table.get('rows') or []
            total = payload.get('pageCount')
            if expected is None and isinstance(total, int):
                expected = total
                coverage['expected_total'] = total
            if not rows:
                coverage['pagination_exhausted'] = True
                coverage['last_page_evidence'] = (
                    f'page={page};rows=0;total={total};observed={len(jobs)}')
                break
            for row in rows:
                item = row.get('itemMap') or {}
                ident = str(item.get('ID') or '').strip()
                if not ident:
                    raise ValueError('CITIC row without official ID')
                title = shared.text(item.get('RELEASENAME') or item.get('POSTNAME'))
                branch = shared.text(item.get('CONTENT'))
                work_addr = shared.text(item.get('WORKADDR'))
                demand = item.get('DEMANDCOUNT')
                is_count = str(item.get('IS_COUNT') or '')
                demand_text = '若干' if is_count == '1' else str(demand if demand is not None else '')
                description = '\n'.join(part for part in [
                    f'岗位：{title}',
                    f'招聘单位：{branch}' if branch else '',
                    f'工作地点：{work_addr}' if work_addr else '',
                    f'招聘人数：{demand_text}' if demand_text else '',
                ] if part)
                detail_url = ('https://job.citicbank.com/CustStyle/zpmhys/positionDetail.html'
                              f'?id={ident}&channelType={code}&showReturn=true&showDelivery=true')
                job = _job(company, scope, ident, title, detail_url, description,
                           work_addr, item)
                job['recruitment_unit'] = branch or COMPANIES[company]
                job['parent_unit_raw'] = branch or COMPANIES[company]
                job['recruiting_unit_raw'] = branch or COMPANIES[company]
                published = _date10(item.get('FBZWDATE'))
                if published:
                    job['published_at'] = published
                    job['publication_date'] = published
                    job['source_publication_field'] = 'FBZWDATE'
                job['scope_evidence'] = (f'Official CITIC recruitQuery recruitmentType={code}; '
                                         f'source channel={scope}')
                jobs.append(job)
            if expected is not None and len(jobs) >= expected:
                coverage['pagination_exhausted'] = True
                coverage['last_page_evidence'] = f'page={page};observed={len(jobs)};total={expected}'
                break
            page += 1
        coverage['detail_complete'] = not coverage['errors']
        coverage['evidence'] = sorted(p.name for p in output_dir.glob('list-*.json'))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (f'Official CITIC recruitQuery channel {scope} '
                                      f'(recruitmentType={code})')
        coverage['scope_request'] = {'company': COMPANIES[company], 'scope': scope,
                                     'source_url': list_url, 'params': body}
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
        coverage['detail_complete'] = False
    except Exception as error:
        coverage['errors'].append(f'{type(error).__name__}: {error}'[:300])
    coverage['request_budget'] = client['budget']
    return shared.finish(jobs, coverage)


# --------------------------------------------------------------------------- CMB

def collect_cmb(company, scope, output_dir, client=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    host = 'https://career.cmbchina.com'
    entry = host + '/campus/home'
    coverage = shared.coverage(entry)
    if scope == 'campus':
        service = 'campusRecruitmentWebsite'
        type_id = CMB_CAMPUS_TYPE
    elif scope == 'social':
        service = 'socialRecruitmentWebsite'
        type_id = CMB_SOCIAL_TYPE
    else:
        return _blocked(entry, '招商银行站点公开频道仅校招/社招，无独立公开实习频道', client)
    client = client or make_client(legacy_tls=False)
    jobs = []
    base = f'{host}/api/{service}/job'
    try:
        expected = None
        page = 1
        while page <= 200:
            body = {'orgIdList': [], 'keywords': '', 'locationIdList': [],
                    'pageIndex': page, 'pageSize': 50, 'recruitmentTypeId': type_id}
            response = _post(client, base + '/getList', json=body,
                             headers={'Referer': entry, 'X-Requested-With': 'XMLHttpRequest'})
            payload = response.json()
            _record(output_dir, f'list-{page}.json', payload)
            coverage['pages_scanned'] += 1
            if payload.get('returnCode') != 'SUC0000':
                raise ValueError(str(payload.get('errorMsg') or payload)[:300])
            data = payload.get('body') or {}
            rows = data.get('data') or []
            if expected is None and isinstance(data.get('total'), int):
                expected = data['total']
                coverage['expected_total'] = expected
            if not rows:
                coverage['pagination_exhausted'] = True
                coverage['last_page_evidence'] = (
                    f'page={page};rows=0;total={expected};observed={len(jobs)}')
                break
            for row in rows:
                ident = str(row.get('publishGID') or '').strip()
                if not ident:
                    raise ValueError('CMB row without publishGID')
                title = shared.text(row.get('jobDisplay'))
                branch = shared.text(row.get('branchCodeName'))
                location = shared.text(row.get('locationName'))
                detail_url = (f'{host}/{scope}/positionDetail/{type_id}?publishId={ident}')
                description = '\n'.join(part for part in [
                    f'岗位：{title}',
                    f'招聘机构：{branch}' if branch else '',
                    f'工作地点：{location}' if location else '',
                ] if part)
                job = _job(company, scope, ident, title, detail_url, description, location, row)
                job['recruitment_unit'] = branch or COMPANIES[company]
                job['parent_unit_raw'] = branch or COMPANIES[company]
                job['recruiting_unit_raw'] = branch or COMPANIES[company]
                deadline = _date10(row.get('expiredOn'))
                if deadline:
                    job['deadline_raw'] = deadline
                    job['deadline'] = deadline
                    job['deadline_type'] = 'explicit'
                job['scope_evidence'] = (f'Official CMB {service} job/getList; '
                                         f'recruitmentTypeId={type_id}')
                jobs.append(job)
            if expected is not None and len(jobs) >= expected:
                coverage['pagination_exhausted'] = True
                coverage['last_page_evidence'] = f'page={page};observed={len(jobs)};total={expected}'
                break
            page += 1
        # Detail pages are the only place with the real duty/requirement text; they
        # are fetched politely and may be cut short by the request budget.
        detail_pending = False
        for job in jobs:
            try:
                response = _get(client, base + '/getDetail',
                                params={'publishId': job['source_record_id']},
                                headers={'Referer': entry})
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                detail_pending = True
                break
            try:
                payload = response.json()
                _record(output_dir, f'detail-{job["source_record_id"]}.json', payload)
                if payload.get('returnCode') == 'SUC0000' and isinstance(payload.get('body'), dict):
                    detail = payload['body']
                    duty = shared.text(detail.get('jobResponsibility'))
                    require = shared.text(detail.get('jobRequirement'))
                    if duty or require:
                        job['description_raw'] = (duty + '\n任职要求\n' + require).strip()
                        job['requirements_field_evidence'] = 'Official CMB jobRequirement'
                    if detail.get('jobCode'):
                        job['job_code'] = detail['jobCode']
                    location = shared.text(detail.get('locationName'))
                    if location:
                        job['location'] = location
                        job['city'] = location
                    deadline = _date10(detail.get('expiredOn'))
                    if deadline:
                        job['deadline_raw'] = deadline
                        job['deadline'] = deadline
                        job['deadline_type'] = 'explicit'
            except Exception as error:
                coverage.setdefault('detail_fetch_errors', []).append(
                    f'{job["source_record_id"]}: {type(error).__name__}: {error}'[:300])
        coverage['detail_complete'] = (not coverage['errors'] and not detail_pending
                                       and not coverage.get('detail_fetch_errors'))
        coverage['evidence'] = sorted(p.name for p in output_dir.glob('list-*.json')) + \
            sorted(p.name for p in output_dir.glob('detail-*.json'))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (f'Official CMB {service}; recruitmentTypeId={type_id}')
        coverage['scope_request'] = {'company': COMPANIES[company], 'scope': scope,
                                     'source_url': base + '/getList',
                                     'params': {'pageSize': 50, 'recruitmentTypeId': type_id}}
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
        coverage['detail_complete'] = False
    except Exception as error:
        coverage['errors'].append(f'{type(error).__name__}: {error}'[:300])
    coverage['request_budget'] = client['budget']
    return shared.finish(jobs, coverage)


# --------------------------------------------------------------------------- BOCOM

BOCOM_ENGAGE = {'campus': 1, 'social': 3}


def _bocom_envelope(engage_type, page, page_size):
    message = {
        'REQ_HEAD': {'TRAN_PROCESS': '', 'TRAN_ID': '', 'ACCESS_TOKEN': None, 'REFRESH_TOKEN': None},
        'REQ_BODY': {
            'params': {
                'businessPara': {'workPlace': '', 'pubName': '', 'bankNumber': '',
                                 'positionId': '', 'engageType': engage_type},
                'pagePara': {'pageNum': page, 'pageSize': page_size},
            },
            'unnessaryLogin': False,
        },
    }
    return urlencode({'REQ_MESSAGE': json.dumps(message, ensure_ascii=False, separators=(',', ':'))},
                     quote_via=quote)


def collect_bocom(company, scope, output_dir, client=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    host = 'https://job.bankcomm.com'
    entry = host + '/school/main'
    coverage = shared.coverage(entry)
    if scope not in BOCOM_ENGAGE:
        return _blocked(entry, '交通银行站点公开频道仅校招(engageType=1)/社招(engageType=3)，'
                               '实习频道(engageType=2)当前无公开在招记录', client)
    client = client or make_client(legacy_tls=True)
    engage = BOCOM_ENGAGE[scope]
    jobs = []
    list_url = host + '/api/GTMS.GTMS-PORTAL.V-1.0/querySocietyRecruitInfo.do'
    try:
        expected = None
        page = 1
        while page <= 200:
            response = _post(client, list_url,
                             data=_bocom_envelope(engage, page, 50).encode('utf-8'),
                             headers={'content-type': 'application/x-www-form-urlencoded',
                                      'Referer': entry,
                                      'Origin': host})
            payload = response.json()
            _record(output_dir, f'list-{page}.json', payload)
            coverage['pages_scanned'] += 1
            head = payload.get('RSP_HEAD') or {}
            if str(head.get('TRAN_SUCCESS')) != '1':
                raise ValueError(str(head.get('ERROR_MESSAGE') or payload)[:300])
            results = ((payload.get('RSP_BODY') or {}).get('results')) or {}
            rows = results.get('policyList') or []
            if expected is None and isinstance(results.get('total'), int):
                expected = results['total']
                coverage['expected_total'] = expected
            if not rows:
                coverage['pagination_exhausted'] = True
                coverage['last_page_evidence'] = (
                    f'page={page};rows=0;total={expected};observed={len(jobs)}')
                break
            for row in rows:
                ident = str(row.get('positionId') or '').strip()
                if not ident:
                    raise ValueError('BOCOM row without positionId')
                title = shared.text(row.get('pubName'))
                branch = shared.text(row.get('bankName'))
                dept = shared.text(row.get('deptName'))
                project = shared.text(row.get('projectName'))
                location = shared.text(row.get('workPlace'))
                amount = row.get('engageAmount')
                description = '\n'.join(part for part in [
                    f'岗位：{title}',
                    f'招聘项目：{project}' if project else '',
                    f'招聘单位：{branch}' if branch else '',
                    f'部门：{dept}' if dept else '',
                    f'工作地点：{location}' if location else '',
                    f'招聘人数：{amount}' if amount not in (None, '') else '',
                ] if part)
                hash_path = '/#/school/recruitmentInfo/' if scope == 'campus' else '/#/social/recruitmentInfo/'
                detail_url = f'{host}{hash_path}?positionId={ident}'
                job = _job(company, scope, ident, title, detail_url, description, location, row)
                job['recruitment_unit'] = branch or COMPANIES[company]
                job['parent_unit_raw'] = branch or COMPANIES[company]
                job['recruiting_unit_raw'] = branch or COMPANIES[company]
                published = _date10(row.get('createTime'))
                if published:
                    job['published_at'] = published
                    job['publication_date'] = published
                    job['source_publication_field'] = 'createTime'
                deadline = _date10(row.get('endDate'))
                if deadline:
                    job['deadline_raw'] = deadline
                    job['deadline'] = deadline
                    job['deadline_type'] = 'explicit'
                job['campaign_cohort_raw'] = project
                job['scope_evidence'] = (f'Official BOCOM GTMS querySocietyRecruitInfo; '
                                         f'engageType={engage} -> {scope}')
                jobs.append(job)
            if expected is not None and len(jobs) >= expected:
                coverage['pagination_exhausted'] = True
                coverage['last_page_evidence'] = f'page={page};observed={len(jobs)};total={expected}'
                break
            page += 1
        coverage['detail_complete'] = not coverage['errors']
        coverage['evidence'] = sorted(p.name for p in output_dir.glob('list-*.json'))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (f'Official BOCOM portal engageType={engage}; channel={scope}')
        coverage['scope_request'] = {'company': COMPANIES[company], 'scope': scope,
                                     'source_url': list_url,
                                     'params': {'businessPara': {'engageType': engage},
                                                'pagePara': {'pageNum': 1, 'pageSize': 50}}}
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
        coverage['detail_complete'] = False
    except Exception as error:
        coverage['errors'].append(f'{type(error).__name__}: {error}'[:300])
    coverage['request_budget'] = client['budget']
    return shared.finish(jobs, coverage)


# --------------------------------------------------------------------------- ICBC / ABC (blocked)

def collect_icbc(company, scope, output_dir, client=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    entry = 'https://job.icbc.com.cn/pc/index.html'
    if scope not in TYPES:
        raise ValueError('invalid scope')
    client = client or make_client(legacy_tls=True)
    evidence = {'entry': entry}
    try:
        # The post-type dictionary is public and proves the host/API base is real.
        response = _post(client, 'https://job.icbc.com.cn/icbc/trmo/post/qryPostType',
                         json={}, headers={'Referer': entry, 'Origin': 'https://job.icbc.com.cn'})
        dictionary = response.json()
        _record(output_dir, 'post-types.json', dictionary)
        evidence['post_type_retCode'] = dictionary.get('retCode')
        types = ((dictionary.get('data') or {}).get('dataList')) or []
        evidence['post_type_count'] = len(types)
        # The position list endpoints all require a login token.
        response = _post(client, 'https://job.icbc.com.cn/icbc/trmo/post/qryPostList',
                         json={'postTypeId': 'D00001', 'conditionType': 1, 'lastNum': 0, 'pageSize': 10},
                         headers={'Referer': entry, 'Origin': 'https://job.icbc.com.cn'})
        listing = response.json()
        _record(output_dir, 'post-list-probe.json', listing)
        evidence['list_retCode'] = listing.get('retCode')
        evidence['list_retMsg'] = listing.get('retMsg')
        response = _post(client, 'https://job.icbc.com.cn/icbc/trmo/api/userInfo',
                         json={}, headers={'Referer': entry, 'Origin': 'https://job.icbc.com.cn'})
        user = response.json()
        _record(output_dir, 'userinfo-probe.json', user)
        evidence['userinfo_retCode'] = user.get('retCode')
    except BudgetExhausted:
        evidence['budget_exhausted'] = True
    except Exception as error:
        evidence['probe_error'] = f'{type(error).__name__}: {error}'[:300]
    reason = ('中国工商银行岗位列表接口 /icbc/trmo/post/qryPostList 返回 '
              'retCode=90/系统繁忙，/icbc/trmo/api/userInfo 返回 TOKEN_001（token is empty），'
              '岗位列表需登录态 token；公开接口仅岗位类别字典可用。按约束不登录、不绕过。')
    result = _blocked(entry, reason, client, evidence)
    result['coverage']['channel_probe'] = evidence
    return result


def collect_abc(company, scope, output_dir, client=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    entry = 'https://career.abchina.com/build/index.html'
    if scope not in TYPES:
        raise ValueError('invalid scope')
    client = client or make_client(legacy_tls=True)
    evidence = {
        'entry': entry,
        'api_module': 'RMIS/pc/static/js/main.*.js',
        'request_helper': 'fetchPost',
        'encryption': ('请求体经 AES 加密（随机 vi/ke）并用服务端 RSA 公钥加密密钥，'
                       '以 viF/keF/pellosetq 头提交；响应同密钥解密。'),
    }
    try:
        response = _get(client, 'https://career.abchina.com/build/index.html',
                        headers={'Referer': 'https://career.abchina.com/'})
        (output_dir / 'official-entry.html').write_bytes(response.content)
        evidence['entry_status'] = response.status_code
    except BudgetExhausted:
        evidence['budget_exhausted'] = True
    except Exception as error:
        evidence['probe_error'] = f'{type(error).__name__}: {error}'[:300]
    reason = ('中国农业银行招聘站 API 使用 AES 请求体加密 + RSA 密钥交换 + '
              'viF/keF/pellosetq 签名头（fetchPost），属签名/加密协议；'
              '按约束不逆向、不绕过，标记 blocked。')
    result = _blocked(entry, reason, client, evidence)
    result['coverage']['channel_probe'] = evidence
    return result


COLLECTORS = {
    'citic': collect_citic,
    'cmb': collect_cmb,
    'bocom': collect_bocom,
    'icbc': collect_icbc,
    'abc': collect_abc,
}


def collect(company, scope, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in TYPES:
        raise ValueError('Unknown recruitment scope')
    slug = _slug(company)
    collector = COLLECTORS[slug]
    result = collector(slug, scope, output_dir)
    result['coverage']['scope_request'] = result['coverage'].get('scope_request') or {
        'company': COMPANIES[slug], 'scope': scope,
        'source_url': result['coverage'].get('source_url')}
    (output_dir / 'result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('company')
    parser.add_argument('scope', choices=list(TYPES))
    parser.add_argument('output_dir')
    parser.add_argument('--max-requests', type=int)
    args = parser.parse_args()
    built = COLLECTORS[_slug(args.company)](_slug(args.company), args.scope, Path(args.output_dir))
    print(json.dumps(built['coverage'], ensure_ascii=False))
