"""Phenom People public careers adapter (``<tenant>/widgets``).

Phenom powers the public careers sites of a number of foreign employers in
China (P&G, Mars, BCG, Roche, ABB, Philips, MSD, Cisco, ...). An earlier round
recorded these tenants as "Phenom adapter not built yet". The contract below was
read off the live public pages, not guessed:

* ``POST {host}/widgets`` ``{"ddoKey": "refineSearch", "refNum": <tenant>, ...}``
  -> ``refineSearch.totalHits`` plus ``refineSearch.data.jobs``. ``size`` is
  capped server-side at 500 and ``from`` is the offset cursor.
* ``POST {host}/widgets`` ``{"ddoKey": "jobDetail", "jobId": ..., "jobSeqNo": ...}``
  -> ``jobDetail.data.job`` with the full official ``description`` (HTML),
  ``postedDate`` and ``postingEndDate``.

Both are the calls the careers page itself makes; nothing here logs in, forges a
signature or solves a challenge. The direct POST is tried first; if a tenant ever
answers 401/403/429 the adapter falls back to loading the public search-results
page in headless Chromium and reading the responses that page itself receives.

Location and scope
------------------
``location``/``country`` filter fields are ignored by the tenants whose careers
site is not country-scoped, so the adapter walks the tenant's public listing and
keeps the postings whose own official country/location text names Greater China.
Scope mapping uses only official labels carried by the posting (title, category,
sub-category, department, contract type): ``Intern``/``Internship``/
``Apprenticeship``/``Vocational & Development Programs``/``Co-op`` -> intern,
``Campus``/``Graduate``/``Students & Graduates``/``校招``/``应届`` -> campus,
everything else -> social.

Data rules: only fields the official payload carries. ``published_at`` comes
from ``postedDate``, ``deadline_raw`` from ``postingEndDate`` (empty when the
posting publishes none) and ``cohort_raw`` stays empty — no graduation year is
ever inferred.

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

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

MODULE_PATH = 'qiuzhao.collector.p1_platform_phenom'
CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
CONFIG_KEY = 'phenom'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
DEFAULT_REQUEST_BUDGET = None
# Server-side cap observed on every tenant: size=1000 still returns 500 rows.
PAGE_SIZE = 500
DEFAULT_MAX_PAGE_LOADS = 25
DETAIL_VERIFY_LIMIT = 0  # 0 = fetch every selected posting's official detail
ALL_FIELDS = ['category', 'country', 'state', 'city', 'type', 'jobFamilyGroup',
              'jobFamily', 'jobs', 'phLocSlider', 'phLocMultiselect',
              'phLocSingleSelect', 'phLocTextField']

# Same vocabulary as the Workday/SuccessFactors/Eightfold adapters, matched with
# word boundaries so "intern" never matches "internal"; a tenant may extend
# either list from its config entry. Intern wins over campus ("Graduate Intern").
INTERN_KEYWORDS = ['intern', 'internship', '实习', 'summer analyst', 'summer intern',
                   'co-op', 'coop', 'placement', 'apprentice', 'apprenticeship',
                   '学徒', 'vocational', 'working student']
CAMPUS_KEYWORDS = ['campus', '校招', '校园', '应届', 'graduate program', 'graduate scheme',
                   'graduate trainee', 'graduate development', 'new grad', 'new graduate',
                   'new college graduate', 'early career', 'earlycareer', 'entry level',
                   'entry-level', 'management associate', 'management trainee', 'trainee',
                   'leadership program', 'leadership development', '管培', '培训生',
                   '储备干部', 'students & graduates', 'student program']
# Official fields whose text may carry the early-career label. Only ``title`` is
# trusted by default: tenants bucket their postings differently (BCG files
# "Experienced Hire, Full-time" under subCategory "Co-op/Intern/Temporary", so a
# whole-field scan produces false early-career rows). A tenant may opt extra
# fields in with ``label_fields`` and may pin an exact official value to a scope
# with ``scope_labels`` (e.g. Roche's subCategory "Development Program").
DEFAULT_LABEL_FIELDS = ('title',)

CHINA_WORDS = ('china', '中国', 'hong kong', '香港', 'taiwan', '台湾', 'taipei',
               'macau', 'macao', '澳门', 'greater china')
COUNTRY_FIELDS = ('country', 'standardisedCountry', 'ml_country', 'country_raw')
LOCATION_FIELDS = ('location', 'cityStateCountry', 'cityState', 'city', 'state',
                   'multi_location', 'address')


class BudgetExhausted(RuntimeError):
    """The politeness budget for this tenant/scope run is used up."""


class DirectRefused(RuntimeError):
    """The tenant answered the direct widget call with an auth/rate gate."""


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
    raise ValueError('unknown Phenom tenant: ' + str(company))


# --- official request shapes -------------------------------------------------

def _setting(entry, key, default):
    value = entry.get(key)
    return default if value is None or str(value) == '' else str(value)


def widgets_url(entry):
    host = str(entry.get('host') or '').rstrip('/')
    if not host:
        raise ValueError('Phenom entry is missing host')
    return host + '/widgets'


def host_url(entry):
    return str(entry.get('host') or '').rstrip('/')


def search_body(entry, offset, size=PAGE_SIZE):
    return {
        'lang': _setting(entry, 'lang', 'en_global'),
        'deviceType': 'desktop',
        'country': _setting(entry, 'country', 'global'),
        'pageName': 'search-results',
        'ddoKey': 'refineSearch',
        'sortBy': '', 'subsearch': '', 'from': int(offset),
        'jobs': True, 'counts': True,
        'all_fields': ALL_FIELDS,
        'size': int(size), 'clicks': 0, 'search': '',
        'location': _setting(entry, 'location', ''),
        'locationData': {},
        'refNum': str(entry.get('ref') or ''),
        'siteType': _setting(entry, 'site_type', 'external'),
    }


def detail_body(entry, job):
    return {
        'lang': _setting(entry, 'lang', 'en_global'),
        'deviceType': 'desktop',
        'country': _setting(entry, 'country', 'global'),
        'pageName': 'job-details',
        'ddoKey': 'jobDetail',
        'jobId': str(job.get('jobId') or ''),
        'jobSeqNo': str(job.get('jobSeqNo') or ''),
        'refNum': str(entry.get('ref') or ''),
        'siteType': _setting(entry, 'site_type', 'external'),
    }


def search_page_url(entry):
    return f'{host_url(entry)}/{_setting(entry, "search_path", "search-results")}'


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


def _post_json(session, entry, body, budget):
    import requests

    def call():
        _spend(budget)
        interval = _min_interval()
        if interval:
            time.sleep(interval)
        host = host_url(entry)
        response = session.post(widgets_url(entry), json=body, timeout=(15, 90),
                                headers={'Referer': host + '/', 'Origin': host})
        if response.status_code in (401, 403, 429):
            raise DirectRefused(f'HTTP {response.status_code} on {widgets_url(entry)}')
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
    """Load the public search page and read the widget JSON the page itself gets.

    Used only when the direct widget call is refused. One browser per tenant run;
    the first listing page costs one real page load, every following widget call
    reuses the page's own request context. Counted against the same politeness
    budget and the per-tenant page-load cap.
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

    def warm_up(self):
        """One real page load so the page's own origin/context is established."""
        self._ensure()
        if self.page_loads >= self.allow_page_loads:
            raise BudgetExhausted(
                f'per-tenant page-load cap reached ({self.allow_page_loads})')
        _spend(self.budget)
        interval = _min_interval()
        if interval:
            time.sleep(interval)
        self.page.goto(search_page_url(self.entry), wait_until='domcontentloaded',
                       timeout=60000)
        self.page.wait_for_timeout(4000)
        self.page_loads += 1

    def widget(self, body):
        self._ensure()
        _spend(self.budget)
        interval = _min_interval()
        if interval:
            time.sleep(interval)
        response = self.page.request.post(
            widgets_url(self.entry), data=json.dumps(body),
            headers={'Content-Type': 'application/json',
                     'Accept': 'application/json, text/plain, */*'})
        if response.status >= 400:
            raise RuntimeError(f'HTTP {response.status} on {widgets_url(self.entry)}')
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
    """Compile one boundary-aware keyword pattern (see Eightfold adapter)."""
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


