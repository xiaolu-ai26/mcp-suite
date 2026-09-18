"""51job corporate campus micro-site adapter (``campus.51job.com/<slug>/``).

A number of foreign employers in China publish their campus programme on a
51job-hosted micro-site instead of an ATS. Those pages are plain server-rendered
HTML, publicly readable without an account; the postings are anchor links into
51job's application form (``xyz.51job.com/External/Apply.aspx?CtmID=...``). This
adapter parses exactly that: one line per site in ``p1_platform_companies.json``
under the ``job51`` key.

robots.txt: ``campus.51job.com/robots.txt`` and ``www.51job.com/robots.txt``
both 302 to ``/in/missing.php`` (no robots file, no crawl directive); the pages
themselves carry ``<meta name="robots" content="all">``. Nothing here logs in,
posts a form or bypasses a challenge — it is a single public GET per micro-site
plus the optional mobile entry page.

Data rules (foreign batch 2): only fields the announcement actually carries.
These micro-sites normally have no publish date and no deadline, so
``published_at``/``deadline_raw`` stay empty, and ``cohort_raw`` is never
inferred — the programme year only survives inside the announcement title.
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

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

MODULE_PATH = 'qiuzhao.collector.p1_platform_51job'
CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
CONFIG_KEY = 'job51'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
DEFAULT_REQUEST_BUDGET = None
# The application form link is the stable, official per-posting identity.
APPLY_RE = re.compile(r'https?://[^"\'\s>]*?(?:Apply\.aspx\?CtmID=|CtmID=)(\d+)', re.I)
TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')


class BudgetExhausted(RuntimeError):
    pass


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
    raise ValueError('unknown 51job company: ' + str(company))


def site_url(key):
    entry = _entry(key)
    url = str(entry.get('url') or '')
    if url:
        return url
    return f'https://campus.51job.com/{key}/'


def _budget_limit(max_requests):
    if max_requests is not None:
        return int(max_requests)
    raw = os.environ.get('QIUZHAO_PLATFORM_REQUEST_BUDGET')
    return int(raw) if raw and raw.strip() else DEFAULT_REQUEST_BUDGET


def _min_interval():
    raw = os.environ.get('QIUZHAO_PLATFORM_REQUEST_INTERVAL')
    return float(raw) if raw and raw.strip() else 0.0


def _make_session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    session.headers['User-Agent'] = UA
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=0)))
    return session


def _get(session, url, budget):
    import requests
    def call():
        if budget is not None:
            if budget['limit'] is not None and budget['used'] >= budget['limit']:
                raise BudgetExhausted('per-site request budget reached')
            budget['used'] += 1
        interval = _min_interval()
        if interval:
            time.sleep(interval)
        response = session.get(url, timeout=(10, 40))
        response.raise_for_status()
        # 51job micro-sites declare utf-8 in <meta> only; requests would otherwise
        # fall back to ISO-8859-1 and mojibake every Chinese posting name.
        response.encoding = response.apparent_encoding or response.encoding or 'utf-8'
        return response.text
    try:
        return call()
    except (requests.RequestException, ValueError):
        time.sleep(2.0)
        return call()


def announcement_title(page_html, fallback):
    match = TITLE_RE.search(page_html or '')
    title = _html.unescape(TAG_RE.sub(' ', match.group(1))).strip() if match else ''
    return re.sub(r'\s+', ' ', title) or fallback


def _clean(value):
    return re.sub(r'\s+', ' ', _html.unescape(TAG_RE.sub(' ', value or ''))).strip()


def _item_block(page_html, match):
    """Smallest official list-item block around one application anchor.

    Returns ``(item_html, anchor_offset)`` where ``anchor_offset`` points at the
    ``<a`` tag itself (not the URL inside it), so the text before it is the
    posting name and never a half-written anchor tag.
    """
    a_start = page_html.rfind('<a', 0, match.start())
    if a_start < 0:
        return '', 0
    for open_tag, close_tag in (('<li', '</li>'), ('<tr', '</tr>')):
        block_start = page_html.rfind(open_tag, 0, match.start())
        block_end = page_html.find(close_tag, match.end())
        if block_start >= 0 and block_end > block_start and a_start >= block_start:
            return page_html[block_start:block_end + len(close_tag)], a_start - block_start
    anchor_end = page_html.find('</a>', match.end())
    return page_html[a_start:anchor_end + 4], 0


BUTTON_TEXT = re.compile(
    r'^(点击投递|立即投递|立即申请|申请职位|投递简历|查看详情|点此投递|投递|申请|'
    r'apply(?: now)?|submit)$', re.I)


def parse_postings(page_html, page_url):
    """[(posting_name, apply_url, block_text)] from one public micro-site page.

    The application anchor (``Apply.aspx?CtmID=...``) is the official per-posting
    identity. The posting name is the item block's own text *before* that anchor,
    so a "点击投递" button label is never mistaken for a job title. Nothing is
    invented: a page with no application anchor yields zero postings and the
    caller reports that instead of guessing.
    """
    postings = []
    seen = set()
    for match in APPLY_RE.finditer(page_html or ''):
        ctm_id = match.group(1)
        if ctm_id in seen:
            continue
        item_html, anchor_off = _item_block(page_html, match)
        before = item_html[:anchor_off] if item_html else ''
        anchor_end = item_html.find('</a>', max(anchor_off, 0)) if item_html else -1
        anchor_text = _clean(item_html[anchor_off:anchor_end + 4]) if anchor_end > 0 else ''
        name = _clean(before)
        if len(name) > 160:  # a nested container, not a title
            name = ''
        if not name or BUTTON_TEXT.match(name):
            name = re.sub(r'\s*(点击投递|立即投递|立即申请|申请职位|投递简历|查看详情|点此投递)$', '',
                          anchor_text).strip()
        if not name or BUTTON_TEXT.match(name):
            continue
        seen.add(ctm_id)
        apply_url = f'https://xyz.51job.com/External/Apply.aspx?CtmID={ctm_id}'
        postings.append((name, apply_url, _clean(item_html) or _clean(before)))
    return postings


def collect(company, scope, output_dir, max_requests=None):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    entry = _entry(key)
    name = COMPANIES[key]
    configured_scope = str(entry.get('scope') or 'campus')
    url = site_url(key)
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(url)
    jobs = []
    session = _make_session()
    try:
        if scope != configured_scope:
            coverage['status'] = 'success'
            coverage['complete'] = True
            coverage['note'] = (f'micro-site publishes only the official '
                                f'{configured_scope} programme; scope={scope} has no page')
            coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': url,
                                         'params': {'configured_scope': configured_scope}}
            return {'jobs': [], 'coverage': coverage}
        page_html = _get(session, url, budget)
        (output_dir / f'{key}-list-1.html').write_text(page_html, encoding='utf-8')
        coverage['pages_scanned'] = 1
        title = announcement_title(page_html, name + '校园招聘')
        postings = parse_postings(page_html, url)
        if not postings and entry.get('mobile_path'):
            mobile_url = url.rstrip('/') + '/' + str(entry['mobile_path']).lstrip('/')
            mobile_html = _get(session, mobile_url, budget)
            (output_dir / f'{key}-list-mobile.html').write_text(mobile_html, encoding='utf-8')
            coverage['pages_scanned'] += 1
            postings = parse_postings(mobile_html, mobile_url)
        seen = set()
        for posting_name, apply_url, block in postings:
            ident = apply_url.rsplit('=', 1)[-1]
            if ident in seen:
                continue
            seen.add(ident)
            description = '\n'.join(x for x in (title, posting_name, block) if x)
            record = shared.job(name, scope, ident, posting_name, apply_url, description,
                                _clean(entry.get('location') or ''), {})
            record['scope_evidence'] = (f'Official 51job micro-site programme page; '
                                        f'announcement={title}')
            record['published_at'] = ''
            record['deadline_raw'] = ''
            record['source_updated_at'] = ''
            record['cohort_raw'] = ''  # never inferred from the announcement year
            record['campaign_cohort_raw'] = title
            record['campaign_scope'] = 'announcement'
            record['campaign_url'] = url
            record['description_source'] = 'official announcement micro-site text'
            record['list_checked_at'] = datetime.now(timezone.utc).isoformat()
            jobs.append(record)
        coverage['expected_total'] = len(seen)
        coverage['list_observed_ids'] = sorted(seen)
        coverage['list_observed_titles'] = sorted(j['job_title'] for j in jobs)
        coverage['pagination_exhausted'] = True
        coverage['detail_complete'] = True
        coverage['evidence'] = sorted(p.name for p in output_dir.glob('*'))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': url,
                                     'params': {'configured_scope': configured_scope}}
        if not jobs:
            coverage['errors'].append(
                'No public application anchor (CtmID) found on the micro-site landing page')
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
    except Exception as error:
        coverage['errors'].append(f'{type(error).__name__}: {error}')
    coverage['request_budget'] = budget
    result = shared.finish(jobs, coverage)
    if coverage.get('request_budget_exhausted'):
        result['coverage'].update(complete=False, detail_complete=False)
        if result['coverage']['status'] == 'success':
            result['coverage']['status'] = 'partial'
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
