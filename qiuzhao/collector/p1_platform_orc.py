"""Oracle Recruiting Cloud (ORC / Oracle Fusion Cloud HCM) platform adapter.

One adapter covers every ORC candidate-experience site. Adding a company = one line
in ``p1_platform_companies.json`` under ``"orc"`` with ``<host>/<siteNumber>`` as key
(for example ``"jpmc.fa.oraclecloud.com/CX_1001"``). Everything it reads is the same
public, login-free REST surface the candidate-experience page itself calls; no
account, cookie, token or signature is involved.

Verified read-only on 2026-09-19 against Oracle (``CX_45001``), Honeywell
(``CX_1``) and JPMorgan Chase (``CX_1001``):

* China geography lookup (site-specific geography id):
  ``GET /hcmRestApi/resources/latest/recruitingHierarchyLocations?onlyData=true
  &finder=findBySiteNumberAndWord;SiteNumber=<site>,FilterAttributes=GeographyFlatName,
  SearchTerms=China,StartsWithFlag=true&limit=1000000``
  -> item with ``GeographyLevel == 1`` and ``GeographyFlatName == "China"``.
  Geography ids differ per site (Honeywell ``300000000469314``,
  JPMorgan ``300000000289192``), so the id is always discovered, never hardcoded.
* Job list: ``GET /hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true
  &expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber=<site>,
  selectedLocationsFacet=<china id>,limit=<n>,offset=<n>,sortBy=POSTING_DATES_DESC``
  (``limit`` is capped server-side at 200).
* Job details (batched, one request per ``detail_batch_size`` requisitions):
  ``GET /hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all
  &onlyData=true&finder=ById;Id=<id> or <id> or ...,siteNumber=<site>&limit=500``.

Data quality: only official ORC fields are written. ``PostedDate`` -> ``published_at``;
``PostingEndDate`` -> ``deadline_raw`` (left empty when the site does not publish one);
there is no Chinese cohort (届别) field in ORC, so ``cohort_raw`` is always left empty --
nothing is inferred. ``Campus / Graduate / Early Careers / Intern`` official labels
(title, ``RequisitionType``, ``WorkerType``) map to campus/intern; anything else is
recorded under the social scope.
"""
from __future__ import annotations
import html as _html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
CONFIG_KEY = 'orc'
MODULE_PATH = 'qiuzhao.collector.p1_platform_orc'
DEFAULT_REQUEST_BUDGET = None
DEFAULT_PAGE_SIZE = 200           # ORC caps the server-side limit at 200
DEFAULT_DETAIL_BATCH = 40         # requisitions per batched detail request
DEFAULT_MAX_LIST_PAGES = 50
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

INTERN_KEYWORDS = ['intern', 'internship', '实习', 'summer analyst', 'summer intern',
                   'co-op', 'coop', 'placement', 'working student', 'werkstudent']
CAMPUS_KEYWORDS = ['graduate', 'graduation', 'campus', 'college', 'early career',
                   'earlycareer', 'entry-level', 'entry level', 'university',
                   'new college graduate', 'trainee', 'management associate',
                   'leadership program', 'leadership development', '校招', '应届',
                   '管培', '培训生', 'analyst program', 'summer program', 'apprentice']
CHINA_CITY_TOKENS = ['beijing', 'shanghai', 'shenzhen', 'guangzhou', 'hangzhou', 'suzhou',
                     'chengdu', 'wuhan', 'nanjing', 'tianjin', "xi'an", 'xian', 'dalian',
                     'qingdao', 'changzhou', 'wuxi', 'hefei', 'xiamen', 'chongqing',
                     'zhuhai', 'dongguan', 'foshan', 'ningbo', 'jinan', 'zhengzhou',
                     'changsha', 'shenyang', 'harbin', 'kunming', 'fuzhou', 'wenzhou',
                     'kunshan', 'taicang', 'zhanjiang', 'huizhou', 'zhongshan', 'shaanxi',
                     'jiangsu', 'zhejiang', 'guangdong', 'shandong', 'sichuan', 'hubei',
                     'liaoning', 'fujian', 'hunan', 'anhui', 'henan', 'hebei', 'jiangxi']
COUNTRY_TOKEN_RE = re.compile(r'(?<![A-Za-z])(?:china|cn|prc|中国|mainland china)(?![A-Za-z])', re.I)


