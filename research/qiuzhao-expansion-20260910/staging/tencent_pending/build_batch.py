#!/usr/bin/env python3
"""Merge details_cache.json into staging -> qualified / incomplete batches."""
import json, os, datetime, re

BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-expansion-20260910/staging/tencent_pending"
OUT_DIR = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release"
CITIES_NORM = {"深圳总部": "深圳", "中国香港": "香港"}
OVERSEAS_CITIES = {"香港", "中国香港", "Hong Kong", "台北"}

now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
jobs = json.load(open(os.path.join(BASE, "jobs.json")))
cache = json.load(open(os.path.join(BASE, "details_cache.json")))

qualified, incomplete = [], []
stat = {"ok": 0, "incomplete_empty": 0, "incomplete_error": 0, "xiaozhao": 0, "shixi": 0, "overseas": 0}

for j in jobs:
    pid = str(j["source_record_id"])
    d = cache.get(pid)
    rec = dict(j)

    if not d or d.get("_error"):
        rec["status_note"] = rec.get("status_note", "") + " | 详情未取得"
        incomplete.append(rec)
        stat["incomplete_error"] += 1
        continue

    desc = (d.get("desc") or "").strip()
    req = (d.get("request") or "").strip()
    topic_detail = (d.get("topicDetail") or "").strip()
    topic_req = (d.get("topicRequirement") or "").strip()
    bonus_g = (d.get("graduateBonus") or "").strip()
    bonus_i = (d.get("internBonus") or "").strip()
    parts = []
    if desc:
        parts.append("【岗位职责】\n" + desc)
    if req:
        parts.append("【任职要求】\n" + req)
    if topic_detail:
        parts.append("【课题描述】\n" + topic_detail)
    if topic_req:
        parts.append("【课题要求】\n" + topic_req)
    if bonus_g:
        parts.append("【加分项】\n" + bonus_g)
    if bonus_i:
        parts.append("【加分项】\n" + bonus_i)
    body = "\n\n".join(parts)

    if len(body) < 30:
        rec["status_note"] = (rec.get("status_note", "") + " | 详情正文过短").strip()
        incomplete.append(rec)
        stat["incomplete_empty"] += 1
        continue

    # education extraction: take the MINIMUM degree floor stated in requirement text
    edu_text = " ".join([req, topic_req])
    def extract_edu(t):
        if re.search(r"博士(?:研究生)?及以上", t): return "博士"
        if re.search(r"硕士(?:研究生)?及以上", t): return "硕士"
        if re.search(r"本科(?:及以上|或以上|学历|学位)", t): return "本科"
        if re.search(r"博士[和或／/].{0,8}硕士", t): return "硕士"   # 博士和优秀硕士 => floor 硕士
        if re.search(r"硕士[和或／/].{0,8}本科", t): return "本科"
        if "硕士" in t: return "硕士"
        if "本科" in t: return "本科"
        if "博士" in t and not re.search(r"博士优先|博士即可", t): return "博士"
        return ""
    education_raw = extract_edu(edu_text)

    # recruitment type
    project = d.get("projectName") or ""
    label = d.get("recruitLabelName") or ""
    rtype = d.get("recruitType")
    is_intern = (rtype == 2) or ("实习" in project) or ("实习" in label)
    rec["recruitment_type"] = "实习" if is_intern else "校招"
    stat["shixi" if is_intern else "xiaozhao"] += 1

    # cities from API, normalize
    raw_cities = d.get("workCityList") or j.get("cities") or []
    cities = []
    for c in raw_cities:
        c = c.strip()
        c = CITIES_NORM.get(c, c)
        if c and c not in cities:
            cities.append(c)
    rec["cities"] = cities

    # overseas flag
    is_overseas = any(any(o in c or c in o for o in OVERSEAS_CITIES) for c in cities)
    rec["overseas_flag"] = is_overseas
    rec["region"] = "overseas" if is_overseas else "mainland"
    if is_overseas:
        stat["overseas"] += 1

    # fill detail fields (no fabrication)
    rec["description_raw"] = body
    rec["education_raw"] = education_raw or j.get("education_raw") or ""  # 从要求正文正则提取，无则留空
    rec["major_requirements_raw"] = j.get("major_requirements_raw") or ""  # API无专业字段，不伪造
    rec["cohort_raw"] = label or project or j.get("cohort_raw") or ""
    rec["recruiting_unit_raw"] = (d.get("intentionBGDList") and " ".join(b.get("showTitle","") for b in d["intentionBGDList"])) or j.get("recruiting_unit_raw") or ""
    rec["hiring_department_raw"] = rec["recruiting_unit_raw"]
    rec["job_category"] = d.get("tidName") or j.get("job_category") or ""
    rec["deadline"] = None
    rec["deadline_type"] = "招满即止"
    rec["deadline_scope"] = "undisclosed"
    rec["published_at"] = None
    rec["published_at_scope"] = "undisclosed"
    rec["reviewed_at"] = now
    rec["status"] = "open"
    rec["industry"] = "互联网/社交游戏"
    rec["announcement_url"] = ""
    rec["campaign_url"] = "https://join.qq.com/post.html"
    qualified.append(rec)
    stat["ok"] += 1

os.makedirs(OUT_DIR, exist_ok=True)
with open(os.path.join(OUT_DIR, "batch_tencent.json"), "w") as f:
    json.dump(qualified, f, ensure_ascii=False, indent=2)
with open(os.path.join(OUT_DIR, "batch_tencent_incomplete.jsonl"), "w") as f:
    for r in incomplete:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print("STAT:", json.dumps(stat, ensure_ascii=False))
print("qualified:", len(qualified), "incomplete:", len(incomplete))
