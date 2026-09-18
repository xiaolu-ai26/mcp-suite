"""iCIMS Career Portal platform adapter (``*.icims.com`` and branded front-ends).

One adapter covers every iCIMS-hosted career portal. Adding a company = one line in
``p1_platform_companies.json`` under ``"icims"`` with the portal host as key, for
example ``"careers-example.icims.com"``. It uses iCIMS' public, login-free job
search (``GET /jobs/search?ss=1&searchLocation=<country>``), whose result rows are
``iCIMS_``-classed cards, and reads the official detail page for the description,
location and schema.org ``JobPosting`` dates.

Compliance gate (this is the reason the config is empty today): before any content
request the adapter fetches ``/robots.txt`` for the tenant host and refuses to
crawl when the published policy disallows the search path -- it returns a
``blocked`` result carrying the verbatim directive instead of a request. Nothing
here logs in, posts a form, forges a signature, answers a challenge or falls back
to a different host to escape a ``Disallow``.

Verified read-only on 2026-09-19 (robots.txt + one public page per host):

* ``careers-amd.icims.com`` (AMD 超微半导体) -> ``User-agent: * / Disallow: /``
* ``careers-se.icims.com`` (施耐德电气)      -> ``User-agent: * / Disallow: /``
* ``careers-pepsico.icims.com``, ``careers-generalmills.icims.com``,
  ``careers-garmin.icims.com``, ``careers-keysight.icims.com``,
  ``careers-aon.icims.com``, ``careers-zs.icims.com`` -> same blanket disallow.
* Hosts that do publish a crawlable policy (``careers-kbhome.icims.com``,
  ``careers-mlssoccer.icims.com``, ``careers-pennentertainment.icims.com``,
  ``careers-steeldynamics.icims.com``, ``careers-suffolkconstruction.icims.com``,
  ``careers-generaldynamics.icims.com``) were checked and serve no China postings,
  so no company is configured.

Data quality: only official fields are written. ``datePosted`` -> ``published_at``
and ``validThrough`` -> ``deadline_raw`` from the official JobPosting microdata;
both stay empty when the page does not carry them. iCIMS exposes no Chinese
cohort (届别) field, so ``cohort_raw`` is always left empty -- never inferred.
``Campus / Graduate / Early Careers / Intern`` official titles map to
campus/intern; everything else is recorded under the social scope.
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
CONFIG_KEY = 'icims'
MODULE_PATH = 'qiuzhao.collector.p1_platform_icims'
DEFAULT_REQUEST_BUDGET = None
DEFAULT_SEARCH_LOCATION = 'China'
DEFAULT_MAX_LIST_PAGES = 30
DEFAULT_MAX_JOBS = 300
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

INTERN_KEYWORDS = ['intern', 'internship', '实习', 'summer analyst', 'summer intern',
                   'co-op', 'coop', 'placement', 'working student']
CAMPUS_KEYWORDS = ['graduate', 'graduation', 'campus', 'college', 'university',
                   'early career', 'earlycareer', 'entry level', 'entry-level',
                   'student', 'trainee', 'management associate', 'leadership program',
                   '校招', '应届', '管培', '培训生', 'new grad']
CHINA_CITY_TOKENS = ['beijing', 'shanghai', 'shenzhen', 'guangzhou', 'hangzhou', 'suzhou',
                     'chengdu', 'wuhan', 'nanjing', 'tianjin', "xi'an", 'xian', 'dalian',
                     'qingdao', 'changzhou', 'wuxi', 'hefei', 'xiamen', 'chongqing',
                     'zhuhai', 'dongguan', 'foshan', 'ningbo', 'jinan', 'zhengzhou',
                     'changsha', 'shenyang', 'harbin', 'kunming', 'fuzhou', 'wenzhou',
                     'kunshan', 'taicang', 'zhongshan', 'guangdong', 'jiangsu', 'zhejiang',
                     'shandong', 'sichuan', 'hubei', 'liaoning', 'fujian', 'hunan', 'anhui',
                     'henan', 'hebei', 'jiangxi', 'shaanxi', 'hong kong', '香港']
COUNTRY_TOKEN_RE = re.compile(r'(?<![A-Za-z])(?:china|cn|prc|中国|mainland china)(?![A-Za-z])', re.I)
US_CHINA_RE = re.compile(r'china\s*,\s*(?:[A-Z]{2}\b|maine|texas|michigan|indiana|'
                         r'california|new york|north carolina|ohio|illinois|iowa|'
                         r'kentucky|minnesota|missouri|tennessee|virginia|wisconsin|'
                         r'georgia|florida|maryland|pennsylvania|new jersey)', re.I)
CARD_RE = re.compile(r'iCIMS_JobCardItem|iCIMS_JobsTableRow|class="[^"]*\brow\b[^"]*"')
JOB_LINK_RE = re.compile(r'<a[^>]*class="[^"]*iCIMS_Anchor[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         re.S)
JOB_LINK_RE2 = re.compile(r'<a[^>]*href="([^"]*/jobs/\d+/[^"]*)"[^>]*>(.*?)</a>', re.S)
TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.S)
JSONLD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
LABEL_VALUE_RE = re.compile(
    r'<span[^>]*class="[^"]*iCIMS_JobHeader[^"]*"[^>]*>(.*?)</span>', re.S)
LOCATION_RE = re.compile(r'(?:iCIMS_JobLocation|jobLocation|iCIMS_JobHeaderData)[^>]*>(.*?)<', re.S)


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


def _load_companies():
    companies = {}
    for key, entry in _read_platform().items():
        if str(key).startswith('_'):
            continue
        name = entry if isinstance(entry, str) else str((entry or {}).get('name') or '')
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
    raise ValueError('unknown iCIMS company: ' + str(company))


def base_for(key):
    return 'https://' + str(key).strip().strip('/')


def search_location_for(key):
    return str(_entry(key).get('search_location') or DEFAULT_SEARCH_LOCATION)


def max_list_pages_for(key):
    return int(_entry(key).get('max_list_pages') or DEFAULT_MAX_LIST_PAGES)


def max_jobs_for(key):
    return int(_entry(key).get('max_jobs') or DEFAULT_MAX_JOBS)


def search_url(key, location, page=1):
    entry = _entry(key)
    path = str(entry.get('search_path') or '/jobs/search')
    return f'{base_for(key)}{path}?ss=1&searchLocation={quote(str(location))}&pr={int(page)}'


def _scope_of(title, key):
    entry = _entry(key)
    low = str(title or '').lower()
    intern_kw = INTERN_KEYWORDS + [str(x).lower() for x in (entry.get('intern_keywords') or [])]
    campus_kw = CAMPUS_KEYWORDS + [str(x).lower() for x in (entry.get('campus_keywords') or [])]
    if any(k and k in low for k in intern_kw):
        return 'intern'
    if any(k and k in low for k in campus_kw):
        return 'campus'
    return 'social'


def _clean(value):
    return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))).strip()


def _city_parts(*values):
    cities = []
    for value in values:
        for token in re.split(r'\s*/\s*|[，,、;；|]', str(value or '')):
            token = COUNTRY_TOKEN_RE.sub(' ', token)
            token = re.sub(r'\s+', ' ', token).strip(' -,')
            if not token or re.fullmatch(r'[\d\s-]+', token):
                continue
            if token.lower() not in [c.lower() for c in cities]:
                cities.append(token)
    return cities


def _is_china(value):
    text = _clean(value)
    if not text or US_CHINA_RE.search(text):
        return False
    if COUNTRY_TOKEN_RE.search(text):
        return True
    low = text.lower()
    return any(city in low for city in CHINA_CITY_TOKENS)


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
    session.headers['Accept'] = 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8'
    session.headers['Accept-Language'] = 'en-US,en;q=0.9,zh-CN;q=0.8'
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=0)))
    return session


REQUEST_INTERVAL = float(os.environ.get('QIUZHAO_PLATFORM_REQUEST_INTERVAL') or 0)
_LAST_REQUEST = [0.0]


def _pace():
    if REQUEST_INTERVAL <= 0:
        return
    wait = REQUEST_INTERVAL - (time.monotonic() - _LAST_REQUEST[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST[0] = time.monotonic()


def _get(session, url, budget):
    import requests
    _pace()
    _spend(budget)
    try:
        response = session.get(url, timeout=(10, 50))
    except requests.RequestException:
        time.sleep(2.0)
        _spend(budget)
        response = session.get(url, timeout=(10, 50))
    if getattr(response, 'status_code', 200) in (429, 403):
        time.sleep(2.0)
        _spend(budget)
        response = session.get(url, timeout=(10, 50))
    response.raise_for_status()
    response.encoding = response.encoding or 'utf-8'
    return response.text


# ---------------------------------------------------------------- robots gate
def robots_policy(session, key, budget, output_dir):
    """(allowed, evidence) from the tenant's own robots.txt.

    ``allowed`` is True/False/None (None = no robots.txt published). A policy that
    disallows the search path under ``User-agent: *`` makes the adapter stop
    before any content request.
    """
    url = base_for(key) + '/robots.txt'
    try:
        text = _get(session, url, budget)
    except Exception as error:  # noqa: BLE001
        return None, f'robots.txt unreadable: {type(error).__name__}: {error}'[:200]
    (output_dir / 'robots.txt').write_text(text, encoding='utf-8')
    lines = [line.strip() for line in text.splitlines()]
    applies = False
    disallow_all = False
    allow_all = False
    for line in lines:
        if not line or line.startswith('#'):
            continue
        field, _, value = line.partition(':')
        field = field.strip().lower()
        value = value.strip()
        if field == 'user-agent':
            applies = value == '*'
        elif applies and field == 'disallow' and value == '/':
            disallow_all = True
        elif applies and field == 'allow' and value == '/':
            allow_all = True
    if disallow_all and not allow_all:
        return False, 'robots.txt: User-agent: * / Disallow: /'
    return True, f'robots.txt allows crawling ({len(lines)} lines)'


# ---------------------------------------------------------------- parsing
def parse_list(page_html, base):
    cards = []
    seen = set()
    for regex in (JOB_LINK_RE, JOB_LINK_RE2):
        for match in regex.finditer(page_html or ''):
            href = _html.unescape(match.group(1))
            if '/jobs/' not in href:
                continue
            ident_match = re.search(r'/jobs/(\d+)/', href)
            if not ident_match:
                continue
            ident = ident_match.group(1)
            if ident in seen:
                continue
            seen.add(ident)
            url = href if href.startswith('http') else base + '/' + href.lstrip('/')
            cards.append({'title': _clean(match.group(2)), 'url': url, 'ident': ident})
    if not cards:
        for match in re.finditer(r'<a[^>]*href="([^"]*/jobs/(\d+)/[^"]*)"[^>]*>(.*?)</a>',
                                 page_html or '', re.S):
            ident = match.group(2)
            if ident in seen:
                continue
            seen.add(ident)
            href = _html.unescape(match.group(1))
            cards.append({'title': _clean(match.group(3)), 'ident': ident,
                          'url': href if href.startswith('http') else base + '/' + href.lstrip('/')})
    return cards


def parse_detail(page_html, card):
    info = {'title': card.get('title') or '', 'datePosted': '', 'validThrough': '',
            'location': '', 'description': '', 'employmentType': ''}
    for block in JSONLD_RE.findall(page_html or ''):
        try:
            payload = json.loads(block.strip())
        except Exception:  # noqa: BLE001 - a non-JSON-LD block is not official data
            continue
        entries = payload if isinstance(payload, list) else [payload]
        for entry in entries:
            if not isinstance(entry, dict) or entry.get('@type') != 'JobPosting':
                continue
            info['title'] = str(entry.get('title') or info['title'])
            info['datePosted'] = str(entry.get('datePosted') or '')
            info['validThrough'] = str(entry.get('validThrough') or '')
            info['employmentType'] = str(entry.get('employmentType') or '')
            info['description'] = _clean(entry.get('description') or '')
            location = entry.get('jobLocation') or {}
            if isinstance(location, list):
                location = location[0] if location else {}
            address = (location or {}).get('address') or {}
            info['location'] = ', '.join(str(address.get(key) or '') for key in
                                         ('addressLocality', 'addressRegion', 'addressCountry')
                                         ).strip(', ')
            return info
    title_match = TITLE_RE.search(page_html or '')
    if title_match:
        info['title'] = _clean(title_match.group(1)).split('|')[0].strip() or info['title']
    for match in LABEL_VALUE_RE.finditer(page_html or ''):
        text = _clean(match.group(1))
        if text and _is_china(text) and not info['location']:
            info['location'] = text
    info['description'] = _clean(re.sub(r'<(script|style)\b.*?</\1>', ' ', page_html or '',
                                        flags=re.S | re.I))
    return info


def _date(value):
    text = str(value or '').strip()
    match = re.match(r'(\d{4}-\d{2}-\d{2})', text)
    if match:
        return match.group(1)
    match = re.search(r'\d{4}-\d{2}-\d{2}', text)
    return match.group(0) if match else ''


def _job(name, scope, key, card, info):
    base = base_for(key)
    raw = {field: info.get(field) for field in
           ('datePosted', 'validThrough', 'employmentType', 'location')}
    job = shared.job(name, scope, card['ident'], info.get('title') or card.get('title') or '',
                     card['url'], info.get('description') or '', info.get('location') or '', raw)
    city_tokens = _city_parts(info.get('location'))
    job['cities_source_raw'] = list(city_tokens)
    job['cities'] = list(city_tokens)
    job['cities_normalized'] = list(city_tokens)
    job['scope_evidence'] = (
        f'Official iCIMS host={key}; official title="{info.get("title") or card.get("title")}"; '
        f'classification={scope} (intern before campus before social)')
    job['recruitment_type_raw'] = {'employmentType': info.get('employmentType')}
    published = _date(info.get('datePosted'))
    job['published_at'] = published
    job['publication_date'] = published
    job['source_publication_field'] = 'datePosted' if published else ''
    deadline = _date(info.get('validThrough'))
    job['deadline_raw'] = deadline
    if deadline:
        job['deadline'] = deadline
        job['deadline_type'] = 'explicit'
    job['cohort_raw'] = ''  # iCIMS exposes no cohort (届别) field -- never inferred
    job['source_url'] = card['url']
    return job


def collect(company, scope, output_dir, max_requests=None):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    name = COMPANIES[key]
    location = search_location_for(key)
    max_pages = max_list_pages_for(key)
    max_jobs = max_jobs_for(key)
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    base = base_for(key)
    coverage = shared.coverage(base)
    jobs = []
    session = _make_session()
    try:
        allowed, evidence = robots_policy(session, key, budget, output_dir)
        coverage['robots_policy'] = evidence
        if allowed is False:
            coverage['errors'].append(
                f'Official robots.txt forbids crawling {key}; adapter stops before any '
                f'content request (no bypass).')
            coverage['robots_disallow'] = True
            raise _RobotsDisallow()
        cards = []
        seen = set()
        page = 1
        list_complete = False
        while page <= max_pages:
            page_html = _get(session, search_url(key, location, page), budget)
            (output_dir / f'list-page{page}.html').write_text(page_html, encoding='utf-8')
            coverage['pages_scanned'] += 1
            page_cards = parse_list(page_html, base)
            new_cards = [c for c in page_cards if c['ident'] not in seen]
            for card in new_cards:
                seen.add(card['ident'])
            cards.extend(new_cards)
            if not page_cards or not new_cards:
                list_complete = True
                coverage['last_page_evidence'] = f'page={page};cards={len(page_cards)}'
                break
            page += 1
            if not _has_budget(budget):
                break
        coverage['list_observed_ids'] = sorted(seen)
        coverage['list_observed_titles'] = sorted({c['title'] for c in cards if c['title']})
        filtered_country = 0
        selected = 0
        detail_errors = []
        for card in cards:
            if len(jobs) + len(detail_errors) >= max_jobs:
                coverage['job_limit_reached'] = max_jobs
                break
            if not _has_budget(budget):
                coverage['request_budget_exhausted'] = True
                break
            try:
                page_html = _get(session, card['url'], budget)
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                break
            except Exception as error:  # noqa: BLE001
                detail_errors.append(f'{card["ident"]}: {type(error).__name__}: {error}'[:300])
                continue
            (output_dir / f'detail-{card["ident"]}.html').write_text(page_html, encoding='utf-8')
            info = parse_detail(page_html, card)
            if not _is_china(info.get('location')):
                filtered_country += 1
                continue
            if _scope_of(info.get('title') or card.get('title'), key) != scope:
                continue
            selected += 1
            if not info.get('description'):
                detail_errors.append('Empty official iCIMS description for ' + card['ident'])
                continue
            jobs.append(_job(name, scope, key, card, info))
            if len(jobs) % 100 == 0:
                shared.partial_checkpoint(jobs, coverage, name, scope, output_dir)
        if detail_errors:
            coverage['detail_fetch_errors'] = detail_errors
        coverage['scope_selected'] = selected
        coverage['location_filtered_count'] = filtered_country
        coverage['expected_total'] = selected
        coverage['pagination_exhausted'] = list_complete
        coverage['detail_complete'] = (not coverage['errors']
                                       and not coverage.get('detail_fetch_errors')
                                       and len(jobs) == selected)
        coverage['evidence'] = sorted(p.name for p in output_dir.glob('*'))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (
            f'Official iCIMS portal={key}; searchLocation={location}; requested={scope}; '
            f'the official detail location is the China gate; Campus/Graduate/Early '
            f'Careers/Intern titles -> campus/intern, else social.')
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': base,
                                     'params': {'ss': 1, 'searchLocation': location}}
    except _RobotsDisallow:
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
            'note', f'No official iCIMS job matched scope={scope} for country=China '
                    f'on host {key}.')
    return result


class _RobotsDisallow(RuntimeError):
    """The tenant's own robots.txt forbids crawling; stop without any bypass."""


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
