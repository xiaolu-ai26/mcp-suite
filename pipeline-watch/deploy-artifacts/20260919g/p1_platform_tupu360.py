"""tupu360 (图谱天下) multi-tenant recruitment site adapter.

A large share of foreign employers in China publish their campus/internship/
social openings on a tupu360-hosted recruitment site. One company = one line in
``p1_platform_companies.json`` under the ``tupu360`` key.

Two public site families were observed in the 2026-09 field survey:

``careersite`` family (public, server-rendered, no account, no WeChat)
    ``https://careersite.tupu360.com/<tenant>/position/index?recruitmentType=...``
    renders the whole posting list as plain HTML (two list templates, see
    ``parse_list``), paginates through a same-origin ``POST
    .../position/nextPageList`` endpoint, and renders one posting per
    ``.../position/detail?positionId=...`` page. ``careersite.tupu360.com/``
    also serves a public per-customer index, which is how tenant slugs are
    discovered. This is the primary channel.

``wxtemp`` family (WeChat-only)
    ``https://<tenant>.tupu360.com/position/list`` answers every HTML route with
    a ``302`` to ``/pageQrCode?targetUrl=...`` ("请用微信扫描二维码打开页面"),
    and with a MicroMessenger User-Agent it redirects into
    ``open.weixin.qq.com/connect/oauth2/authorize``. There is no anonymous
    public route: the content only exists behind WeChat OAuth. This adapter
    never logs in, never performs OAuth and never forges a signature, so such a
    tenant is reported ``blocked`` with that exact official evidence.

Three fetch channels are implemented, most stable first:

``html``      (default) browser-header ``requests`` GET of the rendered list page
              plus the site's own ``nextPageList`` POST for page 2..N.
``api``       (fallback) skip the list GET and POST ``nextPageList`` directly with
              ``offset=0&max=...``; this is what keeps SPA tenants working when
              the list route is redirected to a hash-route single page app.
``headless``  (last resort) Playwright/Chromium opens the list page exactly like a
              normal visitor and the adapter reads the DOM after JS ran. Opt in
              with ``QIUZHAO_TUPU360_HEADLESS=1`` or ``channel='headless'``.

robots.txt: ``careersite.tupu360.com/robots.txt`` and every tenant host answer
``User-agent: * / Disallow: /``. That platform-wide directive is recorded in
``pipeline-watch/RECEIPT-foreign-ats-c.md``; the adapter keeps the per-tenant
request budget and the >=2s spacing the survey used, and a tenant is disabled by
default unless its config line is explicitly enabled.

Data rules (foreign batch): only fields the official page actually carries.
``published_at`` is filled from the official 发布日期 / 发布时间 value when the
site publishes one, ``deadline_raw`` only when the posting states a deadline
(tupu360 postings observed in this batch never do, so it stays empty), and
``cohort_raw`` is never inferred — a programme year only survives inside the
announcement title (``campaign_cohort_raw``).
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
from urllib.parse import urlsplit

try:
    from . import p1_sources_01_10 as shared
except ImportError:  # direct module execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.collector import p1_sources_01_10 as shared

MODULE_PATH = 'qiuzhao.collector.p1_platform_tupu360'
CONFIG_PATH = Path(__file__).with_name('p1_platform_companies.json')
CONFIG_KEY = 'tupu360'
PUBLIC_HOST = 'careersite.tupu360.com'
# Official channel parameter values used by the platform's own navigation.
SCOPE_CHANNELS = {
    'campus': 'CAMPUSRECRUITMENT',
    'intern': 'INTERNSHIPRECRUITMENT',
    'social': 'SOCIALRECRUITMENT',
}
# Extra official channels a tenant may advertise on top of the scope default.
EXTRA_CHANNELS = {
    'campus': ('CAMPUSAMBASSADORRECRUITMENT',),
    'intern': (),
    'social': (),
}
PAGE_SIZE = 15
# Safety valve for the site's own nextPageList paging.  The *target* page count is the
# one the site prints (共N页 / 共N个职位), never the cap: a channel with 828 postings is
# 56 pages, and a cap used as a target silently truncates it.  120 pages = 1800 rows,
# comfortably above the largest channel observed in the 2026-09-19 full-site census.
PAGE_CAP = 120
DEFAULT_REQUEST_BUDGET = None
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
HEADERS = {
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
}
TAG_RE = re.compile(r'<[^>]+>')
TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
ELE_RE = re.compile(r'<div class="ele ([a-zA-Z0-9_\- ]*?)"[^>]*>(.*?)</div>', re.S)
PAGE_TURN_RE = re.compile(r'data-pagenum="(\d+)"\s+data-pagemax="(\d+)"')
TOTAL_LABEL_RE = re.compile(r'共\s*(\d+)\s*个职位')
PAGES_RE = re.compile(r'共\s*(\d+)\s*页')
SUB_TITLE_RE = re.compile(r'id="positionListPageSubTitle"[^>]*>\s*([^<]{0,40}?)\s*<')
HIDDEN_INPUT_RE = re.compile(
    r'<input[^>]*id="(positionName|sourcePid|recruitmentType|positionStatus|positionId)"[^>]*value="([^"]*)"',
    re.I)
DL_RE = re.compile(
    r'<dt class="title">\s*([^<]{0,20}?)\s*[:：]?\s*</dt>\s*<dd class="content"[^>]*>\s*([^<]{0,200}?)\s*</dd>', re.S)
DEADLINE_RE = re.compile(
    r'(?:投递|申请|报名|简历)?截止(?:日期|时间)?\s*[:：]\s*([0-9]{4}[-/年][0-9]{1,2}[-/月][0-9]{1,2}日?)')
TUPU_LIST_MARKERS = ('position-list', 'position-item event-vertical')


class BudgetExhausted(RuntimeError):
    """Raised when the per-tenant request budget for one verification run is used up."""


class ChannelUnavailable(RuntimeError):
    """Raised when the headless channel cannot run (playwright/chromium missing)."""


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def _read_platform():
    data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    return data.get(CONFIG_KEY) or {}


def _entry(key):
    entry = _read_platform().get(key) or {}
    if isinstance(entry, str):
        return {'name': entry}
    return entry


def _load_companies():
    """Enabled tenants only.

    ``"enabled": false`` keeps a surveyed line in the config (so the next person
    sees the tenant, the entry URL and why it is off) without registering the
    company in ``p1_pipeline.REGISTRY`` for the daily run.
    """
    companies = {}
    for key, entry in _read_platform().items():
        if str(key).startswith('_'):
            continue  # section-level documentation key
        if not isinstance(entry, dict):
            companies[str(key)] = str(entry)
            continue
        if entry.get('enabled') is False:
            continue
        name = str(entry.get('name') or '').strip()
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


def resolve(company, include_disabled=False):
    if company in COMPANIES:
        return company
    if company in NAME_TO_KEY:
        return NAME_TO_KEY[company]
    if include_disabled:
        for key, entry in _read_platform().items():
            if str(key).startswith('_') or not isinstance(entry, dict):
                continue
            if company in (key, str(entry.get('name') or '')):
                return str(key)
    raise ValueError('unknown tupu360 company: ' + str(company))


def tenant_host(key):
    entry = _entry(key)
    host = str(entry.get('host') or PUBLIC_HOST).strip()
    return re.sub(r'^https?://', '', host).strip('/')


def tenant_slug(key):
    """Tenant path segment; a company may share another company's tenant."""
    entry = _entry(key)
    return str(entry.get('tenant') or key).strip('/')


