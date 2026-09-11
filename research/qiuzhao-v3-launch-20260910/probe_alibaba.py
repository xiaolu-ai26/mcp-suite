"""Probe Alibaba campus SPA: capture XHRs + cookies after JS renders."""
import json
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
URL = 'https://talent.alibaba.com/campus/position-list'

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = b.new_context(user_agent=UA, locale='zh-CN')
    page = ctx.new_page()
    captured = []

    def on_resp(resp):
        u = resp.url
        if 'position' in u and ('api' in u or '/search' in u or 'json' in resp.headers.get('content-type', '')):
            try:
                body = resp.text()[:400]
            except Exception:
                body = ''
            captured.append((resp.request.method, u, resp.status, body))

    page.on('response', on_resp)
    try:
        page.goto(URL, wait_until='networkidle', timeout=45000)
    except Exception as e:
        print('goto warn:', e)
    page.wait_for_timeout(3000)
    print('--- cookies ---')
    for c in ctx.cookies():
        print(' cookie:', c['name'], '=', c['value'][:30])
    print('--- captured api-ish ---')
    for m, u, s, body in captured[:20]:
        print(m, s, u)
        if body:
            print('   body:', body[:200])
    b.close()
