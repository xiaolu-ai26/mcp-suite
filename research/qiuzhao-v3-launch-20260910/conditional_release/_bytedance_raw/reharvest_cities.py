#!/usr/bin/env python3
"""Re-harvest ByteDance campus jobs from list API to extract city_info/city_list.
The original harvest only extracted `cities` (which was null), but the API returns
`city_info` and `city_list` on each job post. We re-paginate and build a job_id -> cities map."""
import requests, json, time, os
from datetime import datetime

BASE_URL = "https://jobs.bytedance.com/api/v1/search/job/posts"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://jobs.bytedance.com/campus/position",
}
RECRUITMENT_ID = "7649336829398468869"
OUT_DIR = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/conditional_release/_bytedance_raw"

PAGE_SIZE = 100
TOTAL_EXPECTED = 10000
MAX_NO_CAMPUS_STREAK = 3

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

def extract_cities(job):
    """Extract city names from city_info and city_list."""
    cities = []
    # Try city_list first (most complete)
    city_list = job.get("city_list") or []
    for c in city_list:
        name = c.get("name", "")
        if name and name not in cities:
            cities.append(name)
    # Fallback to city_info
    if not cities:
        ci = job.get("city_info") or {}
        name = ci.get("name", "")
        if name:
            cities.append(name)
    return cities

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    job_map = {}  # job_id -> [cities]
    offset = 0
    scanned_total = 0
    no_campus_streak = 0
    page_num = 0
    log_lines = []

    def log(msg):
        print(msg, flush=True)
        log_lines.append(msg)

    log(f"=== ByteDance city re-harvest ===")
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
        if offset == 0:
            log(f"API total: {total}")

        if not jobs:
            log(f"offset={offset}: empty page, reached end")
            break

        page_campus = 0
        for job in jobs:
            scanned_total += 1
            if is_campus(job):
                page_campus += 1
                jid = str(job.get("id", ""))
                cities = extract_cities(job)
                job_map[jid] = cities

        if page_campus == 0:
            no_campus_streak += 1
        else:
            no_campus_streak = 0

        page_num += 1
        if page_num % 10 == 0:
            with_city = sum(1 for v in job_map.values() if v)
            log(f"offset={offset}: campus_in_map={len(job_map)}, with_city={with_city}, streak={no_campus_streak}")

        offset += PAGE_SIZE

        if no_campus_streak >= MAX_NO_CAMPUS_STREAK:
            log(f"Stopping: {no_campus_streak} consecutive pages with no campus jobs")
            break

        time.sleep(1.0)

    log(f"\n=== Harvest complete ===")
    log(f"Pages: {page_num}")
    log(f"Scanned: {scanned_total}")
    log(f"Campus jobs in map: {len(job_map)}")
    with_city = sum(1 for v in job_map.values() if v)
    log(f"With cities: {with_city}")
    log(f"Without cities: {len(job_map) - with_city}")
    log(f"End: {datetime.now().isoformat()}")

    out_path = os.path.join(OUT_DIR, "city_map.json")
    with open(out_path, "w") as f:
        json.dump(job_map, f, ensure_ascii=False)
    log(f"City map saved: {out_path}")

    log_path = os.path.join(OUT_DIR, "city_harvest_log.txt")
    with open(log_path, "w") as f:
        f.write("\n".join(log_lines))

if __name__ == "__main__":
    main()
