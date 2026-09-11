import httpx, re, json
c = httpx.Client(timeout=20, follow_redirects=True, headers={'User-Agent':'Mozilla/5.0'})
r = c.get('https://iflytek.zhiye.com/campus/jobs')
html = r.text
# extract BSGlobal
m = re.search(r'var BSGlobal = (\{.*?\});', html, re.S)
if m:
    try:
        bg = json.loads(m.group(1))
        for k,v in bg.items():
            print(k, '=', str(v)[:120])
    except Exception as e:
        print('BSGlobal parse err', e)
# find api endpoints in scripts
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
allsrc = ' '.join(scripts)
for p in set(re.findall(r'["\'](/[Aa]pi/[A-Za-z0-9_/.-]+)', allsrc)):
    print('API:', p)
# also external js
extjs = re.findall(r'<script[^>]+src="([^"]+)"', html)
print('external js:', extjs[:10])