def is_china_token(token):
    """True when one official country/location string names Greater China."""
    text = str(token or '').strip().lower()
    if not text:
        return False
    if any(word in text for word in CHINA_WORDS):
        return True
    for chunk in re.split(r'[|/,]', text):
        if chunk.strip() in {'cn', 'chn', 'hkg', 'twn', 'mac'}:
            return True
    return False


def _china_values(job):
    values = []
    for field in COUNTRY_FIELDS:
        if job.get(field):
            values.append(str(job[field]))
    for field in LOCATION_FIELDS:
        value = job.get(field)
        if isinstance(value, (list, tuple)):
            values.extend(str(x) for x in value)
        elif isinstance(value, dict):
            values.extend(str(x) for x in value.values())
        elif value:
            values.append(str(value))
    return values


def is_china(job):
    return any(is_china_token(value) for value in _china_values(job))


def _job_id(job):
    ident = str(job.get('jobId') or job.get('reqId') or job.get('jobSeqNo') or '').strip()
    if not ident:
        raise ValueError('Phenom posting without jobId')
    return ident


def _location_text(job):
    values = []
    for field in ('location', 'cityStateCountry', 'cityState', 'city', 'country'):
        value = job.get(field)
        if value and str(value) not in values:
            values.append(str(value))
    multi = job.get('multi_location')
    if isinstance(multi, (list, tuple)):
        for item in multi:
            if item and str(item) not in values:
                values.append(str(item))
    return ' / '.join(values)


