"""Platform-level SAP SuccessFactors Career Site Builder adapter.

One adapter covers every SuccessFactors CSB tenant. Adding a company = one line in
``p1_platform_companies.json`` under ``"successfactors"`` with the career-site host
as key (for example ``"jobs.sap.com"``). It uses the same public, login-free pages
that a browser sees:

* list: ``https://<host>/search/?q=&locationsearch=<country>&startrow=<n>``
  (server-rendered ``<tr class="data-row">`` cards, ``jobTitle-link`` anchors);
* detail: ``https://<host>/job/<slug>/<id>/`` carrying schema.org JobPosting
  microdata (``datePosted``/``title``/``description``/``jobLocation``/``validThrough``).

Verified read-only on 2026-09-18 against jobs.sap.com, jobs.zf.com,
jobs.boehringer-ingelheim.com, careers.akzonobel.com and
careers.bureauveritas.com. No login, cookie or signature is required. The external
contract matches ``p1_sources_*``.

Data quality: only official microdata is written. ``datePosted`` -> ``published_at``;
``validThrough`` -> ``deadline`` (left empty when absent). There is no Chinese
cohort (届别) field, so ``cohort_raw`` is always left empty -- nothing is inferred.
``Early Careers / Campus / Graduate`` titles map to ``campus`` and
``Intern / Internship`` titles map to ``intern`` from the official posting title.
"""
from __future__ import annotations
import html as _html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
MODULE_PATH = 'qiuzhao.collector.p1_platform_successfactors'
DEFAULT_REQUEST_BUDGET = None
DEFAULT_COUNTRY = 'China'
DEFAULT_MAX_LIST_PAGES = 20
DEFAULT_PAGE_SIZE = 25
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

INTERN_KEYWORDS = ['intern', 'internship', '实习', 'summer analyst', 'summer intern',
                   'co-op', 'coop', 'placement', 'ixp']
CAMPUS_KEYWORDS = ['graduate', 'graduation', 'campus', 'college', 'early career',
                   'earlycareer', 'entry-level', 'entry level', 'university',
                   'new college graduate', 'trainee', 'management associate',
                   'leadership program', 'leadership development', '校招', '应届',
                   '管培', '培训生', '新星', 'star program', 'academy']
CHINA_CITIES = ['beijing', 'shanghai', 'shenzhen', 'guangzhou', 'hangzhou', 'suzhou',
                'chengdu', 'wuhan', 'nanjing', 'tianjin', "xi'an", 'xian', 'dalian',
                'qingdao', 'changzhou', 'wuxi', 'hefei', 'xiamen', 'chongqing',
                'zhuhai', 'dongguan', 'foshan', 'ningbo', 'jinan', 'zhengzhou',
                'changsha', 'shenyang', 'harbin', 'kunming', 'fuzhou', 'wenzhou',
                'kunshan', 'taicang', 'zhanjiang', 'huizhou', 'zhongshan']