def site_url(key):
    entry = _entry(key)
    url = str(entry.get('url') or '').strip()
    if url:
        return url
    scope = str(entry.get('default_scope') or 'campus')
    return list_url(key, channel_for(key, scope))


def channel_for(key, scope):
    """Official ``recruitmentType`` value for one company/scope pair."""
    entry = _entry(key)
    channels = entry.get('channels') if isinstance(entry.get('channels'), dict) else {}
    value = channels.get(scope)
    if not value:
        value = SCOPE_CHANNELS[scope]
    return str(value)


def channels_for(key, scope):
    """Channels merged into one scope: the scope default plus explicit extras."""
    entry = _entry(key)
    extra = entry.get('extra_channels') if isinstance(entry.get('extra_channels'), dict) else {}
    values = [channel_for(key, scope)]
    raw = extra.get(scope)
    if isinstance(raw, str):
        raw = [raw]
    for value in raw or []:
        value = str(value)
        if value and value not in values:
            values.append(value)
    return values


def fallback_channels_for(key, scope):
    """Extra official channels tried only when the merged channels carry nothing."""
    values = []
    for value in EXTRA_CHANNELS.get(scope, ()):
        if value not in channels_for(key, scope):
            values.append(value)
    return values


def list_url(key, channel):
    return (f'https://{tenant_host(key)}/{tenant_slug(key)}/position/index'
            f'?recruitmentType={channel}')


def next_page_url(key):
    return f'https://{tenant_host(key)}/{tenant_slug(key)}/position/nextPageList'


def detail_url(key, pid, channel):
    return (f'https://{tenant_host(key)}/{tenant_slug(key)}/position/detail'
            f'?positionId={pid}&recruitmentType={channel}&currentLang=zh_CN')


def is_wechat_only(key):
    """A tenant whose only public entry is the WeChat QR gate.

    Explicit ``"wechat_only"`` in the config wins; otherwise only a
    ``*.tupu360.com`` host that is not the public careersite is the wxtemp
    product. A customer-hosted careersite (e.g. chinacampus.jnj.com.cn) is not.
    """
    entry = _entry(key)
    if entry.get('wechat_only') is not None:
        return bool(entry['wechat_only'])
    host = tenant_host(key)
    return host != PUBLIC_HOST and host.endswith('tupu360.com')


# --------------------------------------------------------------------------- #
# http
# --------------------------------------------------------------------------- #
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
    session.headers.update(HEADERS)
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=0)))
    return session


def _spend(budget):
    if budget is None:
        return
    if budget.get('limit') is not None and budget['used'] >= budget['limit']:
        raise BudgetExhausted('per-tenant request budget reached')
    budget['used'] += 1


