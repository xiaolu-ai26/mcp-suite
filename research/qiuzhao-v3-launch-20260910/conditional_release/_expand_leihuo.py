#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扩源：网易雷火(project_id=77) 2027届校招岗位采集与字段映射。"""
import json, urllib.request, ssl
from datetime import datetime, timezone, timedelta

OUT = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release"
CTX = ssl.create_default_context()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def http_get(url, referer):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    url = ("https://xiaozhao.leihuo.netease.com/api/apply/job/list/show"
           "?job_name=&page_size=200&page_number=1&project_id=77")
    d = http_get(url, "https://leihuo.163.com/campus/")
    assert d.get("status") == 200, d
    jobs = d["data"]["apply_job_list"]
    print(f"[leihuo] list count_number={d['data']['count_number']} fetched={len(jobs)}")

    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    records = []
    for j in jobs:
        ehr = j.get("ehr_job_id") or ""
        desc = (j.get("job_description") or "").strip()
        req = (j.get("job_requirement") or "").strip()
        description_raw = (desc + "\n\n" + req).strip() if req else desc
        cities = [c.strip() for c in (j.get("work_place_name") or "").split(",") if c.strip()]
        dept = j.get("department_name") or []
        target = j.get("target") or j.get("job_target") or ""
        detail = j.get("job_detail_url") or f"https://campus.163.com/app/detail/index?id={ehr}&projectId=77"

        rec = {
            "id": f"netease-leihuo-{ehr}",
            "recruitment_unit": "网易雷火",
            "contracting_entity": "",
            "job_title": j.get("job_name", ""),
            "job_category": j.get("category_name", "") or "",
            "cities": cities,
            "major_requirements_raw": "",
            "major_tags": [],
            "education_raw": "",
            "cohort_raw": f"2027届（网易游戏雷火2027届校园招聘）",
            "deadline": "",
            "deadline_type": "",
            "status": "open",
            "application_url": detail,
            "source_url": detail,
            "published_at": "",
            "reviewed_at": now,
            "source_name": "网易游戏雷火校园招聘官网",
            "evidence_path": "",
            "description_raw": description_raw,
            "recruiting_unit_raw": "网易雷火",
            "deadline_scope": "",
            "cohort_scope": "campaign_announcement",
            "hiring_department_raw": "、".join(dept) if isinstance(dept, list) else str(dept),
            "announcement_url": "",
            "campaign_url": "https://leihuo.163.com/campus/#/full?channel=iSfFmJe",
            "published_at_scope": "",
            "announcement_evidence_path": "",
            "source_record_id": str(ehr),
            "recruitment_type": "校招",
            "overseas_flag": False,
            "region": "mainland",
            "industry_tags": ["互联网", "游戏"],
            "incomplete": (not description_raw),
        }
        records.append(rec)

    out = f"{OUT}/batch_netease_leihuo.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    qualified = sum(1 for r in records if not r["incomplete"])
    print(f"[leihuo] wrote {len(records)} -> {out}; qualified={qualified}; incomplete={len(records)-qualified}")

if __name__ == "__main__":
    main()
