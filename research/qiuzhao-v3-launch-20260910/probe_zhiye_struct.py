import httpx, re, json
c = httpx.Client(timeout=20, follow_redirects=True, headers={'User-Agent':'Mozilla/5.0'})
r = c.get('https://iflytek.zhiye.com/campus/jobs')
html = r.text
for pat in [r'window\.__INITIAL_STATE__', r'window\.__NUXT__', r'jobId', r'recruiterId', r'"jobName"']:
    m = re.findall(pat, html)
    print('PAT', pat, '->', len(m), 'matches')
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
print('num scripts:', len(scripts))
for i, s in enumerate(scripts):
    if 'job' in s.lower() and len(s) > 500:
        print('--- script', i, 'len=', len(s))
        print(s[:400].replace(chr(10), ' '))
# also look for job links / ids in HTML
links = re.findall(r'href="(/campus/jobDetail[^"]*)"', html)
print('jobDetail links:', links[:5])
ids = re.findall(r'/campus/jobDetail/(\w+)', html)
print('job ids:', list(set(ids))[:10])
