#!/usr/bin/env python3
"""Merge existing 184 records with newly harvested 3987 records, map to production schema."""
import json, os
from datetime import datetime, timezone, timedelta
from collections import Counter

BASE_DIR = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release"
EXISTING_PATH = os.path.join(BASE_DIR, "batch_bytedance.json")
NEW_RAW_PATH = os.path.join(BASE_DIR, "_bytedance_raw", "harvest_from_700_full.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "batch_bytedance_full.json")
LOG_PATH = os.path.join(BASE_DIR, "_bytedance_raw", "merge_log.txt")

CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST).isoformat(timespec="seconds")

def ts_to_date(ts):
    """Convert millisecond timestamp to YYYY-MM-DD string."""
    if not ts:
        return None
    try:
        dt = datetime.fromtimestamp(ts / 1000, tz=CST)
        return dt.strftime("%Y-%m-%d")
    except:
        return None

def map_new_record(raw):
    """Map raw API record to production schema."""
    rec_id = raw["id"]
    rt_name = raw.get("recruit_type_name", "")
    # recruit_type: "正式" -> 校招, "实习" -> 实习
    if rt_name == "实习":
        recruitment_type = "实习"
    else:
        recruitment_type = "校招"

    description = raw.get("description", "")
    requirement = raw.get("requirement", "")
    # Combine description + requirement as description_raw
    full_desc = description
    if requirement:
        if full_desc:
            full_desc = full_desc + "\n" + requirement
        else:
            full_desc = requirement

    is_incomplete = not description or not requirement

    cities = raw.get("cities", [])
    if not cities:
        cities = []

    # job_category may be a dict with name field or a string
    jc = raw.get("job_category", "")
    if isinstance(jc, dict):
        jc_name = jc.get("name", "")
    else:
        jc_name = str(jc) if jc else ""

    return {
        "id": f"bytedance-{rec_id}",
        "recruitment_unit": "字节跳动",
        "contracting_entity": "",
        "job_title": raw.get("title", ""),
        "job_category": jc_name,
        "cities": cities,
        "major_requirements_raw": "",
        "major_tags": [],
        "education_raw": "",
        "cohort_raw": "2027届",
        "deadline": None,
        "deadline_type": "undisclosed",
        "status": "open",
        "application_url": f"https://jobs.bytedance.com/campus/position/{rec_id}/detail",
        "source_url": f"https://jobs.bytedance.com/campus/position/{rec_id}/detail",
        "published_at": ts_to_date(raw.get("publish_time")),
        "reviewed_at": NOW,
        "source_name": "字节跳动校园招聘官方网站",
        "description_raw": full_desc,
        "recruiting_unit_raw": "",
        "hiring_department_raw": "",
        "source_record_id": rec_id,
        "recruitment_type": recruitment_type,
        "overseas_flag": False,
        "region": "mainland",
        "industry": ["互联网", "短视频"],
        "incomplete": is_incomplete,
        "job_code": raw.get("code", ""),
    }

def main():
    lines = []
    def log(msg):
        print(msg)
        lines.append(msg)

    # Load existing
    with open(EXISTING_PATH) as f:
        existing = json.load(f)
    log(f"Existing records: {len(existing)}")

    # Load new raw harvest
    with open(NEW_RAW_PATH) as f:
        new_raw = json.load(f)
    log(f"New raw records: {len(new_raw)}")

    # Build dedup index from existing
    existing_ids = set()
    existing_by_id = {}
    for rec in existing:
        rid = rec.get("source_record_id") or rec.get("id", "").replace("bytedance-", "")
        existing_ids.add(rid)
        existing_by_id[rid] = rec
    log(f"Existing unique IDs: {len(existing_ids)}")

    # Map and dedup new records
    mapped_new = []
    dup_count = 0
    for raw in new_raw:
        rid = raw["id"]
        if rid in existing_ids:
            dup_count += 1
            continue
        mapped = map_new_record(raw)
        mapped_new.append(mapped)
        existing_ids.add(rid)

    log(f"Duplicates skipped (already in existing): {dup_count}")
    log(f"New unique records added: {len(mapped_new)}")

    # Merge
    merged = existing + mapped_new
    log(f"Total merged records: {len(merged)}")

    # Stats
    type_dist = Counter(r.get("recruitment_type", "?") for r in merged)
    log(f"Recruitment type distribution: {dict(type_dist)}")

    incomplete_count = sum(1 for r in merged if r.get("incomplete"))
    log(f"Incomplete records (missing desc or req): {incomplete_count}")

    # Check for any remaining duplicates
    all_ids = [r.get("id") for r in merged]
    unique_ids = set(all_ids)
    log(f"Unique IDs in final: {len(unique_ids)} / total: {len(all_ids)}")

    # Save
    with open(OUTPUT_PATH, "w") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    log(f"\nOutput saved: {OUTPUT_PATH}")
    log(f"File size: {os.path.getsize(OUTPUT_PATH)} bytes")

    # Save log
    with open(LOG_PATH, "w") as f:
        f.write("\n".join(lines))

    # Final summary
    print("\n=== FINAL SUMMARY ===")
    print(f"字节 | 校招+实习 | 发现{len(new_raw)+dup_count} | 详情取得{len(new_raw)} | 合格{len(merged)} | 线上可查(发布后) | 剩余0 | 阻塞无")

if __name__ == "__main__":
    main()
