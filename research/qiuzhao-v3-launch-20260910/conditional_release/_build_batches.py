#!/usr/bin/env python3
"""Build qualified batch JSON for ByteDance + Alibaba campus expansion.

Reads raw harvests from _bytedance_raw/ and _alibaba_raw/, maps to the
canonical qualified_jobs.json schema, and writes:
  conditional_release/batch_bytedance.json
  conditional_release/batch_alibaba.json
"""
import json
import re
from datetime import datetime, timezone, timedelta

BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release"
TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")

HK_PAT = re.compile(r"香港|澳门|台湾|Hong Kong|Macau|Taiwan")
OVERSEAS = re.compile(r"新加坡|首尔|东京|悉尼|洛杉矶|纽约|伦敦|巴黎|硅谷|西雅图|旧金山|慕尼黑|阿姆斯特丹|都柏林|圣何塞|西雅图|Taguig|塔吉格|Berlin")


def epoch_ms_to_date(ms):
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, TZ).strftime("%Y-%m-%d")
    except Exception:
        return None


def is_overseas(cities):
    s = " ".join(cities or [])
    return bool(HK_PAT.search(s) or OVERSEAS.search(s))


# ---------------- ByteDance ----------------
def build_bytedance():
    raw = json.load(open(f"{BASE}/_bytedance_raw/bytedance_campus_raw.json"))
    out = []
    incomplete = 0
    for r in raw:
        desc = (r.get("description") or "").strip()
        req = (r.get("requirement") or "").strip()
        body = (desc + "\n" + req).strip()
        if len(body) < 80:
            incomplete_flag = True
            incomplete += 1
        else:
            incomplete_flag = False
        rt = r.get("recruit_type")  # 正式 / 实习
        recruitment_type = "校招" if rt == "正式" else "实习"
        cities = r.get("cities") or []
        overseas = is_overseas(cities)
        rec = {
            "id": f"bytedance-{r['id']}",
            "recruitment_unit": "字节跳动",
            "contracting_entity": "",
            "job_title": r.get("title", ""),
            "job_category": r.get("job_category") or "",
            "cities": cities,
            "major_requirements_raw": "",
            "major_tags": [],
            "education_raw": "",
            "cohort_raw": "2027届",
            "deadline": None,
            "deadline_type": "undisclosed",
            "status": "open",
            "application_url": f"https://jobs.bytedance.com/campus/position/{r['id']}/detail",
            "source_url": f"https://jobs.bytedance.com/campus/position/{r['id']}/detail",
            "published_at": epoch_ms_to_date(r.get("publish_time")),
            "reviewed_at": NOW,
            "source_name": "字节跳动校园招聘官方网站",
            "description_raw": body,
            "recruiting_unit_raw": "",
            "hiring_department_raw": "",
            "source_record_id": str(r.get("id")),
            "recruitment_type": recruitment_type,
            "overseas_flag": overseas,
            "region": "overseas" if overseas else "mainland",
            "industry": ["互联网", "短视频"],
            "incomplete": incomplete_flag,
            "job_code": r.get("code", ""),
        }
        out.append(rec)
    return out, incomplete


# ---------------- Alibaba ----------------
def build_alibaba():
    raw = json.load(open(f"{BASE}/_alibaba_raw/alibaba_campus_raw.json"))
    out = []
    incomplete = 0
    for r in raw:
        desc = (r.get("description") or "").strip()
        req = (r.get("requirement") or "").strip()
        body = (desc + "\n" + req).strip()
        if len(body) < 80:
            incomplete_flag = True
            incomplete += 1
        else:
            incomplete_flag = False
        cities = r.get("workLocations") or []
        overseas = is_overseas(cities)
        gt = r.get("graduationTime") or {}
        cohort = None
        if gt.get("from") and gt.get("to"):
            cohort = f"毕业时间 {epoch_ms_to_date(gt.get('from'))} 至 {epoch_ms_to_date(gt.get('to'))}"
        rec = {
            "id": f"alibaba-{r['id']}",
            "recruitment_unit": "阿里巴巴",
            "contracting_entity": "",
            "job_title": r.get("name", ""),
            "job_category": r.get("categoryName") or "",
            "cities": cities,
            "major_requirements_raw": "",
            "major_tags": [],
            "education_raw": r.get("degree") or "",
            "cohort_raw": cohort or "2027届",
            "deadline": None,
            "deadline_type": "undisclosed",
            "status": "open" if r.get("status") == "recruit" else r.get("status"),
            "application_url": f"https://campus-talent.alibaba.com/campus/position/{r['id']}",
            "source_url": f"https://campus-talent.alibaba.com/campus/position/{r['id']}",
            "published_at": epoch_ms_to_date(r.get("modifyTime")),
            "reviewed_at": NOW,
            "source_name": "阿里巴巴校园招聘官方网站",
            "description_raw": body,
            "recruiting_unit_raw": r.get("department") or "",
            "hiring_department_raw": r.get("department") or "",
            "source_record_id": str(r.get("id")),
            "recruitment_type": "校招",
            "overseas_flag": overseas,
            "region": "overseas" if overseas else "mainland",
            "industry": ["互联网", "电商"],
            "incomplete": incomplete_flag,
            "batch_name": r.get("batchName", ""),
        }
        out.append(rec)
    return out, incomplete


def main():
    bt, bt_inc = build_bytedance()
    al, al_inc = build_alibaba()
    with open(f"{BASE}/batch_bytedance.json", "w", encoding="utf-8") as f:
        json.dump(bt, f, ensure_ascii=False, indent=2)
    with open(f"{BASE}/batch_alibaba.json", "w", encoding="utf-8") as f:
        json.dump(al, f, ensure_ascii=False, indent=2)

    from collections import Counter
    print("=== ByteDance ===")
    print("total:", len(bt), "incomplete(no JD):", bt_inc)
    print("recruitment_type:", Counter(r["recruitment_type"] for r in bt))
    print("overseas:", sum(1 for r in bt if r["overseas_flag"]))
    print("=== Alibaba ===")
    print("total:", len(al), "incomplete(no JD):", al_inc)
    print("overseas:", sum(1 for r in al if r["overseas_flag"]))
    print("cities sample:", Counter(c for r in al for c in r["cities"]).most_common(8))


if __name__ == "__main__":
    main()