def _get(session, url, budget):
    import requests

    def call():
        _spend(budget)
        interval = _min_interval()
        if interval:
            time.sleep(interval)
        response = session.get(url, timeout=(10, 40), allow_redirects=True)
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == 'iso-8859-1':
            response.encoding = response.apparent_encoding or 'utf-8'
        return response
    try:
        return call()
    except (requests.RequestException, ValueError):
        time.sleep(2.0)
        return call()


def _post(session, url, data, budget, referer=None):
    import requests
    headers = {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'text/html, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'https://' + (urlsplit(url).netloc or PUBLIC_HOST),
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }
    if referer:
        headers['Referer'] = referer

    def call():
        _spend(budget)
        interval = _min_interval()
        if interval:
            time.sleep(interval)
        response = session.post(url, data=data, headers=headers, timeout=(10, 40))
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == 'iso-8859-1':
            response.encoding = response.apparent_encoding or 'utf-8'
        return response
    try:
        return call()
    except (requests.RequestException, ValueError):
        time.sleep(2.0)
        return call()


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def _clean(value):
    return re.sub(r'\s+', ' ', _html.unescape(TAG_RE.sub(' ', value or ''))).strip()


def _clean_block(value):
    """``_clean`` for a raw HTML slice that may end mid-tag.

    Splitting a list body on the next card leaves a dangling ``<div class="`` in
    the previous slice; ``TAG_RE`` cannot remove it, so cut the unfinished tag
    first and never let markup leak into the recorded official card text.
    """
    text = value or ''
    tail = text.rfind('<')
    if tail > text.rfind('>'):
        text = text[:tail]
    return _clean(text)


def _iso_date(value):
    """``2026-09-18`` / ``发布于: 2026-09-18`` -> ``2026-09-18``; else ``''``."""
    match = re.search(r'(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})', str(value or ''))
    if not match:
        return ''
    year, month, day = (int(x) for x in match.groups())
    try:
        return datetime(year, month, day).strftime('%Y-%m-%d')
    except ValueError:
        return ''


def _header_columns(block):
    """``[('e-title', '职位名称'), ...]`` in official column order.

    Order matters: several tenants reuse one CSS class (``e-salary``) for the
    业务 / 职位类别 / 工作地点 columns, so a class-keyed lookup would silently
    return the wrong field. The header row is the official column legend and is
    zipped positionally with each row's cells instead.
    """
    columns = []
    for css, inner in ELE_RE.findall(block or ''):
        columns.append((css.strip(), _clean(inner)))
    return columns


def _row_cells(chunk):
    return [(css.strip(), _clean(inner)) for css, inner in ELE_RE.findall(chunk or '')]


def _column_value(columns, cells, keywords):
    """Value of the first officially labelled column matching ``keywords``."""
    for index, (_, label) in enumerate(columns):
        if label and any(key in label for key in keywords) and index < len(cells):
            value = cells[index][1]
            if value:
                return value
    return ''


CITY_LABEL_RE = re.compile(r'^(?:工作城市|工作地点|城市|地点)\s*[:：]?\s*(?=\S)')


def _strip_city_label(value):
    """Drop a redundant template label baked into a city cell ("城市上海")."""
    text = _clean(value)
    stripped = CITY_LABEL_RE.sub('', text)
    if stripped and re.match(r'^[\u4e00-\u9fa5A-Za-z]', stripped):
        return stripped
    return text


