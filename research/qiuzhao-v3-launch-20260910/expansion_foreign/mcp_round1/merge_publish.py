#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge new JD records (JSON array file) into prod jobs.json by `id`, dedup.
Usage: python3 merge_publish.py <new_records.json>
Outputs /tmp/merged.json and prints stats + publish commands.
"""
import json, sys, os
NEW = sys.argv[1]
PROD = "/tmp/prod.json"
new_records = json.load(open(NEW, encoding="utf-8"))
prod = json.load(open(PROD, encoding="utf-8"))
by_id = {r["id"]: r for r in prod}
added, skipped = [], []
for r in new_records:
    if not r.get("id"):
        skipped.append(("no-id", r.get("job_title",""))); continue
    if not r.get("description_raw") or len(str(r["description_raw"]).strip()) < 30:
        skipped.append(("no-desc", r["id"])); continue
    if r["id"] in by_id:
        skipped.append(("dup-id", r["id"])); continue
    by_id[r["id"]] = r
    added.append(r["id"])
merged = list(by_id.values())
json.dump(merged, open("/tmp/merged.json","w",encoding="utf-8"), ensure_ascii=False)
print(f"NEW file: {NEW}")
print(f"records in file: {len(new_records)}")
print(f"ADDED: {len(added)}")
print(f"SKIPPED: {len(skipped)}")
for s in skipped[:20]: print("  skip:", s)
print(f"prod was {len(prod)} -> merged {len(merged)}")
print("--- PUBLISH ---")
print("scp /tmp/merged.json root@114.215.188.109:/var/lib/mcp-suite/jobs.json.new")