class BudgetExhausted(RuntimeError):
    pass


# ---------------------------------------------------------------- config
def _read_platform():
    data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return data.get(CONFIG_KEY) or {}


def _entry(key):
    entry = _read_platform().get(key) or {}
    if isinstance(entry, str):
        return {'name': entry}
    return entry


def _entry_name(entry):
    return entry if isinstance(entry, str) else str((entry or {}).get('name') or '')


def _load_companies():
    companies = {}
    for key, entry in _read_platform().items():
        if str(key).startswith('_'):  # config documentation keys, not tenants
            continue
        name = _entry_name(entry)
        if name:
            companies[str(key)] = name
    return companies


COMPANIES = _load_companies()
NAME_TO_KEY = {name: key for key, name in COMPANIES.items()}


def reload_config():
    global COMPANIES, NAME_TO_KEY
    COMPANIES = _load_companies()
    NAME_TO_KEY = {name: key for key, name in COMPANIES.items()}
    return COMPANIES


def merged_registry():
    return {name: MODULE_PATH for name in COMPANIES.values()}


def resolve(company):
    if company in COMPANIES:
        return company
    if company in NAME_TO_KEY:
        return NAME_TO_KEY[company]
    raise ValueError('unknown Oracle Recruiting Cloud company: ' + str(company))


def host_and_site(key):
    """``<host>/<siteNumber>`` -> (host, siteNumber); a bare host is rejected."""
    parts = [p for p in str(key).strip().strip('/').split('/') if p]
    if len(parts) != 2 or not re.fullmatch(r'CX_\d+', parts[1]):
        raise ValueError('ORC config key must be <host>/<siteNumber>: ' + str(key))
    return parts[0], parts[1]


def page_size_for(key):
    return int(_entry(key).get('page_size') or DEFAULT_PAGE_SIZE)


def detail_batch_for(key):
    return int(_entry(key).get('detail_batch_size') or DEFAULT_DETAIL_BATCH)


def max_list_pages_for(key):
    return int(_entry(key).get('max_list_pages') or DEFAULT_MAX_LIST_PAGES)


def _scope_of(title, key, official):
    entry = _entry(key)
    low = str(title or '').lower()
    intern_kw = INTERN_KEYWORDS + [str(x).lower() for x in (entry.get('intern_keywords') or [])]
    campus_kw = CAMPUS_KEYWORDS + [str(x).lower() for x in (entry.get('campus_keywords') or [])]
    labels = ' '.join(str(official.get(field) or '') for field in
                      ('RequisitionType', 'WorkerType', 'JobFamily')).lower()
    if any(k and (k in low or k in labels) for k in intern_kw):
        return 'intern'
    if any(k and (k in low or k in labels) for k in campus_kw):
        return 'campus'
    return 'social'


def _city_parts(*location_values):
    """Official city/region tokens only -- country and postcode fragments dropped."""
    cities = []
    for value in location_values:
        for token in re.split(r'\s*/\s*|[，,、;；|]', str(value or '')):
            token = COUNTRY_TOKEN_RE.sub(' ', token)
            token = re.sub(r'[\s,]+', ' ', token).strip(' -,')
            if not token or re.fullmatch(r'[\d\s-]+', token):
                continue
            if token.lower() not in [c.lower() for c in cities]:
                cities.append(token)
    return cities


def _strip_country(location):
    """Drop country/postcode fragments and collapse repeated tokens.

    ORC ``PrimaryLocation`` is ``"<city>, <state>, <country>"``, so a Shanghai job
    reads ``"Shanghai, Shanghai, China"``; the official city token is kept once.
    """
    text = COUNTRY_TOKEN_RE.sub(' ', str(location or ''))
    unique = []
    for token in (t.strip(' -,') for t in re.split(r'[，,、;；|/]', text)):
        if token and token.lower() not in [u.lower() for u in unique]:
            unique.append(token)
    return ', '.join(unique)


def _is_china(requisition):
    country = str(requisition.get('PrimaryLocationCountry') or '').upper()
    if country:
        return country == 'CN'
    return bool(_city_parts(requisition.get('PrimaryLocation')))


