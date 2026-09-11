"""Probe beisen zhiye.com tenants - discover which resolve + their job API."""
import httpx, sys, re

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'
c = httpx.Client(timeout=15, follow_redirects=True, headers={'User-Agent': UA})

TENANTS = [
    'huawei','zte','lenovo','hikvision','smics','iflytek','yonyou','sangfor',
    'qianxin','immomo','ximalaya','cmbchina','icbc','bocom','spdb','cmbc',
    'cib','pingan','cpic','picc','cta','newchinalife','360','beike','yiche',
    'mi','xiaomi','bytedance','tencent','alibaba','baidu','jd','meituan',
]

for t in TENANTS:
    for url in [f'https://{t}.zhiye.com/campus/jobs', f'https://{t}.zhiye.com/']:
        try:
            r = c.get(url)
            if r.status_code == 200 and len(r.text) > 3000 and '二维码' not in r.text[:1500]:
                title = re.search(r'<title>(.*?)</title>', r.text)
                print(f'[OK] {t}: {url} len={len(r.text)} title={(title.group(1) if title else "")[:50]}')
                break
        except Exception:
            pass
    else:
        print(f'[--] {t}: blocked/notfound', file=sys.stderr)
