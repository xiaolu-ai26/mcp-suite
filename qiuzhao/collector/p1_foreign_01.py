"""Foreign-company dedicated adapters, batch 2 — Dayee (hotjob.cn).

The Big Four and a number of other foreign employers in China publish their
campus/intern/social openings through Dayee's multi-tenant portal
(``<host>/wecruit/...``, branded ``hotjob.cn``). Unlike Beisen/Moka there is no
public per-tenant list endpoint family, so this module plays the same role for
Dayee that ``p1_banks_01`` plays for the banks: one parser, one config block,
one company = one line in ``p1_platform_companies.json``.

Official contract (read off the tenant SPA bundle, not guessed):

* ``POST /wecruit/positionInfo/listPosition/<SU>`` (form-encoded)
  ``recruitType=1|campus, 2|society, 12|intern, 13|overseas`` plus
  ``currentPage``/``pageSize``; returns ``data.pageForm.totalPage/pageData``.
* ``POST /wecruit/positionInfo/listPositionDetail/<SU>`` (form-encoded)
  ``postId`` + ``recruitType``; returns the full official posting.

Everything is public and account-free. Data rules follow the batch-1 foreign
receipt: only official fields are written, ``published_at`` comes from
``publishDate``, ``deadline_raw`` from ``endDate`` (empty when absent) and
``cohort_raw`` is always empty — Dayee has no cohort field and we never infer a
graduation year.

Politeness: every outbound request is spaced by
``QIUZHAO_PLATFORM_REQUEST_INTERVAL`` seconds (default 0, verification runs pass
2.0) and counted against ``QIUZHAO_PLATFORM_REQUEST_BUDGET`` /
``max_requests`` (production default: no cap).
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

MODULE_PATH = 'qiuzhao.collector.p1_foreign_01'
CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
CONFIG_KEY = 'dayee'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
DEFAULT_REQUEST_BUDGET = None
# Official SPA mapping ee(): society=2, campus=1, intern=12, overseas=13.
RECRUIT_TYPE = {'campus': 1, 'social': 2, 'intern': 12, 'overseas': 13}
ISSUE_RE = re.compile(r'(SU[0-9a-fA-F]{16,})')
DEFAULT_HOST = 'wecruit.hotjob.cn'
DETAIL_VERIFY_LIMIT = 0  # 0 = fetch every selected posting's official detail


class BudgetExhausted(RuntimeError):
    pass


def _read_platform():
    data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return data.get(CONFIG_KEY) or {}


def _entry_name(entry):
    return entry if isinstance(entry, str) else str((entry or {}).get('name') or '')


def _entry_host(entry, key):
    if isinstance(entry, dict) and entry.get('host'):
        return str(entry['host'])
    issue = ISSUE_RE.search(str(key))
    return DEFAULT_HOST if issue else DEFAULT_HOST


def _load_companies():
    companies = {}
    for key, entry in _read_platform().items():
        if isinstance(entry, dict) and entry.get('enabled') is False:
            continue  # parked survey line: kept on file, never registered
        name = _entry_name(entry)
        declared = str((entry or {}).get('su') or '') if isinstance(entry, dict) else ''
        issue = ISSUE_RE.search(declared) or ISSUE_RE.search(str(key))
        if name and issue:
            companies[issue.group(1)] = name
    return companies


COMPANIES = _load_companies()
NAME_TO_SU = {name: su for su, name in COMPANIES.items()}


def reload_config():
    global COMPANIES, NAME_TO_SU
    COMPANIES = _load_companies()
    NAME_TO_SU = {name: su for su, name in COMPANIES.items()}
    return COMPANIES


def merged_registry():
    """Company name -> adapter module path for the pipeline REGISTRY."""
    return {name: MODULE_PATH for name in COMPANIES.values()}


def resolve(company):
    if company in COMPANIES:
        return company
    if company in NAME_TO_SU:
        return NAME_TO_SU[company]
    raise ValueError('unknown Dayee company: ' + str(company))


def _host_for(su):
    entry = _read_platform().get(su) or {}
    return _entry_host(entry, su)


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


def _spend(budget):
    if budget is None:
        return
    if budget['limit'] is not None and budget['used'] >= budget['limit']:
        raise BudgetExhausted('per-tenant request budget reached')
    budget['used'] += 1


def _post(session, host, path, data, budget, referer):
    """POST one official Dayee endpoint, honouring the spacing and the budget."""
    import requests
    url = f'https://{host}{path}'
    headers = {'Content-Type': 'application/x-www-form-urlencoded',
               'Accept': 'application/json, text/plain, */*',
               'Referer': referer,
               'X-Requested-With': 'XMLHttpRequest'}
    def call():
        _spend(budget)
        interval = _min_interval()
        if interval:
            time.sleep(interval)
        response = session.post(url, data=urlencode(data), headers=headers, timeout=(10, 40))
        response.raise_for_status()
        return response.json()
    try:
        return call()
    except (requests.RequestException, ValueError):
        time.sleep(2.0)
        return call()


def _list_page(session, host, su, recruit_type, page, budget, referer):
    return _post(session, host, f'/wecruit/positionInfo/listPosition/{su}',
                 {'recruitType': recruit_type, 'currentPage': page, 'pageSize': 10},
                 budget, referer)


def _detail(session, host, su, recruit_type, post_id, budget, referer):
    return _post(session, host, f'/wecruit/positionInfo/listPositionDetail/{su}',
                 {'postId': post_id, 'recruitType': recruit_type}, budget, referer)


def _text(value):
    return shared.text(value)


def _job(name, scope, su, host, recruit_type, row, detail):
    ident = str(row.get('postId') or '')
    title = _text(row.get('postName') or detail.get('postName'))
    url = (f'https://{host}/{su}/mc/position/detail?postId={ident}'
           f'&recruitType={recruit_type}')
    description = '\n'.join(x for x in (
        _text(detail.get('workContent')), _text(detail.get('serviceCondition')),
        _text(detail.get('applyPositionContent'))) if x)
    location = _text(row.get('workPlaceStr') or detail.get('workPlaceStr'))
    raw = dict(row)
    raw.update({k: v for k, v in detail.items() if k not in raw})
    record = shared.job(name, scope, ident, title, url, description, location, raw)
    record['scope_evidence'] = (f'Official Dayee recruitType={recruit_type} '
                                f'({scope}); postTypeName={row.get("postTypeName", "")}')
    record['recruitment_type_raw'] = {'recruitType': recruit_type,
                                      'postTypeName': row.get('postTypeName')}
    record['published_at'] = _text(row.get('publishDate') or detail.get('publishDate'))[:16]
    record['deadline_raw'] = _text(row.get('endDate') or detail.get('endDate'))
    record['source_updated_at'] = ''
    record['cohort_raw'] = ''
    record['campaign_cohort_raw'] = _text(row.get('projectName'))
    record['campaign_scope'] = 'project' if row.get('projectName') else ''
    record['campaign_url'] = url
    record['list_checked_at'] = datetime.now(timezone.utc).isoformat()
    record['detail_checked_at'] = datetime.now(timezone.utc).isoformat()
    return record


def collect(company, scope, output_dir, max_requests=None):
    """Collect one Dayee tenant/scope.

    The list and the official detail are interleaved on purpose: a politeness
    budget (``QIUZHAO_PLATFORM_REQUEST_BUDGET``) can be smaller than
    ``pages + postings`` for a large tenant, and interleaving guarantees that a
    budget-stopped run still publishes the postings it did read as ``partial``
    instead of throwing away every request. Without a budget the walk is the same
    full list scan followed by every detail, so ``complete`` still requires
    ``pagination_exhausted``.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    if scope not in RECRUIT_TYPE:
        raise ValueError('Dayee has no official channel for scope=' + str(scope))
    su = resolve(company)
    name = COMPANIES[su]
    host = _host_for(su)
    recruit_type = RECRUIT_TYPE[scope]
    referer = f'https://{host}/{su}/mc/position/{scope}'
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(referer)
    jobs = []
    observed = []
    seen = set()
    list_complete = False
    session = _make_session()
    try:
        page = 1
        while True:
            payload = _list_page(session, host, su, recruit_type, page, budget, referer)
            state = str(payload.get('state'))
            if state not in ('200', '0'):
                raise ValueError(f'Dayee list error state={state} msg={payload.get("msg")}')
            (output_dir / f'{su}-list-{scope}-{page}.json').write_text(
                json.dumps(payload, ensure_ascii=False))
            coverage['pages_scanned'] += 1
            page_form = ((payload.get('data') or {}).get('pageForm') or {})
            rows = page_form.get('pageData') or []
            total_page = page_form.get('totalPage')
            if not rows:
                list_complete = True
                coverage['last_page_evidence'] = (f'su={su};scope={scope};page={page};rows=0;'
                                                  f'totalPage={total_page}')
                break
            new_in_page = 0
            for row in rows:
                ident = str(row.get('postId') or '')
                if not ident:
                    raise ValueError('Dayee row without postId')
                if ident in seen:
                    # Dayee pages can repeat an already-listed posting (observed on
                    # 益海嘉里 / ZURU). It is a duplicate row, not a new posting:
                    # skip it, and treat a page with no new posting as the terminal
                    # page so a repeating pagination can never loop forever.
                    continue
                seen.add(ident)
                new_in_page += 1
                observed.append({'id': ident, 'title': row.get('postName'),
                                 'postTypeName': row.get('postTypeName'),
                                 'recruitType': row.get('recruitType')})
                try:
                    detail_payload = _detail(session, host, su, recruit_type, ident, budget, referer)
                except BudgetExhausted:
                    coverage['request_budget_exhausted'] = True
                    raise
                except Exception as error:  # one bad posting never kills the tenant
                    coverage['errors'].append(f'detail {ident}: {type(error).__name__}: {error}')
                    continue
                detail = detail_payload.get('data') or {}
                if str(detail.get('postId') or '') != ident:
                    coverage['errors'].append(f'Incomplete Dayee detail {ident}')
                    continue
                (output_dir / f'detail-{ident}.json').write_text(
                    json.dumps(detail, ensure_ascii=False))
                jobs.append(_job(name, scope, su, host, recruit_type, row, detail))
                if len(jobs) % 100 == 0:
                    shared.partial_checkpoint(jobs, coverage, name, scope, output_dir)
            if new_in_page == 0:
                coverage['last_page_evidence'] = (
                    f'su={su};scope={scope};page={page};rows={len(rows)};new=0;'
                    f'totalPage={total_page};repeated_page=true')
                coverage['note'] = ('Dayee pagination repeated an already-listed page; '
                                    'listing completeness cannot be confirmed')
                break
            # Only a positive totalPage ends the scan; 0 with real rows would end it
            # after page 1 and still claim the listing was read to the end.
            if isinstance(total_page, int) and total_page > 0 and page >= total_page:
                list_complete = True
                break
            page += 1
        coverage['expected_total'] = len(seen)
        coverage['list_observed_ids'] = sorted(o['id'] for o in observed)
        coverage['list_observed_titles'] = sorted(o['title'] for o in observed if o['title'])
        coverage['pagination_exhausted'] = list_complete
        coverage['detail_complete'] = (not coverage['errors'] and len(jobs) == len(seen))
        coverage['evidence'] = sorted(p.name for p in output_dir.glob('*.json'))
        coverage['evidence_files'] = coverage['evidence']
        coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': referer,
                                     'params': {'su': su, 'recruitType': recruit_type,
                                                'pageSize': 10, 'scope': scope}}
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
        if 'list_observed_ids' not in coverage and observed:
            coverage['expected_total'] = len(seen)
            coverage['list_observed_ids'] = sorted(o['id'] for o in observed)
            coverage['list_observed_titles'] = sorted(o['title'] for o in observed if o['title'])
    except Exception as error:
        coverage['errors'].append(f'{type(error).__name__}: {error}')
    if observed and 'list_observed_ids' not in coverage:
        coverage['list_observed_ids'] = sorted(o['id'] for o in observed)
        coverage['list_observed_titles'] = sorted(o['title'] for o in observed if o['title'])
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
