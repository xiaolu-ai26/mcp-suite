"""Platform-level Moka (app.mokahr.com) campus/intern/social adapter.

One adapter covers every org/site: adding a company is one line in
``p1_platform_companies.json``. It reuses the verified Moka request/decrypt
logic from ``p1_sources_01_10`` (``request_json`` / ``moka_detail_cached`` /
``apply_moka_status``) and keeps the exact ``p1_sources_*`` result contract.

Request budget: ``QIUZHAO_PLATFORM_REQUEST_BUDGET`` (or ``max_requests``) caps
network calls per tenant per run. Production defaults to no cap
(``DEFAULT_REQUEST_BUDGET = None``); the offline verification runs set 20 only as
a politeness limit, which would truncate a large org.
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

CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
MODULE_PATH = 'qiuzhao.collector.p1_platform_moka'
SITE_RE = re.compile(r'/(?:(?:campus|social)-recruitment|campus_apply|apply)/([^/]+)/(\d+)')
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
# Production default: no cap. The per-tenant request budget is an opt-in guard for
# polite/offline verification (the verification runs pass 20). A low default would
# truncate a healthy org's listing (安踏集团 has 158 published rows, >20 requests);
# per-scope wall-clock is still bounded by --scope-timeout / --max-run-seconds.
DEFAULT_REQUEST_BUDGET = None


class BudgetExhausted(RuntimeError):
    pass


def _read_platform():
    data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return data.get('moka') or {}


def _entry_name(entry):
    return entry if isinstance(entry, str) else str((entry or {}).get('name') or '')


def _load_companies():
    """Enabled tenants only.

    ``"enabled": false`` keeps a surveyed tenant in the config (so the next
    person sees the org/site id and why it is off) without registering the
    company in ``p1_pipeline.REGISTRY`` for the daily run. Same contract as
    ``p1_platform_tupu360``; 毕马威's second tenant ``kpmg/74356`` is parked this
    way so ``NAME_TO_SLUG`` resolves 毕马威 to the shipped ``kpmg/76195``
    deterministically instead of by dict order.
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
    global COMPANIES, NAME_TO_SLUG
    COMPANIES = _load_companies()
    NAME_TO_SLUG = {name: key for key, name in COMPANIES.items()}
    return COMPANIES


def resolve(company):
    if company in COMPANIES:
        return company
    if company in NAME_TO_SLUG:
        return NAME_TO_SLUG[company]
    raise ValueError('unknown moka company: ' + str(company))


def _entry(key):
    entry = _read_platform().get(key) or {}
    return entry if isinstance(entry, dict) else {}


def sites_for(key):
    """[(url, basis)] for the tenant; explicit sites win, else derive from org/siteId."""
    entry = _entry(key)
    explicit = entry.get('sites') or []
    sites = []
    for item in explicit:
        if isinstance(item, str):
            sites.append((item, f'configured Moka portal for {key}'))
        elif isinstance(item, dict) and item.get('url'):
            sites.append((str(item['url']), str(item.get('basis') or f'configured Moka portal for {key}')))
    if sites:
        return sites
    if '/' in key:
        org, site = key.split('/', 1)
        return [(f'https://app.mokahr.com/campus-recruitment/{org}/{site}',
                 f'derived from configured key {key}')]
    return []


def _budget_limit(max_requests):
    if max_requests is not None:
        return int(max_requests)
    raw = os.environ.get('QIUZHAO_PLATFORM_REQUEST_BUDGET')
    return int(raw) if raw and raw.strip() else DEFAULT_REQUEST_BUDGET


def _make_session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    session.headers['User-Agent'] = UA
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=0)))
    return session


def _spend(budget):
    if budget is None:
        return
    if budget['limit'] is not None and budget['used'] >= budget['limit']:
        raise BudgetExhausted('per-tenant request budget reached')
    budget['used'] += 1


def _retrying(budget, call):
    import requests
    _spend(budget)
    try:
        return call()
    except requests.RequestException:
        time.sleep(2.0)
        _spend(budget)
        return call()


def _get(session, url, budget, **kwargs):
    return _retrying(budget, lambda: session.get(url, **kwargs))


def _list_page(session, host, org, site, iv, offset, budget):
    return _retrying(budget, lambda: shared.request_json(
        session, host + '/api/outer/ats-apply/website/jobs/v2',
        {'orgId': org, 'siteId': int(site), 'limit': 50, 'offset': offset,
         'needStat': True, 'locale': 'zh-CN'}, iv))


