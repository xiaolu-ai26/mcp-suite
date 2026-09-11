#!/usr/bin/env python3
"""从 jobs.json 抽取12-20条多样化样本，保留原始结构。"""
import json
import random
from pathlib import Path

JOBS_PATH = Path("/Users/maxzhl/Projects/mcp-suite/qiuzhao/data/jobs.json")
OUT_PATH = Path("/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-review-pack-20260910/B_data_samples/job_samples.json")

with open(JOBS_PATH, encoding="utf-8") as f:
    jobs = json.load(f)

random.seed(42)
samples = []
used_ids = set()

def add(job, reason):
    if job["id"] in used_ids:
        return
    used_ids.add(job["id"])
    samples.append({"_sample_reason": reason, **job})

# 1. 每个来源至少1条
by_source = {}
for j in jobs:
    pid = j["id"].split("-")[0]
    if pid == "guopin":
        src = "guopin-" + j.get("source_group_key", "unknown")
    else:
        src = pid
    by_source.setdefault(src, []).append(j)

for src, rows in sorted(by_source.items()):
    add(random.choice(rows), f"来源代表: {src}")

# 2. 明确截止日期的
explicit = [j for j in jobs if j.get("deadline_type") == "explicit" and j.get("deadline")]
if explicit:
    add(random.choice(explicit), "明确截止日期(explicit)")

# 3. 未披露截止日期的
undisclosed = [j for j in jobs if j.get("deadline_type") == "undisclosed"]
for j in undisclosed[:2]:
    add(j, "未披露截止日期(undisclosed)")

# 4. unverified状态
unverified = [j for j in jobs if j.get("status") == "unverified"]
for j in unverified[:2]:
    add(j, "unverified状态")

# 5. 多城市
multi_city = [j for j in jobs if len(j.get("cities", [])) > 1]
if multi_city:
    add(random.choice(multi_city), f"多城市({len(multi_city[0]['cities'])}个)")

# 6. 有cohort_raw明确2027的
cohort_2027 = [j for j in jobs if "2027" in (j.get("cohort_raw") or "")]
if cohort_2027:
    add(random.choice(cohort_2027), "岗位级明确2027届(cohort_raw)")

# 7. 只有campaign_cohort_raw没有cohort_raw的
campaign_only = [j for j in jobs if not (j.get("cohort_raw") or "").strip() and (j.get("campaign_cohort_raw") or "").strip()]
if campaign_only:
    add(random.choice(campaign_only), "仅活动标题有届别(campaign_cohort_raw, cohort_raw为空)")

# 8. 有2026届明确的
cohort_2026 = [j for j in jobs if "2026" in (j.get("cohort_raw") or "")]
if cohort_2026:
    add(random.choice(cohort_2026), "岗位级明确2026届(cohort_raw)")

# 9. 岗位大类(job_category有值)
with_category = [j for j in jobs if (j.get("job_category") or "").strip()]
if with_category:
    add(random.choice(with_category), "有岗位大类(job_category)")

# 10. 有parent_unit_raw的
with_parent = [j for j in jobs if (j.get("parent_unit_raw") or "").strip()]
if with_parent:
    add(random.choice(with_parent), "有上级单位(parent_unit_raw)")

# 11. 有hiring_department_raw的
with_dept = [j for j in jobs if (j.get("hiring_department_raw") or "").strip()]
if with_dept:
    add(random.choice(with_dept), "有招聘部门(hiring_department_raw)")

# 12. 有education_raw的
with_edu = [j for j in jobs if (j.get("education_raw") or "").strip()]
if with_edu:
    add(random.choice(with_edu), "有学历要求(education_raw)")

# 限制在20条以内
samples = samples[:20]

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(samples, f, ensure_ascii=False, indent=2)

print(f"Extracted {len(samples)} samples")
for s in samples:
    print(f"  [{s['_sample_reason']}] {s['id']} - {s['job_title']} ({s['recruitment_unit']})")
print(f"\nOutput: {OUT_PATH}")
