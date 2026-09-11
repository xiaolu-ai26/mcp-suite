#!/usr/bin/env python3
import subprocess, concurrent.futures, json
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
SLUGS=[
 # securities
 "huatai","gtja","haitong","sws","gfzq","cms","gxzq","dfzq","xczq","cmsky",
 "citics","citicssec","csc","cmschina","ebscn","cmscapital",
 # insurers
 "newchina","taikang","taikanglife","sunshine","aia","aiachina","cpic2","picclife","pinganlife",
 # new energy auto / auto
 "nio","nextev","lixiang","lixiang","xpeng","xiaopeng","leapmotor","hozon","seres","sereshz",
 "saic","saicmotor","gac","baic","jac","chery","brilliance","dongfeng2","dfac",
 # pharma
 "hengrui","hengruimedicine","wuxiapptec","sinopharm","shph","fosh Pharma","foscopharma","jassen",
 "pharmaron","asymchem","3s","zhifei","kanglong","hjb","walvax",
 # tech/campus
 "iqiyi","sina","sohu","mgtv","douyu","huya","xunlei","kingsoft","ctrip2","tujia",
 "netease2","leihuo","kaola","fliggy","eleme","dianping2","meituan2",
 # logistics / energy / construction
 "cosco","coscoshipping","jdl","jdlcorp","huaneng","guodian","shenhua","chinacoal","cgn2",
 "ctg2","mcc","powerchina","ceec","cncec","crrc","crsc",
 # banks other
 "hsbc","scb","bankeast","dbs","hangseng","cgb","cgbchina","cbb","psbc","abc","boc","ccb",
 # retail/consumer
 "walmart","carrefour","yonghui","crvanguard","dashang","wfj","luckin2","heytea","nayuki",
 # misc big beisen
 "antgroup2","ant2","alipay2","webank","webank","cmbwing","cindasc","cinda","hxb2",
 "spic2","cnnc","cnnc2","cgnglobal","sdic2","chd2","cdt2",
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
                t=d["Data"][0]["JobAdName"][:36] if d.get("Data") else ""
                return (slug,d.get("Count",0),t)
    except Exception: return None
live=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=18) as ex:
    for r in ex.map(probe,SLUGS):
        if r: live.append(r)
print("=== LIVE round3 ===")
for s,c,t in sorted(live,key=lambda x:-x[1]): print(f"  {s:14} {c:5}  {t}")
print("total:",len(live))
json.dump(live,open("/tmp/beisen_slug_live3.json","w"))