def _cached_detail(output_dir, ident):
    """Reuse a detail saved by an earlier bounded pass without spending budget."""
    path = Path(output_dir) / f'detail-{ident}.json'
    if not ident or not path.is_file():
        return None
    try:
        detail = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return None
    if detail.get('id') != ident or not shared.text(detail.get('jobDescription')):
        return None
    checked = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return detail, checked, True


def _detail(company, scope, row, host, org, site, iv, output_dir, budget):
    """Network detail fetch, budgeted; already-saved/shared-cache hits are free.

    Budget counts real requests only, so repeated bounded passes resume where the
    previous one stopped instead of re-spending the budget on cached rows.
    """
    ident = row.get('id')
    reused = _cached_detail(output_dir, ident)
    if reused is not None:
        return reused
    if budget['limit'] is not None and budget['used'] >= budget['limit']:
        raise BudgetExhausted('per-tenant request budget reached')
    budget['used'] += 1
    detail, checked, cached = shared.moka_detail_cached(company, scope, row, host, org, site,
                                                        iv, output_dir)
    if cached and budget['limit'] is not None:
        budget['used'] -= 1
    return detail, checked, cached


def _scope_of(row):
    commitment = str(row.get('commitment', ''))
    mode = row.get('hireMode')
    if mode not in (1, 2):
        raise ValueError(f'Unknown official hireMode={mode}; job={row.get("id")}')
    return 'intern' if shared.is_internship(commitment, row.get('title', '')) else ('campus' if mode == 2 else 'social')


def _job(row, detail, detail_checked, cached, site_url, basis, name, scope):
    ident = row['id']
    url = site_url.split('#')[0].rstrip('/') + '#/job/' + ident
    location = ' / '.join(x.get('cityName') or x.get('provinceName') or x.get('country', '')
                          for x in detail.get('locations', []))
    job = shared.job(name, scope, ident, detail.get('title') or row.get('title') or '',
                     url, detail.get('jobDescription') or '', location, detail)
    job['scope_evidence'] = (f'{basis}; hireMode={row.get("hireMode")}; '
                             f'commitment={row.get("commitment", "")}; title={row.get("title", "")}')
    job['recruitment_type_raw'] = {'hireMode': detail.get('hireMode'), 'commitment': detail.get('commitment')}
    shared.apply_moka_status(job, row, detail)
    job['list_checked_at'] = datetime.now(timezone.utc).isoformat()
    job['detail_checked_at'] = detail_checked
    job['detail_cache_reused'] = cached
    project = detail.get('projectFolder') or {}
    settings = project.get('settings') or {}
    job['cohort_raw'] = ''
    job['campaign_cohort_raw'] = shared.text(settings.get('graduateDateLimit') or project.get('name') or '')
    job['campaign_scope'] = 'project'
    job['campaign_url'] = site_url
    opened = str(detail.get('publishedAt') or detail.get('openedAt')
                 or row.get('openedAt') or '')
    job['published_at'] = opened[:16] if opened else ''
    job['source_updated_at'] = str(detail.get('updatedAt') or row.get('updatedAt') or '')
    closed = str(detail.get('closedAt') or row.get('closedAt') or '')
    job['deadline_raw'] = closed
    if '校园大使' in str(detail.get('title') or '') and scope == 'social':
        job['recruitment_type_conflict'] = ('Official hireMode=1 (social), title names campus '
                                            'ambassador; retain source classification for review')
    return job