def parse_list(page_html):
    """Parse one official posting-list fragment.

    Handles both list templates the platform serves:

    * template ``A`` — ``div.position-list-header`` + ``div.position-item`` rows
      whose ``div.ele.e-*`` cells are labelled by the header, and whose
      ``position/detail`` anchor carries the official posting id.
    * template ``B`` — ``div.position-item.event-vertical[pid]`` cards with
      ``.position-name .txt`` as the title, ``li.e-city`` for city/function,
      ``li.e-count`` for the headcount and ``div.time`` for 发布于.
    Returns ``{'template', 'rows', 'sub_title', 'total_label', 'pages',
    'page_size', 'columns'}``. Nothing is invented: a page that carries no
    posting item yields an empty ``rows`` list.
    """
    page_html = page_html or ''
    sub_title = SUB_TITLE_RE.search(page_html)
    total_label = TOTAL_LABEL_RE.search(page_html)
    pages = PAGES_RE.search(page_html)
    page_turn = PAGE_TURN_RE.search(page_html)
    result = {
        'template': '',
        'rows': [],
        'sub_title': _clean(sub_title.group(1)) if sub_title else '',
        'total_label': int(total_label.group(1)) if total_label else None,
        'pages': int(pages.group(1)) if pages else None,
        'page_size': int(page_turn.group(2)) if page_turn else None,
        'columns': [],
        'markers': [marker for marker in TUPU_LIST_MARKERS if marker in page_html],
    }
    header_at = page_html.find('class="position-list-header"')
    if header_at >= 0:
        result['template'] = 'A'
        header_end = page_html.find('position-list-body', header_at)
        block = page_html[header_at:header_end if header_end > 0 else header_at + 4000]
        result['columns'] = _header_columns(block)
        body_start = header_end if header_end > 0 else header_at
        body_end = page_html.find('position-show-more', body_start)
        body = page_html[body_start:body_end if body_end > 0 else len(page_html)]
        for chunk in body.split('<div class="position-item">')[1:]:
            cells = _row_cells(chunk)
            if not cells:
                continue
            anchor = re.search(r"href='([^']*positionId=([0-9a-zA-Z]+)[^']*)'", chunk)
            if not anchor:
                anchor = re.search(r'href="([^"]*positionId=([0-9a-zA-Z]+)[^"]*)"', chunk)
            if not anchor:
                continue
            columns = result['columns']
            by_label = {label: value for (_, label), (_, value) in zip(columns, cells) if label}
            title = (by_label.get('职位名称') or by_label.get('岗位名称')
                     or _column_value(columns, cells, ('职位名称', '岗位名称', 'title'))
                     or cells[0][1])
            title_attr = re.search(r'class="ele e-title"[^>]*title="([^"]*)"', chunk)
            if title_attr and _clean(title_attr.group(1)):
                title = _clean(title_attr.group(1))
            result['rows'].append({
                'pid': anchor.group(2),
                'title': title,
                'city': _strip_city_label(
                    _column_value(columns, cells, ('工作地点', '工作城市', '城市', '地点'))),
                'function': _column_value(columns, cells, ('职能类别', '职位类别', '业务', '部门')),
                'published_at': _iso_date(
                    _column_value(columns, cells, ('发布日期', '发布时间', '更新日期'))),
                'detail_url': _html.unescape(anchor.group(1)),
                'list_text': _clean_block(chunk),
            })
        return result

    if 'position-item event-vertical' in page_html:
        result['template'] = 'B'
        body_end = page_html.find('position-show-more')
        body = page_html[:body_end if body_end > 0 else len(page_html)]
        for raw_chunk in body.split('<div class="position-item event-vertical"')[1:]:
            # The split keeps the rest of the opening tag; drop its attributes so
            # the recorded card text never leaks data-action/pid/recruitment markup.
            chunk = raw_chunk.split('>', 1)[1] if '>' in raw_chunk else raw_chunk
            pid = re.search(r'pid="([0-9a-zA-Z]+)"', raw_chunk)
            if not pid:
                continue
            name = re.search(r'<div class="position-name">(.*?)<div class="position-extend">', chunk, re.S)
            title = ''
            if name:
                txt = re.search(r'<span class="txt">(.*?)</span>', name.group(1), re.S)
                title = _clean(txt.group(1)) if txt else ''
            when = re.search(r'<div class="time">\s*([^<]*?)\s*</div>', chunk)
            city = ''
            function = ''
            headcount = ''
            # Card cells are tenant-configurable: 舍弗勒 uses two e-city cells
            # (city, then 学历 or a data-original-title category) plus e-count;
            # 茵梦达 labels the business line with a plain li.ele; 强生 prints a
            # single "工作地点：北京" line with no e-city class at all.
            items = re.findall(r'<li class="ele ([^"]*)"[^>]*>(.*?)</li>', chunk, re.S)
            for css, inner in items:
                css = css.strip()
                if 'icons' in css:
                    continue
                value = _clean(inner)
                if not value:
                    continue
                label = re.match(r'^(工作地点|工作城市|城市|职能类别|职位类别|招聘人数)\s*[:：]\s*(.+)$', value)
                if label:
                    field, text = label.group(1), label.group(2).strip()
                    if field in ('工作地点', '工作城市', '城市') and not city:
                        city = _strip_city_label(text)
                    elif field in ('职能类别', '职位类别') and not function:
                        function = text
                    elif field == '招聘人数' and not headcount:
                        headcount = '招聘人数：' + text
                    continue
                if 'e-count' in css:
                    headcount = headcount or value
                    continue
                if 'e-city' in css and not city:
                    city = _strip_city_label(value)
                    continue
                if not function:
                    function = value
            titled = re.search(r'<li class="ele [^"]*"[^>]*data-original-title="([^"]*)"', chunk)
            if titled and _clean(titled.group(1)):
                function = _html.unescape(titled.group(1)).strip()
            if not city:
                city = _strip_city_label(_clean(
                    (re.search(r'(?:工作地点|工作城市|城市)\s*[:：]\s*([^<]{1,40})', chunk) or [None, ''])[1]))
            result['rows'].append({
                'pid': pid.group(1),
                'title': title,
                'city': city,
                'function': function,
                'published_at': _iso_date(when.group(1) if when else ''),
                'headcount_raw': headcount,
                'detail_url': '',
                'list_text': _clean_block(chunk),
            })
        return result
    return result


