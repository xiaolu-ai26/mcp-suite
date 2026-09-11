"""Probe Alibaba v2: capture POST bodies for /position/search + dump batches."""
import json
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
URL = 'https://talent.alibaba.com/campus/position-list'

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = b.new_context(user_agent=UA, locale='zh-CN')
    page = ctx.new_page()

    def on_req(req):
        if '/position/search' in req.url and req.method == 'POST':
            print('POST BODY ->', req.post_data)
        if 'campus-position-list.json' in req.url:
            print('STATIC URL ->', req.url)

    page.on('request', on_req)
    try:
        page.goto(URL, wait_until='networkidle', timeout=45000)
    except Exception as e:
        print('goto warn:', e)
    page.wait_for_timeout(4000)

    # read static batches json directly
    r = page.request.get('https://fc.alibaba.com/0.0.5/ali-star/campus-position-list.json')
    data = r.json()
    print('--- batches ---')
    for bch in data[:10]:
        print(' batchCode=', bch.get('batchCode'), '|', bch.get('batchName'))

    # try a search with a known batchCode
    xsrf = ''
    for c in ctx.cookies():
        if c['name'] == 'XSRF-TOKEN':
            xsrf = c['value']
    print('xsrf=', xsrf)
    body = {'currentPage': 1, 'pageSize': 10, 'campusType': 'campus', 'batchCode': 'freshman'}
    rr = page.request.post(f'https://talent.alibaba.com/position/search?_csrf={xsrf}',
                           data=json.dumps(body),
                           headers={'Content-Type': 'application/json'})
    print('--- manual search ---')
    print(rr.status, rr.text()[:600])
    b.close()
