"""Baseline vs release-B totals on data/jobs.json.

Runs each tree's own qiuzhao.tools.Jobs.search (the function the MCP tool calls) in a
separate interpreter, collects the matching ids, and explains any gap above 10%.
Writes evidence/compare_totals.{json,md}.
"""
import collections
import json
import os
import subprocess
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
DATA = W / "data" / "jobs.json"
ROWS = [
    ("job_category=产品", {"job_category": "产品"}, {"job_category": "产品"}),
    ("job_category=技术/研发", {"job_category": "技术/研发"}, {"job_category": "技术/研发"}),
    ("cohort=2027 → graduation_year=2027届", {"cohort": "2027"}, {"graduation_year": "2027届"}),
    ("major_category=计算机类 → major=计算机类", {"major_category": "计算机类"}, {"major": "计算机类"}),
    ("region=北京 → city=北京", {"region": "北京"}, {"city": "北京"}),
    ("keyword=产品", {"keyword": "产品"}, {"keyword": "产品"}),
]
CHILD = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import qiuzhao.tools as tools
tools.MISSING_QUERIES_FILE = tools.Path("/dev/null")
jobs = tools.Jobs(sys.argv[2])
rows = jobs.load()
jobs.load = lambda: rows
out = []
for kwargs in json.loads(sys.argv[3]):
    result = jobs.search(limit=10**6, **kwargs)
    out.append({"total": result["total"], "ids": [j["id"] for j in result["jobs"]]})
print(json.dumps(out))
"""


def run(tree, queries):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-c", CHILD, str(W / tree), str(DATA), json.dumps(queries)],
                          capture_output=True, text=True, env=env, check=True)
    return json.loads(done.stdout)


def top(counter, n=6):
    return [[k, v] for k, v in counter.most_common(n)]


base = run("live-baseline", [r[1] for r in ROWS])
rel_b = run("release-B", [r[2] for r in ROWS])
records = {}
for row in json.loads(DATA.read_text()):
    if row.get("source_url") and row.get("application_url"):
        records.setdefault(row["id"], row)

report = []
for (label, q_base, q_b), a, b in zip(ROWS, base, rel_b):
    # Multiset difference: the dataset has duplicate ids, so plain sets would undercount.
    only_base = list((collections.Counter(a["ids"]) - collections.Counter(b["ids"])).elements())
    only_b = list((collections.Counter(b["ids"]) - collections.Counter(a["ids"])).elements())
    pct = (b["total"] - a["total"]) / a["total"] * 100 if a["total"] else None
    item = {"label": label, "baseline_args": q_base, "b_args": q_b, "baseline_total": a["total"],
            "b_total": b["total"], "diff": b["total"] - a["total"], "diff_pct": round(pct, 1) if pct is not None else None,
            "only_in_baseline": len(only_base), "only_in_b": len(only_b)}
    if "job_category" in q_b:
        item["only_in_baseline_by_raw_category"] = top(collections.Counter(
            f"{records[i].get('job_category_normalized')} | 原文:{records[i].get('job_category')}" for i in only_base))
    if "graduation_year" in q_b:
        item["only_in_baseline_by_normalized_year"] = top(collections.Counter(
            records[i].get("graduation_year_normalized") for i in only_base))
        item["only_in_baseline_examples"] = top(collections.Counter(
            f"cohort_raw:{(records[i].get('cohort_raw') or '')[:30]} | campaign:{records[i].get('campaign_cohort_raw')}" for i in only_base), 5)
        item["only_in_b_examples"] = top(collections.Counter(
            f"cohort_raw:{(records[i].get('cohort_raw') or '')[:30]} | campaign:{records[i].get('campaign_cohort_raw')}" for i in only_b), 5)
    if "city" in q_b:
        item["only_in_b_examples"] = top(collections.Counter(
            f"city_normalized:{records[i].get('city_normalized')} | cities:{records[i].get('cities')}" for i in only_b), 5)
    report.append(item)

(W / "evidence").mkdir(exist_ok=True)
(W / "evidence" / "compare_totals.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
lines = ["| 条件（baseline → B） | baseline total | B total | 差值 | 差异% | 仅 baseline 命中 | 仅 B 命中 |",
         "|---|---:|---:|---:|---:|---:|---:|"]
for r in report:
    lines.append(f"| {r['label']} | {r['baseline_total']} | {r['b_total']} | {r['diff']:+d} | {r['diff_pct']:+.1f}% "
                 f"| {r['only_in_baseline']} | {r['only_in_b']} |")
(W / "evidence" / "compare_totals.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
print(json.dumps([{k: v for k, v in r.items() if k.startswith("only_in_") and not isinstance(v, int)} | {"label": r["label"]}
                  for r in report], ensure_ascii=False, indent=1))
