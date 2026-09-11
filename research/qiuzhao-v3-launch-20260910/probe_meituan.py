"""Capture Meituan real pagination request via headless."""
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')
URL = 'https://zhaopin.meituan.com/web/position'

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = b.new_context(user_agent=UA, locale='zh-CN')
    page = ctx.new_page()
    bodies = []

    def on_req(req):
        if 'getJobList' in req.url and req.method == 'POST':
            bodies.append(req.post_data)

    page.on('request', on_req)
    page.goto(URL, wait_until='networkidle', timeout=45000)
    page.wait_for_timeout(3000)
    # try clicking next page
    try:
        page.get_by_text('下一页').first.click()
        page.wait_for_timeout(2500)
    except Exception as e:
        print('click next warn:', e)
    try:
        page.get_by_text('2').first.click()
        page.wait_for_timeout(2500)
    except Exception as e:
        print('click page2 warn:', e)

    print('--- captured getJobList bodies ---')
    for bd in bodies[:6]:
        print(bd)
    b.close()
