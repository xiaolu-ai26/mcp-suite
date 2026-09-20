"""Platform-level Workday (myworkdayjobs.com CXS) campus/intern/social adapter.

One adapter covers every Workday tenant. Adding a company = one line in
``p1_platform_companies.json`` under ``"workday"`` with key
``<tenant>/<region>/<site>`` (for example ``nvidia/wd5/NVIDIAExternalCareerSite``).
It calls the public Workday CXS endpoint

    POST https://<tenant>.<region>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs

which reports ``userAuthenticated:false`` and needs neither login nor signature
(curl-verified in the 2026-09-18 data-source survey). The external contract is
identical to ``p1_sources_*``: ``COMPANIES`` + ``collect(company, scope,
output_dir)`` returning ``{'jobs': [...], 'coverage': {...}}`` and writing the
same kind of evidence files (``list-<offset>.json`` / ``detail-<id>.json``).

Request budget: ``QIUZHAO_PLATFORM_REQUEST_BUDGET`` (or the ``max_requests``
argument) caps network calls per tenant per run. Production defaults to no cap
(``DEFAULT_REQUEST_BUDGET = None``); the read-only verification runs set 20 only
to stay polite, which truncates a large tenant and yields ``partial``.

Data quality: only official Workday fields are written. ``startDate`` ->
``published_at``; ``endDate`` -> ``deadline`` (left empty when absent). Workday
has no Chinese cohort (届别) field, so ``cohort_raw`` is always left empty --
nothing is inferred. ``Early Careers / Campus / Graduate`` titles map to
``campus`` and ``Intern / Internship`` titles map to ``intern`` from the official
posting title; every job records the exact official title as ``scope_evidence``.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
MODULE_PATH = 'qiuzhao.collector.p1_platform_workday'
# Production default: no cap. Budgeting is an opt-in politeness guard used by the
# read-only verification runs (which pass 20). A low default would truncate a
# healthy tenant: NVIDIA's China slice alone has 200+ postings.
DEFAULT_REQUEST_BUDGET = None
DEFAULT_SEARCH_TEXT = 'China'
DEFAULT_COUNTRY = 'China'
DEFAULT_MAX_LIST_PAGES = 20
PAGE_SIZE = 20
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

# Intern before campus: a "Graduate Intern" is an internship, not a graduate role.
INTERN_KEYWORDS = ['intern', 'internship', '实习', 'summer analyst', 'summer intern',
                   'co-op', 'coop', 'placement', 'ixp']
CAMPUS_KEYWORDS = ['graduate', 'graduation', 'campus', 'college', 'early career',
                   'earlycareer', 'entry-level', 'entry level', 'university',
                   'new college graduate', 'trainee', 'management associate',
                   'leadership program', 'leadership development', '校招', '应届',
                   '管培', '培训生', '新星', 'star program', 'academy']
# Mainland China city names used only as a cheap list-page pre-filter; the
# authoritative country check happens on the official detail payload.
CHINA_CITIES = ['beijing', 'shanghai', 'shenzhen', 'guangzhou', 'hangzhou', 'suzhou',
                'chengdu', 'wuhan', 'nanjing', 'tianjin', "xi'an", 'xian', 'dalian',
                'qingdao', 'changzhou', 'wuxi', 'hefei', 'xiamen', 'chongqing',
                'zhuhai', 'dongguan', 'foshan', 'ningbo', 'jinan', 'zhengzhou',
                'changsha', 'shenyang', 'harbin', 'kunming', 'fuzhou', 'wenzhou',
                'shaoxing', 'jiaxing', 'nantong', 'yangzhou', 'zibo', 'weifang',
                'huizhou', 'zhongshan', 'langfang', 'baoding', 'taiyuan', 'lanzhou']
LOCATION_COUNT_RE = re.compile(r'\b\d+\s+locations?\b', re.I)
# Tokens that are a country/region/postal code, not a city. Workday reports
# locations like "Shanghai, China"; the city is the official non-country token.
COUNTRY_STOPWORDS = {'china', 'cn', 'prc', 'p.r. china', 'p.r.china',
                     '中国', "people's republic of china"}


class BudgetExhausted(RuntimeError):
    pass


# ---------------------------------------------------------------- config
def _read_platform():
    data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return data.get('workday') or {}


def _entry_name(entry):
    return entry if isinstance(entry, str) else str((entry or {}).get('name') or '')


def _load_companies():
    """Enabled tenants only.

    ``"enabled": false`` keeps a surveyed tenant in the config (so the next
    person sees the tenant/site id and why it is off) without registering the
    company in ``p1_pipeline.REGISTRY`` for the daily run. Same contract as
    ``p1_platform_tupu360``. 惠普 / 应用材料 / 飞利浦 are parked this way because
    the Eightfold / Phenom adapters read strictly more China postings from the
    same employers' current careers platforms (measured 2026-09-19).
    """
    companies = {}
    for key, entry in _read_platform().items():
        if isinstance(entry, dict) and entry.get('enabled') is False:
            continue
        name = _entry_name(entry)
        if name:
            companies[str(key)] = name
    return companies


COMPANIES = _load_companies()
NAME_TO_SLUG = {name: key for key, name in COMPANIES.items()}


def reload_config():
    """Re-read the shared JSON config (tests point CONFIG_PATH at a fixture)."""
    global COMPANIES, NAME_TO_SLUG
    COMPANIES = _load_companies()
    NAME_TO_SLUG = {name: key for key, name in COMPANIES.items()}
    return COMPANIES


def merged_registry():
    """Company name -> adapter module path for the pipeline REGISTRY."""
    return {name: MODULE_PATH for name in COMPANIES.values()}


def resolve(company):
    if company in COMPANIES:
        return company
    if company in NAME_TO_SLUG:
        return NAME_TO_SLUG[company]
    raise ValueError('unknown workday company: ' + str(company))


def _entry(key):
    entry = _read_platform().get(key) or {}
    return entry if isinstance(entry, dict) else {}


def host_for(key):
    entry = _entry(key)
    if entry.get('host'):
        return str(entry['host']).rstrip('/')
    tenant, region, _site = key.split('/')
    return f'https://{tenant}.{region}.myworkdayjobs.com'


def search_text_for(key, scope):
    value = _entry(key).get('search_text')
    if isinstance(value, dict):
        return str(value.get(scope) or value.get('default') or DEFAULT_SEARCH_TEXT)
    return str(value or DEFAULT_SEARCH_TEXT)


def max_list_pages_for(key):
    return int(_entry(key).get('max_list_pages') or DEFAULT_MAX_LIST_PAGES)


def country_for(key):
    return str(_entry(key).get('country') or DEFAULT_COUNTRY)


def _scope_of(title, key):
    low = str(title or '').lower()
    entry = _entry(key)
    intern_kw = INTERN_KEYWORDS + [str(x).lower() for x in (entry.get('intern_keywords') or [])]
    campus_kw = CAMPUS_KEYWORDS + [str(x).lower() for x in (entry.get('campus_keywords') or [])]
    if any(k and k in low for k in intern_kw):
        return 'intern'
    if any(k and k in low for k in campus_kw):
        return 'campus'
    return 'social'


def _location_candidate(locations_text, country):
    text = str(locations_text or '')
    if not text.strip():
        return True
    low = text.lower()
    if country.lower() in low:
        return True
    if any(city in low for city in CHINA_CITIES):
        return True
    return bool(LOCATION_COUNT_RE.search(text))  # ambiguous: confirm on detail


def _city_parts(*location_values):
    """Official city tokens only: drop country/region and postal-code fragments.

    Workday ``location`` is e.g. ``"Shanghai, China"``. The city is the official
    token; the trailing country is not a city. Nothing is translated or inferred --
    a payload with no city token yields an empty list.
    """
    cities = []
    for value in location_values:
        for token in re.split(r'\s*/\s*|[，,、;；]', str(value or '')):
            token = token.strip()
            if not token or token.lower() in COUNTRY_STOPWORDS:
                continue
            if re.fullmatch(r'[\d\s-]+', token):  # postal code fragment
                continue
            if token not in cities:
                cities.append(token)
    return cities


def _country_ok(info, country):
    raw = info.get('country')
    descriptor = raw.get('descriptor') if isinstance(raw, dict) else raw
    if descriptor:
        return country.lower() in str(descriptor).lower()
    location = str(info.get('location') or '')
    low = location.lower()
    return country.lower() in low or any(city in low for city in CHINA_CITIES)


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


def _send(budget, call, *args, **kwargs):
    """One polite retry (429/WAF/connection), then give up and let the caller block."""
    import requests
    _pace()
    _spend(budget)
    try:
        response = call(*args, **kwargs)
    except requests.RequestException:
        time.sleep(2.0)
        _spend(budget)
        response = call(*args, **kwargs)
    if getattr(response, 'status_code', 200) in (429, 403):
        time.sleep(2.0)
        _spend(budget)
        response = call(*args, **kwargs)
    response.raise_for_status()
    return response


def _list_page(session, tenant, region, site, query, offset, facets, budget, output_dir):
    url = f'https://{tenant}.{region}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs'
    body = {'appliedFacets': facets or {}, 'limit': PAGE_SIZE, 'offset': offset,
            'searchText': query}
    response = _send(budget, session.post, url, json=body, timeout=(10, 45),
                     headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
    payload = response.json()
    (output_dir / f'list-{offset}.json').write_text(json.dumps(payload, ensure_ascii=False))
    return payload


def _detail(session, tenant, region, site, external_path, budget, output_dir):
    url = f'https://{tenant}.{region}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{external_path}'
    response = _send(budget, session.get, url, timeout=(10, 45),
                     headers={'Accept': 'application/json'})
    payload = response.json()
    info = payload.get('jobPostingInfo') or {}
    if info.get('id'):
        (output_dir / f'detail-{info["id"]}.json').write_text(
            json.dumps(payload, ensure_ascii=False))
    return info


def _date(value):
    text = str(value or '').strip()
    match = re.match(r'(\d{4}-\d{2}-\d{2})', text)
    return match.group(1) if match else ''


def _job(name, scope, info, posting, host, site, key, query):
    ident = str(info.get('id') or posting.get('externalPath') or '')
    external_path = posting.get('externalPath') or ''
    url = info.get('externalUrl') or (host + '/' + site + external_path)
    locations = [x for x in [info.get('location')] + list(info.get('additionalLocations') or []) if x]
    location = ' / '.join(str(x) for x in locations)
    title = info.get('title') or posting.get('title') or ''
    description = shared.text(info.get('jobDescription'))
    job = shared.job(name, scope, ident, title, url, description, location, info)
    city_tokens = _city_parts(*locations)
    job['cities_source_raw'] = list(city_tokens)
    job['cities'] = list(city_tokens)
    job['cities_normalized'] = list(city_tokens)
    job['scope_evidence'] = (f'Official Workday CXS tenant={key}; searchText="{query}"; '
                             f'official title="{posting.get("title") or title}"; '
                             f'classification={scope}')
    job['recruitment_type_raw'] = {
        'postedOn': info.get('postedOn') or posting.get('postedOn'),
        'timeType': info.get('timeType'),
        'country': (info.get('country') or {}).get('descriptor')
        if isinstance(info.get('country'), dict) else info.get('country'),
        'jobReqId': info.get('jobReqId'),
    }
    published = _date(info.get('startDate'))
    job['published_at'] = published
    job['publication_date'] = published
    job['source_publication_field'] = 'startDate' if published else ''
    deadline = _date(info.get('endDate'))
    job['deadline_raw'] = deadline
    if deadline:
        job['deadline'] = deadline
        job['deadline_type'] = 'explicit'
    job['cohort_raw'] = ''  # Workday is a global ATS with no cohort field
    job['source_url'] = url
    return job


def collect(company, scope, output_dir, max_requests=None):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    name = COMPANIES[key]
    tenant, region, site = key.split('/')
    host = host_for(key)
    query = search_text_for(key, scope)
    country = country_for(key)
    max_pages = max_list_pages_for(key)
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(host)
    coverage['source_url'] = host
    jobs = []
    observed = []
    selected = []
    seen = set()
    list_complete = False
    total = None
    session = _make_session()
    try:
        offset = 0
        pages = 0
        while pages < max_pages:
            payload = _list_page(session, tenant, region, site, query, offset, {}, budget, output_dir)
            coverage['pages_scanned'] += 1
            pages += 1
            rows = payload.get('jobPostings') or []
            if total is None:
                total = payload.get('total')
            if not rows:
                list_complete = True
                coverage['last_page_evidence'] = (f'offset={offset};rows=0;'
                                                  f'prior_total={total};total={payload.get("total")}')
                break
            for posting in rows:
                external_path = posting.get('externalPath')
                if not external_path or external_path in seen:
                    continue
                seen.add(external_path)
                observed.append({'externalPath': external_path, 'title': posting.get('title'),
                                 'locationsText': posting.get('locationsText')})
                if (_scope_of(posting.get('title'), key) == scope
                        and _location_candidate(posting.get('locationsText'), country)):
                    selected.append(posting)
            offset += PAGE_SIZE
            # Only a *positive* site total can end the scan: a total of 0 next to real
            # rows is the site contradicting itself, and treating it as the end would
            # report an exhausted listing after one page. The empty-page path below is
            # the other (and only other) terminator.
            if total and offset >= int(total):
                list_complete = True
                coverage['last_page_evidence'] = (f'offset={offset};reached_total={total};'
                                                  f'scanned={len(seen)}')
                break
            if not _has_budget(budget):
                break
        coverage['list_total'] = total
        coverage['list_observed_ids'] = sorted({o['externalPath'] for o in observed})
        coverage['list_observed_titles'] = sorted({o['title'] for o in observed if o['title']})
        filtered_country = 0
        for posting in selected:
            if not _has_budget(budget):
                coverage['request_budget_exhausted'] = True
                break
            try:
                info = _detail(session, tenant, region, site, posting['externalPath'], budget, output_dir)
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                break
            except Exception as error:  # noqa: BLE001 - record and keep the rest
                coverage.setdefault('detail_fetch_errors', []).append(
                    f'{posting.get("externalPath")}: {type(error).__name__}: {error}'[:300])
                continue
            if not info or not shared.text(info.get('jobDescription')):
                coverage.setdefault('detail_fetch_errors', []).append(
                    'No official Workday description for ' + str(posting.get('externalPath')))
                continue
            if not _country_ok(info, country):
                filtered_country += 1
                continue
            jobs.append(_job(name, scope, info, posting, host, site, key, query))
            if len(jobs) % 100 == 0:
                shared.partial_checkpoint(jobs, coverage, name, scope, output_dir)
        coverage['expected_total'] = max(len(selected) - filtered_country, 0)
        coverage['location_filtered_count'] = filtered_country
        coverage['pagination_exhausted'] = list_complete
        coverage['detail_complete'] = (not coverage['errors']
                                       and not coverage.get('detail_fetch_errors')
                                       and len(jobs) == coverage['expected_total'])
        coverage['evidence'] = (sorted(p.name for p in output_dir.glob('list-*.json'))
                                + sorted(p.name for p in output_dir.glob('detail-*.json')))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (
            f'Official Workday CXS tenant={key}; searchText="{query}"; requested={scope}; '
            f'title-keyword mapping (intern before campus).')
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': host,
                                     'params': {'tenant': tenant, 'region': region, 'site': site,
                                                'searchText': query, 'limit': PAGE_SIZE,
                                                'offset': 0, 'country': country}}
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
    except Exception as error:  # noqa: BLE001 - never let a source corrupt the pipeline
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
            'note', f'No official Workday job matched scope={scope} and country={country}.')
    return result


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
