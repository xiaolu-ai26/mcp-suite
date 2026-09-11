#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch probe Beisen zhiye tenants: which resolve + return 200 + have jobs."""
import subprocess, concurrent.futures, json, re

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# (tenant, display, industry)
TENANTS = [
    ("cmbchina","招商银行","金融/银行"),
    ("icbc","工商银行","金融/银行"),
    ("bocom","交通银行","金融/银行"),
    ("spdb","浦发银行","金融/银行"),
    ("cmbc","民生银行","金融/银行"),
    ("cib","兴业银行","金融/银行"),
    ("pingan","平安集团","金融/保险"),
    ("cpic","太平洋保险","金融/保险"),
    ("picc","中国人保","金融/保险"),
    ("citicbank","中信银行","金融/银行"),
    ("cebbank","光大银行","金融/银行"),
    ("hxb","华夏银行","金融/银行"),
    ("huawei","华为","科技/通信"),
    ("zte","中兴","科技/通信"),
    ("lenovo","联想","科技/硬件"),
    ("hikvision","海康威视","科技/硬件"),
    ("smics","中芯国际","科技/半导体"),
    ("iflytek","科大讯飞","科技/AI"),
    ("yonyou","用友","科技/SaaS"),
    ("sangfor","深信服","科技/安全"),
    ("qianxin","奇安信","科技/安全"),
    ("immomo","陌陌","科技/互联网"),
    ("ximalaya","喜马拉雅","科技/音频"),
    ("sensetime","商汤科技","科技/AI"),
    ("cambricon","寒武纪","科技/半导体"),
    ("ziguang","紫光","科技/IT"),
    ("inspur","浪潮","科技/服务器"),
    ("faw","中国一汽","制造/汽车"),
    ("dfm","东风汽车","制造/汽车"),
    ("changan","长安汽车","制造/汽车"),
    ("geely","吉利汽车","制造/汽车"),
    ("gwm","长城汽车","制造/汽车"),
    ("byd","比亚迪","制造/汽车"),
    ("catl","宁德时代","制造/电池"),
    ("chd","中国华电","能源"),
    ("cdt","中国大唐","能源"),
    ("spic","国家电投","能源"),
    ("crec","中国中铁","建筑"),
    ("crcc","中国铁建","建筑"),
    ("ccccltd","中国交建","建筑"),
]

def probe(t):
    tenant, disp, ind = t
    domain = f"{tenant}.zhiye.com"
    # try campus list page
    for path in ["/campus/", "/campus/jobs", "/campus/job", "/"]:
        url = f"https://{domain}{path}"
        try:
            out = subprocess.run(
                ["curl","-s","-L","-A",UA,"--max-time","12","-o","/tmp/_beisen_probe_body","-w","%{http_code}|%{size_download}|%{url_effective}",url],
                capture_output=True, text=True, timeout=18).stdout.strip()
            parts = out.split("|")
            code = parts[0] if parts else "000"
            size = int(parts[1]) if len(parts)>1 and parts[1].isdigit() else 0
            eff = parts[2] if len(parts)>2 else url
            if code == "200" and size > 800:
                # read body markers
                body = open("/tmp/_beisen_probe_body","r",errors="ignore").read()
                has_job = bool(re.search(r"job|position|职位|岗位|招聘", body, re.I))
                is_404 = ("404" in body[:500] and "不存在" in body) or "没有找到" in body
                # detect if SPA shell
                spa = ("<div id=\"app\"" in body or 'id="root"' in body) and len(body) < 30000
                return {"tenant":tenant,"disp":disp,"industry":ind,"url":eff,"code":code,"size":size,"has_job_kw":has_job,"spa_shell":spa,"path":path}
        except Exception as e:
            continue
    return {"tenant":tenant,"disp":disp,"industry":ind,"url":f"https://{domain}/","code":"FAIL","size":0,"has_job_kw":False,"spa_shell":False,"path":""}

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
    for r in ex.map(probe, TENANTS):
        results.append(r)

json.dump(results, open("/tmp/beisen_probe.json","w"), ensure_ascii=False, indent=2)
print(f"{'tenant':12} {'disp':10} code size  kw  spa  path")
for r in results:
    print(f"{r['tenant']:12} {r['disp']:10} {r['code']} {r['size']:6} {str(r['has_job_kw'])[0]}  {str(r['spa_shell'])[0]}  {r['path']}")