def parse_detail(page_html):
    """Official posting-detail fields from one ``position/detail`` page."""
    page_html = page_html or ''
    hidden = {key: _html.unescape(value).strip()
              for key, value in HIDDEN_INPUT_RE.findall(page_html)}
    title = hidden.get('positionName') or ''
    if not title:
        match = re.search(r'<h4 class="name">(.*?)</h4>', page_html, re.S)
        title = _clean(match.group(1)) if match else ''
    description = ''
    at = page_html.find('class="position-description')
    if at >= 0:
        start = page_html.find('>', at) + 1
        end = page_html.find('<footer', start)
        if end < 0:
            end = len(page_html)
        description = page_html[start:end]
        # Trim everything that follows the description block: the share box, the
        # 职位概况 card and the apply button column are siblings, not posting text.
        for marker in ('<div class="card', 'id="shareFloat"', 'id="buttonDiv"',
                       '<div class="btns', 'class="deliver-position',
                       '<div class="col-lg-3', '<div class="col-md-1 actions'):
            cut = description.find(marker)
            if cut > 0:
                description = description[:cut]
    extra = {}
    for label, value in DL_RE.findall(page_html):
        extra[_clean(label)] = _clean(value)
    return {
        'title': title,
        'description_html': description,
        'published_at': _iso_date(extra.get('发布时间') or extra.get('发布日期')),
        'city': extra.get('工作城市') or extra.get('工作地点') or '',
        'function': extra.get('职能类别') or extra.get('职位类别') or '',
        'status_raw': hidden.get('positionStatus') or '',
        'extra': extra,
    }


def _deadline_from_text(text):
    match = DEADLINE_RE.search(text or '')
    return match.group(1) if match else ''


# --------------------------------------------------------------------------- #
# channels
# --------------------------------------------------------------------------- #
def _fetch_list_html(session, key, channel, budget, evidence):
    """Channel ``html``: rendered list page, then the site's own nextPageList."""
    url = list_url(key, channel)
    response = _get(session, url, budget)
    page_html = response.text
    evidence.append({'channel': 'html', 'url': str(response.url), 'status': response.status_code,
                     'bytes': len(response.content)})
    parsed = parse_list(page_html)
    parsed['final_url'] = str(response.url)
    parsed['raw'] = page_html
    return parsed


