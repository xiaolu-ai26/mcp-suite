#!/usr/bin/env python3
"""Condition 3: fix known issues, derive canonical recruitment_type,
flag HK/overseas, classify qualified vs needs-review, emit qualified_jobs.json.

Read-only on staging_merged/jobs.json. Writes only to conditional_release/.
"""
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone, timedelta

BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910"
STAGING = f"{BASE}/job_mvp/staging_merged/jobs.json"
OUT_DIR = f"{BASE}/conditional_release"
OUT_QUALIFIED = f"{OUT_DIR}/qualified_jobs.json"
OUT_REVIEW = f"{OUT_DIR}/needs_review.jsonl"

TZ = timezone(timedelta(hours=8))

HK_PAT = re.compile(r"香港|澳门|台湾|Hong Kong|Macau|Taiwan")
# Note: "柏林" alone would false-positive on 太原万柏林区; require English Berlin
# or a clear overseas context. Use a word-boundary-aware approach.
OVERSEAS_CITY_HINT = re.compile(
    r"新加坡|首尔|东京|悉尼|洛杉矶|纽约|伦敦|巴黎|硅谷|西雅图|旧金山|慕尼黑|阿姆斯特丹|都柏林|Berlin"
)


def src_prefix(rid: str) -> str:
    return rid.split("-", 1)[0]


def canonical_recruitment_type(r: dict) -> str:
    """Derive 校招/实习/社招 from raw signals."""
    rt = (r.get("recruitment_type_raw") or "").strip()
    nat = (r.get("nature_raw") or "").strip()
    text = f"{rt} {nat}"
    if "实习" in text:
        return "实习"
    if "校招" in text or "校园" in text:
        return "校招"
    if "社招" in text or "社会招聘" in text:
        return "社招"
    # Old sources without explicit label: they come from 2027 campus campaigns
    p = src_prefix(r.get("id", ""))
    if p in ("postal", "chn", "ccb", "boc", "telecom", "guopin"):
        return "校招"
    return "未知"


def is_hk_or_overseas(cities) -> bool:
    s = " ".join(cities or [])
    return bool(HK_PAT.search(s) or OVERSEAS_CITY_HINT.search(s))


def fix_pg(rec: dict) -> list:
    """Fix P&G graduation-period pollution in major_requirements_raw.

    Returns list of change descriptions.
    """
    changes = []
    old_major = rec.get("major_requirements_raw") or ""
    desc = rec.get("description_raw") or ""

    # The polluted value is literally "Required Graduation Period : 2025."
    if re.search(r"Required Graduation Period", old_major, re.I):
        # Extract real major list from description_raw Requirement section, if any
        real_major = ""
        m = re.search(
            r"Requirement[s]?:(.*?)(?:Work Location|Interview City|^)",
            desc, re.S | re.M | re.I,
        )
        if m:
            req_text = m.group(1)
            # Look for a degree-in-majors sentence
            mm = re.search(
                r"(?:Pursuing or recently completed|degree in|Bachelor['`]?s?\s*(?:degree)?\s*,?\s*Master['`]?s?\s*,?\s*or\s*PhD\.?\s*)"
                r"([A-Z][^.]*?(?:disciplines|majors|fields))",
                req_text, re.I,
            )
            if mm:
                real_major = mm.group(0).strip()
                # Trim trailing sentences that are soft-skills
                real_major = re.split(r"\.\s+(?=Strong|Interest|Candidates|Pursuing)", real_major)[0]
                real_major = real_major.rstrip(" .") + "."
            elif "degree in" in req_text:
                # Generic: no specific major list (e.g. BRM/Finance/HR/CMK/CBD/IT)
                real_major = ""
        rec["major_requirements_raw"] = real_major
        changes.append(
            f"major_requirements_raw: removed graduation-period pollution; "
            f"set to {'real majors extracted from JD' if real_major else 'empty (P&G JD does not specify major)'}"
        )

        # Backfill education_raw from Requirement section where empty
        if not (rec.get("education_raw") or "").strip():
            if re.search(r"at least a bachelor", desc, re.I):
                rec["education_raw"] = "本科及以上"
                changes.append("education_raw: backfilled '本科及以上' from JD Requirement section")
            elif re.search(r"Bachelor['`]?s degree or above", desc, re.I):
                rec["education_raw"] = "本科及以上"
                changes.append("education_raw: backfilled '本科及以上' from JD Requirement section")

    return changes


def has_real_jd(rec: dict) -> bool:
    """Heuristic: does description_raw contain actual JD content vs list metadata?"""
    desc = (rec.get("description_raw") or "").strip()
    if not desc:
        return False
    # List-metadata patterns for new sources
    list_meta_patterns = [
        r"^职位族ID:",
        r"^职位编码",
        r"^职位编码.*；研发族",
    ]
    for pat in list_meta_patterns:
        if re.match(pat, desc):
            return False
    # Tencent-style: short metadata string
    if len(desc) < 80 and ("职位族ID" in desc or "招聘标签" in desc):
        return False
    # Otherwise treat as real JD
    return True