# ---------------------------------------------------------------- budget / http
def _budget_limit(max_requests):
    if max_requests is not None:
        return int(max_requests)
    raw = os.environ.get('QIUZHAO_PLATFORM_REQUEST_BUDGET')
    return int(raw) if raw and raw.strip() else DEFAULT_REQUEST_BUDGET


def _has_budget(budget):
    return budget is None or budget['limit'] is None or budget['used'] < budget['limit']


def _spend(budget):
    if budget is None:
        return
    if budget['limit'] is not None and budget['used'] >= budget['limit']:
        raise BudgetExhausted('per-tenant request budget reached')
    budget['used'] += 1


def _make_session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    session.headers['User-Agent'] = UA
    session.headers['Accept'] = 'application/json'
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=0)))
    return session


# Politeness interval between outbound requests. Production leaves it at 0 (the
# daily chain already spaces companies); the read-only verification runs set
# QIUZHAO_PLATFORM_REQUEST_INTERVAL=2 to guarantee >=2s between every call.
REQUEST_INTERVAL = float(os.environ.get('QIUZHAO_PLATFORM_REQUEST_INTERVAL') or 0)
_LAST_REQUEST = [0.0]


def _pace():
    if REQUEST_INTERVAL <= 0:
        return
    wait = REQUEST_INTERVAL - (time.monotonic() - _LAST_REQUEST[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST[0] = time.monotonic()


def _send(budget, session, url):
    import requests
    _pace()
    _spend(budget)
    try:
        response = session.get(url, timeout=(10, 60))
    except requests.RequestException:
        time.sleep(2.0)
        _spend(budget)
        response = session.get(url, timeout=(10, 60))
    if getattr(response, 'status_code', 200) in (429, 403):
        time.sleep(2.0)
        _spend(budget)
        response = session.get(url, timeout=(10, 60))
    response.raise_for_status()
    return response


def _json(session, budget, url, output_dir, name):
    response = _send(budget, session, url)
    payload = response.json()
    (output_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return payload


# ---------------------------------------------------------------- ORC calls
def china_geography_id(session, host, site, budget, output_dir):
    """Site-specific China geography id (official ``recruitingHierarchyLocations``)."""
    finder = (f'findBySiteNumberAndWord;SiteNumber={site},'
              f'FilterAttributes=GeographyFlatName,SearchTerms=China,StartsWithFlag=true')
    url = (f'https://{host}/hcmRestApi/resources/latest/recruitingHierarchyLocations'
           f'?onlyData=true&finder={finder}&limit=1000000')
    payload = _json(session, budget, url, output_dir, 'hierarchy-china.json')
    for item in payload.get('items') or []:
        if item.get('GeographyLevel') == 1 and str(item.get('GeographyFlatName')) == 'China':
            return item.get('GeographyId')
    return None


def list_page(session, host, site, china_id, offset, limit, budget, output_dir):
    finder = (f'findReqs;siteNumber={site},selectedLocationsFacet={china_id},'
              f'limit={limit},offset={offset},sortBy=POSTING_DATES_DESC')
    url = (f'https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions'
           f'?onlyData=true&expand=requisitionList.secondaryLocations&finder={finder}')
    payload = _json(session, budget, url, output_dir, f'list-offset{offset}.json')
    item = (payload.get('items') or [{}])[0]
    return item.get('requisitionList') or [], item.get('TotalJobsCount')


def detail_batch(session, host, site, ids, budget, output_dir, index):
    finder = 'ById;Id=' + ' or '.join(str(i) for i in ids) + f',siteNumber={site}'
    url = (f'https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails'
           f'?expand=all&onlyData=true&finder={finder}&limit=500')
    payload = _json(session, budget, url, output_dir, f'detail-batch-{index}.json')
    return {str(item.get('Id')): item for item in payload.get('items') or []}


# ---------------------------------------------------------------- mapping
def _date(value):
    text = str(value or '').strip()
    match = re.match(r'(\d{4}-\d{2}-\d{2})', text)
    return match.group(1) if match else ''


def _description(detail, requisition):
    """Official ORC description text; short description is the documented fallback."""
    parts = []
    for field in ('ExternalDescriptionStr', 'ExternalResponsibilitiesStr',
                  'ExternalQualificationsStr'):
        value = _html.unescape(str(detail.get(field) or '')).strip()
        if value:
            parts.append(value)
    if not parts:
        short = _html.unescape(str(requisition.get('ShortDescriptionStr')
                                   or detail.get('ShortDescriptionStr') or '')).strip()
        if short:
            parts.append(short)
    return '\n'.join(parts)


def _job(name, scope, key, requisition, detail, host, site):
    ident = str(requisition.get('Id') or detail.get('Id'))
    url = (f'https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{ident}')
    title = str(detail.get('Title') or requisition.get('Title') or '')
    location = str(requisition.get('PrimaryLocation') or detail.get('PrimaryLocation') or '')
    secondary = requisition.get('secondaryLocations') or detail.get('secondaryLocations') or []
    extra_locations = [str(x.get('Name') or '') for x in secondary if isinstance(x, dict)]
    raw = {field: requisition.get(field) for field in
           ('Id', 'Title', 'PostedDate', 'PostingEndDate', 'PrimaryLocation',
            'PrimaryLocationCountry', 'RequisitionType', 'WorkerType', 'JobFamily',
            'Category', 'StudyLevel', 'WorkplaceType', 'JobSchedule', 'Organization')}
    raw.update({field: detail.get(field) for field in
                ('RequisitionType', 'WorkerType', 'JobFamily', 'Category', 'StudyLevel',
                 'WorkplaceType', 'JobSchedule', 'Organization', 'LegalEmployer',
                 'BusinessUnit') if detail.get(field)})
    job = shared.job(name, scope, ident, title, url, _description(detail, requisition),
                     ' / '.join(x for x in [location, *extra_locations] if x), raw)
    city_tokens = _city_parts(location, *extra_locations)
    job['cities_source_raw'] = list(city_tokens)
    job['cities'] = list(city_tokens)
    job['cities_normalized'] = list(city_tokens)
    job['location'] = _strip_country(location) or location
    official_labels = {field: (detail.get(field) or requisition.get(field))
                       for field in ('RequisitionType', 'WorkerType', 'JobFamily',
                                     'StudyLevel', 'Category')}
    job['scope_evidence'] = (
        f'Official Oracle Recruiting Cloud site={site}; official title="{title}"; '
        f'official labels={json.dumps(official_labels, ensure_ascii=False)}; '
        f'classification={scope} (intern before campus before social)')
    job['recruitment_type_raw'] = official_labels
    published = _date(requisition.get('PostedDate') or detail.get('PostedDate'))
    job['published_at'] = published
    job['publication_date'] = published
    job['source_publication_field'] = 'PostedDate' if published else ''
    deadline = _date(requisition.get('PostingEndDate') or detail.get('PostingEndDate'))
    job['deadline_raw'] = deadline
    if deadline:
        job['deadline'] = deadline
        job['deadline_type'] = 'explicit'
    job['cohort_raw'] = ''  # ORC exposes no cohort (届别) field -- never inferred
    job['source_url'] = url
    return job


def collect(company, scope, output_dir, max_requests=None):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    name = COMPANIES[key]
    host, site = host_and_site(key)
    page_size = page_size_for(key)
    batch_size = detail_batch_for(key)
    max_pages = max_list_pages_for(key)
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    base_url = f'https://{host}/hcmUI/CandidateExperience/en/sites/{site}/jobs'
    coverage = shared.coverage(base_url)
    coverage['source_url'] = base_url
    jobs = []
    observed = []
    raw_by_id = {}
    seen = set()
    list_complete = False
    session = _make_session()
    try:
        china_id = china_geography_id(session, host, site, budget, output_dir)
        coverage['china_geography_id'] = china_id
        if not china_id:
            coverage['note'] = (f'Official ORC site {site} publishes no country-level '
                                f'"China" geography; nothing collected.')
            raise _NoChina()
        offset = 0
        pages = 0
        while pages < max_pages:
            rows, total = list_page(session, host, site, china_id, offset, page_size,
                                    budget, output_dir)
            coverage['pages_scanned'] += 1
            pages += 1
            if total is not None:
                coverage['site_total_china'] = int(total)
            if not rows:
                list_complete = True
                coverage['last_page_evidence'] = f'offset={offset};rows=0;total={total}'
                break
            for row in rows:
                ident = str(row.get('Id'))
                if ident in seen:
                    continue
                seen.add(ident)
                raw_by_id[ident] = row
                observed.append({'id': ident, 'title': row.get('Title'),
                                 'location': row.get('PrimaryLocation'),
                                 'country': row.get('PrimaryLocationCountry'),
                                 'scope': _scope_of(row.get('Title'), key, row)})
            offset += page_size
            if coverage.get('site_total_china') is not None and offset >= coverage['site_total_china']:
                list_complete = True
                coverage['last_page_evidence'] = f'offset={offset};total={total}'
                break
            if not _has_budget(budget):
                break
        coverage['list_observed_ids'] = sorted(seen)
        coverage['list_observed_titles'] = sorted({o['title'] for o in observed if o['title']})
        selected = [o for o in observed if o['scope'] == scope]
        coverage['scope_selected'] = len(selected)
        detail_map = {}
        for index in range(0, len(selected), batch_size):
            if not _has_budget(budget):
                coverage['request_budget_exhausted'] = True
                break
            chunk = [o['id'] for o in selected[index:index + batch_size]]
            try:
                detail_map.update(detail_batch(session, host, site, chunk, budget,
                                               output_dir, index // batch_size))
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                break
            except Exception as error:  # noqa: BLE001
                coverage.setdefault('detail_fetch_errors', []).append(
                    f'ids={chunk[:3]}...: {type(error).__name__}: {error}'[:300])
        filtered_country = 0
        missing_detail = 0
        for ident in [o['id'] for o in selected]:
            requisition = raw_by_id[ident]
            detail = detail_map.get(ident) or {}
            if not detail:
                missing_detail += 1
                coverage.setdefault('detail_fetch_errors', []).append(
                    'No official ORC detail returned for requisition ' + ident)
                continue
            if not _is_china(requisition) and not _is_china(detail):
                filtered_country += 1
                continue
            description = _description(detail, requisition)
            if not description:
                missing_detail += 1
                coverage.setdefault('detail_fetch_errors', []).append(
                    'Empty official ORC description for requisition ' + ident)
                continue
            row = dict(requisition)
            row.update({k: v for k, v in detail.items() if v not in (None, '')})
            jobs.append(_job(name, scope, key, row, detail, host, site))
            if len(jobs) % 100 == 0:
                shared.partial_checkpoint(jobs, coverage, name, scope, output_dir)
        coverage['location_filtered_count'] = filtered_country
        coverage['expected_total'] = max(len(selected) - filtered_country, 0)
        coverage['pagination_exhausted'] = list_complete
        coverage['detail_complete'] = (not coverage['errors']
                                       and not coverage.get('detail_fetch_errors')
                                       and len(jobs) == coverage['expected_total'])
        coverage['evidence'] = sorted(p.name for p in output_dir.glob('*.json'))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (
            f'Official Oracle Recruiting Cloud site={site}; '
            f'selectedLocationsFacet={china_id} (China); requested={scope}; '
            f'Campus/Graduate/Early Careers/Intern official labels -> campus/intern, '
            f'everything else -> social.')
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': base_url,
                                     'params': {'siteNumber': site,
                                                'selectedLocationsFacet': china_id,
                                                'limit': page_size, 'offset': 0,
                                                'sortBy': 'POSTING_DATES_DESC'}}
    except _NoChina:
        pass
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
    except Exception as error:  # noqa: BLE001
        coverage['errors'].append(f'{type(error).__name__}: {error}')
    coverage['request_budget'] = budget
    result = shared.finish(jobs, coverage)
    if coverage.get('request_budget_exhausted'):
        result['coverage'].update(complete=False, detail_complete=False)
        if result['coverage']['status'] == 'success':
            result['coverage']['status'] = 'partial'
    if not result['jobs']:
        result['coverage']['status'] = 'blocked'
        result['coverage']['complete'] = False
        result['coverage'].setdefault(
            'note', f'No official Oracle Recruiting Cloud job matched scope={scope} '
                    f'for country=China on site {site}.')
    return result


class _NoChina(RuntimeError):
    """Official ORC site exposes no China geography (a clean, expected outcome)."""


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('company')
    parser.add_argument('--scope', choices=list(shared.TYPES), default='campus')
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--max-requests', type=int)
    args = parser.parse_args()
    payload = collect(args.company, args.scope, args.output_dir, max_requests=args.max_requests)
    print(json.dumps({'company': args.company, 'scope': args.scope,
                      'coverage': payload['coverage']}, ensure_ascii=False))