def _posted_at(job):
    raw = str(job.get('postedDate') or job.get('dateCreated') or '').strip()
    if not raw:
        return ''
    match = re.match(r'(\d{4}-\d{2}-\d{2})', raw)
    return match.group(1) if match else raw


def select_jobs(jobs, scope, key=None, seen=None):
    """Postings of one listing page that belong to ``scope`` and to China."""
    selected = []
    seen = seen if seen is not None else set()
    for job in jobs:
        try:
            ident = _job_id(job)
        except ValueError:
            continue
        if ident in seen:
            continue
        seen.add(ident)
        if not is_china(job):
            continue
        if classify_scope(job, key) != scope:
            continue
        selected.append(job)
    return selected


def _record(name, scope, entry, job, detail):
    ident = _job_id(job)
    detail = detail or {}
    title = shared.text(job.get('title') or detail.get('title'))
    apply_url = str(job.get('applyUrl') or detail.get('applyUrl') or '')
    host = host_url(entry)
    if apply_url:
        detail_link = apply_url
    else:
        seq = str(job.get('jobSeqNo') or detail.get('jobSeqNo') or '')
        detail_link = f'{host}/job/{seq}' if seq else host
    description = detail.get('description') or detail.get('ml_Description') \
        or job.get('descriptionTeaser') or ''
    location = _location_text(job) or _location_text(detail)
    record = shared.job(name, scope, ident, title, detail_link, description, location, {
        'id': ident,
        'category': job.get('category'),
        'subCategory': job.get('subCategory'),
        'contractType': job.get('contractType') or job.get('jobType'),
        'type': job.get('type'),
        'department': job.get('department'),
    })
    record['application_url'] = apply_url or detail_link
    record['detail_url'] = detail_link
    record['source_url'] = detail_link
    record['recruitment_unit'] = name
    record['published_at'] = _posted_at(detail) or _posted_at(job)
    # Phenom only carries a deadline when the posting itself publishes one.
    record['deadline_raw'] = shared.text(detail.get('postingEndDate'))
    record['cohort_raw'] = ''  # never inferred from the posting date
    record['source_updated_at'] = _posted_at(detail)
    record['scope_evidence'] = (
        'Official Phenom posting labels: '
        f"title={title!r}; category={job.get('category')!r}; "
        f"subCategory={job.get('subCategory')!r}; "
        f"contractType={job.get('contractType') or job.get('jobType')!r}")
    record['detail_checked_at'] = datetime.now(timezone.utc).isoformat()
    record['list_checked_at'] = record['detail_checked_at']
    record['description_source'] = 'official Phenom jobDetail description'
    record['company_name'] = name
    record['company'] = name
    record['unit'] = name
    return record


