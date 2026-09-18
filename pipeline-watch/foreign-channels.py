#!/usr/bin/env python3
"""Multi-channel read-only fetch harness for the foreign-company "find-all" task.

站长要求"请求方式多换几个":every source / company is retried through an explicit
channel ladder instead of a single request style:

  C1 browser  -- requests + a full desktop browser header set (Accept-Language, Referer)
  C2 mobile   -- mobile UA (iPhone/Android) against the site, its m./AMP variant
  C3 machine  -- the site's own JSON endpoint, sitemap.xml, RSS/Atom, public PDF/XLSX
  C4 headless -- Playwright Chromium: DOM after render + the responses the page itself
                 requests (XHR/fetch) are captured
  C5 archive  -- search engine ``site:`` query (DuckDuckGo html endpoint) and the
                 Wayback Machine CDX / availability API

Every outbound request goes through :class:`Ledger`, which
  * enforces a global >= ``FOREIGN_MIN_INTERVAL`` (default 1.5s) gap between requests,
  * enforces a per-host >= ``FOREIGN_HOST_INTERVAL`` (default 3.0s) gap,
  * appends one JSONL row per request (ts / channel / url / status / note),
  * refuses to start once ``FOREIGN_REQUEST_CAP`` (default 2500) is reached.

Nothing logs in, posts a form, or solves a challenge: only public GET/HEAD.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import zlib
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlsplit

UA_DESKTOP = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
UA_MOBILE = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 '
             '(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1')
UA_ANDROID = ('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36')

DEFAULT_LEDGER = '/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/r2/request-log.jsonl'
DEFAULT_RAW = '/Volumes/臭垃圾桶/生财MCP/_worktrees/foreign-discovery-out/r2/raw'

# ---------------------------------------------------------------- ATS markers
# Order matters: the first hit wins. Each entry is (platform, regex, key template).
ATS_PATTERNS = [
    ('Moka', re.compile(r'app\.mokahr\.com/(?:campus-recruitment|campus_apply|social-recruitment|apply|m/campus-recruitment|m/apply)/([^/"\'?\s#]+)/(\d+)'), '{0}/{1}'),
    ('Moka', re.compile(r'mokahr\.com/([^/"\'?\s#]+)/(\d+)'), '{0}/{1}'),
    ('北森', re.compile(r'https?://([a-z0-9][a-z0-9\-]*)\.zhiye\.com'), '{0}'),
    ('北森', re.compile(r'zhiye\.com/[^"\'\s]*?[?&](?:PortalId|portalId|pid)=([0-9a-fA-F\-]{8,})'), '{0}'),
    ('飞书招聘', re.compile(r'https?://([a-z0-9][a-z0-9\-]*)\.jobs\.feishu\.cn'), '{0}'),
    ('飞书招聘', re.compile(r'([a-z0-9][a-z0-9\-]*)\.jobs\.feishu\.cn'), '{0}'),
    ('大易', re.compile(r'https?://([a-z0-9][a-z0-9\-]*)\.hotjob\.cn[^"\'\s]*?(SU[0-9a-fA-F]{20,})'), '{0}|{1}'),
    ('大易', re.compile(r'(SU[0-9a-fA-F]{20,})'), '{0}'),
    ('大易', re.compile(r'hotjob\.cn/wecruit/[^"\'\s]*'), '{0}'),
    ('51job', re.compile(r'campus\.51job\.com/([A-Za-z0-9_\-]+)'), '{0}'),
    ('前程无忧', re.compile(r'https?://(?:xyz|xym|young|jobs|meta|m|we|i)\.51job\.com'), '{0}'),
    ('Workday', re.compile(r'https?://([a-z0-9\-]+)\.wd(\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/"\'?\s]+)'), '{0}/wd{1}/{2}'),
    ('Workday', re.compile(r'myworkdayjobs\.com'), '{0}'),
    ('SuccessFactors', re.compile(r'https?://([a-z0-9\-]+\.(?:jobs|careers|career|job)[a-z0-9\-]*\.[a-z.]+)/(?:search|careers)?'), '{0}'),
    ('SuccessFactors', re.compile(r'(?:successfactors|sapsf)\.(?:com|eu)'), '{0}'),
    ('Eightfold', re.compile(r'https?://([a-z0-9\-]+)\.eightfold\.ai'), '{0}'),
    ('Phenom', re.compile(r'https?://([a-z0-9\-]+)\.phenompeople\.com'), '{0}'),
    ('Phenom', re.compile(r'phenompeople\.com|phenom\.cloud'), '{0}'),
    ('Avature', re.compile(r'https?://([a-z0-9\-]+)\.avature\.net'), '{0}'),
    ('iCIMS', re.compile(r'https?://careers-([a-z0-9\-]+)\.icims\.com'), '{0}'),
    ('iCIMS', re.compile(r'icims\.com'), '{0}'),
    ('ORC', re.compile(r'https?://([a-z0-9\-]+)\.(?:oraclecloud|fa\.oraclecloud)\.com'), '{0}'),
    ('Taleo', re.compile(r'https?://([a-z0-9\-]+)\.taleo\.net'), '{0}'),
    ('SmartRecruiters', re.compile(r'(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_\-]+)'), '{0}'),
    ('Greenhouse', re.compile(r'boards\.greenhouse\.io/([A-Za-z0-9_\-]+)'), '{0}'),
    ('Greenhouse', re.compile(r'job-boards\.greenhouse\.io/([A-Za-z0-9_\-]+)'), '{0}'),
    ('Lever', re.compile(r'jobs\.lever\.co/([A-Za-z0-9_\-]+)'), '{0}'),
    ('tupu360', re.compile(r'https?://([a-z0-9\-]+)\.tupu360\.com'), '{0}'),
    ('tupu360', re.compile(r'tupu360\.com'), '{0}'),
    ('moseeker', re.compile(r'moseeker\.com'), '{0}'),
    ('ajinga', re.compile(r'ajinga\.com/recruiting/company/(\d+)'), '{0}'),
    ('智联招聘', re.compile(r'zhaopin\.com'), '{0}'),
    ('牛客', re.compile(r'nowcoder\.com'), '{0}'),
    ('BOSS直聘', re.compile(r'zhipin\.com'), '{0}'),
    ('猎聘', re.compile(r'liepin\.com'), '{0}'),
]

ATS_ORDER = ['Moka', '北森', '飞书招聘', '大易', '51job', '前程无忧', 'Workday',
             'SuccessFactors', 'Eightfold', 'Phenom', 'Avature', 'iCIMS', 'ORC',
             'Taleo', 'SmartRecruiters', 'Greenhouse', 'Lever', 'tupu360',
             'moseeker', 'ajinga', '智联招聘', '牛客', 'BOSS直聘', '猎聘']


def classify_ats(text: str):
    """Return (platform, key, evidence) for the first ATS marker found in *text*."""
    if not text:
        return '自建/未识别', '', ''
    for platform, rx, keyfmt in ATS_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        try:
            key = keyfmt.format(*m.groups())
        except Exception:
            key = m.group(0)
        return platform, key, m.group(0)[:200]
    return '自建/未识别', '', ''


# ------------------------------------------------------------------- Ledger
class Ledger:
    def __init__(self, path=None, min_interval=None, host_interval=None, cap=None,
                 raw_dir=None, log=True):
        self.path = Path(path or os.environ.get('FOREIGN_LEDGER', DEFAULT_LEDGER))
        self.raw_dir = Path(raw_dir or os.environ.get('FOREIGN_RAW', DEFAULT_RAW))
        self.min_interval = float(min_interval if min_interval is not None
                                  else os.environ.get('FOREIGN_MIN_INTERVAL', '1.5'))
        self.host_interval = float(host_interval if host_interval is not None
                                   else os.environ.get('FOREIGN_HOST_INTERVAL', '3.0'))
        self.cap = int(cap if cap is not None else os.environ.get('FOREIGN_REQUEST_CAP', '2500'))
        self.enabled = log
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.count = self._load_count()
        self.by_channel = {}
        self.by_status = {}
        self._last_global = 0.0
        self._last_host = {}
        self._session = None

    def _load_count(self):
        n = 0
        if self.path.exists():
            with self.path.open(encoding='utf-8') as fh:
                for line in fh:
                    if line.strip():
                        n += 1
        return n

    @property
    def session(self):
        if self._session is None:
            import requests
            s = requests.Session()
            s.headers.update({'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                              'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7'})
            self._session = s
        return self._session

    def _wait(self, host):
        now = time.time()
        gaps = [self.min_interval - (now - self._last_global)]
        if host:
            gaps.append(self.host_interval - (now - self._last_host.get(host, 0)))
        gap = max(gaps)
        if gap > 0:
            time.sleep(gap)

    def record(self, channel, url, status, note=''):
        self.count += 1
        self.by_channel[channel] = self.by_channel.get(channel, 0) + 1
        key = str(status)
        self.by_status[key] = self.by_status.get(key, 0) + 1
        if not self.enabled:
            return
        with self.path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps({'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'channel': channel,
                                 'url': url, 'status': status, 'note': note[:200]},
                                ensure_ascii=False) + '\n')

    def get(self, url, channel='C1', profile='desktop', referer='', note='', timeout=25,
            allow_redirects=True, save='', verify=True, headers=None):
        """One polite public GET. Returns the ``requests`` response or None on failure."""
        if self.count >= self.cap:
            raise RuntimeError('request cap %d reached; stop and report' % self.cap)
        host = urlsplit(url).netloc.lower()
        self._wait(host)
        h = {}
        h['User-Agent'] = {'desktop': UA_DESKTOP, 'mobile': UA_MOBILE,
                           'android': UA_ANDROID}.get(profile, UA_DESKTOP)
        if referer:
            h['Referer'] = referer
        if headers:
            h.update(headers)
        try:
            r = self.session.get(url, headers=h, timeout=timeout,
                                 allow_redirects=allow_redirects, verify=verify)
            self._last_global = self._last_host[host] = time.time()
            self.record(channel, url, r.status_code, note or profile)
            if save:
                dest = self.raw_dir / save
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
            return r
        except Exception as exc:  # noqa: BLE001 - network errors are data here
            self._last_global = self._last_host[host] = time.time()
            self.record(channel, url, 'ERR', '%s: %s' % (note or profile, str(exc)[:120]))
            return None

    def text(self, url, channel='C1', **kw):
        r = self.get(url, channel, **kw)
        if r is None:
            return ''
        ct = (r.headers.get('content-type') or '').lower()
        if 'charset' not in ct:
            r.encoding = r.apparent_encoding or r.encoding or 'utf-8'
        return r.text

    def keep(self, name, data):
        dest = self.raw_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (bytes, bytearray)):
            dest.write_bytes(data)
        else:
            dest.write_text(data, encoding='utf-8')
        return dest

    def cached(self, name):
        dest = self.raw_dir / name
        return dest.read_bytes() if dest.exists() else None


# ----------------------------------------------------------- C3: sitemap/RSS
def parse_sitemap(xml):
    return [u for u in re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', xml or '')]


def parse_feed(xml):
    items = re.findall(r'<item>(.*?)</item>', xml or '', re.S) or \
        re.findall(r'<entry>(.*?)</entry>', xml or '', re.S)
    out = []
    for it in items:
        m = re.search(r'<link[^>]*href="([^"]+)"', it) or re.search(r'<link>\s*([^<]+)\s*</link>', it)
        t = re.search(r'<title[^>]*>(.*?)</title>', it, re.S)
        if m:
            out.append({'url': m.group(1).strip(),
                        'title': re.sub(r'<[^>]+>', '', t.group(1)).strip() if t else ''})
    return out


def pdf_text(data):
    """Best-effort text out of a public PDF (FlateDecode streams + Tj/TJ operators)."""
    out = []
    for m in re.finditer(rb'stream\r?\n(.*?)endstream', data or b'', re.S):
        chunk = m.group(1)
        try:
            chunk = zlib.decompress(chunk)
        except Exception:
            continue
        for tm in re.finditer(rb'\((?:\\.|[^\\()])*\)', chunk):
            s = tm.group(0)[1:-1]
            s = s.replace(b'\\(', b'(').replace(b'\\)', b')').replace(b'\\\\', b'\\')
            try:
                out.append(s.decode('utf-8'))
            except Exception:
                try:
                    out.append(s.decode('gbk', 'ignore'))
                except Exception:
                    pass
    return ' '.join(out)


def xlsx_rows(data):
    """Minimal .xlsx reader (shared strings + first worksheet) with no third-party deps."""
    import io
    import zipfile
    import xml.etree.ElementTree as ET
    ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    zf = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if 'xl/sharedStrings.xml' in zf.namelist():
        root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
        for si in root.findall(ns + 'si'):
            shared.append(''.join(t.text or '' for t in si.iter(ns + 't')))
    rows = []
    sheets = [n for n in zf.namelist() if n.startswith('xl/worksheets/sheet')]
    for name in sorted(sheets)[:1]:
        root = ET.fromstring(zf.read(name))
        for row in root.iter(ns + 'row'):
            cells = []
            for c in row.findall(ns + 'c'):
                v = c.find(ns + 'v')
                txt = v.text if v is not None else ''
                if c.get('t') == 's' and txt:
                    txt = shared[int(txt)] if int(txt) < len(shared) else ''
                cells.append(txt or '')
            rows.append(cells)
    return rows


# ---------------------------------------------------------- C5: search/CDX
def ddg(ledger, query, note='', pages=1, channel='C5-search'):
    """DuckDuckGo html endpoint (no JS, no login). Returns [{title,url,snippet}]."""
    from bs4 import BeautifulSoup
    results = []
    for page in range(pages):
        url = 'https://html.duckduckgo.com/html/?q=' + quote_plus(query)
        if page:
            url += '&s=%d&dc=%d' % (page * 30, page * 30 + 1)
        html = ledger.text(url, channel, referer='https://duckduckgo.com/', note=note or query[:60])
        if not html:
            break
        soup = BeautifulSoup(html, 'html.parser')
        got = 0
        for res in soup.select('div.result, div.web-result'):
            a = res.select_one('a.result__a')
            if not a:
                continue
            href = a.get('href') or ''
            m = re.search(r'uddg=([^&]+)', href)
            if m:
                href = unquote(m.group(1))
            sn = res.select_one('.result__snippet')
            results.append({'title': a.get_text(' ', strip=True), 'url': href,
                            'snippet': sn.get_text(' ', strip=True) if sn else ''})
            got += 1
        if got == 0:
            break
    return results


def wayback_cdx(ledger, url, match_type='domain', limit=2000, collapse='urlkey',
                fl='original,timestamp,statuscode', extra='', note=''):
    """Wayback CDX API -> list of dict rows. Machine-readable archive channel."""
    api = ('http://web.archive.org/cdx/search/cdx?url=' + quote_plus(url) +
           '&matchType=%s&limit=%d&fl=%s&output=json' % (match_type, limit, fl))
    if collapse:
        api += '&collapse=' + collapse
    if extra:
        api += '&' + extra
    txt = ledger.text(api, 'C5-cdx', note=note or ('cdx ' + url))
    if not txt:
        return []
    try:
        rows = json.loads(txt)
    except Exception:
        return []
    if not rows:
        return []
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:]]


def wayback_available(ledger, url, note=''):
    txt = ledger.text('https://archive.org/wayback/available?url=' + quote_plus(url),
                      'C5-wayback', note=note or ('avail ' + url))
    try:
        return json.loads(txt or '{}')
    except Exception:
        return {}


# ------------------------------------------------------------ C4: headless
def headless(ledger, url, wait_ms=5000, note='', grab_json=True, scroll=1,
             timeout_ms=45000, profile='desktop'):
    """Render with Playwright Chromium, return (dom_html, xhr_payloads, final_url)."""
    from playwright.sync_api import sync_playwright
    captured = []
    dom = ''
    final = url
    ua = {'desktop': UA_DESKTOP, 'mobile': UA_MOBILE, 'android': UA_ANDROID}.get(profile, UA_DESKTOP)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=ua, locale='zh-CN',
                                  viewport={'width': 1440, 'height': 900},
                                  extra_http_headers={'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'})
        page = ctx.new_page()

        def on_response(resp):
            if not grab_json:
                return
            try:
                ct = (resp.headers or {}).get('content-type', '')
                if 'json' in ct.lower() and len(captured) < 40:
                    captured.append({'url': resp.url, 'status': resp.status,
                                     'body': resp.text()[:200000]})
            except Exception:
                pass

        page.on('response', on_response)
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
            page.wait_for_timeout(wait_ms)
            for _ in range(max(0, scroll)):
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(1200)
            dom = page.content()
            final = page.url
        except Exception as exc:
            note = (note + ' | render-error ' + str(exc)[:100]).strip(' |')
        ctx.close()
        browser.close()
    ledger.record('C4', url, 'render', note or ('%dB dom, %d json' % (len(dom), len(captured))))
    return dom, captured, final


# ------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('url', nargs='?')
    ap.add_argument('--channel', default='C1')
    ap.add_argument('--profile', default='desktop')
    ap.add_argument('--referer', default='')
    ap.add_argument('--save', default='')
    ap.add_argument('--ddg', default='')
    ap.add_argument('--cdx', default='')
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--count', action='store_true')
    args = ap.parse_args()
    led = Ledger()
    if args.count:
        print(json.dumps({'ledger': str(led.path), 'requests': led.count}, ensure_ascii=False))
        return 0
    if args.ddg:
        for row in ddg(led, args.ddg)[:15]:
            print(json.dumps(row, ensure_ascii=False))
        return 0
    if args.cdx:
        for row in wayback_cdx(led, args.cdx)[:25]:
            print(json.dumps(row, ensure_ascii=False))
        return 0
    if not args.url:
        ap.error('need url / --ddg / --cdx')
    if args.headless:
        dom, js, final = headless(led, args.url)
        print(json.dumps({'final': final, 'dom': len(dom), 'json': len(js)}, ensure_ascii=False))
        print(classify_ats(dom))
        return 0
    text = led.text(args.url, args.channel, profile=args.profile, referer=args.referer, save=args.save)
    print(len(text), classify_ats(text))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
