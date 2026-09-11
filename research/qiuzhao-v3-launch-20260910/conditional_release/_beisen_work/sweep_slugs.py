#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wide slug sweep against Beisen API: live tenant => JSON Code200+Count."""
import subprocess, concurrent.futures, json

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

SLUGS = [
 # banks / insurance variants
 "cmb","cmbcn","cmbchinahr","cmbjob","cmbcampus","cmbchina2",
 "icbccampus","gsbank","icbchr","icbcc",
 "bankcomm","jiaohang","bocomcard","bocom2",
 "pudong","spdbank","spcc","spdb2",
 "minsheng","cmbcbank","mshr","cmbc2",
 "cibbank","cibcampus","industrialbank","cib2",
 "paic","pingangroup","pinganjobs","pabank","pa","pingan2","pafp",
 "cpcifg","taibao","cpicglobal","cpic2",
 "citic","citicsec","citicgroup","citicholding","citic2",
 "cebank","everbright","ceb2","cebbank2",
 "huaxiabank","hxbank","hxbchina","hxb2",
 # tech / internet variants
 "hw","careerhw","huaweijob","huawei2","hwcampus",
 "ztecorp","ztehr","zte2","zxtelecom",
 "legend","lenovohr","lenovo2",
 "hik","hikcampus","hikvision2",
 "smic","smiccampus","smics2",
 "yonyouhr","yonyoucampus","yonyou2",
 "sangforhr","sangfor2","sangforcampus",
 "qax","qianxinhr","qianxin2","qianxincampus",
 "momo","momohr","immomo2",
 "xmlaya","ximalayahr","ximalaya2",
 "sensetimehr","sensetimecampus","sensetime2",
 "cambriconhr","cambricon2",
 "unis","unisgroup","ziguang2","thunis",
 "inspurhr","inspur2","inspurcampus","inspurgroup",
 # auto variants
 "fawgroup","fawcar","faw2","fawcampus",
 "dongfeng","dfcv","dongfenghr","dfm2",
 "geelyhr","geelycampus","geely2","geelyauto",
 "gwmhr","greatwall","gwm2","gwmcampus",
 "bydhr","byd2","bydcampus",
 "catlhr","catl2","catlcampus",
 # energy / construction variants
 "chdgroup","chdpower","chd2","huadian",
 "chinadatang","datang","cdt2",
 "spicglobal","spicjob","spic2","sdic",
 "crecgroup","crechr","crec2","crccgroup","crcc2","crcccampus",
 "ccccltd2","cccchr",
 # extra common beisen tenants (high-probability)
 "vanke","ali","tencent","baidu","jd","meituan","pinduoduo","bytedance",
 "djicampus","dji","haier","midea","gree","tcl","boe","lg","xiaomi",
 "oppo","vivo","oneplus","nintendo","netease","360","lianjia","ke",
 "pingan3","pICC2","peopleInsurance","zhongxin","caitong",
]

def probe(slug):
    url = f"https://{slug}.zhiye.com/api/Jobad/GetJobAdPageList"
    try:
        p = subprocess.run(
            ["curl","-s","-A",UA,"--max-time","10","-X","POST",url,
             "-H","Content-Type: application/json","--data-binary",'{"PageIndex":0,"PageSize":1}'],
            capture_output=True, timeout=14)
        raw = p.stdout
        if raw[:1] == b"{":
            d = json.loads(raw.decode("utf-8","replace"))
            if d.get("Code")==200:
                title = ""
                if d.get("Data"):
                    title = d["Data"][0].get("JobAdName","")[:40]
                return (slug, d.get("Count",0), title)
        return None
    except Exception:
        return None

live=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
    for r in ex.map(probe, SLUGS):
        if r: live.append(r)

print("=== LIVE BEISEN TENANTS FOUND ===")
for slug,cnt,title in sorted(live, key=lambda x:-x[1]):
    print(f"  {slug:18} Count={cnt:5}  e.g. {title}")
print("total live:", len(live))
json.dump(live, open("/tmp/beisen_slug_live.json","w"))
