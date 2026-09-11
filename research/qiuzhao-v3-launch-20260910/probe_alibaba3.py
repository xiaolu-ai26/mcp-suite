"""Probe Alibaba v3: capture ALL XHRs + rendered job cards."""
import json
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
URL = 'https://talent.alibaba.com/campus/position-list'

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = b.new_context(user_agent=UA, locale='zh-CN')
    page = ctx.new_page()
    calls = []

    def on_req(req):
        if req.resource_type in ('xhr', 'fetch') and req.method == 'POST':
            calls.append((req.url, req.post_data))

    page.on('request', on_req)
    try:
        page.goto(URL, wait_until='networkidle', timeout=45000)
    except Exception as e:
        print('goto warn:', e)
    page.wait_for_timeout(5000)

    print('--- all post XHRs ---')
    for u, body in calls:
        print(u)
        print('   ', (body or '')[:300])

    # visible text hints
    txt = page.inner_text('body')
    import re
    print('--- page contains "共" / 条 ---')
    for m in re.findall(r'共\s*\d+\s*条', txt)[:5]:
        print(' ', m)
    print('first 300 chars of visible:', txt[:300].replace('\n', ' '))
    b.close()
