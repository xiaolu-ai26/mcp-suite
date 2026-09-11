#!/usr/bin/env python3
"""Conditional-release condition 3: staging data quality audit.

Read-only on staging_merged/jobs.json. Emits an audit summary to stdout
and dumps per-source per-field coverage.
"""
import json
from collections import Counter, defaultdict

STAGING = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/job_mvp/staging_merged/jobs.json"

FIELDS = [
    "id", "title", "recruitment_unit", "recruitment_type",
    "cohort_raw", "cities", "major_requirements_raw",
    "education_raw", "deadline", "source_url", "application_url",
    "reviewed_at",
]

# field aliases in actual schema
ALIAS = {
    "title": "job_title",
}


def src_prefix(rid: str) -> str:
    return rid.split("-", 1)[0]


def is_present(v):
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict, tuple)):
        return len(v) > 0
    return True


def canonical_recruitment_type(r: dict) -> str:
    """Derive 校招/实习/社招 from raw signals."""
    rt = (r.get("recruitment_type_raw") or "").strip()
    nat = (r.get("nature_raw") or "").strip()
    text = f"{rt} {nat}"
    if "实习" in text:
        return "实习"
    if "校招" in text or "校园" in text:
        return "校招"
    if "社招" in text or "社会" in text:
        return "社招"
    # old sources without explicit label: they come from 2027 campus campaigns
    p = src_prefix(r.get("id", ""))
    if p in ("postal", "chn", "ccb", "boc", "telecom", "guopin"):
        return "校招"
    return "未知"


def main():
    with open(STAGING, "r", encoding="utf-8") as f:
        data = json.load(f)

    by_source = defaultdict(list)
    for r in data:
        by_source[src_prefix(r["id"])].append(r)

    print(f"TOTAL: {len(data)} records, sources: {sorted(by_source)}")
    print()

    # Field coverage table
    print("=== FIELD COVERAGE PER SOURCE ===")
    header = f"{'source':<10}{'n':>6}"
    for fld in FIELDS:
        header += f"{fld:>22}"
    print(header)
    print("-" * len(header))

    coverage_rows = {}
    for src in sorted(by_source):
        rows = by_source[src]
        n = len(rows)
        line = f"{src:<10}{n:>6}"
        cov = {}
        for fld in FIELDS:
            actual = ALIAS.get(fld, fld)
            if fld == "recruitment_type":
                cnt = sum(1 for r in rows if canonical_recruitment_type(r) != "未知")
            else:
                cnt = sum(1 for r in rows if is_present(r.get(actual)))
            cov[fld] = cnt
            pct = cnt / n * 100 if n else 0
            line += f"{cnt:>8d}({pct:4.0f}%)"
        coverage_rows[src] = (n, cov)
        print(line)

    # recruitment_type breakdown per source
    print()
    print("=== recruitment_type (derived) per source ===")
    for src in sorted(by_source):
        c = Counter(canonical_recruitment_type(r) for r in by_source[src])
        print(f"{src:<10} n={len(by_source[src]):<5} " +
              " ".join(f"{k}:{v}" for k, v in c.most_common()))

    # overseas_flag breakdown
    print()
    print("=== overseas_flag per source ===")
    for src in sorted(by_source):
        c = Counter(str(r.get("overseas_flag", "<unset>")) for r in by_source[src])
        print(f"{src:<10} " + " ".join(f"{k}:{v}" for k, v in c.most_common()))

    # status breakdown
    print()
    print("=== status per source ===")
    for src in sorted(by_source):
        c = Counter(r.get("status", "<none>") for r in by_source[src])
        print(f"{src:<10} " + " ".join(f"{k}:{v}" for k, v in c.most_common()))

    # duplicate check
    print()
    print("=== duplicate id check ===")
    ids = [r["id"] for r in data]
    dup = len(ids) - len(set(ids))
    print(f"duplicate ids: {dup}")

    # duplicate by (title, unit, city) rough
    seen = Counter()
    for r in data:
        key = (r.get("job_title", ""), r.get("recruitment_unit", ""),
               ",".join(r.get("cities", []) or []))
        seen[key] += 1
    dups = sum(v - 1 for v in seen.values() if v > 1)
    print(f"rough duplicate (title+unit+city): {dups}")


if __name__ == "__main__":
    main()