def collect(company, scope, output_dir, max_requests=None):
    """Collect one Phenom tenant/scope.

    The listing is walked once per scope and each selected posting's official
    detail is fetched immediately, so a politeness budget smaller than
    ``pages + postings`` still publishes the postings it did read as ``partial``
    rather than discarding every request.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    entry = _entry(key)
    name = COMPANIES[key]
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(search_page_url(entry))
    jobs = []
    collected, seen_ids = [], set()
    listing_exhausted = False
    last_page_evidence = ''
    evidence = []
    headless = None
    mode = 'direct'
    total = None
    session = _make_session()
    try:
        offset = 0
        while True:
            body = search_body(entry, offset)
            if mode == 'direct':
                try:
                    payload = _post_json(session, entry, body, budget)
                except DirectRefused as refused:
                    coverage['note'] = (f'direct widget refused ({refused}); switched to the '
                                        'public search page in headless Chromium')
                    mode = 'headless'
                    headless = _HeadlessReader(entry, budget, _max_page_loads())
                    headless.warm_up()
                    continue
            else:
                payload = headless.widget(body)
            result = payload.get('refineSearch') or {}
            if result.get('status') != 200 or not isinstance(result.get('data'), dict):
                raise ValueError(
                    f'Phenom refineSearch refused: status={result.get("status")} '
                    f'error={str(result.get("error"))[:200]}')
            data = result['data']
            evidence_name = f'{key}-list-{scope}-{offset}.json'
            (output_dir / evidence_name).write_text(
                json.dumps(data, ensure_ascii=False), encoding='utf-8')
            evidence.append(evidence_name)
            coverage['pages_scanned'] += 1
            page = data.get('jobs') or []
            if total is None:
                total = result.get('totalHits')
            if not page:
                listing_exhausted = True
                last_page_evidence = (f'key={key};scope={scope};from={offset};rows=0;'
                                      f'totalHits={total}')
                break
            fresh = 0
            for job in page:
                try:
                    ident = _job_id(job)
                except ValueError:
                    continue
                if ident in seen_ids:
                    continue
                seen_ids.add(ident)
                fresh += 1
                collected.append(job)
            offset += len(page)
            if fresh == 0:
                last_page_evidence = (f'key={key};scope={scope};from={offset};'
                                      f'rows={len(page)};new=0;totalHits={total};repeated_page=true')
                coverage['note'] = (coverage.get('note') or '') + (
                    ' Phenom pagination repeated an already-listed page; '
                    'listing completeness cannot be confirmed')
                break
            # Only a positive totalHits ends the scan; 0 with real rows is a site
            # contradiction and must not be read as an exhausted listing.
            if total and offset >= int(total):
                listing_exhausted = True
                last_page_evidence = (f'key={key};scope={scope};from={offset};'
                                      f'totalHits={total};rows_read={len(seen_ids)}')
                break
        selected = select_jobs(collected, scope, key)
        coverage['expected_total'] = len(selected)
        coverage['list_observed_ids'] = sorted(seen_ids)
        for job in selected:
            ident = _job_id(job)
            detail_request = detail_body(entry, job)
            try:
                if mode == 'direct':
                    payload = _post_json(session, entry, detail_request, budget)
                else:
                    payload = headless.widget(detail_request)
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                raise
            except DirectRefused:
                coverage['errors'].append(f'detail {ident}: direct widget refused')
                continue
            except Exception as error:
                coverage['errors'].append(f'detail {ident}: {type(error).__name__}: {error}')
                continue
            detail = ((payload.get('jobDetail') or {}).get('data') or {}).get('job') or {}
            if str(detail.get('jobId') or '') != ident:
                coverage['errors'].append(f'Incomplete Phenom detail {ident}')
                continue
            evidence_name = f'detail-{ident}.json'
            (output_dir / evidence_name).write_text(
                json.dumps(detail, ensure_ascii=False), encoding='utf-8')
            evidence.append(evidence_name)
            jobs.append(_record(name, scope, entry, job, detail))
            if len(jobs) % 50 == 0:
                shared.partial_checkpoint(jobs, coverage, name, scope, output_dir)
        coverage['list_observed_titles'] = sorted(
            str(x.get('title') or '') for x in collected)
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
        'company': name, 'scope': scope, 'source_url': search_page_url(entry),
        'params': {'refNum': str(entry.get('ref') or ''),
                   'widget': 'refineSearch', 'pagination': 'from', 'page_size': PAGE_SIZE,
                   'locale': _setting(entry, 'lang', 'en_global'),
                   'transport': mode},
    }
    coverage['evidence'] = sorted(set(evidence))
    coverage['evidence_files'] = coverage['evidence']
    if not jobs and not coverage['errors'] and listing_exhausted \
            and not coverage.get('request_budget_exhausted'):
        coverage['note'] = (coverage.get('note') or '') + (
            f' official Phenom list carries no {shared.TYPES[scope]} posting for '
            f'{name} in Greater China')
    result = shared.finish(jobs, coverage)
    if not result['jobs'] and listing_exhausted and not coverage['errors'] \
            and not coverage.get('request_budget_exhausted'):
        # An exhausted listing that genuinely holds no posting for this scope is
        # a successful empty read, not a blocked source. The official listing
        # request stays the scope evidence, exactly as it is for a non-empty read.
        result['coverage'].update(
            status='success', complete=True, detail_complete=True,
            scope_evidence=(f'Official Phenom listing {search_page_url(entry)} read to exhaustion; '
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
