"""Step-5 verification for the collector normalize fix. Run from the worktree root:
  .venv-python research/collector-fix-20260911/run_tests.py
Reads qiuzhao/data/jobs.json (gitignored copy of production data). Writes only to /tmp.
"""
import copy, json, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from qiuzhao.normalize import NORMALIZED_FIELDS, normalize_records, normalize_file

DATA = ROOT / "qiuzhao" / "data" / "jobs.json"
TABLES = json.loads((ROOT / "qiuzhao" / "normalize_tables.json").read_text())
VALUE_SETS = {k: set(v) for k, v in TABLES["value_sets"].items()}

def nonempty(v):
    return v is not None and v != "" and v != []

results = {}

records = json.loads(DATA.read_text())
print(f"loaded {len(records)} records")

# T1 idempotency: no existing non-empty value may change; second run fills nothing.
work = copy.deepcopy(records)
before = {f: {id(j): j.get(f) for j in work if nonempty(j.get(f))} for f in NORMALIZED_FIELDS}
t0 = time.monotonic()
filled1 = normalize_records(work)
elapsed = time.monotonic() - t0
changed = 0
pos = {id(j): j for j in work}
for f in NORMALIZED_FIELDS:
    for i, v in before[f].items():
        if pos[i].get(f) != v:
            changed += 1
filled2 = normalize_records(work)
results["T1_idempotency"] = {"would_change_existing": changed, "second_run_filled": filled2,
                             "first_run_filled": filled1}
print("T1 idempotency: changed existing =", changed, "| second run filled =", sum(filled2.values()))
assert changed == 0, "normalize modified existing values"
assert sum(filled2.values()) == 0, "normalize not idempotent"

# T2 reproduction: strip all normalized fields, recompute, compare per field.
work = copy.deepcopy(records)
original = [{f: j.get(f) for f in NORMALIZED_FIELDS} for j in work]
for j in work:
    for f in NORMALIZED_FIELDS:
        j.pop(f, None)
normalize_records(work)
repro = {}
for f in NORMALIZED_FIELDS:
    total = match = 0
    for j, orig in zip(work, original):
        if nonempty(orig[f]):
            total += 1
            if j.get(f) == orig[f]:
                match += 1
    repro[f] = {"original_nonempty": total, "matched": match,
                "rate": round(match / total, 4) if total else None}
results["T2_reproduction"] = repro
for f, r in repro.items():
    print(f"T2 {f}: {r['matched']}/{r['original_nonempty']} = {r['rate']}")

# T3 merge: drive the real Collector.run with a stubbed postal source returning 500
# records stripped of normalized fields; fields must be 100% restored.
from qiuzhao.collector import run as run_mod

tmp = Path(tempfile.mkdtemp(prefix="merge-test-"))
real = copy.deepcopy(records)
(tmp / "jobs.json").write_text(json.dumps(real, ensure_ascii=False))
postal = [j for j in real if str(j.get("id", "")).startswith("postal-")][:500]
stripped = []
for j in postal:
    nj = {k: v for k, v in j.items() if k not in NORMALIZED_FIELDS}
    nj["reviewed_at"] = run_mod.now()
    stripped.append(nj)
orig_by_id = {j["id"]: j for j in postal}
collector = run_mod.Collector(tmp, delay=0)
collector.postal = lambda: copy.deepcopy(stripped)
collector.states["postal"] = {"complete": False}
collector.run("postal", None)
merged = {j.get("id") or f"auto-{i}": j for i, j in enumerate(json.loads((tmp / "jobs.json").read_text()))}
bad = 0
for jid, orig in orig_by_id.items():
    for f in NORMALIZED_FIELDS:
        if nonempty(orig.get(f)) and merged[jid].get(f) != orig[f]:
            bad += 1
results["T3_merge_restore"] = {"records": len(orig_by_id), "mismatched_fields": bad}
print(f"T3 merge restore: {len(orig_by_id)} records, mismatched fields = {bad}")
assert bad == 0, "merge did not restore normalized fields"

# T4 unseen records: all normalized fields filled, values within existing value sets.
unseen = [
    dict(id="new-1", recruitment_unit="某未见过的央企集团有限公司", job_title="软件开发工程师（2027届校招）",
         job_category="没见过的大类写法XYZ", cities=["深圳-南山区"], major_requirements_raw="计算机科学与技术、软件工程等相关专业",
         cohort_raw="2027届校园招聘", source_name="", recruitment_unit_raw="某未见过的央企集团有限公司"),
    dict(id="new-2", recruitment_unit="Some New Bank Corp", job_title="Data Analyst Intern",
         job_category="", cities=["NewYork"], major_requirements_raw="",
         cohort_raw="", source_name="", recruitment_unit_raw=""),
    dict(id="new-3", recruitment_unit="某新单位", job_title="客户经理",
         job_category="", cities=[], major_requirements_raw="",
         cohort_raw="社会人才招聘", source_name="国聘", recruitment_unit_raw=""),
]
normalize_records(unseen)
t4 = {}
for j in unseen:
    for f in NORMALIZED_FIELDS:
        v = j.get(f)
        assert nonempty(v) or f == "overseas_flag", f"{j['id']} field {f} left empty: {v!r}"
        vals = v if isinstance(v, list) else [v]
        allowed = VALUE_SETS.get(f, set())
        for x in vals:
            ok = x in allowed
            t4[f"{j['id']}:{f}"] = (x, ok)
            assert ok, f"{j['id']} field {f} value {x!r} not in existing value set"
results["T4_unseen"] = {j["id"]: {f: j.get(f) for f in NORMALIZED_FIELDS} for j in unseen}
print("T4 unseen records: all fields filled and within existing value sets")
print(json.dumps(results["T4_unseen"], ensure_ascii=False, indent=2))

# T5 timing on 28,616 records.
work = copy.deepcopy(records)
for j in work:
    for f in NORMALIZED_FIELDS:
        j.pop(f, None)
t0 = time.monotonic()
normalize_records(work)
results["T5_timing"] = {"records": len(work), "seconds": round(time.monotonic() - t0, 2)}
print("T5 timing:", results["T5_timing"])

out = ROOT / "research" / "collector-fix-20260911" / "test-results.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
print("results written to", out)
