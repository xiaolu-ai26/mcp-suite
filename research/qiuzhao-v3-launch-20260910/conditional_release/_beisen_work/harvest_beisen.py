#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Harvest Beisen zhiye campus jobs via POST /api/Jobad/GetJobAdPageList.
List response already contains Duty + Require (full JD body). No login.
"""
import json, subprocess, re, time, datetime as dt

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TZ = dt.timezone(dt.timedelta(hours=8))
NOW = dt.datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")

# tenant -> (slug, display_name, recruitment_unit, industry_tags)
TENANTS = {
    "picc":     ("picc",     "中国人保",   "中国人民保险集团股份有限公司", ["金融","保险"]),
    "ccccltd":  ("ccccltd",  "中国交建",   "中国交通建设集团有限公司",     ["建筑","基建"]),
    "iflytek":  ("iflytek",  "科大讯飞",   "科大讯飞股份有限公司",         ["科技","人工智能"]),
    "changan":  ("changan",  "长安汽车",   "重庆长安汽车股份有限公司",     ["制造","汽车"]),
}

CAMPUS_KW = re.compile(r"校招|校园|应届|20\d{2}届|届|秋招|春招|管培|实习生?|计划|星火|飞星|星辰|启航")
INTERNSHIP_KW = re.compile(r"实习")
COHORT_RE = re.compile(r"(20\d{2}\s*届)")
# crude city extraction from title
CITY_RE = re.compile(r"(北京|上海|天津|重庆|广州|深圳|杭州|南京|成都|武汉|西安|苏州|长沙|合肥|青岛|济南|郑州|福州|厦门|昆明|贵阳|兰州|沈阳|大连|长春|哈尔滨|石家庄|太原|呼和浩特|南宁|海口|银川|西宁|乌鲁木齐|拉萨|贵州|云南|四川|陕西|广东|浙江|江苏|山东|河南|湖北|湖南|福建|安徽|河北|山西|辽宁|吉林|黑龙江|江西|广西|海南|甘肃|青海|宁夏|新疆|内蒙古|西藏)")

def api_post(tenant, page=0, size=50):
    url = f"https://{tenant}.zhiye.com/api/Jobad/GetJobAdPageList"
    body = json.dumps({"PageIndex": page, "PageSize": size}).encode()
    p = subprocess.run(
        ["curl","-s","-A",UA,"--max-time","25","-X","POST",url,
         "-H","Content-Type: application/json","-H",f"Referer: https://{tenant}.zhiye.com/campus/",
         "--data-binary","@-"],
        input=body, capture_output=True, timeout=35)
    raw = p.stdout
    if raw[:2] == b"\x1f\x8b":
        import gzip; raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8","replace"))

def norm_city(name):
    m = CITY_RE.search(name or "")
    if not m: return []
    c = m.group(1)
    prov2city = {"贵州":"贵阳市","云南":"昆明市","四川":"成都市","陕西":"西安市","广东":"广州市",
                 "浙江":"杭州市","江苏":"南京市","山东":"济南市","河南":"郑州市","湖北":"武汉市",
                 "湖南":"长沙市","福建":"福州市","安徽":"合肥市","河北":"石家庄市","山西":"太原市",
                 "辽宁":"沈阳市","吉林":"长春市","黑龙江":"哈尔滨市","江西":"南昌市","广西":"南宁市",
                 "海南":"海口市","甘肃":"兰州市","青海":"西宁市","宁夏":"银川市","新疆":"乌鲁木齐市",
                 "内蒙古":"呼和浩特市","西藏":"拉萨市"}
    if c.endswith("市"): return [c]
    if c in prov2city: return [prov2city[c]]
    return [c+"市"]

def classify(title):
    if INTERNSHIP_KW.search(title):
        return "实习"
    if CAMPUS_KW.search(title):
        return "校招"
    return ""  # unknown -> will not force 校招

harvested = []
report = {}
for tenant,(slug,disp,unit,ind) in TENANTS.items():
    try:
        resp = api_post(tenant, 0, 60)
    except Exception as e:
        report[tenant] = {"status":"fail","reason":str(e)[:120]}
        continue
    if resp.get("Code") != 200:
        report[tenant] = {"status":"fail","reason":f"Code {resp.get('Code')}"}
        continue
    rows = resp.get("Data") or []
    total = resp.get("Count")
    picked = 0
    used = 0
    for r in rows:
        if picked >= 4: break
        title = (r.get("JobAdName") or "").strip()
        duty = (r.get("Duty") or "").strip()
        req = (r.get("Require") or "").strip()
        body = (duty + ("\n\n【任职要求】\n"+req if req else "")).strip()
        if len(body) < 50:   # hard minimum
            continue
        rt = classify(title)
        if rt == "":   # ambiguous -> don't fake 校招, but keep scanning; only take clear campus
            continue
        jid = str(r.get("JobAdId"))
        uuid = r.get("Id")
        cohort_m = COHORT_RE.search(title)
        cohort = cohort_m.group(1) if cohort_m else "2027届"
        cities = norm_city(title)
        detail = f"https://{tenant}.zhiye.com/campus/job/{uuid}"
        rec = {
            "id": f"{slug}-{jid}",
            "recruitment_unit": unit,
            "contracting_entity": "",
            "job_title": title,
            "job_category": r.get("Category") or "",
            "cities": cities,
            "major_requirements_raw": "",
            "major_tags": [],
            "education_raw": r.get("Degree") or "",
            "cohort_raw": cohort,
            "deadline": None,
            "deadline_type": "undisclosed",
            "status": "open",
            "application_url": detail,
            "source_url": detail,
            "published_at": "",
            "reviewed_at": NOW,
            "source_name": f"{disp}校园招聘官方网站(北森)",
            "evidence_path": "",
            "description_raw": body[:6000],
            "recruiting_unit_raw": "",
            "hiring_department_raw": "",
            "source_record_id": jid,
            "recruitment_type": rt,
            "overseas_flag": False,
            "region": "内地",
            "industry_tags": ind,
            "incomplete": False,
        }
        harvested.append(rec)
        picked += 1
        used += 1
    report[tenant] = {"status":"ok","total":total,"picked":picked}
    print(f"{tenant:9} {disp:6} total={total:5} picked={picked}")
    time.sleep(0.8)

json.dump(harvested, open("/tmp/beisen_harvest.json","w"), ensure_ascii=False, indent=2)
print("=== TOTAL harvested:", len(harvested))
print(json.dumps(report, ensure_ascii=False, indent=2))
