#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扩源：网易互娱(projectId=102) 2027届校招岗位采集与字段映射。"""
import json, time, urllib.request, ssl, sys
from datetime import datetime, timezone, timedelta

OUT = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release"
CTX = ssl.create_default_context()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def http_get(url, referer):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    list_url = "https://campus.game.163.com/api/campuspc/position/getJobList?pageSize=200&currentPage=1&projectId=102"
    d = http_get(list_url, "https://campus.game.163.com/app/job/position?id=102")
    assert d.get("code") == 200, d
    jobs = d["data"]["list"]
    total = d["data"]["total"]
    print(f"[huyu] list total={total} fetched={len(jobs)}")

    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    records = []
    for j in jobs:
        jid = j["id"]
        # enrich detail for publishTime
        pub = ""
        try:
            det = http_get(f"https://campus.game.163.com/api/campuspc/position/getJobDetails?id={jid}",
                           f"https://campus.game.163.com/app/detail/index?id={jid}")
            if det.get("code") == 200 and det.get("data"):
                pub = det["data"].get("publishTime") or ""
        except Exception as e:
            print(f"  [detail warn] id={jid}: {e}", file=sys.stderr)
        time.sleep(0.15)

        desc = (j.get("positionDescription") or "").strip()
        req = (j.get("positionRequirement") or "").strip()
        description_raw = (desc + "\n\n" + req).strip() if req else desc
        cities = [c.strip() for c in (j.get("workPlaceName") or "").split(",") if c.strip()]

        rec = {
            "id": f"netease-huyu-{jid}",
            "recruitment_unit": "网易互娱",
            "contracting_entity": "",
            "job_title": j.get("positionName", ""),
            "job_category": j.get("positionTypeName", "") or "",
            "cities": cities,
            "major_requirements_raw": "",
            "major_tags": [],
            "education_raw": "",
            "cohort_raw": "2027届（网易互娱2027届校园招聘）",
            "deadline": "",
            "deadline_type": "",
            "status": "open",
            "application_url": f"https://campus.163.com/app/detail/index?id={jid}",
            "source_url": f"https://campus.game.163.com/app/detail/index?id={jid}",
            "published_at": pub,
            "reviewed_at": now,
            "source_name": "网易互娱校招官网",
            "evidence_path": "",
            "description_raw": description_raw,
            "recruiting_unit_raw": "网易互娱",
            "deadline_scope": "",
            "cohort_scope": "campaign_announcement",
            "hiring_department_raw": "",
            "announcement_url": "",
            "campaign_url": "https://campus.game.163.com/app/job/position?id=102",
            "published_at_scope": "listing",
            "announcement_evidence_path": "",
            "source_record_id": str(jid),
            "recruitment_type": "校招",
            "overseas_flag": False,
            "region": "mainland",
            "industry_tags": ["互联网", "游戏"],
            "incomplete": (not description_raw),
        }
        records.append(rec)

    out = f"{OUT}/batch_netease_huyu.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    qualified = sum(1 for r in records if not r["incomplete"])
    print(f"[huyu] wrote {len(records)} -> {out}; qualified={qualified}; incomplete={len(records)-qualified}")

if __name__ == "__main__":
    main()