def main():
    with open(STAGING, "r", encoding="utf-8") as f:
        data = json.load(f)

    qualified = []
    needs_review = []
    fix_log = []
    seen_ids = set()

    for rec in data:
        r = deepcopy(rec)
        rid = r["id"]
        src = src_prefix(rid)

        # 1. Derive canonical recruitment_type
        r["recruitment_type"] = canonical_recruitment_type(r)

        # 2. HK / overseas flagging (backfill for old sources that lack it)
        if is_hk_or_overseas(r.get("cities")):
            r["overseas_flag"] = True
            r["region"] = "overseas"
        elif "overseas_flag" not in r:
            r["overseas_flag"] = False
            r["region"] = "mainland"

        # 3. P&G fix
        if src == "pg":
            changes = fix_pg(r)
            for c in changes:
                fix_log.append({"id": rid, "source": src, "change": c})

        # 4. Dedup
        if rid in seen_ids:
            needs_review.append({
                "id": rid, "source": src, "reason": "duplicate_id",
                "title": r.get("job_title", ""),
            })
            continue
        seen_ids.add(rid)

        # 5. Qualification logic
        reasons_not_qualified = []

        # Critical fields
        if not (r.get("job_title") or "").strip():
            reasons_not_qualified.append("missing_title")
        if not (r.get("recruitment_unit") or "").strip():
            reasons_not_qualified.append("missing_unit")
        if not (r.get("source_url") or "").strip():
            reasons_not_qualified.append("missing_source_url")
        if not (r.get("reviewed_at") or "").strip():
            reasons_not_qualified.append("missing_reviewed_at")
        if r["recruitment_type"] == "未知":
            reasons_not_qualified.append("unknown_recruitment_type")

        # List-only metadata (no real JD body) -> needs review
        if not has_real_jd(r):
            # Exception: postal/chn/ccb/boc have description_raw always (verified earlier)
            # Tencent/Mindray/Midea list-metadata -> needs review
            if src in ("tencent", "mindray"):
                reasons_not_qualified.append("list_metadata_only_no_jd_detail")
            elif src == "midea":
                # Midea has real responsibility text in description_raw (short but real)
                pass

        # Telecom: all 10 are status=unverified, no cohort, no deadline, titles look experienced
        if src == "telecom":
            reasons_not_qualified.append("telecom_unverified_no_cohort_no_deadline")

        # Status flag: respect original "unverified" only when data is genuinely lacking
        if r.get("status") == "unverified" and src not in ("guopin",):
            # guopin 92 unverified have real JDs; other unverified need review
            if "list_metadata_only_no_jd_detail" not in reasons_not_qualified:
                reasons_not_qualified.append(f"status_unverified:{src}")

        if reasons_not_qualified:
            needs_review.append({
                "id": rid,
                "source": src,
                "recruitment_type": r["recruitment_type"],
                "overseas_flag": r.get("overseas_flag", False),
                "title": r.get("job_title", ""),
                "cities": r.get("cities", []),
                "reason": ";".join(reasons_not_qualified),
            })
        else:
            qualified.append(r)

    # Write outputs
    with open(OUT_QUALIFIED, "w", encoding="utf-8") as f:
        json.dump(qualified, f, ensure_ascii=False, indent=2)

    with open(OUT_REVIEW, "w", encoding="utf-8") as f:
        for item in needs_review:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Summary
    print(f"TOTAL input: {len(data)}")
    print(f"QUALIFIED:   {len(qualified)}")
    print(f"NEEDS REVIEW: {len(needs_review)}")
    print()

    print("=== Qualified by source ===")
    q_by_src = Counter(src_prefix(r["id"]) for r in qualified)
    for s in sorted(q_by_src):
        print(f"  {s:<10} {q_by_src[s]}")

    print()
    print("=== Qualified by recruitment_type ===")
    q_by_rt = Counter(r["recruitment_type"] for r in qualified)
    for k, v in q_by_rt.most_common():
        print(f"  {k:<6} {v}")

    print()
    print("=== Qualified overseas/HK ===")
    q_overseas = [r for r in qualified if r.get("overseas_flag")]
    print(f"  overseas/HK qualified: {len(q_overseas)}")
    for r in q_overseas:
        print(f"    {r['id']:<35} {r.get('job_title','')[:40]:<40} {r.get('cities')}")

    print()
    print("=== Needs review by reason ===")
    reason_counter = Counter()
    for item in needs_review:
        for reason in item["reason"].split(";"):
            reason_counter[reason] += 1
    for k, v in reason_counter.most_common():
        print(f"  {v:5d}  {k}")

    print()
    print("=== Needs review by source ===")
    nr_by_src = Counter(item["source"] for item in needs_review)
    for s in sorted(nr_by_src):
        print(f"  {s:<10} {nr_by_src[s]}")

    print()
    print("=== P&G fix log ===")
    for entry in fix_log:
        print(f"  {entry['id']}: {entry['change']}")

    # Qualified mainland campus-only count (for default 校招 query, excluding overseas)
    print()
    main_land_campus = [
        r for r in qualified
        if r["recruitment_type"] == "校招" and not r.get("overseas_flag")
    ]
    print(f"Qualified mainland 校招 (default query): {len(main_land_campus)}")
    main_land_intern = [
        r for r in qualified
        if r["recruitment_type"] == "实习" and not r.get("overseas_flag")
    ]
    print(f"Qualified mainland 实习: {len(main_land_intern)}")


if __name__ == "__main__":
    main()
