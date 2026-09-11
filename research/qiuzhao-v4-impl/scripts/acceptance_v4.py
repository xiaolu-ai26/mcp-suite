"""SPEC section 8 acceptance questions (plus Q21–Q24 for the inferred tier) with the final v4 rules.

usage (from the code root):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python research/qiuzhao-v4-impl/scripts/acceptance_v4.py
Runs the real qiuzhao/tools.py in-process on qiuzhao/data/jobs.json with today = MCP_TODAY
(default 2026-09-11), writes research/qiuzhao-v4-impl/evidence/acceptance_v4.json and prints a
side-by-side table against the SPEC's simulated values (evidence/acceptance_expected.json of the
interface study). tests/test_v4_tools.py checks that the HTTP server returns exactly these results.
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from acceptance_cases import CASES, resolve  # noqa: E402
from qiuzhao.tools import Jobs  # noqa: E402

TODAY = os.environ.get("MCP_TODAY", "2026-09-11")
jobs = Jobs(os.environ.get("MCP_JOBS_PATH", ROOT / "qiuzhao" / "data" / "jobs.json"), today=date.fromisoformat(TODAY))
CALL = {"jobs_search": jobs.search, "jobs_stats": jobs.stats, "jobs_detail": jobs.detail}
SPEC = json.loads((ROOT / "research" / "qiuzhao-v4-interface-20260911" / "evidence" / "acceptance_expected.json").read_text())
# ACCEPTANCE_OUT: write elsewhere (e.g. the same questions on the live jobs.json of another day).
OUT = Path(os.environ.get("ACCEPTANCE_OUT") or ROOT / "research" / "qiuzhao-v4-impl" / "evidence" / "acceptance_v4.json")


def brief(tool, r):
    keys = ("total", "explicit_total", "inferred_total", "unspecified_total", "excluded_social_total", "returned",
            "has_next", "next_offset", "truncated", "groups_total", "other_count", "found", "not_found")
    b = {k: r[k] for k in keys if k in r}
    if "groups" in r:
        b["groups"] = [[g["value"], g["count"], g["explicit_count"], g["inferred_count"], g["unspecified_count"]]
                       for g in r["groups"]]
    if tool == "jobs_search":
        b["first_ids"] = [j["id"] for j in r["jobs"][:3]]
        b["first_match"] = [j.get("match") for j in r["jobs"][:3]]
        b["first_deadlines"] = [j["deadline"] for j in r["jobs"][:3]]
    return b


def spec_brief(call):
    r = call["result"]
    b = {k: r[k] for k in ("total", "explicit_total", "found", "groups_total") if k in r}
    if "groups" in r:
        b["groups"] = r["groups"][:5]
    return b


def main():
    data = jobs.dataset()
    first, questions = {}, {}
    for qid, (question, steps) in CASES.items():
        calls = []
        for n, (tool, args) in enumerate(steps):
            args = resolve(args, first)
            result = CALL[tool](**args)
            if n == 0:
                first[qid] = result
            calls.append({"tool": tool, "arguments": args, "result": brief(tool, result)})
        questions[qid] = {"question": question, "calls": calls}
    keep = {"新加坡", "圣何塞", "海外", "全国", "未注明"}  # Q19: only the overseas-related city groups
    q19 = questions["Q19"]["calls"][1]["result"]
    q19["groups"] = [g for g in q19["groups"] if g[0] in keep]
    vs_spec = {}
    for qid, spec_calls in SPEC["questions"].items():
        vs_spec[qid] = [{"tool": c["tool"], "spec": spec_brief(c),
                         "v4": {k: v for k, v in questions[qid]["calls"][i]["result"].items()
                                if k in ("total", "explicit_total", "inferred_total", "unspecified_total",
                                         "excluded_social_total", "found", "groups_total")}
                         | ({"groups": questions[qid]["calls"][i]["result"]["groups"][:5]}
                            if "groups" in questions[qid]["calls"][i]["result"] else {})}
                        for i, c in enumerate(spec_calls)]
    doc = {"data_as_of": data.data_as_of, "today": TODAY, "items": len(data.items), "questions": questions,
           "vs_spec": vs_spec}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    for qid, rows in vs_spec.items():
        for row in rows:
            print(qid, row["tool"], "SPEC", json.dumps(row["spec"], ensure_ascii=False)[:160])
            print("   ", " " * len(row["tool"]), "v4  ", json.dumps(row["v4"], ensure_ascii=False)[:200])
    for qid in ("Q21", "Q22", "Q23", "Q24"):
        for c in questions[qid]["calls"]:
            print(qid, c["tool"], json.dumps(c["arguments"], ensure_ascii=False),
                  json.dumps({k: v for k, v in c["result"].items() if k not in ("first_ids", "first_deadlines")},
                             ensure_ascii=False)[:400])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