# CSB themes differ: title links carry the class as one of possibly several
# (``class="jobTitle-link fontcolora880bb1b"``), and href may precede or follow it.
TITLE_LINK_RE = re.compile(
    r'<a[^>]*class="[^"]*jobTitle-link[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
TITLE_LINK_RE2 = re.compile(
    r'<a[^>]*href="([^"]+)"[^>]*class="[^"]*jobTitle-link[^"]*"[^>]*>(.*?)</a>', re.S)
JOB_LINK_RE = re.compile(r'<a[^>]*href="([^"]*(?:/job/)[^"]+)"[^>]*>(.*?)</a>', re.S)
LOCATION_RE = re.compile(r'class="jobLocation[^"]*"[^>]*>(.*?)</span>', re.S)
LOCATION_ITEMPROP_RE = re.compile(r'itemprop="jobLocation"[^>]*>(.*?)</span>', re.S)
DATA_ROW_RE = re.compile(r'<tr[^>]*class="[^"]*data-row', re.I)
# Some themes (e.g. Boehringer Ingelheim) render tiles as
# ``<div class="row job job-row">`` instead of ``<tr class="data-row">``.
JOB_ROW_RE = re.compile(r'class="[^"]*\bjob-row\b[^"]*"', re.I)
# Countries/regions (and the fragments SuccessFactors mixes into streetAddress,
# e.g. "Shanghai China, CN, 200000"). Only the official city token is kept.
LOCATION_COUNTRY_RE = re.compile(r'(?<![A-Za-z])(?:china|cn|prc|中国)(?![A-Za-z])', re.I)


class BudgetExhausted(RuntimeError):
    pass


# ---------------------------------------------------------------- config
def _read_platform():
    data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return data.get('successfactors') or {}


def _entry_name(entry):
    return entry if isinstance(entry, str) else str((entry or {}).get('name') or '')


def _load_companies():
    companies = {}
    for key, entry in _read_platform().items():
        if isinstance(entry, dict) and entry.get('enabled') is False:
            continue  # parked survey line: kept on file, never registered
        name = _entry_name(entry)
        if name:
            companies[str(key)] = name
    return companies


COMPANIES = _load_companies()
NAME_TO_SLUG = {name: key for key, name in COMPANIES.items()}


def reload_config():
    global COMPANIES, NAME_TO_SLUG
    COMPANIES = _load_companies()
    NAME_TO_SLUG = {name: key for key, name in COMPANIES.items()}
    return COMPANIES


def merged_registry():
    return {name: MODULE_PATH for name in COMPANIES.values()}


def resolve(company):
    if company in COMPANIES:
        return company
    if company in NAME_TO_SLUG:
        return NAME_TO_SLUG[company]
    raise ValueError('unknown successfactors company: ' + str(company))


def _entry(key):
    entry = _read_platform().get(key) or {}
    return entry if isinstance(entry, dict) else {}


def base_for(key):
    return 'https://' + key.strip().strip('/')


def query_for(key):
    return str(_entry(key).get('query') or '')


def country_for(key):
    return str(_entry(key).get('country') or DEFAULT_COUNTRY)


def page_size_for(key):
    return int(_entry(key).get('page_size') or DEFAULT_PAGE_SIZE)


def max_list_pages_for(key):
    return int(_entry(key).get('max_list_pages') or DEFAULT_MAX_LIST_PAGES)


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


def _city_parts(*location_values):
    """Official city tokens only: strip the country/region/postal fragments.

    SuccessFactors ``streetAddress`` is e.g. ``"Shanghai China, CN, 200000"``.
    The city (``Shanghai``) is official; the country and postal code are not
    cities. Nothing is translated or inferred -- no city token yields [].
    """
    cities = []
    for value in location_values:
        for token in re.split(r'\s*/\s*|[，,、;；]', str(value or '')):
            token = LOCATION_COUNTRY_RE.sub(' ', token)
            token = re.sub(r'[\s,]+', ' ', token).strip(' ,')
            if not token or re.fullmatch(r'[\d\s-]+', token):  # postal code fragment
                continue
            if token not in cities:
                cities.append(token)
    return cities


def _location_candidate(location, country):
    text = str(location or '')
    if not text.strip():
        return True
    low = text.lower()
    if country.lower() in low:
        return True
    return any(city in low for city in CHINA_CITIES)


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


def _list_page(session, base, query, country, startrow, budget, output_dir):
    url = (f'{base}/search/?q={quote(query)}&locationsearch={quote(country)}'
           f'&startrow={startrow}')
    response = _send(budget, session.get, url, timeout=(10, 45))
    response.encoding = 'utf-8'
    (output_dir / f'list-{startrow}.html').write_text(response.text, encoding='utf-8')
    return response.text


def _detail(session, base, href, ident, budget, output_dir):
    url = base + '/' + href.lstrip('/')
    response = _send(budget, session.get, url, timeout=(10, 45))
    response.encoding = 'utf-8'
    (output_dir / f'detail-{ident}.html').write_text(response.text, encoding='utf-8')
    return response.text


UNIFY_PATH = '/services/recruiting/v1/jobs'
UNIFY_LOCALE = 'en_US'


def _unify_page(session, base, country, page_number, budget, output_dir, locale=None):
    """Public ``POST /services/recruiting/v1/jobs`` page used by newer CSB themes.

    Contract read from the site's own ``j2w.searchManager`` bundle: the browser
    posts ``{keywords, locale, location, pageNumber, sortBy}`` and renders
    ``jobSearchResult[].response``. No login, cookie or signature is involved.
    """
    body = {'keywords': '', 'locale': locale or UNIFY_LOCALE, 'location': country,
            'pageNumber': int(page_number), 'sortBy': 'recent'}
    response = _send(budget, session.post, base + UNIFY_PATH, json=body, timeout=(10, 45),
                     headers={'Accept': 'application/json',
                              'Content-Type': 'application/json'})
    payload = response.json()
    (output_dir / f'unify-{page_number}.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    rows = [item.get('response') or {} for item in payload.get('jobSearchResult') or []]
    return rows, payload.get('totalJobs')


def _unify_card(row):
    """Official unify row -> the same card shape the classic list parser produces.

    The detail link is the one the page's own renderer builds:
    ``/job/<unifiedStandardTitle>/<id>-<locale>``.
    """
    ident = str(row.get('id') or '').strip()
    if not ident:
        return None
    title = str(row.get('unifiedStandardTitle') or row.get('urlTitle') or '').strip()
    locations = row.get('jobLocationShort') or []
    if isinstance(locations, str):
        locations = [locations]
    return {'href': f'/job/{quote(title or "untitled")}/{ident}-{UNIFY_LOCALE}',
            'title': title, 'location': str(locations[0]).strip() if locations else ''}


# ---------------------------------------------------------------- parsing
def _parse_list(page_html):
    """Return (unique cards, raw row count). Cards keep the official href.

    Row markup is theme-dependent. Most CSB sites use ``<tr class="data-row">``;
    some (Boehringer Ingelheim) use ``<div class="row job job-row">``. When no
    data-row exists we split on the title anchors themselves and use the number of
    parsed cards as the pagination count, so a valid tenant is never silently read
    as an empty list.
    """
    if DATA_ROW_RE.search(page_html):
        chunks = re.split(r'(?=<tr[^>]*class="[^"]*data-row)', page_html)[1:]
    elif JOB_ROW_RE.search(page_html):
        chunks = re.split(r'(?=<div[^>]*class="[^"]*job-row)', page_html)[1:]
    else:
        chunks = re.split(r'(?=<a[^>]*jobTitle-link)', page_html)[1:]
    cards = []
    seen = set()
    for chunk in chunks:
        match = TITLE_LINK_RE.search(chunk) or TITLE_LINK_RE2.search(chunk) or JOB_LINK_RE.search(chunk)
        if not match:
            continue
        href = _html.unescape(match.group(1))
        if href in seen:
            continue
        seen.add(href)
        title = shared.text(match.group(2))
        loc_match = LOCATION_RE.search(chunk) or LOCATION_ITEMPROP_RE.search(chunk)
        location = shared.text(loc_match.group(1)) if loc_match else ''
        cards.append({'href': href, 'title': title, 'location': location})
    raw_rows = len(DATA_ROW_RE.findall(page_html)) or len(cards)
    return cards, raw_rows


def _meta(page_html, prop):
    for tag in re.findall(r'<meta[^>]*>', page_html):
        if f'itemprop="{prop}"' in tag:
            content = re.search(r'content="([^"]*)"', tag)
            return _html.unescape(content.group(1)) if content else ''
    return ''


def _element_html(page_html, marker):
    """Inner HTML of the element carrying ``marker`` (tag-balance aware)."""
    index = page_html.find(marker)
    if index < 0:
        return ''
    start = page_html.rfind('<', 0, index)
    if start < 0:
        return ''
    tag_match = re.match(r'<([a-zA-Z0-9]+)', page_html[start:start + 24])
    if not tag_match:
        return ''
    tag = tag_match.group(1).lower()
    open_end = page_html.find('>', index)
    if open_end < 0:
        return ''
    open_re = re.compile(r'<' + tag + r'\b', re.I)
    close_re = re.compile(r'</' + tag + r'\s*>', re.I)
    depth = 1
    position = open_end + 1
    while depth > 0:
        nxt_open = open_re.search(page_html, position)
        nxt_close = close_re.search(page_html, position)
        if not nxt_close:
            return page_html[open_end + 1:]
        if nxt_open and nxt_open.start() < nxt_close.start():
            depth += 1
            position = nxt_open.end()
        else:
            depth -= 1
            if depth == 0:
                return page_html[open_end + 1:nxt_close.start()]
            position = nxt_close.end()
    return page_html[open_end + 1:]


def _parse_detail(page_html, fallback_title=''):
    return {
        'title': shared.text(_element_html(page_html, 'itemprop="title"')) or fallback_title,
        'description': shared.text(_element_html(page_html, 'itemprop="description"')),
        'datePosted': _meta(page_html, 'datePosted'),
        'validThrough': _meta(page_html, 'validThrough'),
        'location': _meta(page_html, 'streetAddress'),
        'organization': _meta(page_html, 'hiringOrganization'),
        'employmentType': _element_html(page_html, 'itemprop="employmentType"'),
    }


def _ident_from_href(href):
    parts = [p for p in str(href).split('/') if p]
    for part in reversed(parts):
        if part.isdigit():
            return part
        # Newer "unify" themes end the detail path with ``<id>-<locale>``.
        leading = re.match(r'^(\d+)-[A-Za-z]{2}_[A-Za-z]{2}$', part)
        if leading:
            return leading.group(1)
    return parts[-1] if parts else str(href)


def _date(value):
    text = str(value or '').strip()
    if not text:
        return ''
    match = re.match(r'(\d{4}-\d{2}-\d{2})', text)
    if match:
        return match.group(1)
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except Exception:  # noqa: BLE001 - unparseable official date stays empty
        return ''


def _job(name, scope, detail, card, base, key, country):
    ident = _ident_from_href(card['href'])
    url = base + '/' + card['href'].lstrip('/')
    title = detail.get('title') or card.get('title') or ''
    raw = {'datePosted': detail.get('datePosted'), 'validThrough': detail.get('validThrough'),
           'organization': detail.get('organization'), 'employmentType': detail.get('employmentType')}
    job = shared.job(name, scope, ident, title, url, detail.get('description') or '',
                     detail.get('location') or card.get('location') or '', raw)
    city_tokens = _city_parts(detail.get('location'), card.get('location'))
    job['cities_source_raw'] = list(city_tokens)
    job['cities'] = list(city_tokens)
    job['cities_normalized'] = list(city_tokens)
    job['scope_evidence'] = (f'Official SuccessFactors CSB host={key}; '
                             f'official title="{card.get("title") or title}"; classification={scope}')
    job['recruitment_type_raw'] = {'hiringOrganization': detail.get('organization'),
                                   'datePosted': detail.get('datePosted'),
                                   'validThrough': detail.get('validThrough')}
    published = _date(detail.get('datePosted'))
    job['published_at'] = published
    job['publication_date'] = published
    job['source_publication_field'] = 'datePosted' if published else ''
    deadline = _date(detail.get('validThrough'))
    job['deadline_raw'] = deadline
    if deadline:
        job['deadline'] = deadline
        job['deadline_type'] = 'explicit'
    job['cohort_raw'] = ''  # no cohort field in SuccessFactors
    job['source_url'] = url
    return job


def collect(company, scope, output_dir, max_requests=None):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    name = COMPANIES[key]
    base = base_for(key)
    query = query_for(key)
    country = country_for(key)
    page_size = page_size_for(key)
    max_pages = max_list_pages_for(key)
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(base)
    coverage['source_url'] = base
    jobs = []
    observed = []
    selected = []
    seen = set()
    list_complete = False
    session = _make_session()
    try:
        startrow = 0
        pages = 0
        classic_empty = False
        while pages < max_pages:
            page_html = _list_page(session, base, query, country, startrow, budget, output_dir)
            coverage['pages_scanned'] += 1
            pages += 1
            cards, raw_rows = _parse_list(page_html)
            if not cards and raw_rows == 0:
                classic_empty = pages == 1
                list_complete = True
                coverage['last_page_evidence'] = f'startrow={startrow};rows=0'
                break
            for card in cards:
                if card['href'] in seen:
                    continue
                seen.add(card['href'])
                observed.append({'href': card['href'], 'title': card['title'],
                                 'location': card['location']})
                if (_scope_of(card['title'], key) == scope
                        and _location_candidate(card['location'], country)):
                    selected.append(card)
            if raw_rows < page_size:
                list_complete = True
                coverage['last_page_evidence'] = (f'startrow={startrow};rows={raw_rows};'
                                                  f'page_size={page_size}')
                break
            startrow += page_size
            if not _has_budget(budget):
                break
        if classic_empty:
            # Newer "unify" CSB themes (BASF, Standard Chartered, Morgan Stanley) render
            # the result rows client-side and keep the server-rendered HTML empty. The
            # same page then loads its postings from the public, login-free JSON endpoint
            # ``POST /services/recruiting/v1/jobs``; that official contract is used as a
            # strict fallback so classic themes (SAP/ZF/Boehringer) keep their behaviour.
            coverage['list_endpoint'] = 'services/recruiting/v1/jobs'
            page_number = 0
            unify_total = None
            while page_number < max_pages:
                rows, unify_total = _unify_page(session, base, country, page_number,
                                                budget, output_dir)
                if not rows:
                    list_complete = True
                    coverage['last_page_evidence'] = f'unify page={page_number};rows=0'
                    break
                for row in rows:
                    card = _unify_card(row)
                    if not card or card['href'] in seen:
                        continue
                    seen.add(card['href'])
                    observed.append({'href': card['href'], 'title': card['title'],
                                     'location': card['location']})
                    if (_scope_of(card['title'], key) == scope
                            and _location_candidate(card['location'], country)):
                        selected.append(card)
                if unify_total is not None and len(seen) >= int(unify_total):
                    list_complete = True
                    coverage['last_page_evidence'] = (f'unify page={page_number};'
                                                      f"total={unify_total}")
                    break
                page_number += 1
                if not _has_budget(budget):
                    break
            coverage['expected_total_unify'] = unify_total
        coverage['list_observed_ids'] = sorted({o['href'] for o in observed})
        coverage['list_observed_titles'] = sorted({o['title'] for o in observed if o['title']})
        filtered_country = 0
        for card in selected:
            if not _has_budget(budget):
                coverage['request_budget_exhausted'] = True
                break
            ident = _ident_from_href(card['href'])
            try:
                page_html = _detail(session, base, card['href'], ident, budget, output_dir)
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                break
            except Exception as error:  # noqa: BLE001
                coverage.setdefault('detail_fetch_errors', []).append(
                    f'{card["href"]}: {type(error).__name__}: {error}'[:300])
                continue
            detail = _parse_detail(page_html, card.get('title'))
            if not detail.get('description'):
                coverage.setdefault('detail_fetch_errors', []).append(
                    'No official SuccessFactors description for ' + card['href'])
                continue
            if not _location_candidate(detail.get('location') or card.get('location'), country):
                filtered_country += 1
                continue
            jobs.append(_job(name, scope, detail, card, base, key, country))
            if len(jobs) % 100 == 0:
                shared.partial_checkpoint(jobs, coverage, name, scope, output_dir)
        coverage['expected_total'] = max(len(selected) - filtered_country, 0)
        coverage['location_filtered_count'] = filtered_country
        coverage['pagination_exhausted'] = list_complete
        coverage['detail_complete'] = (not coverage['errors']
                                       and not coverage.get('detail_fetch_errors')
                                       and len(jobs) == coverage['expected_total'])
        coverage['evidence'] = (sorted(p.name for p in output_dir.glob('list-*.html'))
                                + sorted(p.name for p in output_dir.glob('detail-*.html')))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (
            f'Official SuccessFactors CSB host={key}; locationsearch={country}; requested={scope}; '
            f'JobPosting microdata mapping (intern before campus).')
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': base,
                                     'params': {'q': query, 'locationsearch': country,
                                                'startrow': 0, 'page_size': page_size}}
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
            'note', f'No official SuccessFactors job matched scope={scope} and country={country}.')
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
