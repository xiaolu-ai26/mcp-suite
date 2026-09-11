#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Second wide slug sweep."""
import subprocess, concurrent.futures, json
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
SLUGS = [
 # still-unfound targets, more variants
 "cmb","cmbjob","cmbcampus","cmbchinahr","cmb2","cmbcn2",
 "icbc","icbccampus","icbchr","gsbank2",
 "bocom","bankcomm","bocomcard","bocom2",
 "spdb","pudong","spdbank","minsheng","cmbc","cibbank","cib2",
 "paic","pingan","pingangroup","pabank","cpcifg","cpic",
 "citic","citicsec","citicbank","cebbank","everbright","ceb2","hxbank","huaxia",
 "huawei","zte","lenovo","hikvision","smic","yonyou","sangfor","qianxin",
 "immomo","ximalaya","sensetime","cambricon","ziguang","unis","inspur",
 "faw","dfm","dongfeng","geely","gwm","byd","catl",
 "chd","cdt","spic","crec","crcc","ccccltd",
 # famous Beisen users
 "jd","jdcampus","jdzhaopin","xiaomi","mi","oppomobile","oppo","hapoppo",
 "dji","djicampus","djitechnology","haier","midea","gree","tcl","tclcampus",
 "mengniu","yili","vanke","longfor","crland","crc","cofco","poly","cscec",
 "cnooc","sinopec","cnpc","sgcc","stategrid","csg","chinatelecom","cmcc",
 "chinamobile","cu","chinaunicom","avic","comac","cssc","cast","cgn","ctg",
 "baowu","baosteel","kuaishou","ks","mihoyo","ctrip","bilibili","bili","weibo",
 "zhihu","shein","luckin","haidilao","sfexpress","sf","zto","jtexpress",
 "vipshop","dewu","poizon","anjuke","ziroom","didiglobal","didi","pdd",
 "genki","nongfu","wanda","gemdale","agile","shimao","sinocean","logon",
 "colina","chinaoverseas","cmsk","cmhk","sinochem","chinatech",
 "fesco","liepin","kanzhun","51job","zhaopin",
 "ant","antgroup","alipay","tencenthr","tencent","alihr","alibaba",
 "bytedancehr","bytedance","meituan","ele","dianping","baidu",
 "360","qiku","kingsoft","wps","shunfeng","yz","yto","sto","yunda",
 "mpc","cicc","cmbwind","hf","szse","sse","csrc","pbc",
]
def probe(slug):
    try:
        p=subprocess.run(["curl","-s","-A",UA,"--max-time","9","-X","POST",
            f"https://{slug}.zhiye.com/api/Jobad/GetJobAdPageList",
            "-H","Content-Type: application/json","--data-binary",'{"PageIndex":0,"PageSize":1}'],
            capture_output=True,timeout=13)
        raw=p.stdout
        if raw[:1]==b"{":
            d=json.loads(raw.decode("utf-8","replace"))
            if d.get("Code")==200:
                t=d["Data"][0]["JobAdName"][:38] if d.get("Data") else ""
                return (slug,d.get("Count",0),t)
    except Exception: return None
live=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=18) as ex:
    for r in ex.map(probe,SLUGS):
        if r: live.append(r)
print("=== LIVE ===")
for s,c,t in sorted(live,key=lambda x:-x[1]): print(f"  {s:16} {c:5}  {t}")
print("total:",len(live))
json.dump(live,open("/tmp/beisen_slug_live2.json","w"))
