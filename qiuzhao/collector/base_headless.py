"""Shared headless-Chromium base for SPA recruitment sources.

Some public recruitment sites render their position list in JS and gate the
underlying JSON API with a generated token/signature (e.g. Alibaba's CSRF
`_csrf` cookie). Plain urllib POSTs fail; loading the page in a real browser
lets JS set the cookie/token, after which the same page context can issue the
JSON request via `page.request` (cookies + headers shared).

No login, no CAPTCHA solving, no credential reuse. Only public listing pages.

Usage:
    with HeadlessSource(collector) as h:
        h.open(LISTING_URL)
        data = h.post_json(API_URL, payload)
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager

from .run import now

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36')


class HeadlessUnavailable(RuntimeError):
    """Playwright or Chromium is not installed; caller should degrade gracefully."""


class HeadlessSource:
    """Thin wrapper around a Playwright headless Chromium page.

    Lazy import so the daily cron path (API adapters only) never requires
    playwright. If chromium is missing, open() raises HeadlessUnavailable.
    """

    def __init__(self, collector, delay=1.5, timeout_ms=45000):
        self.collector = collector
        self.delay = delay
        self.timeout_ms = timeout_ms
        self._pw = None
        self._browser = None
        self._context = None
        self.page = None
        self.last_call = 0

    def _ensure(self):
        if self.page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:  # pragma: no cover - environment dependent
            raise HeadlessUnavailable(f'playwright not importable: {e}') from e
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True, args=['--no-sandbox'])
            self._context = self._browser.new_context(user_agent=UA, locale='zh-CN')
            self._context.set_default_timeout(self.timeout_ms)
            self.page = self._context.new_page()
        except Exception as e:
            self.close()
            raise HeadlessUnavailable(f'chromium launch failed: {e}') from e

    def open(self, url, wait_until='networkidle'):
        self._ensure()
        self.page.goto(url, wait_until=wait_until)
        return self.page

    def throttle(self):
        time.sleep(max(0, self.delay - (time.monotonic() - self.last_call)))
        self.last_call = time.monotonic()

    def post_json(self, url, payload, headers=None):
        """POST JSON via the browser request context (shares cookies/CSRF)."""
        self._ensure()
        self.throttle()
        resp = self.page.request.post(
            url, data=json.dumps(payload),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                     **(headers or {})})
        return resp.status, resp.json()

    def get_json(self, url, headers=None):
        self._ensure()
        self.throttle()
        resp = self.page.request.get(url, headers={'Accept': 'application/json', **(headers or {})})
        return resp.status, resp.json()

    def cookies(self):
        return self._context.cookies() if self._context else []

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

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@contextmanager
def headless_session(collector, **kw):
    h = HeadlessSource(collector, **kw)
    try:
        h._ensure()
        yield h
    finally:
        h.close()
