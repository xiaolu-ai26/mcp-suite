"""Alibaba-family campus recruitment headless adapter (multi-entity).

The Alibaba group careers platform (``campus-talent.alibaba.com``) renders its
position list in a SPA and gates the JSON search behind an ``XSRF-TOKEN`` cookie
that the page JS sets. Plain HTTP clients get a fresh session without the token
and are rejected by the WAF, so the first request must be issued inside a real
headless Chromium page; afterwards the same page context carries the cookie plus
the ``_csrf`` query parameter.

The same platform also powers the independent subsidiary campuses
(``talent.taotian.com`` / ``careers.aliyun.com`` / ``talent.amap.com`` /
``talent.ele.me`` / ``talent.cainiao.com``).  The Alibaba group site exposes a
``searchCondition/list`` dictionary whose ``customDept`` node enumerates the
business groups (淘天集团 / 阿里云 / 高德地图 / 淘宝闪购 ...).  Selecting one
expands to a comma-separated list of leaf department codes which
``/position/search`` accepts as ``customDeptCode``.  That is how each entity is
registered as an independent company while still reading the official platform.

Entities and their entries (verified read-only 2026-09-18):

* 阿里巴巴   ``campus-talent.alibaba.com/campus/position/``  batch 100000760001 (2027届应届生)
* 淘天       same platform, ``customDeptCode`` = 淘天集团 leaves
* 阿里云     same platform, ``customDeptCode`` = 阿里云 leaves
* 高德       same platform, ``customDeptCode`` = 高德地图 leaves
* 饿了么     same platform, ``customDeptCode`` = 淘宝闪购 leaves (品牌已更名)
* 菜鸟       ``talent.cainiao.com/campus/recruitment-position`` 独立站点

Contract: identical to ``p1_sources_*`` -- ``collect(company, scope, output_dir)``
returns ``{'jobs': [...], 'coverage': {...}}`` and writes the same on-disk
evidence plus ``result.json``.  ``merged_registry()`` lets ``p1_pipeline`` append
the entities without editing the hardcoded 50 ordinals.

Politeness: every page/request goes through :class:`HeadlessTransport`, which
sleeps ``QIUZHAO_ALIBABA_MIN_INTERVAL`` seconds (default 2.0) and stops at
``QIUZHAO_ALIBABA_REQUEST_BUDGET`` (default 40) per entity.  No login, no
CAPTCHA solving, no signature bypass; public listing pages only.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import re
import time
from pathlib import Path

MODULE_PATH = 'qiuzhao.collector.alibaba_headless'

SCOPES = {'campus': '校园招聘', 'intern': '实习招聘', 'social': '社会招聘'}
CHANNEL = 'campus_group_official_site'
PAGE_SIZE = 50
DEFAULT_REQUEST_BUDGET = 40
DEFAULT_MIN_INTERVAL = 2.0
MAX_PAGES_PER_BATCH = 40

# Which batch buckets serve which scope on the platform.
SCOPE_BATCH_KEYS = {'campus': ('graduate', 'topTalentPlan'), 'intern': ('internship',), 'social': ()}
# categoryType the platform SPA sends for each scope (batchId still decides membership).
SCOPE_CATEGORY = {'campus': 'freshman', 'intern': 'intern', 'social': 'social'}

_DETAIL_TPL = 'https://campus-talent.alibaba.com/campus/position-detail?jobId={id}'

ENTITIES = {
    '阿里巴巴': {
        'base': 'https://campus-talent.alibaba.com',
        'listing': '/campus/position/',
        'listing_query': '?batchId=100000760001',
        'dept_label': None,
        'batch_discovery': True,
        'recruitment_unit': '阿里巴巴集团控股有限公司',
        'source_name': '阿里巴巴校园招聘官方网站',
        'detail_tpl': _DETAIL_TPL,
    },
    '淘天': {
        'base': 'https://campus-talent.alibaba.com',
        'listing': '/campus/position/',
        'listing_query': '?batchId=100000760001',
        'dept_label': '淘天集团',
        'batch_discovery': True,
        'recruitment_unit': '淘天集团',
        'source_name': '淘天集团校园招聘（阿里巴巴集团招聘平台）',
        'detail_tpl': _DETAIL_TPL,
    },
    '阿里云': {
        'base': 'https://campus-talent.alibaba.com',
        'listing': '/campus/position/',
        'listing_query': '?batchId=100000760001',
        'dept_label': '阿里云',
        'batch_discovery': True,
        'recruitment_unit': '阿里云',
        'source_name': '阿里云校园招聘（阿里巴巴集团招聘平台）',
        'detail_tpl': _DETAIL_TPL,
    },
    '高德': {
        'base': 'https://campus-talent.alibaba.com',
        'listing': '/campus/position/',
        'listing_query': '?batchId=100000760001',
        'dept_label': '高德地图',
        'batch_discovery': True,
        'recruitment_unit': '高德软件有限公司',
        'source_name': '高德地图校园招聘（阿里巴巴集团招聘平台）',
        'detail_tpl': _DETAIL_TPL,
    },
    '饿了么': {
        'base': 'https://campus-talent.alibaba.com',
        'listing': '/campus/position/',
        'listing_query': '?batchId=100000760001',
        # 饿了么已品牌化为「淘宝闪购」，官方平台业务集团名以站点为准。
        'dept_label': '淘宝闪购',
        'batch_discovery': True,
        'recruitment_unit': '拉扎斯网络科技（上海）有限公司',
        'source_name': '饿了么（淘宝闪购）校园招聘（阿里巴巴集团招聘平台）',
        'detail_tpl': _DETAIL_TPL,
    },
    '菜鸟': {
        'base': 'https://talent.cainiao.com',
        'listing': '/campus/recruitment-position',
        'listing_query': '?batchCode=freshman',
        'dept_label': None,
        'batch_discovery': False,
        # batchCode -> numeric batchId observed in the official page requests.
        'fallback_batches': {'campus': ['4000000250'], 'intern': ['4000000249']},
        'batch_names': {'4000000250': '菜鸟生计划', '4000000249': '实习生计划',
                        '123123213': '菜鸟星计划', '4000000245': '鸿翎生计划'},
        'recruitment_unit': '菜鸟网络科技有限公司',
        'source_name': '菜鸟校园招聘官方网站',
        'detail_tpl': 'https://talent.cainiao.com/campus/recruitment-position?batchCode={batch}',
    },
}


class BudgetExhausted(RuntimeError):
    """Raised when the per-run request budget is reached; callers keep partial rows."""


class HeadlessUnavailable(RuntimeError):
    """Playwright/Chromium is not installed; caller should degrade gracefully."""


def merged_registry():
    """Company name -> adapter module path for the pipeline REGISTRY."""
    return {name: MODULE_PATH for name in ENTITIES}


def _budget_limit(max_requests):
    if max_requests is not None:
        return int(max_requests)
    raw = os.environ.get('QIUZHAO_ALIBABA_REQUEST_BUDGET')
    return int(raw) if raw and raw.strip() else DEFAULT_REQUEST_BUDGET


def _min_interval(delay):
    if delay is not None:
        return float(delay)
    raw = os.environ.get('QIUZHAO_ALIBABA_MIN_INTERVAL')
    return float(raw) if raw and raw.strip() else DEFAULT_MIN_INTERVAL


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _ms_date(value):
    """Official epoch-millisecond field -> Asia/Shanghai date; blank when absent."""
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return ''
    if ms <= 0:
        return ''
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d')


def _parse_list(raw):
    """Alibaba list fields arrive as Python/JSON-ish list strings."""
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    if not raw:
        return []
    text = str(raw).strip()
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        value = None
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [part.strip() for part in re.split(r'[,，、;；/]', text) if part.strip()]


def _record(output_dir, name, payload):
    (Path(output_dir) / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return name


class HeadlessTransport:
    """Playwright headless Chromium; lazy import so the pipeline imports offline."""

    def __init__(self, delay=None, max_requests=None, timeout_ms=45000):
        self.delay = _min_interval(delay)
        self.limit = _budget_limit(max_requests)
        self.used = 0
        self.timeout_ms = timeout_ms
        self.base = None
        self._pw = None
        self._browser = None
        self._context = None
        self.page = None
        self._last = 0.0

    # -- browser lifecycle -------------------------------------------------
    def _launch(self, pw):
        errors = []
        for kwargs in ({}, {'channel': 'chrome'}):
            try:
                return pw.chromium.launch(headless=True, args=['--no-sandbox'], **kwargs)
            except Exception as error:  # try the system Chrome channel next
                errors.append(f'{kwargs or "bundled"}: {type(error).__name__}: {error}')
        raise HeadlessUnavailable('chromium launch failed; ' + ' | '.join(errors)[:400])

    def _ensure(self, base):
        if self.page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except Exception as error:
            raise HeadlessUnavailable(f'playwright not importable: {error}') from error
        try:
            self._pw = sync_playwright().start()
            self._browser = self._launch(self._pw)
            self._context = self._browser.new_context(
                locale='zh-CN',
                user_agent=('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                            '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'))
            self._context.set_default_timeout(self.timeout_ms)
            self.page = self._context.new_page()
            self.base = base
        except HeadlessUnavailable:
            self.close()
            raise
        except Exception as error:
            self.close()
            raise HeadlessUnavailable(f'chromium launch failed: {error}') from error

    def open(self, url):
        self._ensure(_origin(url))
        self._charge()
        self.page.goto(url, wait_until='domcontentloaded')
        try:
            self.page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass

    def _charge(self):
        if self.limit is not None and self.used >= self.limit:
            raise BudgetExhausted(f'request budget {self.limit} reached')
        self.used += 1

    def _throttle(self):
        time.sleep(max(0.0, self.delay - (time.monotonic() - self._last)))
        self._last = time.monotonic()

    def _token(self):
        for cookie in (self._context.cookies() if self._context else []):
            if cookie.get('name') == 'XSRF-TOKEN':
                return cookie.get('value') or ''
        return ''

    def post_json(self, path, payload):
        self._ensure(self.base)
        self._charge()
        self._throttle()
        response = self.page.request.post(
            self.base + path + '?_csrf=' + self._token(),
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            return response.status, response.json()
        except Exception:
            return response.status, {'_non_json': response.text()[:500]}

    def budget(self):
        return {'limit': self.limit, 'used': self.used}

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


def _origin(url):
    match = re.match(r'^(https?://[^/]+)', url or '')
    return match.group(1) if match else url


def make_transport(max_requests=None, delay=None):
    return HeadlessTransport(delay=delay, max_requests=max_requests)


def resolve_dept_code(conditions, label):
    """Join the leaf codes of an official ``customDept`` business group."""
    if not label:
        return '', None
    content = (conditions or {}).get('content') or {}
    for node in content.get('searchItems') or []:
        if node.get('type') != 'customDept':
            continue
        for group in node.get('items') or []:
            if str(group.get('label') or '') != label:
                continue
            children = [str(c.get('value')) for c in (group.get('children') or []) if c.get('value')]
            if children:
                return ','.join(children), group.get('value')
            return str(group.get('value') or ''), group.get('value')
    return '', None


def batches_for_scope(list_batch, cfg, scope):
    """Resolve official batch ids for a scope from listBatch, else the config."""
    if cfg.get('batch_discovery') and isinstance(list_batch, dict) and list_batch.get('success'):
        content = list_batch.get('content') or {}
        seen, found = set(), []
        for key in SCOPE_BATCH_KEYS.get(scope, ()):
            for batch in content.get(key) or []:
                bid = str(batch.get('id') or '')
                if bid and bid not in seen:
                    seen.add(bid)
                    found.append({'id': bid, 'name': (batch.get('name') or '').strip(),
                                  'remark': (batch.get('remark') or '').strip()})
        if found:
            return found
    names = cfg.get('batch_names') or {}
    return [{'id': str(bid), 'name': names.get(str(bid), ''), 'remark': ''}
            for bid in (cfg.get('fallback_batches') or {}).get(scope, [])]


def _row_to_job(raw, cfg, scope, checked, batch, source_url):
    pid = str(raw.get('id') or raw.get('positionId') or '')
    title = (raw.get('name') or raw.get('title') or '').strip()
    detail = (cfg.get('detail_tpl') or '').format(id=pid, batch=batch.get('id', ''))
    description = (raw.get('description') or '').strip()
    requirement = (raw.get('requirement') or '').strip()
    combined = description
    if requirement:
        combined = (description + '\n任职要求\n' + requirement) if description else requirement
    graduation = raw.get('graduationTime')
    if not isinstance(graduation, dict):
        graduation = {}
    batch_name = (raw.get('batchName') or batch.get('name') or '').strip()
    record = {
        'id': f'alibaba:{pid}',
        'source_record_id': pid,
        'title': title,
        'job_title': title,
        'recruitment_unit': cfg['recruitment_unit'],
        'recruitment_type': SCOPES[scope],
        'source_url': detail,
        'detail_url': detail,
        'application_url': detail,
        'job_listing_url': source_url,
        'campaign_url': source_url,
        'description_raw': combined[:20000],
        'job_category': (raw.get('categoryName') or raw.get('categories') or ''),
        'cities': _parse_list(raw.get('workLocations')),
        'recruiting_unit_raw': raw.get('department') or '',
        'hiring_department_raw': raw.get('department') or '',
        'cohort_raw': '',
        'campaign_cohort_raw': batch_name,
        'campaign_scope': 'batch',
        'batch_name': batch_name,
        'source_name': cfg['source_name'],
        'source': 'official_career',
        'record_kind': 'official_position_id',
        'source_fields': {key: raw.get(key) for key in
                          ('id', 'batchId', 'batchName', 'categoryName', 'status', 'modifyTime',
                           'graduationTime', 'workLocations', 'code', 'positionType', 'degree',
                           'isLingYang', 'isTongyi') if raw.get(key) is not None},
        'status': 'open' if str(raw.get('status')) == 'recruit' else 'unverified',
        'status_note': '官网公开在招岗位；未披露截止日期，未尝试投递。',
        'reviewed_at': checked,
    }
    if raw.get('publishTime'):
        record['published_at'] = raw.get('publishTime')
    updated = _ms_date(raw.get('modifyTime'))
    if updated:
        record['source_updated_at'] = updated
    if graduation.get('from'):
        record['graduation_time_from'] = _ms_date(graduation.get('from'))
    if graduation.get('to'):
        record['graduation_time_to'] = _ms_date(graduation.get('to'))
    if str(raw.get('status')) == 'recruit':
        record['source_is_active'] = True
        record['source_status_raw'] = 'recruit'
    return record


def _coverage(source_url):
    return {'status': 'blocked', 'complete': False, 'expected_total': None,
            'collected_jobs': 0, 'pages_scanned': 0, 'detail_complete': False,
            'source_url': source_url, 'errors': [], 'evidence': [], 'evidence_files': []}


def _finalize(result, transport=None):
    coverage = result['coverage']
    jobs = result['jobs']
    coverage['collected_jobs'] = len(jobs)
    coverage['unique_source_ids'] = len({job['source_record_id'] for job in jobs})
    missing = sum(1 for job in jobs if not str(job.get('description_raw') or '').strip())
    coverage['detail_complete'] = missing == 0
    expected = coverage.get('expected_total')
    coverage['complete'] = bool(
        expected is not None and expected == len(jobs)
        and not coverage['errors']
        and coverage.get('pagination_exhausted') is True
        and coverage['detail_complete'])
    coverage['status'] = 'success' if coverage['complete'] else ('partial' if jobs else 'blocked')
    if transport is not None:
        coverage['request_budget'] = transport.budget()
    return result


def _collect_entity(transport, company, scope, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = ENTITIES[company]
    source_url = cfg['base'] + cfg['listing'] + cfg.get('listing_query', '')
    coverage = _coverage(source_url)
    coverage['scope_request'] = {'company': company, 'scope': scope, 'source_url': source_url,
                                 'params': {'channel': CHANNEL, 'language': 'zh',
                                            'categoryType': SCOPE_CATEGORY.get(scope, ''),
                                            'pageSize': PAGE_SIZE}}
    result = {'jobs': [], 'coverage': coverage}
    if scope == 'social':
        coverage['errors'] = ['阿里巴巴系校园平台仅提供校招/实习批次；社招在独立站点，本适配器不覆盖 social。']
        return _finalize(result, transport)
    try:
        transport.open(source_url)
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
        coverage['errors'].append('request budget exhausted before listing load')
        return _finalize(result, transport)
    except HeadlessUnavailable as error:
        coverage['errors'].append(f'headless unavailable: {error}')
        return _finalize(result, transport)
    except Exception as error:
        coverage['errors'].append(f'listing load failed: {type(error).__name__}: {error}'[:300])
        return _finalize(result, transport)

    slug = company

    # 1. official batch dictionary
    list_batch = None
    if cfg.get('batch_discovery'):
        try:
            status, list_batch = transport.post_json('/searchCondition/listBatch', {})
        except BudgetExhausted:
            coverage['request_budget_exhausted'] = True
            coverage['errors'].append('request budget exhausted at listBatch')
            return _finalize(result, transport)
        except Exception as error:
            coverage['errors'].append(f'listBatch failed: {type(error).__name__}: {error}'[:300])
            list_batch = None
        coverage['evidence'].append(_record(output_dir, f'ali-{slug}-batches.json', {
            'source_url': cfg['base'] + '/searchCondition/listBatch',
            'request_body': {}, 'http_status': status if list_batch is not None else None,
            'response': list_batch}))
    batches = batches_for_scope(list_batch, cfg, scope)
    if not batches:
        coverage['errors'].append(
            f'no official batch for {company}/{scope}; batch dictionary empty and no fallback')
        return _finalize(result, transport)

    # 2. business-group (customDeptCode) filter
    dept_code = ''
    if cfg.get('dept_label'):
        try:
            status, conditions = transport.post_json('/searchCondition/list', {
                'channel': CHANNEL, 'language': 'zh',
                'categoryType': SCOPE_CATEGORY.get(scope, '')})
        except BudgetExhausted:
            coverage['request_budget_exhausted'] = True
            coverage['errors'].append('request budget exhausted at searchCondition/list')
            return _finalize(result, transport)
        except Exception as error:
            coverage['errors'].append(f'searchCondition failed: {type(error).__name__}: {error}'[:300])
            conditions = None
        coverage['evidence'].append(_record(output_dir, f'ali-{slug}-conditions.json', {
            'source_url': cfg['base'] + '/searchCondition/list',
            'request_body': {'channel': CHANNEL, 'language': 'zh',
                             'categoryType': SCOPE_CATEGORY.get(scope, '')},
            'http_status': status if conditions is not None else None,
            'response': conditions}))
        dept_code, matched_parent = resolve_dept_code(conditions, cfg['dept_label'])
        if not dept_code:
            coverage['errors'].append(
                f'official business group not found in searchCondition: {cfg["dept_label"]}')
            return _finalize(result, transport)
        coverage['dept_match'] = {'label': cfg['dept_label'], 'parent': matched_parent,
                                  'leaf_codes': dept_code.split(',')}

    # 3. paginate every official batch for the scope
    coverage['expected_total'] = 0
    coverage['pagination_exhausted'] = True
    seen_ids = set()
    for batch in batches:
        page = 1
        batch_total = None
        while True:
            payload = {'channel': CHANNEL, 'language': 'zh', 'pageSize': PAGE_SIZE,
                       'batchId': batch['id'], 'subCategories': '', 'regions': '',
                       'customDeptCode': dept_code, 'corpCode': '', 'pageIndex': page,
                       'key': '', 'categoryType': SCOPE_CATEGORY.get(scope, '')}
            try:
                status, response = transport.post_json('/position/search', payload)
            except BudgetExhausted:
                coverage['request_budget_exhausted'] = True
                coverage['pagination_exhausted'] = False
                coverage['errors'].append(f'request budget exhausted at batch {batch["id"]} page {page}')
                break
            except Exception as error:
                coverage['pagination_exhausted'] = False
                coverage['errors'].append(
                    f'batch {batch["id"]} page {page}: {type(error).__name__}: {error}'[:300])
                break
            coverage['pages_scanned'] += 1
            if status != 200 or not isinstance(response, dict) or not response.get('success'):
                coverage['pagination_exhausted'] = False
                message = response.get('errorMsg') if isinstance(response, dict) else response
                coverage['errors'].append(
                    f'batch {batch["id"]} page {page}: http={status} error={str(message)[:200]}')
                break
            content = response.get('content') or {}
            rows = content.get('datas') or []
            total = int(content.get('totalCount') or 0)
            if page == 1:
                batch_total = total
                coverage['expected_total'] += total
            safe_rows = [{key: row.get(key) for key in
                          ('id', 'name', 'batchName', 'categoryName', 'status', 'workLocations')}
                         for row in rows]
            coverage['evidence'].append(_record(
                output_dir, f'ali-{slug}-batch{batch["id"]}-page{page}.json',
                {'source_url': cfg['base'] + '/position/search', 'request_body': payload,
                 'http_status': status, 'totalCount': total,
                 'batch': {'id': batch['id'], 'name': batch['name']},
                 'datas': safe_rows}))
            checked = _now()
            for raw in rows:
                pid = str(raw.get('id') or raw.get('positionId') or '')
                title = (raw.get('name') or '').strip()
                if not pid or pid in seen_ids or not title:
                    continue
                if re.search(r'需登录|请登录|投递入口|报名入口|招聘公告', title):
                    continue
                seen_ids.add(pid)
                result['jobs'].append(_row_to_job(raw, cfg, scope, checked, batch, source_url))
            if not rows or (batch_total is not None and len(rows) < PAGE_SIZE) or (
                    batch_total is not None and page * PAGE_SIZE >= batch_total):
                break
            if page >= MAX_PAGES_PER_BATCH:
                coverage['pagination_exhausted'] = False
                coverage['errors'].append(f'batch {batch["id"]}: page guard {MAX_PAGES_PER_BATCH} hit')
                break
            page += 1

    coverage['evidence_files'] = list(coverage['evidence'])
    coverage['scope_evidence'] = (
        f"Official {company} campus listing {source_url}; batches="
        f"{[b['id'] for b in batches]}; customDeptCode={dept_code or '(all)'}; "
        f"official totalCount={coverage['expected_total']}; "
        f"pageSize={PAGE_SIZE}; categoryType={SCOPE_CATEGORY.get(scope, '')}.")
    coverage['scope_request']['params'].update(
        {'batchIds': [b['id'] for b in batches], 'customDeptCode': dept_code})
    coverage['request_params'] = dict(coverage['scope_request']['params'])
    return _finalize(result, transport)


def collect(company, scope, output_dir, transport=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if company not in ENTITIES:
        raise ValueError('unknown Alibaba entity: ' + str(company))
    if scope not in SCOPES:
        raise ValueError('Unknown recruitment scope')
    owned = transport is None
    transport = transport or make_transport()
    try:
        result = _collect_entity(transport, company, scope, output_dir)
    finally:
        if owned:
            transport.close()
    (output_dir / 'result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Alibaba-family campus headless collector')
    parser.add_argument('company', choices=list(ENTITIES))
    parser.add_argument('scope', choices=list(SCOPES))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--max-requests', type=int)
    parser.add_argument('--delay', type=float)
    args = parser.parse_args()
    built = collect(args.company, args.scope, args.output_dir,
                    transport=make_transport(max_requests=args.max_requests, delay=args.delay))
    print(json.dumps(built['coverage'], ensure_ascii=False, indent=2))
