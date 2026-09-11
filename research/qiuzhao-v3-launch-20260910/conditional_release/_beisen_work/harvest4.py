#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harvest round 4: chery, asymchem, wuxiapptec, cnnc, leapmotor."""
import json, subprocess, re, time, datetime as dt
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
TZ=dt.timezone(dt.timedelta(hours=8))
NOW=dt.datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")
TENANTS={
 "chery":      ("chery",    "奇瑞汽车", "奇瑞汽车股份有限公司",           ["制造","汽车"]),
 "asymchem":   ("asymchem", "凯莱英",   "凯莱英医药集团（天津）股份有限公司", ["医药","CXO"]),
 "wuxiapptec": ("wuxiapptec","药明康德","药明康德新药开发有限公司",        ["医药","CXO"]),
 "cnnc":       ("cnnc",     "中核集团", "中国核工业集团有限公司",           ["能源","核电"]),
 "leapmotor":  ("leapmotor","零跑汽车", "浙江零跑科技股份有限公司",         ["制造","新能源汽车"]),
}
FRESH=re.compile(r"应届|毕业|校招|校园|20\d{2}届|管培|实习生?|智校|暑期|open\s*day|启航|未来|星|营")
CITY_RE=re.compile(r"(北京|上海|天津|重庆|广州|深圳|东莞|南京|苏州|珠海|合肥|成都|武汉|西安|杭州|长沙|芜湖|上海外高桥|天津滨海|上海张江|黄石|常州|泰兴|上海金山)")
def api(tenant,size=50):
    body=json.dumps({"PageIndex":0,"PageSize":size}).encode()
    p=subprocess.run(["curl","-s","-A",UA,"--max-time","25","-X","POST",
        f"https://{tenant}.zhiye.com/api/Jobad/GetJobAdPageList","-H","Content-Type: application/json",
        "-H",f"Referer: https://{tenant}.zhiye.com/campus/","--data-binary","@-"],
        input=body,capture_output=True,timeout=35)
    return json.loads(p.stdout.decode("utf-8","replace"))
def city_of(*t):
    s=" ".join(t); m=CITY_RE.search(s)
    return [m.group(1)+"市"] if m and not m.group(1).endswith("市") else ([m.group(1)] if m else [])
out=[]
for tenant,(slug,disp,unit,ind) in TENANTS.items():
    try: resp=api(tenant)
    except Exception as e: print(tenant,"FAIL",e); continue
    rows=resp.get("Data") or []; picked=0
    for r in rows:
        if picked>=4: break
        title=(r.get("JobAdName") or "").strip()
        duty=(r.get("Duty") or "").strip(); req=(r.get("Require") or "").strip()
        body=(duty+("\n\n【任职要求】\n"+req if req else "")).strip()
        if len(body)<50: continue
        if not FRESH.search(title+req): continue
        rt="实习" if "实习" in title+req else "校招"
        cm=re.search(r"(20\d{2}\s*届)",title+req); cohort=cm.group(1) if cm else "2027届"
        detail=f"https://{tenant}.zhiye.com/campus/job/{r['Id']}"
        out.append({"id":f"{slug}-{r['JobAdId']}","recruitment_unit":unit,"contracting_entity":"",
            "job_title":title,"job_category":r.get("Category") or "","cities":city_of(title,duty),
            "major_requirements_raw":"","major_tags":[],"education_raw":r.get("Degree") or "",
            "cohort_raw":cohort,"deadline":None,"deadline_type":"undisclosed","status":"open",
            "application_url":detail,"source_url":detail,"published_at":"","reviewed_at":NOW,
            "source_name":f"{disp}校园招聘官方网站(北森)","evidence_path":"",
            "description_raw":body[:6000],"recruiting_unit_raw":"","hiring_department_raw":"",
            "source_record_id":str(r['JobAdId']),"recruitment_type":rt,
            "overseas_flag":False,"region":"内地","industry_tags":ind,"incomplete":False})
        picked+=1
    print(f"{tenant:11} {disp:6} total={resp.get('Count'):5} picked={picked}")
    time.sleep(0.6)
json.dump(out,open("/tmp/beisen_round4.json","w"),ensure_ascii=False,indent=2)
print("round4:",len(out))
for r in out: print("  -",r["id"],r["recruitment_type"],r["cities"],r["cohort_raw"],"|",r["job_title"][:36])
