#!/usr/bin/env python3
"""ByteDance campus recruitment harvest from offset 700 to end."""
import requests, json, time, os, sys
from datetime import datetime, timezone, timedelta

BASE_URL = "https://jobs.bytedance.com/api/v1/search/job/posts"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://jobs.bytedance.com/campus/position",
}
RECRUITMENT_ID = "7649336829398468869"
OUT_DIR = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release/_bytedance_raw"
BATCH_DIR = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release"

PAGE_SIZE = 100
START_OFFSET = 700
TOTAL_EXPECTED = 10000
MAX_NO_CAMPUS_STREAK = 3  # stop after 3 consecutive pages with no campus jobs

def fetch_page(offset, limit=PAGE_SIZE):
    body = {
        "recruitment_id_list": [RECRUITMENT_ID],
        "portal_type": 3,
        "portal_entrance": 1,
        "limit": limit,
        "offset": offset,
    }
    resp = requests.post(BASE_URL, headers=HEADERS, json=body, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"API error: {data.get('code')} {data.get('message')}")
    return data.get("data", {})

def is_campus(job):
    rt = job.get("recruit_type") or {}
    parent = rt.get("parent") or {}
    return parent.get("name") == "校招"

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    collected = []
    offset = START_OFFSET
    scanned_total = 0
    no_campus_streak = 0
    batch_num = 0
    log_lines = []

    def log(msg):
        print(msg, flush=True)
        log_lines.append(msg)

    log(f"=== ByteDance harvest from offset {START_OFFSET} ===")
    log(f"Start: {datetime.now().isoformat()}")

    while offset < TOTAL_EXPECTED:
        try:
            data = fetch_page(offset)
        except Exception as e:
            log(f"ERROR at offset {offset}: {e}")
            time.sleep(3)
            try:
                data = fetch_page(offset)
            except Exception as e2:
                log(f"RETRY FAILED at offset {offset}: {e2}, stopping")
                break

        jobs = data.get("job_post_list", [])
        total = data.get("count", TOTAL_EXPECTED)
        if offset == START_OFFSET:
            log(f"API total: {total}")

        if not jobs:
            log(f"offset={offset}: empty page, reached end")
            break

        page_campus = 0
        for job in jobs:
            scanned_total += 1
            if is_campus(job):
                page_campus += 1
                rt = job.get("recruit_type", {})
                collected.append({
                    "id": str(job.get("id", "")),
                    "title": job.get("title", ""),
                    "code": job.get("code", ""),
                    "description": job.get("description", ""),
                    "requirement": job.get("requirement", ""),
                    "job_category": job.get("job_category", ""),
                    "cities": job.get("cities", []),
                    "recruit_type_name": rt.get("name", ""),
                    "publish_time": job.get("publish_time"),
                })

        if page_campus == 0:
            no_campus_streak += 1
        else:
            no_campus_streak = 0

        batch_num += 1
        if batch_num % 10 == 0 or page_campus > 0:
            log(f"offset={offset}: scanned={len(jobs)}, campus={page_campus}, total_collected={len(collected)}, streak={no_campus_streak}")

        offset += PAGE_SIZE

        if no_campus_streak >= MAX_NO_CAMPUS_STREAK:
            log(f"Stopping: {no_campus_streak} consecutive pages with no campus jobs")
            break

        # Rate limit: 1.2s between pages
        time.sleep(1.2)

    log(f"\n=== Harvest complete ===")
    log(f"Pages processed: {batch_num}")
    log(f"Total scanned: {scanned_total}")
    log(f"Campus jobs collected: {len(collected)}")
    log(f"Final offset: {offset}")
    log(f"End: {datetime.now().isoformat()}")

    # Save raw harvest
    raw_path = os.path.join(OUT_DIR, "harvest_from_700_full.json")
    with open(raw_path, "w") as f:
        json.dump(collected, f, ensure_ascii=False)
    log(f"Raw data saved: {raw_path}")

    # Save log
    log_path = os.path.join(OUT_DIR, "harvest_log.txt")
    with open(log_path, "w") as f:
        f.write("\n".join(log_lines))
    log(f"Log saved: {log_path}")

if __name__ == "__main__":
    main()
