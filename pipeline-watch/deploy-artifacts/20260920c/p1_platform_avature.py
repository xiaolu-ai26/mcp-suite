"""Avature platform adapter (``*.avature.net`` and the custom domains Avature powers).

One adapter covers every Avature portal that publishes a server-rendered job
search. Adding a company = one line in ``p1_platform_companies.json`` under
``"avature"`` with ``<host>/<locale>/<portal>`` as key, for example
``"mycareer.hsbc.com/en_GB/external"``. Avature is a highly configurable
recruiting CRM, so every deployment looks different; this adapter only relies on
the two structures every Avature portal shares -- the search-results page and the
``article__content__view__field`` detail blocks -- and tolerates the theme
differences (``JobDetail`` vs ``PipelineDetail``, labelled vs unlabelled fields,
description inside ``tf_replaceFieldVideoTokens`` or a plain content block).

Verified read-only on 2026-09-19 against:

* HSBC ``mycareer.hsbc.com/en_GB/external`` (``avature.portal.id`` 88; robots.txt
  allows ``/en_GB/external``);
* Siemens ``jobs.siemens.com/en_US/externaljobs`` (portal 144; robots allows
  ``/externaljobs``; ``?search=China`` returns 215 official postings);
* L'Oreal ``careers.loreal.com/en_US/jobs`` (portal 170);
* Electronic Arts ``jobs.ea.com/en_US/careers`` (portal 4).

Nothing here logs in, posts a form, forges a signature or answers a challenge: it
is the same public ``GET`` the browser makes, with ``?search=<keyword>`` used as
the narrowest built-in filter (Avature's country facet ids are per-portal and
POST-only, so the official keyword search is used instead and the per-job
location on the official detail page is the final gate).

Data quality: only fields the official page carries are written. ``Opening date``
/ ``Posted since`` -> ``published_at``; ``Closing date`` -> ``deadline_raw``
(left empty when absent). Avature exposes no Chinese cohort (届别) field, so
``cohort_raw`` stays empty -- never inferred. The official ``Experience level``
and title labels (``Graduate``/``Intern``/``Early Careers``/``Campus``) map to
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
CONFIG_KEY = 'avature'
MODULE_PATH = 'qiuzhao.collector.p1_platform_avature'
DEFAULT_REQUEST_BUDGET = None
DEFAULT_SEARCH_KEYWORD = 'China'
DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_LIST_PAGES = 60
DEFAULT_MAX_JOBS = 400            # bound on per-run detail fetches
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

INTERN_KEYWORDS = ['intern', 'internship', '实习', 'summer analyst', 'summer intern',
                   'placement', 'working student', 'co-op', 'coop', 'trainee']
CAMPUS_KEYWORDS = ['graduate', 'graduation', 'campus', 'college', 'university',
                   'early career', 'earlycareer', 'entry level', 'entry-level',
                   'student', 'apprentice', 'management associate', 'leadership program',
                   '校招', '应届', '管培', '培训生', 'new grad', 'recent graduate']
COUNTRY_TOKEN_RE = re.compile(r'(?<![A-Za-z])(?:china|cn|prc|中国)(?![A-Za-z])', re.I)
# "China, ME" / "China, Texas" are US towns, not the country.
US_CHINA_RE = re.compile(
    r'china\s*,\s*(?:[A-Z]{2}\b|maine|texas|michigan|indiana|arkansas|alabama|'
    r'california|new york|north carolina|south carolina|missouri|ohio|illinois|iowa|'
    r'kentucky|minnesota|mississippi|nebraska|oklahoma|oregon|tennessee|virginia|'
    r'wisconsin|georgia|florida|maryland|delaware|kansas|nevada|utah|wyoming|idaho|'
    r'montana|arizona|colorado|new mexico|west virginia|pennsylvania|new jersey|'
    r'massachusetts|connecticut|vermont|new hampshire|rhode island|south dakota|'
    r'north dakota|louisiana|alaska|hawaii)', re.I)
CHINA_CITY_TOKENS = ['beijing', 'shanghai', 'shenzhen', 'guangzhou', 'hangzhou', 'suzhou',
                     'chengdu', 'wuhan', 'nanjing', 'tianjin', "xi'an", 'xian', 'dalian',
                     'qingdao', 'changzhou', 'wuxi', 'hefei', 'xiamen', 'chongqing',
                     'zhuhai', 'dongguan', 'foshan', 'ningbo', 'jinan', 'zhengzhou',
                     'changsha', 'shenyang', 'harbin', 'kunming', 'fuzhou', 'wenzhou',
                     'kunshan', 'taicang', 'zhanjiang', 'huizhou', 'zhongshan',
                     'guangdong', 'jiangsu', 'zhejiang', 'shandong', 'sichuan', 'hubei',
                     'liaoning', 'fujian', 'hunan', 'anhui', 'henan', 'hebei', 'jiangxi',
                     'shaanxi', 'hong kong', '香港', '北京', '上海', '深圳', '广州']
TITLE_RE = re.compile(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
CARD_SPLIT_RE = re.compile(r'(?=<article[^>]*class="[^"]*article--result)')
DETAIL_BLOCK_RE = re.compile(r'(?=<article class="article article--details)')
FIELD_RE = re.compile(r'<div class="article__content__view__field\b(.*?)(?=<div class="article__content__view__field\b|</article>)', re.S)
# Themes differ: Siemens/HSBC put the class alone in its attribute and close with
# their own <div>, L'Oreal appends extra classes and wraps the value in a <span>
# ("class=\"article__content__view__field__value column__item__value\""). Both are
# accepted so a value-only theme still yields the official location tokens.
LABEL_RE = re.compile(r'__field__label[^>]*>(.*?)(?:</span>|</div>)', re.S)
VALUE_RE = re.compile(r'__field__value[^>]*>(.*?)(?:</span>|</div>)', re.S)
LOCATION_SPAN_RE = re.compile(r'<span class="location">\s*(.*?)\s*</span>', re.S)
LEGEND_RE = re.compile(r'list-controls__text__legend[^>]*>(.*?)</div>', re.S)
DETAIL_HREF_RE = re.compile(r'/(?:JobDetail|PipelineDetail|FolderDetail)/[^"\'?#]*?/(\d+)')
DATE_FORMATS = ('%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d %b %Y', '%b %d, %Y')
POSTED_LABELS = ('posted since', 'posted date', 'opening date', 'date posted', 'posted',
                 'publication date', 'start date')
DEADLINE_LABELS = ('closing date', 'close date', 'deadline', 'end date', 'expiry date',
                   'expires', 'application deadline')
LOCATION_LABELS = ('location', 'locations', 'location(s)', 'work location', 'city',
                   'primary location')
LABEL_FIELDS = ('experience level', 'job type', 'worker type', 'employment type',
                'contract type', 'career level')


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
        if str(key).startswith('_'):  # config documentation keys, not tenants
            continue
        if isinstance(entry, dict) and entry.get('enabled') is False:
            continue  # parked survey line: kept on file, never registered
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
    raise ValueError('unknown Avature company: ' + str(company))


def parts_for(key):
    """``<host>/<locale>/<portal>`` -> (host, locale, portal)."""
    parts = [p for p in str(key).strip().strip('/').split('/') if p]
    if len(parts) < 3:
        raise ValueError('Avature config key must be <host>/<locale>/<portal>: ' + str(key))
    return parts[0], parts[1], '/'.join(parts[2:])


def search_keyword_for(key):
    """Portal search keyword; an explicit empty string means "list everything"."""
    entry = _entry(key)
    value = entry.get('search')
    if value is None:
        return DEFAULT_SEARCH_KEYWORD
    return str(value).strip()


def page_size_for(key):
    return int(_entry(key).get('page_size') or DEFAULT_PAGE_SIZE)


def max_list_pages_for(key):
    return int(_entry(key).get('max_list_pages') or DEFAULT_MAX_LIST_PAGES)


def max_jobs_for(key):
    return int(_entry(key).get('max_jobs') or DEFAULT_MAX_JOBS)


def search_url(key, keyword, offset, page_size):
    """Official search-results URL.

    Avature portals differ in the pagination parameter name (HSBC's pipeline list
    uses ``pipelineOffset``/``pipelineRecordsPerPage``, everything else uses
    ``jobOffset``/``jobRecordsPerPage``), so both names are config-overridable.
    An empty ``search`` keyword means "list everything the portal publishes".
    """
    host, locale, portal = parts_for(key)
    entry = _entry(key)
    offset_param = str(entry.get('offset_param') or 'jobOffset')
    size_param = str(entry.get('page_size_param') or 'jobRecordsPerPage')
    query = f'{offset_param}={int(offset)}&{size_param}={int(page_size)}'
    if str(keyword or '').strip():
        query = f'search={quote(str(keyword))}&' + query
    return f'https://{host}/{locale}/{portal}/SearchJobs/?{query}'


def _scope_of(title, fields, key):
    entry = _entry(key)
    low = str(title or '').lower()
    intern_kw = INTERN_KEYWORDS + [str(x).lower() for x in (entry.get('intern_keywords') or [])]
    campus_kw = CAMPUS_KEYWORDS + [str(x).lower() for x in (entry.get('campus_keywords') or [])]
    labels = ' '.join(str(fields.get(name) or '') for name in LABEL_FIELDS).lower()
    if any(k and (k in low or k in labels) for k in intern_kw):
        return 'intern'
    if any(k and (k in low or k in labels) for k in campus_kw):
        return 'campus'
    return 'social'


def _clean(value):
    text = _html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))
    return re.sub(r'\s+', ' ', text).strip()


def _block_text(block_html):
    text = re.sub(r'<(script|style)\b.*?</\1>', ' ', block_html, flags=re.S | re.I)
    return _clean(text)


def _parse_date(value):
    text = _clean(value)
    if not text:
        return ''
    iso = re.match(r'(\d{4}-\d{2}-\d{2})', text)
    if iso:
        return iso.group(1)
    match = re.search(r'\d{1,2}[-/ ]\w{3}[-/ ]\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{4}|'
                      r'\w{3,9} \d{1,2}, \d{4}', text)
    candidate = match.group(0) if match else text
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    return ''


def _is_china_location(value):
    text = _clean(value)
    if not text:
        return False
    if US_CHINA_RE.search(text):
        return False
    if COUNTRY_TOKEN_RE.search(text):
        return True
    low = text.lower()
    return any(city in low for city in CHINA_CITY_TOKENS)


def _country_only_location(value):
    """A location value that names China without naming a city ("China", "中国")."""
    text = _clean(value)
    return bool(text) and not US_CHINA_RE.search(text) and bool(
        re.fullmatch(r'(?:china|cn|prc|中国|mainland china)[\s,]*', text, re.I))


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


def _slug(key):
    return re.sub(r'[^A-Za-z0-9]+', '-', str(key)).strip('-').lower()


def _detail_cache_dir(output_dir):
    """Per-run, per-company page cache shared by the campus/intern/social runs.

    The pipeline runs one process per scope with ``runs/<date>/<ordinal>/<scope>``,
    so the cache one level up is reused across the three scopes of one company and
    the same official page is never downloaded three times.
    """
    cache = output_dir.parent / 'avature-page-cache'
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def cached_page(session, url, cache_name, budget, output_dir, key='', force=False):
    """Official page text, cached for the whole company run (all three scopes)."""
    cache_dir = _detail_cache_dir(output_dir)
    name = (f'{_slug(key)}-{cache_name}' if key else cache_name)
    cached = cache_dir / name
    if not force and cached.exists() and cached.stat().st_size > 0:
        page = cached.read_text(encoding='utf-8')
        (output_dir / cache_name).write_text(page, encoding='utf-8')
        return page
    page = _get(session, url, budget)
    (output_dir / cache_name).write_text(page, encoding='utf-8')
    cached.write_text(page, encoding='utf-8')
    return page


def fetch_detail(session, url, ident, budget, output_dir, key=''):
    cache_dir = _detail_cache_dir(output_dir)
    name = (f'{_slug(key)}-detail-{ident}.html' if key else f'{ident}.html')
    cached = cache_dir / name
    if cached.exists() and cached.stat().st_size > 0:
        page = cached.read_text(encoding='utf-8')
        (output_dir / f'detail-{ident}.html').write_text(page, encoding='utf-8')
        return page
    page = _get(session, url, budget)
    (output_dir / f'detail-{ident}.html').write_text(page, encoding='utf-8')
    cached.write_text(page, encoding='utf-8')
    return page


# ---------------------------------------------------------------- parsing
def _ident_from_href(href):
    match = DETAIL_HREF_RE.search(str(href or ''))
    if match:
        return match.group(1)
    parts = [p for p in str(href or '').split('/') if p]
    return parts[-1] if parts else str(href)


def parse_list(page_html):
    """[(title, href, ident, card_location)] from one official search-results page."""
    cards = []
    seen = set()
    for block in CARD_SPLIT_RE.split(page_html or '')[1:]:
        title_match = TITLE_RE.search(block)
        if not title_match:
            continue
        href = _html.unescape(title_match.group(1))
        ident = _ident_from_href(href)
        if not ident.isdigit():
            # Official job detail URLs always end in the numeric posting id; a
            # non-numeric target is a navigation card (e.g. "Join our Talent
            # Community"), not an official posting.
            continue
        if ident in seen:
            continue
        seen.add(ident)
        location = LOCATION_SPAN_RE.search(block)
        cards.append({'title': _clean(title_match.group(2)), 'href': href, 'ident': ident,
                      'location': _clean(location.group(1)) if location else ''})
    return cards


def parse_legend(page_html):
    """(page_first, page_last, total|None) from "1 - 6 of 999+ results"."""
    match = LEGEND_RE.search(page_html or '')
    if not match:
        return None, None, None
    text = _clean(match.group(1))
    numbers = re.findall(r'([\d,]+)', text)
    if len(numbers) < 3:
        return None, None, None
    total_text = numbers[2].replace(',', '')
    total = int(total_text) if total_text.isdigit() else None
    return int(numbers[0].replace(',', '')), int(numbers[1].replace(',', '')), total


def parse_pagination(page_html):
    """(current_page|None, [(page_number, url), ...]) from the portal's own pager.

    Avature portals name the paging parameters differently (``jobOffset``,
    ``pipelineOffset`` for HSBC, ``folderOffset`` for Siemens), so the adapter
    follows the page's own pagination links instead of guessing parameter names.
    """
    start = (page_html or '').find('list-controls__pagination')
    block = page_html[start:start + 20000] if start >= 0 else ''
    current = None
    # Avature themes mark the active page either with ``aria-label="Current Page N"``
    # or with a bare ``N`` inside the current-page element. ``</li>`` is not reliable
    # (several themes omit it), so the number is taken from the attribute first.
    current_match = re.search(r'currentPageLink[^>]*aria-label="Current Page (\d+)"', block)
    if not current_match:
        current_match = re.search(r'currentPageLink[^>]*>\s*(?:<[^>]+>\s*)*(\d+)\s*<', block)
    if current_match:
        current = int(current_match.group(1))
    links = []
    for match in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S):
        label = _clean(match.group(2))
        if label.isdigit():
            links.append((int(label), _html.unescape(match.group(1))))
    return current, links


def next_page_url(page_html, fallback=''):
    current, links = parse_pagination(page_html)
    if not links:
        return fallback
    target = (current or 1) + 1
    for number, url in links:
        if number == target:
            return url
    forward = sorted((n, u) for n, u in links if current is None or n > current)
    return forward[0][1] if forward else ''


def parse_detail(page_html):
    """Official Avature detail page -> {title, fields, values, description, ...}."""
    fields = {}
    ordered_values = []
    blocks = DETAIL_BLOCK_RE.split(page_html or '')[1:]
    content_texts = []
    for block in blocks:
        found = False
        for field_html in FIELD_RE.findall(block):
            label = LABEL_RE.search(field_html)
            value = VALUE_RE.search(field_html)
            value_text = _clean(value.group(1)) if value else ''
            if label:
                found = True
                label_text = _clean(label.group(1))
                if label_text and value_text:
                    fields.setdefault(label_text.lower(), value_text)
            if value_text:
                ordered_values.append(value_text)
        text = _block_text(block)
        if len(text) > 250:
            content_texts.append(text)
        elif not found and not content_texts and text:
            content_texts.append(text)
    # Only the job-specific detail headline is used. A bare <h1> on several themes is
    # the site/brand name ("HSBC Group", "L'Oreal"), so the card's official posting
    # title is the better fallback and stays authoritative in ``_job``.
    title_match = re.search(r'<h3[^>]*class="[^"]*section__header__text__title[^"]*"[^>]*>(.*?)</h3>',
                            page_html or '', re.S)
    title = _clean(title_match.group(1)) if title_match else ''
    posted = ''
    for label in POSTED_LABELS:
        if fields.get(label):
            posted = _parse_date(fields[label])
            if posted:
                break
    if not posted:
        for value in ordered_values:
            parsed = _parse_date(value)
            if parsed:
                posted = parsed
                break
    deadline = ''
    for label in DEADLINE_LABELS:
        if fields.get(label):
            deadline = _parse_date(fields[label])
            if deadline:
                break
    locations = [fields[label] for label in fields if any(x in label for x in LOCATION_LABELS)]
    if not locations:
        locations = [v for v in ordered_values if _is_china_location(v) or _country_only_location(v)]
    return {'title': title, 'fields': fields, 'values': ordered_values,
            'description': '\n'.join(dict.fromkeys(content_texts)),
            'posted': posted, 'deadline': deadline, 'locations': locations}


def _china_locations(parsed, card):
    candidates = list(parsed.get('locations') or [])
    if card.get('location'):
        candidates.append(card['location'])
    hits = [c for c in dict.fromkeys(candidates) if _is_china_location(c)]
    return hits


def _job(name, scope, key, card, parsed, china_locations):
    host, locale, portal = parts_for(key)
    ident = card['ident']
    url = card['href'] if str(card['href']).startswith('http') else f'https://{host}{card["href"]}'
    title = parsed.get('title') or card.get('title') or ''
    location = ' / '.join(china_locations)
    fields = parsed.get('fields') or {}
    raw = {k: v for k, v in fields.items() if len(str(v)) < 500}
    job = shared.job(name, scope, ident, title, url, parsed.get('description') or '',
                     location, raw)
    city_tokens = []
    for value in china_locations:
        text = COUNTRY_TOKEN_RE.sub(' ', _clean(value))
        for token in re.split(r'[，,、;；|/]|\s+-\s+', text):
            token = re.sub(r'\s+', ' ', token).strip(' -,')
            if token and token.lower() not in [c.lower() for c in city_tokens]:
                city_tokens.append(token)
    job['cities_source_raw'] = list(city_tokens)
    job['cities'] = list(city_tokens)
    job['cities_normalized'] = list(city_tokens)
    job['scope_evidence'] = (
        f'Official Avature portal={host}/{locale}/{portal}; official title="{title}"; '
        f'official labels={json.dumps({k: fields.get(k) for k in LABEL_FIELDS if fields.get(k)}, ensure_ascii=False)}; '
        f'classification={scope} (intern before campus before social)')
    job['recruitment_type_raw'] = {k: fields.get(k) for k in LABEL_FIELDS if fields.get(k)}
    job['published_at'] = parsed.get('posted') or ''
    job['publication_date'] = job['published_at']
    job['source_publication_field'] = 'opening_date' if job['published_at'] else ''
    job['deadline_raw'] = parsed.get('deadline') or ''
    if job['deadline_raw']:
        job['deadline'] = job['deadline_raw']
        job['deadline_type'] = 'explicit'
    job['cohort_raw'] = ''  # Avature exposes no cohort (届别) field -- never inferred
    job['source_url'] = url
    return job


def collect(company, scope, output_dir, max_requests=None):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    name = COMPANIES[key]
    keyword = search_keyword_for(key)
    page_size = page_size_for(key)
    max_pages = max_list_pages_for(key)
    max_jobs = max_jobs_for(key)
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    entry_url = search_url(key, keyword, 0, page_size)
    coverage = shared.coverage(entry_url)
    jobs = []
    cards = []
    seen = set()
    list_complete = False
    session = _make_session()
    try:
        offset = 0
        pages = 0
        page_url = entry_url
        visited = set()
        while pages < max_pages and page_url and page_url not in visited:
            visited.add(page_url)
            page_html = cached_page(session, page_url, f'list-page{pages + 1}.html',
                                    budget, output_dir, key)
            coverage['pages_scanned'] += 1
            pages += 1
            page_cards = parse_list(page_html)
            first, last, total = parse_legend(page_html)
            if not page_cards and total is None and pages == 1:
                # Avature's front end occasionally answers a perfectly valid search
                # with a degraded "no results / Talent Community" shell. Retry the
                # exact same official URL once before believing the empty list.
                time.sleep(2.0)
                page_html = cached_page(session, page_url, f'list-page{pages + 1}.html',
                                        budget, output_dir, key, force=True)
                coverage['pages_scanned'] += 1
                coverage['degraded_page_retry'] = True
                page_cards = parse_list(page_html)
                first, last, total = parse_legend(page_html)
            if total is not None:
                coverage['search_total'] = total
            new_cards = [c for c in page_cards if c['ident'] not in seen]
            for card in new_cards:
                seen.add(card['ident'])
            cards.extend(new_cards)
            if not page_cards or not new_cards:
                # An empty or fully-repeated page is only the end of the list when the
                # portal's own legend does not contradict it. When the legend still
                # reports more postings than we have seen, nothing proves the listing
                # ended: record the truncation and never let `pagination_exhausted`
                # become true (a capped / degraded read must not be reported as a
                # finished one).
                known = coverage.get('search_total')
                if known is not None and len(seen) < int(known):
                    coverage['page_cap_hit'] = True
                    coverage['list_truncated'] = True
                    coverage['last_page_evidence'] = (
                        f'page={pages};cards={len(page_cards)};new={len(new_cards)};'
                        f'seen={len(seen)};legend_total={known};truncated=true')
                    coverage['note'] = (
                        f'Avature page {pages} of portal={key} returned '
                        f'{len(page_cards)} card(s) with {len(new_cards)} new while the '
                        f'portal legend still reports {known} results; the listing is '
                        f'truncated and completeness cannot be confirmed')
                    break
                list_complete = True
                coverage['last_page_evidence'] = (f'page={pages};cards={len(page_cards)};'
                                                  f'new={len(new_cards)};total={total}')
                break
            offset += max(len(page_cards), 1)
            fallback = search_url(key, keyword, offset, page_size)
            following = next_page_url(page_html, fallback)
            if last is not None and total is not None and last >= total:
                list_complete = True
                coverage['last_page_evidence'] = (f'page={pages};last={last};total={total}')
                break
            if following == page_url:
                following = ''
            page_url = following
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
                page_html = fetch_detail(session, card['href'], card['ident'], budget,
                                         output_dir, key)
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                break
            except Exception as error:  # noqa: BLE001
                detail_errors.append(f'{card["ident"]}: {type(error).__name__}: {error}'[:300])
                continue
            parsed = parse_detail(page_html)
            china = _china_locations(parsed, card)
            if not china:
                filtered_country += 1
                continue
            if _scope_of(parsed.get('title') or card.get('title'), parsed.get('fields') or {}, key) != scope:
                continue
            selected += 1
            if not parsed.get('description'):
                detail_errors.append('Empty official Avature description for ' + card['ident'])
                continue
            jobs.append(_job(name, scope, key, card, parsed, china))
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
        coverage['evidence'] = sorted(p.name for p in output_dir.glob('*.html'))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (
            f'Official Avature portal={key}; built-in search="{keyword}"; requested={scope}; '
            f'the official detail location is the China gate; official '
            f'Graduate/Intern/Early Careers/Campus labels -> campus/intern, else social.')
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': entry_url,
                                     'params': {'search': keyword, 'jobOffset': 0,
                                                'jobRecordsPerPage': page_size}}
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
            'note', f'No official Avature job matched scope={scope} for country=China '
                    f'on portal {key}.')
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
