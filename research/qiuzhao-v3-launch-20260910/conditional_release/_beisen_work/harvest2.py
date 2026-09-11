#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harvest round 2: boe, vivo, cmbcn (campus-signal filtered)."""
import json, subprocess, re, time, datetime as dt

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
TZ = dt.timezone(dt.timedelta(hours=8))
NOW = dt.datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")

TENANTS = {
    "boe":    ("boe",   "京东方", "京东方科技集团股份有限公司", ["科技","显示面板"]),
    "vivo":   ("vivo",  "vivo",   "维沃移动通信有限公司",         ["科技","智能手机"]),
    "cmbcn":  ("cmbcn", "招商银行", "招商银行股份有限公司",         ["金融","银行"]),
}
FRESH = re.compile(r"应届|毕业|校招|校园|20\d{2}届|管培")
CITY_RE = re.compile(r"(北京|上海|天津|重庆|广州|深圳|东莞|南京|苏州|珠海|张家港|合肥|成都|武汉|西安|杭州|长沙|佛山|惠州|西安)")

def api_post(tenant, page=0, size=40):
    url = f"https://{tenant}.zhiye.com/api/Jobad/GetJobAdPageList"
    body = json.dumps({"PageIndex": page, "PageSize": size}).encode()
    p = subprocess.run(["curl","-s","-A",UA,"--max-time","25","-X","POST",url,
        "-H","Content-Type: application/json","-H",f"Referer: https://{tenant}.zhiye.com/campus/",
        "--data-binary","@-"], input=body, capture_output=True, timeout=35)
    return json.loads(p.stdout.decode("utf-8","replace"))

def city_of(*texts):
    s = " ".join(texts)
    m = CITY_RE.search(s)
    if not m: return []
    c = m.group(1)
    zj = {"张家港":"苏州市"}
    if c in zj: return [zj[c]]
    if c.endswith("市"): return [c]
    return [c+"市"]

out=[]
for tenant,(slug,disp,unit,ind) in TENANTS.items():
    resp = api_post(tenant, 0, 40)
    rows = resp.get("Data") or []
    picked=0
    for r in rows:
        if picked>=4: break
        title=(r.get("JobAdName") or "").strip()
        duty=(r.get("Duty") or "").strip()
        req=(r.get("Require") or "").strip()
        body=(duty+("\n\n【任职要求】\n"+req if req else "")).strip()
        if len(body)<50: continue
        # campus-signal gate: must have fresh-grad signal in title OR require
        blob = title+req
        if not FRESH.search(blob): continue
        rt = "实习" if "实习" in title+req else "校招"
        jid=str(r.get("JobAdId")); uuid=r.get("Id")
        cm = re.search(r"(20\d{2}\s*届)", title+req)
        cohort = cm.group(1) if cm else "2027届"
        cities = city_of(title, duty)
        detail=f"https://{tenant}.zhiye.com/campus/job/{uuid}"
        out.append({
            "id":f"{slug}-{jid}","recruitment_unit":unit,"contracting_entity":"",
            "job_title":title,"job_category":r.get("Category") or "",
            "cities":cities,"major_requirements_raw":"","major_tags":[],
            "education_raw":r.get("Degree") or "","cohort_raw":cohort,
            "deadline":None,"deadline_type":"undisclosed","status":"open",
            "application_url":detail,"source_url":detail,"published_at":"",
            "reviewed_at":NOW,"source_name":f"{disp}校园招聘官方网站(北森)",
            "evidence_path":"","description_raw":body[:6000],
            "recruiting_unit_raw":"","hiring_department_raw":"",
            "source_record_id":jid,"recruitment_type":rt,
            "overseas_flag":False,"region":"内地","industry_tags":ind,
            "incomplete":False,
        })
        picked+=1
    print(f"{tenant:7} {disp:6} total={resp.get('Count')} picked={picked}")
    time.sleep(0.7)

json.dump(out, open("/tmp/beisen_harvest2.json","w"), ensure_ascii=False, indent=2)
print("harvested round2:", len(out))
for r in out:
    print("  -",r["id"],r["recruitment_type"],r["cities"],r["cohort_raw"],"|",r["job_title"][:40])