def _fetch_next_pages(session, key, channel, parsed, budget, evidence, page_cap=PAGE_CAP):
    """Page 2..N through the site's own ``nextPageList`` endpoint.

    The page count is the site's own: ``共N页`` when the list template prints it,
    otherwise ``ceil(共N个职位 / page size)``.  ``page_cap`` is a safety valve, not
    a target -- a channel with 828 postings is 56 pages, and stopping at a
    40-page target would silently truncate it to 600 rows.  When the cap really is
    reached before the site's last page the scan stops and records
    ``page_cap_hit`` so no caller can claim ``pagination_exhausted``.
    """
    rows = list(parsed['rows'])
    seen = {row['pid'] for row in rows}
    size = parsed.get('page_size') or PAGE_SIZE
    expected = parsed.get('total_label')
    pages = parsed.get('pages') or 0
    if expected and size:
        pages = max(pages, -(-int(expected) // int(size)))
    pages = pages or 1
    cap_hit = False
    page = 2
    while page <= pages:
        if page > page_cap:
            cap_hit = True
            break
        offset = (page - 1) * size
        response = _post(session, next_page_url(key),
                         {'recruitmentType': channel, 'offset': str(offset),
                          'max': str(size), 'currentLang': 'zh_CN'},
                         budget, referer=list_url(key, channel))
        chunk = parse_list(response.text)
        evidence.append({'channel': 'api', 'url': next_page_url(key), 'status': response.status_code,
                         'bytes': len(response.content), 'page': page, 'offset': offset, 'max': size})
        fresh = [row for row in chunk['rows'] if row['pid'] not in seen]
        for row in fresh:
            seen.add(row['pid'])
        rows.extend(fresh)
        if not chunk['rows'] or not fresh:
            break
        page += 1
    parsed['rows'] = rows
    parsed['expected_total'] = expected
    parsed['pages_target'] = pages
    parsed['page_cap_hit'] = cap_hit
    return parsed


def _fetch_direct_api(session, key, channel, budget, evidence, size, page_cap=60):
    """Channel ``api``: page through nextPageList without the (possibly SPA) list page.

    This is what keeps a tenant whose list route redirects into a hash-route SPA
    working, and it is also the cheapest way to reach a large social channel: the
    endpoint honours ``offset``/``max`` and reports the official 共N个职位 total.
    """
    rows = []
    seen = set()
    expected = None
    template = ''
    first_raw = ''
    offset = 0
    pages_done = 0
    for _ in range(max(1, page_cap)):
        pages_done += 1
        response = _post(session, next_page_url(key),
                         {'recruitmentType': channel, 'offset': str(offset),
                          'max': str(size), 'currentLang': 'zh_CN'},
                         budget, referer=list_url(key, channel))
        parsed = parse_list(response.text)
        evidence.append({'channel': 'api-direct', 'url': next_page_url(key),
                         'status': response.status_code, 'bytes': len(response.content),
                         'offset': offset, 'max': size,
                         'rows': len(parsed['rows'])})
        if not first_raw:
            first_raw = response.text
        template = parsed['template'] or template
        if expected is None:
            expected = parsed['total_label']
        fresh = [row for row in parsed['rows'] if row['pid'] not in seen]
        for row in fresh:
            seen.add(row['pid'])
        rows.extend(fresh)
        if not parsed['rows'] or not fresh:
            break
        offset += size
        if expected is not None and len(rows) >= expected:
            break
    capped = pages_done >= max(1, page_cap) and (expected is None or len(rows) < expected)
    return {'rows': rows, 'template': template, 'sub_title': '', 'pages': None,
            'page_size': size, 'total_label': expected, 'columns': [],
            'raw': first_raw, 'final_url': next_page_url(key), 'page_cap_hit': capped}


def _fetch_headless(key, channel, evidence):
    """Channel ``headless``: a real browser loads the list page like a visitor.

    Last-resort fallback for a tenant whose list only materialises after JS runs.
    No login, no OAuth, no CAPTCHA work — it only navigates the public URL and
    reads back the DOM the site itself rendered.
    """
    try:
        from .base_headless import HeadlessSource, HeadlessUnavailable
    except ImportError:  # direct module execution
        from qiuzhao.collector.base_headless import HeadlessSource, HeadlessUnavailable
    url = list_url(key, channel)
    source = HeadlessSource(None, delay=max(2.0, _min_interval()))
    try:
        try:
            page = source.open(url, wait_until='networkidle')
        except HeadlessUnavailable:
            raise
        except Exception as error:  # navigation timeout still leaves a DOM to read
            evidence.append({'channel': 'headless', 'url': url, 'status': 'nav-error',
                             'error': f'{type(error).__name__}: {error}'})
            page = source.page
        if page is None:
            raise HeadlessUnavailable('headless page unavailable')
        page.wait_for_timeout(1500)
        dom = page.content()
        evidence.append({'channel': 'headless', 'url': url, 'status': 'ok', 'bytes': len(dom)})
        parsed = parse_list(dom)
        parsed['raw'] = dom
        parsed['final_url'] = page.url
        return parsed
    finally:
        source.close()


def _direct_api_safe(session, key, channel_value, budget, evidence, coverage, size):
    """``nextPageList`` that turns a channel miss into an empty list."""
    try:
        return _fetch_direct_api(session, key, channel_value, budget, evidence, size)
    except BudgetExhausted:
        raise
    except Exception as error:
        evidence.append({'channel': 'api-direct', 'url': next_page_url(key),
                         'status': 'error', 'error': f'{type(error).__name__}: {error}'})
        coverage['errors'].append(f'nextPageList channel miss: {type(error).__name__}: {error}')
        return {'rows': [], 'template': '', 'sub_title': '', 'pages': None,
                'page_size': size, 'total_label': None, 'columns': [],
                'raw': '', 'final_url': '', 'page_cap_hit': False}


def _headless_safe(key, channel_value, evidence, coverage):
    """Playwright fallback that degrades to an empty parse instead of raising."""
    try:
        return _fetch_headless(key, channel_value, evidence)
    except ChannelUnavailable as error:
        coverage['errors'].append(f'headless channel unavailable: {error}')
    except Exception as error:
        coverage['errors'].append(f'headless channel failed: {type(error).__name__}: {error}')
    return {'rows': [], 'template': '', 'sub_title': '', 'pages': None, 'page_size': None,
            'total_label': None, 'columns': [], 'raw': '', 'final_url': ''}


def _fetch_sequence(session, key, channel_value, budget, evidence, coverage, mode, entry):
    """Run one official channel through the requested fetch method.

    ``mode`` is ``None`` for the documented ladder (rendered HTML -> the site's
    own nextPageList -> headless browser), or one explicit method for channel
    verification. The method is *not* the platform's recruitmentType value.
    """
    if mode == 'api':
        return _direct_api_safe(session, key, channel_value, budget, evidence, coverage, 100)
    if mode == 'headless':
        return _headless_safe(key, channel_value, evidence, coverage)
    parsed = _fetch_list_html(session, key, channel_value, budget, evidence)
    if parsed['rows'] or mode == 'html':
        return parsed
    parsed = _direct_api_safe(session, key, channel_value, budget, evidence, coverage, 100)
    if parsed['rows']:
        return parsed
    if _headless_enabled(entry, mode):
        return _headless_safe(key, channel_value, evidence, coverage)
    return parsed


def _headless_enabled(entry, channel):
    if channel == 'headless':
        return True
    if str(entry.get('channel') or '').lower() == 'headless':
        return True
    return str(os.environ.get('QIUZHAO_TUPU360_HEADLESS') or '').strip().lower() in {'1', 'true', 'yes'}


# --------------------------------------------------------------------------- #
# collect
# --------------------------------------------------------------------------- #
def _blocked_result(coverage, reason):
    coverage['status'] = 'blocked'
    coverage['complete'] = False
    coverage['errors'].append(reason)
    coverage['note'] = reason
    return {'jobs': [], 'coverage': coverage}


def collect(company, scope, output_dir, max_requests=None, fetch_channel=None,
            include_disabled=False):
    """Collect one company/scope.

    ``fetch_channel`` pins one fetch method (``html`` / ``api`` / ``headless``)
    for channel verification; it is never a ``recruitmentType`` value, which
    always comes from the config. The default ``None`` runs the documented
    ladder. ``include_disabled`` lets an auditor run a line whose config says
    ``"enabled": false`` (used by ``pipeline-watch/tupu360-verify.py``); the
    daily pipeline never sets it.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if scope not in shared.TYPES:
        raise ValueError('invalid scope')
    key = resolve(company, include_disabled=include_disabled)
    entry = _entry(key)
    name = str(entry.get('name') or key)
    host = tenant_host(key)
    url = str(entry.get('url') or list_url(key, channel_for(key, scope)))
    budget = {'limit': _budget_limit(max_requests), 'used': 0}
    coverage = shared.coverage(url)
    coverage['scope_request'] = {'company': name, 'scope': scope, 'source_url': url,
                                 'params': {'recruitmentType': channel_for(key, scope),
                                            'tenant': key, 'host': host}}
    coverage['channels_used'] = []
    coverage['channel_evidence'] = []
    jobs = []
    session = _make_session()

    if is_wechat_only(key):
        reason = (f'tupu360 WeChat-only tenant {host}: every public HTML route answers 302 to '
                  f'/pageQrCode?targetUrl=... ("请用微信扫描二维码打开页面"), and a MicroMessenger '
                  f'User-Agent redirects into open.weixin.qq.com OAuth. No anonymous public route; '
                  f'this adapter never logs in and never performs WeChat OAuth.')
        result = _blocked_result(coverage, reason)
        result['coverage']['request_budget'] = budget
        return result

    configured_scope = str(entry.get('scope') or '')
    if configured_scope and scope != configured_scope:
        reason = (f'tenant {host} publishes only its official {configured_scope} channel; '
                  f'scope={scope} has no page on this site')
        result = _blocked_result(coverage, reason)
        result['coverage']['request_budget'] = budget
        return result

    rows = []
    expected_total = None
    template = ''
    sub_title = ''
    pagination_exhausted = False
    page_cap_hit = False
    if fetch_channel is not None:
        sequence = [channel_for(key, scope)]
    else:
        sequence = channels_for(key, scope)
    try:
        for channel_value in sequence:
            parsed = _fetch_sequence(session, key, channel_value, budget,
                                     coverage['channel_evidence'], coverage,
                                     fetch_channel, entry)
            last = coverage['channel_evidence'][-1]['channel'] if coverage['channel_evidence'] else 'none'
            coverage['channels_used'].append(f'{channel_value}:{last}')
            if not parsed['rows']:
                continue
            template = parsed['template'] or template
            sub_title = parsed['sub_title'] or sub_title
            # A scope may merge several official channels, so the expected total is
            # their sum rather than the last channel's own 共N个职位.
            if parsed['total_label'] is not None:
                expected_total = (parsed['total_label'] if expected_total is None
                                  else expected_total + parsed['total_label'])
            if parsed.get('raw'):
                (output_dir / f'{key}-{channel_value}-list-1.html').write_text(parsed['raw'], encoding='utf-8')
            if not str(parsed.get('final_url') or '').endswith('nextPageList'):
                parsed = _fetch_next_pages(session, key, channel_value, parsed, budget,
                                           coverage['channel_evidence'], page_cap=PAGE_CAP)
            page_cap_hit = page_cap_hit or bool(parsed.get('page_cap_hit'))
            pagination_exhausted = True
            seen = {row['pid'] for row in rows}
            for row in parsed['rows']:
                if row['pid'] not in seen:
                    seen.add(row['pid'])
                    row['channel'] = channel_value
                    rows.append(row)
        if fetch_channel is None and not rows:
            # Official extra channels (e.g. 校园大使) are only worth a request when
            # the scope's own channels carried nothing.
            for channel_value in fallback_channels_for(key, scope):
                parsed = _fetch_list_html(session, key, channel_value, budget,
                                          coverage['channel_evidence'])
                if not parsed['rows']:
                    continue
                last = coverage['channel_evidence'][-1]['channel']
                coverage['channels_used'].append(f'{channel_value}:{last}')
                template = parsed['template'] or template
                sub_title = parsed['sub_title'] or sub_title
                if parsed['total_label'] is not None:
                    expected_total = (parsed['total_label'] if expected_total is None
                                      else expected_total + parsed['total_label'])
                if parsed.get('raw'):
                    (output_dir / f'{key}-{channel_value}-list-1.html').write_text(
                        parsed['raw'], encoding='utf-8')
                seen = {row['pid'] for row in rows}
                for row in parsed['rows']:
                    if row['pid'] not in seen:
                        seen.add(row['pid'])
                        row['channel'] = channel_value
                        rows.append(row)
                break
        if page_cap_hit:
            # A truncated scan is reported as truncated: `pagination_exhausted` stays
            # false and `complete` (finish()) can never become true for this unit.
            coverage['page_cap_hit'] = True
            pagination_exhausted = False
            coverage['errors'].append(
                f'list pagination stopped at the {PAGE_CAP}-page safety cap before the '
                f'site\'s own last page for tenant {host}/{key}')
        coverage['pages_scanned'] = sum(1 for item in coverage['channel_evidence']
                                        if item.get('channel') == 'html')
        coverage['list_observed_ids'] = sorted({row['pid'] for row in rows})
        coverage['expected_total'] = expected_total if expected_total is not None else len(rows)

        remaining = None
        if budget['limit'] is not None:
            remaining = budget['limit'] - budget['used']
        # A tenant whose own position/detail route redirects into a hash-route SPA
        # has no public detail page; its official list card is then the whole
        # published posting text. That is recorded instead of invented.
        detail_mode = str(entry.get('detail') or 'page').lower()
        detail_complete = True
        for row in rows:
            detail = detail_url(key, row['pid'], row['channel'])
            parsed_detail = {'title': '', 'description_html': '', 'published_at': '',
                             'city': '', 'function': '', 'status_raw': ''}
            if detail_mode == 'list':
                description = row.get('list_text') or row['title']
                description_source = ('official tupu360 posting-list card (tenant '
                                      'position/detail redirects to its own SPA; no public detail page)')
            else:
                if remaining is not None and remaining <= 0:
                    detail_complete = False
                    break
                try:
                    response = _get(session, detail, budget)
                except BudgetExhausted:
                    detail_complete = False
                    break
                except Exception as error:
                    coverage['errors'].append(f'detail {row["pid"]}: {type(error).__name__}: {error}')
                    detail_complete = False
                    continue
                if budget['limit'] is not None:
                    remaining = budget['limit'] - budget['used']
                parsed_detail = parse_detail(response.text)
                (output_dir / f'{key}-detail-{row["pid"]}.html').write_text(response.text, encoding='utf-8')
                description = _clean(parsed_detail['description_html'])
                description_source = 'official tupu360 position/detail page'
                if not description:
                    coverage['errors'].append(f'empty official description for {row["pid"]}')
                    detail_complete = False
                    continue
            title = parsed_detail['title'] or row['title']
            city = parsed_detail['city'] or row['city']
            record = shared.job(name, scope, row['pid'], title, detail, description, city, {})
            record['scope_evidence'] = (
                f'Official tupu360 careersite tenant {host}/{key}; '
                f'channel={row["channel"]} ({sub_title or shared.TYPES[scope]}); '
                f'list template {template or "?"}')
            record['published_at'] = parsed_detail['published_at'] or row.get('published_at') or ''
            record['published_at_source'] = (
                'official position/detail 发布时间 field' if parsed_detail['published_at']
                else ('official posting-list 发布日期 column' if row.get('published_at')
                      else 'not published'))
            record['deadline_raw'] = _deadline_from_text(parsed_detail['description_html'])
            record['deadline_source'] = 'official posting text' if record['deadline_raw'] else 'not published'
            record['source_updated_at'] = ''
            record['cohort_raw'] = ''  # never inferred from the posting year
            record['campaign_cohort_raw'] = ''
            record['campaign_scope'] = ''
            record['campaign_url'] = url
            record['position_function_raw'] = parsed_detail['function'] or row.get('function') or ''
            record['headcount_raw'] = row.get('headcount_raw') or ''
            record['source_status_raw'] = parsed_detail['status_raw']
            record['source_status_evidence'] = {
                'positionStatus': parsed_detail['status_raw'],
                'basis': 'Official tupu360 positionStatus hidden field (PUBLISHING = live posting)',
            }
            record['source_is_active'] = parsed_detail['status_raw'].upper() == 'PUBLISHING'
            record['status'] = 'open' if record['source_is_active'] else 'unverified'
            record['description_source'] = description_source
            record['list_checked_at'] = datetime.now(timezone.utc).isoformat()
            record['channel_used'] = row['channel']
            record['list_template'] = template
            jobs.append(record)
        coverage['detail_complete'] = detail_complete
        coverage['detail_source'] = detail_mode
        coverage['pagination_exhausted'] = pagination_exhausted
        coverage['list_observed_titles'] = sorted(job['job_title'] for job in jobs)
        if not rows:
            channels_tried = ', '.join(coverage['channels_used']) or channel_for(key, scope)
            note = (f'官方站点 {host}/{key} 的公开频道当前 0 条职位(已核对列表页与站点自带的 '
                    f'nextPageList 分页接口): {channels_tried}')
            coverage['errors'].append(
                f'no public posting found for tenant {host}/{key} on channel {channel_for(key, scope)}')
            coverage['note'] = note
    except BudgetExhausted:
        coverage['request_budget_exhausted'] = True
        coverage['pagination_exhausted'] = False
        coverage['detail_complete'] = False
    except Exception as error:
        coverage['errors'].append(f'{type(error).__name__}: {error}')
    coverage['request_budget'] = budget
    coverage['evidence'] = sorted(path.name for path in output_dir.glob('*'))
    coverage['evidence_files'] = coverage['evidence']
    result = shared.finish(jobs, coverage)
    if coverage.get('request_budget_exhausted'):
        result['coverage'].update(complete=False)
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
    parser.add_argument('--fetch-channel', dest='fetch_channel',
                        choices=['html', 'api', 'headless'])
    args = parser.parse_args()
    payload = collect(args.company, args.scope, args.output_dir,
                      max_requests=args.max_requests, fetch_channel=args.fetch_channel)
    print(json.dumps({'company': args.company, 'scope': args.scope,
                      'coverage': payload['coverage']}, ensure_ascii=False))