def collect(company, scope, output_dir, max_requests=None):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    name = COMPANIES[key]
    sites = sites_for(key)
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(sites[0][0] if sites else '')
    jobs = []
    if not sites:
        shared.finish(jobs, coverage)
        coverage['errors'].append('no Moka site configured for ' + key)
        coverage['status'] = 'blocked'
        coverage['complete'] = False
        return {'jobs': [], 'coverage': coverage}
    session = _make_session()
    observed = []
    seen = set()
    selected = []
    list_complete = True
    try:
        for site_url, basis in sites:
            match = SITE_RE.search(site_url)
            if not match:
                raise ValueError('Unrecognized Moka URL: ' + site_url)
            org, site = match.groups()
            host = site_url.split('/')[0] + '//' + site_url.split('/')[2]
            response = _get(session, site_url, budget, timeout=(10, 45))
            response.raise_for_status()
            page_html = _html.unescape(response.text)
            iv_match = re.search(r'"aesIv"\s*:\s*"([^"]+)"', page_html)
            if not iv_match:
                raise ValueError(f'Moka WAF challenge / aesIv missing for {site_url}')
            iv = iv_match.group(1)
            listed = set()
            total = None
            terminal = False
            site_key = org + '/' + site
            counts = coverage.setdefault('source_list_status_counts', {}).setdefault(site_key, {})
            offset = 0
            while True:
                payload = _list_page(session, host, org, site, iv, offset, budget)
                (output_dir / f'{site}-list-{offset}.json').write_text(json.dumps(payload, ensure_ascii=False))
                coverage['pages_scanned'] += 1
                rows = payload.get('jobs') or []
                count = (payload.get('jobStats') or {}).get('total')
                if not rows:
                    if total is not None and len(listed) == total:
                        terminal = True
                        coverage['last_page_evidence'] = (f'site={site};offset={offset};rows=0;'
                                                          f'prior_total={total};terminal_total={count}')
                    elif total is None:
                        terminal = True
                        coverage['last_page_evidence'] = f'site={site};offset={offset};rows=0;total=0'
                    break
                if total is not None and count != total:
                    raise ValueError('Moka total changed during scan')
                total = count
                for row in rows:
                    ident = row.get('id')
                    if not ident or ident in listed:
                        raise ValueError(f'Repeated Moka ID {ident}')
                    listed.add(ident)
                    status = str(row.get('status'))
                    counts[status] = counts.get(status, 0) + 1
                    actual = _scope_of(row)
                    observed.append({'id': ident, 'title': row.get('title'),
                                     'hireMode': row.get('hireMode'),
                                     'commitment': row.get('commitment'),
                                     'status': status, 'scope': actual, 'site': site_key})
                    if actual == scope and ident not in seen:
                        seen.add(ident)
                        selected.append((row, site_url, basis, org, site, host, iv))
                offset += 50
                time.sleep(0.2)
            if not terminal or (total is not None and len(listed) != total):
                list_complete = False
                raise ValueError(f'Incomplete list site={site}: observed={len(listed)}, total={total}')
            coverage.setdefault('source_list_totals', {})[site_key] = total
        coverage['expected_total'] = len(seen)
        coverage['list_observed_ids'] = sorted({o['id'] for o in observed if o['scope'] == scope})
        coverage['list_observed_titles'] = sorted({o['title'] for o in observed
                                                   if o['scope'] == scope and o['title']})
        for row, site_url, basis, org, site, host, iv in selected:
            try:
                detail, detail_checked, cached = _detail(name, scope, row, host, org, site,
                                                         iv, output_dir, budget)
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                break
            except Exception as error:
                coverage['errors'].append(f'detail {row.get("id")}: {error}')
                continue
            ident = row['id']
            if detail.get('id') != ident or not shared.text(detail.get('jobDescription')):
                coverage['errors'].append(f'Incomplete Moka detail {ident}')
                continue
            (output_dir / f'detail-{ident}.json').write_text(json.dumps(detail, ensure_ascii=False))
            jobs.append(_job(row, detail, detail_checked, cached, site_url, basis, name, scope))
            if len(jobs) % 100 == 0:
                shared.partial_checkpoint(jobs, coverage, name, scope, output_dir)
        coverage['source_status_counts'] = {
            state: sum(1 for j in jobs if str(j.get('source_list_status_raw')) == state)
            for state in sorted({str(j.get('source_list_status_raw')) for j in jobs})}
        coverage['active_jobs'] = sum(j.get('source_is_active') is True for j in jobs)
        coverage['inactive_jobs'] = sum(j.get('source_is_active') is False for j in jobs)
        coverage['pagination_exhausted'] = list_complete
        coverage['detail_complete'] = (not coverage['errors'] and len(jobs) == len(selected))
        coverage['evidence'] = sorted(p.name for p in output_dir.glob('*-list-*.json'))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = ('Official Moka hireMode 1 social/2 campus; internship '
                                      'commitment/title; requested=' + scope)
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': sites[0][0],
                                     'params': {'sites': [s[0] for s in sites], 'limit': 50,
                                                'offset': 0, 'needStat': True, 'moka_key': key}}
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
    except Exception as error:
        coverage['errors'].append(f'{type(error).__name__}: {error}')
    # List-phase observations survive an early budget stop; they are the
    # id/title evidence used for the dedicated-vs-generic superset check.
    if observed and 'list_observed_ids' not in coverage:
        coverage['list_observed_ids'] = sorted({o['id'] for o in observed if o['scope'] == scope})
        coverage['list_observed_titles'] = sorted({o['title'] for o in observed
                                                   if o['scope'] == scope and o['title']})
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
