#!/usr/bin/env python3
"""Batch-fetch Tencent job details via discovered API.
GET https://join.qq.com/api/v1/jobDetails/getJobDetailsByPostId?postId=<postId>
"""
import json, os, sys, time, urllib.request, urllib.error, ssl

BASE = os.path.dirname(os.path.abspath(__file__))
STAGING = os.path.join(BASE, "jobs.json")
CACHE = os.path.join(BASE, "details_cache.json")
LOG = os.path.join(BASE, "collect_details.log")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
API = "https://join.qq.com/api/v1/jobDetails/getJobDetailsByPostId?postId="

ctx = ssl.create_default_context()

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def fetch(pid, retries=3):
    url = API + str(pid)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": f"https://join.qq.com/post_detail.html?postid={pid}",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                body = r.read().decode("utf-8")
            return json.loads(body)
        except Exception as e:
            if attempt == retries - 1:
                return {"_error": f"{type(e).__name__}: {e}"}
            time.sleep(1.5 * (attempt + 1))

def main():
    jobs = json.load(open(STAGING))
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE))
    todo = [j for j in jobs if str(j["source_record_id"]) not in cache]
    log(f"total={len(jobs)} cached={len(cache)} todo={len(todo)}")

    ok = fail = 0
    for i, j in enumerate(todo):
        pid = str(j["source_record_id"])
        resp = fetch(pid)
        data = resp.get("data") if isinstance(resp, dict) else None
        if data:
            cache[pid] = data
            ok += 1
        else:
            cache[pid] = {"_error": resp.get("_error") if isinstance(resp, dict) else "no data",
                          "_status": resp.get("status") if isinstance(resp, dict) else None,
                          "_message": resp.get("message") if isinstance(resp, dict) else None}
            fail += 1
        if (i + 1) % 25 == 0 or i == len(todo) - 1:
            json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
            log(f"progress {i+1}/{len(todo)} ok={ok} fail={fail}")
        time.sleep(0.35)

    json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
    log(f"DONE total_cached={len(cache)} ok_run={ok} fail_run={fail}")

if __name__ == "__main__":
    main()
