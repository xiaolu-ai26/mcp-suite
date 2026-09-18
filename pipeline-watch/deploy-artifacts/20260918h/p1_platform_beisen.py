"""Platform-level Beisen (zhiye.com) campus/intern/social adapter.

One adapter covers every tenant: adding a company is one line in
``p1_platform_companies.json``. Contract matches the per-company
``p1_sources_*`` modules: ``COMPANIES`` + ``collect(company, scope, output_dir)``
returning ``{'jobs': [...], 'coverage': {...}}`` and writing the same evidence.

Request budget: ``QIUZHAO_PLATFORM_REQUEST_BUDGET`` (or the ``max_requests``
argument) caps network calls per tenant per run. Production defaults to no cap
(``DEFAULT_REQUEST_BUDGET = None``); the offline verification runs set 20 only to
stay polite in front of the Beisen WAF, which would truncate a large tenant.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
MODULE_PATH = 'qiuzhao.collector.p1_platform_beisen'
DEFAULT_CATEGORIES = {'1': 'social', '2': 'campus', '3': 'intern'}
IGNORE = '__ignore__'
FIELDS = ['LocId', 'Degree', 'Kind', 'OrgId', 'Category', 'PostDate', 'HeadCount',
          'EndTime', 'YearsOfWorking', 'Duty', 'Require']
# Details are fetched for verification (and as a fallback when the list omits
# role text), never above the remaining request budget.
DETAIL_VERIFY_LIMIT = 5
# Production default: no cap. Budgeting is an opt-in politeness guard; the offline
# verification runs pass 20 on purpose via QIUZHAO_PLATFORM_REQUEST_BUDGET /
# max_requests. A low default would truncate a healthy tenant: 安踏集团 alone has
# 158 published rows, which needs far more than 20 list/detail requests. A run is
# still bounded per scope by the pipeline's --scope-timeout / --max-run-seconds.
DEFAULT_REQUEST_BUDGET = None
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


class BudgetExhausted(RuntimeError):
    pass


def _read_platform():
    data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return data.get('beisen') or {}


def _entry_name(entry):
    return entry if isinstance(entry, str) else str((entry or {}).get('name') or '')


def _load_companies():
    companies = {}
    for key, entry in _read_platform().items():
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
    from qiuzhao.collector import p1_platform_moka as moka
    registry = {name: MODULE_PATH for name in COMPANIES.values()}
    registry.update({name: moka.MODULE_PATH for name in moka.COMPANIES.values()})
    return registry


def resolve(company):
    if company in COMPANIES:
        return company
    if company in NAME_TO_SLUG:
        return NAME_TO_SLUG[company]
    raise ValueError('unknown beisen company: ' + str(company))


def _entry(key):
    entry = _read_platform().get(key) or {}
    return entry if isinstance(entry, dict) else {}


def host_for(key):
    return str(_entry(key).get('host') or f'https://{key}.zhiye.com')


def categories_for(key):
    mapping = dict(DEFAULT_CATEGORIES)
    for category in _entry(key).get('ignore_categories') or []:
        mapping[str(category)] = IGNORE
    for category, scope in (_entry(key).get('categories') or {}).items():
        mapping[str(category)] = scope
    return mapping


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


def _has_budget(budget):
    return budget is None or budget['limit'] is None or budget['used'] < budget['limit']


def _spend(budget):
    if budget is None:
        return
    if budget['limit'] is not None and budget['used'] >= budget['limit']:
        raise BudgetExhausted('per-tenant request budget reached')
    budget['used'] += 1


def _send(budget, call, *args, **kwargs):
    """One polite retry (429/WAF/connection), then give up and let the caller block."""
    import requests
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


def _get(session, url, budget, **kwargs):
    return _send(budget, session.get, url, **kwargs)


def _post(session, url, budget, **kwargs):
    return _send(budget, session.post, url, **kwargs)


def _date(value):
    text = str(value or '')
    if text.startswith('0001') or not text.strip():
        return ''
    match = re.match(r'(\d{4}-\d{2}-\d{2})', text)
    if not match:
        return text[:32]
    year = int(match.group(1)[:4])
    if year >= 2100:  # platform sentinel such as 2222-02-02 means "no deadline"
        return ''
    return match.group(1)


def _description(row):
    duty = shared.text((row or {}).get('Duty'))
    require = shared.text((row or {}).get('Require'))
    if not duty and not require:
        return ''
    return duty + '\n任职要求\n' + require


def _job_from(row, name, scope, host, key, detail_source):
    ident = row['Id']
    duty = shared.text(row.get('Duty'))
    require = shared.text(row.get('Require'))
    description = (duty + '\n任职要求\n' + require).strip()
    locations = row.get('LocNames') or []
    location = ' / '.join(str(x) for x in locations)
    job = shared.job(name, scope, ident, row.get('JobAdName') or '',
                     host + '/' + scope + '/detail?jobAdId=' + ident, description, location, row)
    job['recruitment_type_raw'] = {'CategoryId': row.get('CategoryId'), 'Category': row.get('Category')}
    job['scope_evidence'] = (f'Official Beisen CategoryId={row.get("CategoryId")}; '
                             f'Category={row.get("Category")}; tenant={key}')
    published = _date(row.get('PostDate'))
    job['published_at'] = published
    job['publication_date'] = published
    job['source_updated_at'] = _date(row.get('ChangeDate'))
    deadline = _date(row.get('EndTime'))
    job['deadline_raw'] = deadline
    if deadline:
        job['deadline'] = deadline
        job['deadline_type'] = 'explicit'
    job['detail_source'] = detail_source
    job['source_publication_field'] = 'PostDate' if published else ''
    return job


def collect(company, scope, output_dir, max_requests=None):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company)
    name = COMPANIES[key]
    host = host_for(key)
    categories = categories_for(key)
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(host)
    coverage['source_url'] = host
    jobs = []
    session = _make_session()
    unmapped = {}
    try:
        page = _get(session, host, budget, timeout=(10, 30))
        page.encoding = 'utf-8'
        (output_dir / 'official-entry.html').write_text(page.text)
        portal_ids = set(re.findall(r'"PortalId"\s*:\s*"([^"]+)"', page.text))
        if len(portal_ids) != 1:
            raise ValueError('Official Beisen PortalId missing or ambiguous (WAF challenge?)')
        portal = portal_ids.pop()
        host = urlsplit(page.url).scheme + '://' + urlsplit(page.url).netloc
        coverage['source_url'] = host
        body = {'PortalId': portal, 'PageIndex': 0, 'PageSize': 50, 'Category': [],
                'KeyWords': '', 'SpecialType': 0, 'DisplayFields': FIELDS}

        def list_page(index):
            payload = dict(body, PageIndex=index)
            response = _post(session, host + '/api/Jobad/GetJobAdPageList', budget,
                             json=payload, timeout=(10, 45))
            payload_json = response.json()
            (output_dir / f'list-{index}.json').write_text(json.dumps(payload_json, ensure_ascii=False))
            coverage['pages_scanned'] += 1
            if payload_json.get('Code') != 200:
                raise ValueError(str(payload_json)[:300])
            return payload_json

        selected = []
        seen = set()
        total = None
        index = 0
        while True:
            payload_json = list_page(index)
            rows = payload_json.get('Data') or []
            count = payload_json.get('Count')
            if not rows:
                coverage['pagination_exhausted'] = True
                coverage['last_page_evidence'] = (f'index={index};rows=0;'
                                                  + (f'prior_total={total};' if total is not None else '')
                                                  + f'total={count}')
                break
            for row in rows:
                ident = row.get('Id')
                if not ident or ident in seen:
                    raise ValueError('Repeated Beisen pagination GUID')
                seen.add(ident)
                actual = str(row.get('CategoryId'))
                if actual not in categories:
                    unmapped[actual] = row.get('Category')
                    continue
                if categories[actual] == IGNORE:
                    continue
                if categories[actual] == scope:
                    selected.append(row)
            if total is not None and count != total:
                raise ValueError('Official count changed during scan')
            total = count
            index += 1
        if total is not None and len(seen) != total:
            raise ValueError(f'Incomplete list: {len(seen)} vs {total}')
        coverage['list_total'] = total
        coverage['expected_total'] = len(selected)
        coverage['unmapped_categories'] = {k: v for k, v in unmapped.items()}
        for category, label in sorted(unmapped.items()):
            coverage['errors'].append(f'Unknown official Beisen category {category}: {label}')

        for position, row in enumerate(selected):
            description = _description(row)
            verified = False
            if _has_budget(budget) and (position < DETAIL_VERIFY_LIMIT or not description):
                try:
                    params = {'jobAdId': row['Id'], 'portalId': portal,
                              'category': str(row.get('CategoryId')),
                              'displayFields': json.dumps(FIELDS)}
                    response = _get(session, host + '/api/JobAd/GetJobAdInfo', budget,
                                    params=params, timeout=(10, 45))
                    detail_env = response.json()
                    (output_dir / f'detail-{row["Id"]}.json').write_text(
                        json.dumps(detail_env, ensure_ascii=False))
                    if detail_env.get('Code') != 200:
                        coverage.setdefault('detail_fetch_errors', []).append(
                            f'{row["Id"]}: {str(detail_env)[:200]}')
                    else:
                        detail = detail_env.get('Data') or {}
                        if (detail.get('Id') != row['Id']
                                or str(detail.get('CategoryId')) != str(row.get('CategoryId'))):
                            coverage.setdefault('detail_fetch_errors', []).append(
                                f'{row["Id"]}: detail identity/category mismatch')
                        else:
                            if not description:
                                row = detail
                                description = _description(row)
                            verified = True
                except BudgetExhausted:
                    coverage['request_budget_exhausted'] = True
                    break
                except Exception as error:  # official list remains authoritative
                    coverage.setdefault('detail_fetch_errors', []).append(
                        f'{row["Id"]}: {type(error).__name__}: {error}'[:300])
            if not description:
                coverage['errors'].append('No official description for ' + str(row.get('Id')))
                continue
            job = _job_from(row, name, scope, host, key,
                            'official_detail' if verified else 'official_list')
            if verified:
                job['detail_verified'] = True
            jobs.append(job)
        coverage['detail_verified_count'] = sum(1 for j in jobs if j.get('detail_verified'))
        coverage['list_only_count'] = sum(1 for j in jobs if not j.get('detail_verified'))
        coverage['detail_complete'] = (not coverage['errors']
                                       and len(jobs) == len(selected))
        coverage['evidence'] = (['official-entry.html']
                                + sorted(p.name for p in output_dir.glob('list-*.json'))
                                + sorted(p.name for p in output_dir.glob('detail-*.json')))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_evidence'] = (f'Official Beisen tenant={key}; verified category mapping={categories}; '
                                      f'requested={scope}')
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': host,
                                     'params': {'PortalId': portal, 'Category': [],
                                                'DisplayFields': FIELDS, 'tenant': key}}
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
