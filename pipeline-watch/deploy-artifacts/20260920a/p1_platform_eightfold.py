"""Eightfold AI public careers adapter (``<tenant>/api/pcsx/...``).

Eightfold powers the public careers sites of a number of foreign employers in
China (HP, Microsoft, Qualcomm, Applied Materials, Lam Research, ...). The
listing is a client-rendered page whose own XHR is a plain, account-free JSON
endpoint; an earlier round marked these tenants "unreachable" because a bare
probe used the wrong request shape and got ``403 Not authorized for PCSX``. The
contract below was read off the live public pages (the response the page itself
asks for), not guessed:

* ``GET {host}/api/pcsx/search?domain={domain}&query=&location={loc}
  &start={n}&sort_by=distance&filter_include_remote=1&hl={hl}``
  -> ``data.count`` (total) and ``data.positions`` (10 per page, server-fixed;
  ``num``/``size`` are ignored). ``start`` is the page cursor.
* ``GET {host}/api/pcsx/position_details?position_id={id}&domain={domain}
  &hl={hl}&queried_location={loc}`` -> ``data.jobDescription`` (full official
  body) plus ``publicUrl`` and the official ATS apply link.

Nothing here logs in, forges a signature or solves a challenge. The direct call
uses the same URL the page itself issues; if a tenant ever answers 401/403/429
the adapter falls back to loading the public careers page in headless Chromium
and reading the response the page itself receives (the ``start=`` query
parameter is the page's own pagination control).

Scope mapping uses only official labels carried by the posting itself
(``Intern``/``Internship``/``Apprentice`` -> intern, ``Campus``/``Graduate``/
``Early Career``/``University``/``校招``/``应届`` -> campus); everything else is
social. Cohort year, deadline and publish date are never inferred: an absent
value stays empty.

Politeness: every outbound request is spaced by
``QIUZHAO_PLATFORM_REQUEST_INTERVAL`` seconds (default 0, verification runs pass
2.0) and counted against ``QIUZHAO_PLATFORM_REQUEST_BUDGET`` / ``max_requests``
(production default: no cap). The headless fallback additionally caps real page
loads per tenant at ``QIUZHAO_PLATFORM_MAX_PAGE_LOADS`` (default 25).
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

MODULE_PATH = 'qiuzhao.collector.p1_platform_eightfold'
CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
CONFIG_KEY = 'eightfold'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
DEFAULT_REQUEST_BUDGET = None
# Eightfold pins the list page to 10 rows; ``num``/``size`` are ignored.
PAGE_SIZE = 10
DEFAULT_MAX_PAGE_LOADS = 25
DETAIL_VERIFY_LIMIT = 0  # 0 = fetch every selected posting's official detail

# Official early-career labels. Same vocabulary as the Workday/SuccessFactors
# adapters, matched with word boundaries so "intern" never matches "internal"
# and "graduate" never matches a senior "Graduate School" liaison role by
# accident; a tenant may extend either list from its config entry.
# Intern before campus: a "Graduate Intern" is an internship, not a graduate role.
INTERN_KEYWORDS = ['intern', 'internship', '实习', 'summer analyst', 'summer intern',
                   'co-op', 'coop', 'placement', 'apprentice', 'apprenticeship', '学徒']
CAMPUS_KEYWORDS = ['campus', '校招', '校园', '应届', 'graduate program', 'graduate scheme',
                   'graduate trainee', 'graduate development', 'new grad', 'new graduate',
                   'new college graduate', 'early career', 'earlycareer', 'entry level',
                   'entry-level', 'management associate', 'management trainee', 'trainee',
                   'leadership program', 'leadership development', '管培', '培训生',
                   '储备干部', 'student program', 'students & graduates']
# Official fields whose text may carry the early-career label. Only ``title`` is
# trusted by default: tenants bucket their postings differently (BCG files
# "Experienced Hire, Full-time" under subCategory "Co-op/Intern/Temporary", so a
# whole-field scan produces false early-career rows). A tenant may opt extra
# fields in with ``label_fields`` and may pin an exact official value to a scope
# with ``scope_labels`` (e.g. Roche's subCategory "Development Program").
DEFAULT_LABEL_FIELDS = ('name',)  # Eightfold calls the posting title ``name``

# China membership tokens. Eightfold tenants spell the same place three ways:
# "Chongqing, Chongqing, China", "Jinan,CHN" and "Jinan, Shandong, CN".
CHINA_WORDS = ('china', '中国', 'hong kong', '香港', 'taiwan', '台湾', 'taipei',
               'macau', 'macao', '澳门', 'greater china')


class BudgetExhausted(RuntimeError):
    """The politeness budget for this tenant/scope run is used up."""


class DirectRefused(RuntimeError):
    """The tenant answered the direct API call with an auth/rate gate."""


def _read_platform():
    data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return data.get(CONFIG_KEY) or {}


def _entry(key):
    entry = _read_platform().get(key) or {}
    return {'name': entry} if isinstance(entry, str) else entry


def _load_companies():
    companies = {}
    for key, entry in _read_platform().items():
        if str(key).startswith('_'):  # section documentation, not a tenant
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
    raise ValueError('unknown Eightfold tenant: ' + str(company))


# --- official request shapes -------------------------------------------------

def _base(entry):
    host = str(entry.get('host') or '').rstrip('/')
    if not host:
        raise ValueError('Eightfold entry is missing host')
    return host


def _setting(entry, key, default):
    value = entry.get(key)
    return default if value is None or str(value) == '' else str(value)


def _list_query(entry, start):
    query = {
        'domain': _setting(entry, 'domain', ''),
        'location': _setting(entry, 'location', 'china'),
        'start': int(start),
        'sort_by': _setting(entry, 'sort_by', 'distance'),
        'filter_include_remote': _setting(entry, 'filter_include_remote', '1'),
        'hl': _setting(entry, 'hl', 'en-US'),
    }
    if str(entry.get('filter_include_relocation') or '') != '':
        query['filter_include_relocation'] = str(entry['filter_include_relocation'])
    return query


def search_url(entry, start):
    """The exact ``/api/pcsx/search`` URL the public careers page itself asks for."""
    query = _list_query(entry, start)
    query['query'] = ''
    ordered = {'domain': query.pop('domain'), 'query': query.pop('query'), **query}
    return f'{_base(entry)}/api/pcsx/search?' + urlencode(ordered)


def careers_url(entry, start):
    """The public careers page URL, used as the headless-fallback entry point."""
    return f'{_base(entry)}{_setting(entry, "careers_path", "/careers")}?' + \
        urlencode(_list_query(entry, start))


def detail_url(entry, position_id):
    query = {
        'position_id': str(position_id),
        'domain': _setting(entry, 'domain', ''),
        'hl': _setting(entry, 'hl', 'en-US'),
        'queried_location': _setting(entry, 'location', 'china'),
    }
    return f'{_base(entry)}/api/pcsx/position_details?' + urlencode(query)


# --- budget / interval -------------------------------------------------------

def _budget_limit(max_requests):
    if max_requests is not None:
        return int(max_requests)
    raw = os.environ.get('QIUZHAO_PLATFORM_REQUEST_BUDGET')
    return int(raw) if raw and raw.strip() else DEFAULT_REQUEST_BUDGET


def _max_page_loads():
    raw = os.environ.get('QIUZHAO_PLATFORM_MAX_PAGE_LOADS')
    return int(raw) if raw and raw.strip() else DEFAULT_MAX_PAGE_LOADS


def _min_interval():
    raw = os.environ.get('QIUZHAO_PLATFORM_REQUEST_INTERVAL')
    return float(raw) if raw and raw.strip() else 0.0


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
    session.headers['Accept'] = 'application/json, text/plain, */*'
    session.headers['Accept-Language'] = 'zh-CN,zh;q=0.9,en;q=0.8'
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=0)))
    return session


def _http_json(session, url, budget, referer):
    import requests

    def call():
        _spend(budget)
        interval = _min_interval()
        if interval:
            time.sleep(interval)
        response = session.get(url, timeout=(10, 45),
                               headers={'Referer': referer, 'Origin': _base({'host': referer})})
        if response.status_code in (401, 403, 429):
            raise DirectRefused(f'HTTP {response.status_code} on {url}')
        response.raise_for_status()
        return response.json()

    try:
        return call()
    except DirectRefused:
        raise
    except (requests.RequestException, ValueError):
        time.sleep(2.0)
        return call()


# --- headless fallback -------------------------------------------------------

class _HeadlessReader:
    """Load the public careers page and read the JSON the page itself receives.

    Used only when the direct API call is refused. One browser per tenant run;
    each listing page costs one real page load and is counted against the same
    politeness budget and the per-tenant page-load cap.
    """

    def __init__(self, entry, budget, allow_page_loads):
        self.entry = entry
        self.budget = budget
        self.allow_page_loads = allow_page_loads
        self.page_loads = 0
        self._pw = None
        self._browser = None
        self._context = None
        self.page = None

    def _ensure(self):
        if self.page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except Exception as error:  # pragma: no cover - environment dependent
            raise RuntimeError(f'playwright not importable: {error}') from error
        self._pw = sync_playwright().start()
        last = None
        # Bundled chromium first (the collector machine), system Chrome second.
        for kwargs in ({}, {'channel': 'chrome'}):
            try:
                self._browser = self._pw.chromium.launch(headless=True,
                                                         args=['--no-sandbox'], **kwargs)
                break
            except Exception as error:
                last = error
        if self._browser is None:
            self._pw.stop()
            self._pw = None
            raise RuntimeError(f'chromium launch failed: {last}')
        self._context = self._browser.new_context(user_agent=UA, locale='zh-CN',
                                                  viewport={'width': 1440, 'height': 900})
        self._context.set_default_timeout(60000)
        self.page = self._context.new_page()

    def search_page(self, start):
        """Return the ``data`` object of the listing response for page ``start``."""
        self._ensure()
        if self.page_loads >= self.allow_page_loads:
            raise BudgetExhausted(
                f'per-tenant page-load cap reached ({self.allow_page_loads})')
        _spend(self.budget)
        captured = {}

        def on_response(response):
            if '/api/pcsx/search' not in response.url or captured:
                return
            try:
                captured['payload'] = response.json()
            except Exception:
                pass

        self.page.on('response', on_response)
        try:
            interval = _min_interval()
            if interval:
                time.sleep(interval)
            self.page.goto(careers_url(self.entry, start),
                           wait_until='domcontentloaded', timeout=60000)
            deadline = time.monotonic() + 45
            while not captured and time.monotonic() < deadline:
                self.page.wait_for_timeout(500)
        finally:
            self.page.remove_listener('response', on_response)
        self.page_loads += 1
        if not captured:
            raise RuntimeError(f'no /api/pcsx/search response on page start={start}')
        return (captured['payload'] or {}).get('data') or {}

    def get_json(self, url):
        self._ensure()
        _spend(self.budget)
        interval = _min_interval()
        if interval:
            time.sleep(interval)
        response = self.page.request.get(url, headers={'Accept': 'application/json'})
        if response.status >= 400:
            raise RuntimeError(f'HTTP {response.status} on {url}')
        return response.json()

    def close(self):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        finally:
            self.page = self._context = self._browser = self._pw = None


# --- classification / mapping ------------------------------------------------

def keyword_re(keyword):
    """Compile one boundary-aware keyword pattern.

    ASCII keywords must not match inside a longer word ("intern" vs "internal",
    "co-op" vs "cooperate"); CJK keywords are plain substrings because they have
    no word boundaries.
    """
    text = str(keyword or '').strip()
    if not text:
        return None
    if text.isascii() and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 .\-]*', text):
        body = re.escape(text).replace(r'\ ', r'[\s\-]+')
        return re.compile(r'(?<![A-Za-z0-9])' + body + r'(?![A-Za-z0-9])', re.I)
    return re.compile(re.escape(text), re.I)


def _keyword_patterns(keywords):
    return [pattern for pattern in (keyword_re(k) for k in keywords) if pattern]


def field_text(job, field):
    value = job.get(field)
    if isinstance(value, (list, tuple)):
        return ' | '.join(str(x) for x in value)
    if isinstance(value, dict):
        return ' | '.join(str(x) for x in value.values())
    return str(value or '')


def classify_scope(job, key=None):
    """Map a posting's own official labels to a scope.

    Only labels the posting carries are used; nothing is inferred from the
    posting date. A tenant's exact ``scope_labels`` pin wins first, then the
    boundary-aware keyword scan over the tenant's trusted ``label_fields``.
    Intern is the more specific label and wins over campus.
    """
    entry = _entry(key) if key else {}
    for field, mapping in (entry.get('scope_labels') or {}).items():
        if not isinstance(mapping, dict):
            continue
        value = field_text(job, field).strip().lower()
        if not value:
            continue
        for label, scope in mapping.items():
            if value == str(label).strip().lower() and scope in shared.TYPES:
                return scope
    fields = entry.get('label_fields') or list(DEFAULT_LABEL_FIELDS)
    text = ' | '.join(field_text(job, f) for f in fields if job.get(f))
    if not text.strip():
        return 'social'
    intern_kw = INTERN_KEYWORDS + [str(x) for x in (entry.get('intern_keywords') or [])]
    campus_kw = CAMPUS_KEYWORDS + [str(x) for x in (entry.get('campus_keywords') or [])]
    if any(pattern.search(text) for pattern in _keyword_patterns(intern_kw)):
        return 'intern'
    if any(pattern.search(text) for pattern in _keyword_patterns(campus_kw)):
        return 'campus'
    return 'social'


def _location_tokens(position):
    tokens = []
    for value in (position.get('locations') or []):
        if str(value).strip():
            tokens.append(str(value).strip())
    for value in (position.get('standardizedLocations') or []):
        if str(value).strip():
            tokens.append(str(value).strip())
    return tokens


def is_china_location(token):
    """True when one official location string names a Greater-China place.

    Handles all three spellings the tenants emit: ``..., China``, ``Jinan,CHN``
    and ``Jinan, Shandong, CN``.
    """
    text = str(token or '').strip().lower()
    if not text:
        return False
    if any(word in text for word in CHINA_WORDS):
        return True
    return text.replace(' ', '').rsplit(',', 1)[-1] in {'cn', 'chn', 'hkg', 'twn', 'mac'}


def is_china(position):
    return any(is_china_location(token) for token in _location_tokens(position))


def _location_text(position):
    return ' / '.join(dict.fromkeys(_location_tokens(position)))


def _position_id(position):
    ident = position.get('id')
    if ident is None or str(ident).strip() == '':
        raise ValueError('Eightfold position without id')
    return str(ident)


def select_positions(positions, scope, key=None, seen=None):
    """Positions of one listing page that belong to ``scope`` and to China."""
    selected = []
    seen = seen if seen is not None else set()
    for position in positions:
        ident = _position_id(position)
        if ident in seen:
            continue
        seen.add(ident)
        if not is_china(position):
            continue
        if classify_scope(position, key) != scope:
            continue
        selected.append(position)
    return selected


def _published_at(ts):
    try:
        value = int(ts)
    except (TypeError, ValueError):
        return ''
    if value <= 0:
        return ''
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _job(name, scope, entry, position, detail):
    ident = _position_id(position)
    detail = detail or {}
    title = shared.text(position.get('name') or detail.get('name'))
    action = (detail.get('positionUserActions') or {}).get('applyAction') or {}
    apply_link = str(action.get('applyUrl') or '')
    public_url = str(detail.get('publicUrl') or '')
    if not public_url:
        public_url = f"{_base(entry)}{position.get('positionUrl') or '/careers/job/' + ident}"
    description = detail.get('jobDescription') or position.get('jobDescription') or ''
    location = _location_text(position) or str(detail.get('location') or '')
    record = shared.job(name, scope, ident, title, public_url, description, location, {
        'id': ident,
        'department': position.get('department'),
        'displayJobId': position.get('displayJobId') or position.get('atsJobId'),
        'workLocationOption': position.get('workLocationOption'),
    })
    # Only the official application link the posting itself carries is used; when
    # the posting exposes none, the official public detail page is the target.
    record['application_url'] = apply_link or public_url
    record['detail_url'] = public_url
    record['source_url'] = public_url
    record['recruitment_unit'] = name
    record['published_at'] = _published_at(position.get('postedTs') or detail.get('postedTs'))
    # Eightfold publishes no application deadline and no cohort year for these
    # tenants; both stay empty rather than being derived from the posting date.
    record['deadline_raw'] = ''
    record['cohort_raw'] = ''
    record['source_updated_at'] = record['published_at']
    record['scope_evidence'] = (
        'Official Eightfold posting labels: '
        f"title={title!r}; department={position.get('department')!r}")
    record['detail_checked_at'] = datetime.now(timezone.utc).isoformat()
    record['list_checked_at'] = record['detail_checked_at']
    record['description_source'] = 'official Eightfold position_details jobDescription'
    record['company_name'] = name
    record['company'] = name
    record['unit'] = name
    return record


def collect(company, scope, output_dir, max_requests=None):
    """Collect one Eightfold tenant/scope.

    Listing and detail are interleaved so a politeness budget smaller than
    ``pages + postings`` still publishes the postings it did read as ``partial``
    rather than discarding every request. Without a budget the walk is the full
    list scan followed by every selected detail, so ``complete`` still requires
    pagination exhaustion.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    entry = _entry(key)
    name = COMPANIES[key]
    stem = key.replace('/', '_').replace(':', '_')
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(search_url(entry, 0))
    jobs = []
    positions, seen_ids = [], set()
    listing_exhausted = False
    last_page_evidence = ''
    evidence = []
    headless = None
    mode = 'direct'
    session = _make_session()
    try:
        start, total = 0, None
        while True:
            if mode == 'direct':
                try:
                    payload = _http_json(session, search_url(entry, start), budget,
                                         careers_url(entry, start))
                    data = payload.get('data') or {}
                except DirectRefused as refused:
                    coverage['note'] = (f'direct API refused ({refused}); switched to the '
                                        'public careers page in headless Chromium')
                    mode = 'headless'
                    headless = _HeadlessReader(entry, budget, _max_page_loads())
                    continue
            else:
                data = headless.search_page(start)
            evidence_name = f'{stem}-list-{scope}-{start}.json'
            (output_dir / evidence_name).write_text(
                json.dumps(data, ensure_ascii=False), encoding='utf-8')
            evidence.append(evidence_name)
            coverage['pages_scanned'] += 1
            page = data.get('positions') or []
            if total is None:
                total = data.get('count')
            if not page:
                listing_exhausted = True
                last_page_evidence = f'key={key};scope={scope};start={start};rows=0;count={total}'
                break
            fresh = 0
            for position in page:
                ident = _position_id(position)
                if ident in seen_ids:
                    continue
                seen_ids.add(ident)
                fresh += 1
                positions.append(position)
            start += len(page)
            if fresh == 0:
                last_page_evidence = (f'key={key};scope={scope};start={start};'
                                      f'rows={len(page)};new=0;count={total};repeated_page=true')
                coverage['note'] = (coverage.get('note') or '') + (
                    ' Eightfold pagination repeated an already-listed page; '
                    'listing completeness cannot be confirmed')
                break
            if total is not None and start >= int(total):
                listing_exhausted = True
                last_page_evidence = (f'key={key};scope={scope};start={start};count={total};'
                                      f'rows_read={len(seen_ids)}')
                break
        selected = select_positions(positions, scope, key)
        coverage['expected_total'] = len(selected)
        coverage['list_observed_ids'] = sorted(seen_ids)
        for position in selected:
            ident = _position_id(position)
            try:
                if mode == 'direct':
                    payload = _http_json(session, detail_url(entry, ident), budget,
                                         careers_url(entry, 0))
                else:
                    payload = headless.get_json(detail_url(entry, ident))
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                raise
            except DirectRefused:
                coverage['errors'].append(f'detail {ident}: direct API refused')
                continue
            except Exception as error:
                coverage['errors'].append(f'detail {ident}: {type(error).__name__}: {error}')
                continue
            detail = payload.get('data') or {}
            if str(detail.get('id') or '') != ident:
                coverage['errors'].append(f'Incomplete Eightfold detail {ident}')
                continue
            evidence_name = f'detail-{ident}.json'
            (output_dir / evidence_name).write_text(
                json.dumps(detail, ensure_ascii=False), encoding='utf-8')
            evidence.append(evidence_name)
            jobs.append(_job(name, scope, entry, position, detail))
            if len(jobs) % 50 == 0:
                shared.partial_checkpoint(jobs, coverage, name, scope, output_dir)
        coverage['list_observed_titles'] = sorted(str(x.get('name') or '') for x in positions)
        coverage['last_page_evidence'] = last_page_evidence
        coverage['pagination_exhausted'] = bool(listing_exhausted)
        coverage['detail_complete'] = bool(selected) and len(jobs) == len(selected)
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
    except Exception as error:
        coverage['errors'].append(f'{type(error).__name__}: {error}')
    finally:
        if headless is not None:
            headless.close()
    coverage['request_budget'] = budget
    coverage['mode'] = mode
    coverage['scope_request'] = {
        'company': name, 'scope': scope, 'source_url': search_url(entry, 0),
        'params': {'domain': _setting(entry, 'domain', ''),
                   'location': _setting(entry, 'location', 'china'),
                   'hl': _setting(entry, 'hl', 'en-US'),
                   'pagination': 'start', 'page_size': PAGE_SIZE,
                   'transport': mode},
    }
    coverage['evidence'] = sorted(set(evidence))
    coverage['evidence_files'] = coverage['evidence']
    if not jobs and not coverage['errors'] and listing_exhausted \
            and not coverage.get('request_budget_exhausted'):
        coverage['note'] = (coverage.get('note') or '') + (
            f' official Eightfold list carries no {shared.TYPES[scope]} posting for '
            f'{name} in location={_setting(entry, "location", "china")}')
    result = shared.finish(jobs, coverage)
    if not result['jobs'] and listing_exhausted and not coverage['errors'] \
            and not coverage.get('request_budget_exhausted'):
        # An exhausted listing that genuinely holds no posting for this scope is
        # a successful empty read, not a blocked source. The official listing
        # request stays the scope evidence, exactly as it is for a non-empty read.
        result['coverage'].update(
            status='success', complete=True, detail_complete=True,
            scope_evidence=(f'Official Eightfold listing {search_url(entry, 0)} read to exhaustion; '
                            f'no posting in Greater China carries the official '
                            f'{shared.TYPES[scope]} early-career label.'),
            scope_request=coverage.get('scope_request'))
    if coverage.get('request_budget_exhausted'):
        result['coverage'].update(complete=False, detail_complete=False)
        if result['coverage']['status'] == 'success':
            result['coverage']['status'] = 'partial'
        if not result['jobs'] and coverage.get('expected_total'):
            # The official list confirmed postings but the run ran out of budget
            # before any detail; that is an unfinished read, never a dead source.
            result['coverage']['status'] = 'partial'
            result['coverage']['note'] = (result['coverage'].get('note') or '') + (
                f' request budget ran out after the listing confirmed '
                f"{coverage['expected_total']} selected posting(s); no detail fetched")
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('company')
    parser.add_argument('--scope', choices=list(shared.TYPES), default='campus')
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--max-requests', type=int)
    args = parser.parse_args()
    payload = collect(args.company, args.scope, args.output_dir,
                      max_requests=args.max_requests)
    print(json.dumps({'company': args.company, 'scope': args.scope,
                      'jobs': len(payload['jobs']),
                      'coverage': payload['coverage']}, ensure_ascii=False))
