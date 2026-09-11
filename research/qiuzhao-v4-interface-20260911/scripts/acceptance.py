"""验收问题集的参考值：按 SPEC.md 第 8 节每个问题的期望调用链，在本地模拟结果。

用法（在 qiuzhao-v4-interface-20260911/ 下）：python3 scripts/acceptance.py
输出 evidence/acceptance_expected.json。数字是 2026-09-11 数据的模拟值；上线当天请用当天的 jobs.json 重跑，
再和三个客户端的实际回答对照（数据每天更新，数字会变，调用链和“必须包含”的要素不变）。
"""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4lib as L  # noqa: E402

items, AS_OF = L.build()
F = {"jobs_search": L.jobs_search, "jobs_stats": L.jobs_stats, "jobs_detail": L.jobs_detail}


def run(tool, **args):
    r = F[tool](items, AS_OF, **args)
    brief = {k: r[k] for k in ("total", "explicit_total", "unspecified_total", "has_next", "next_offset",
                               "groups_total", "found", "not_found") if k in r}
    if "groups" in r:
        brief["groups"] = [(g["value"], g["count"], g["explicit_count"]) for g in r["groups"]]
    if tool == "jobs_search":
        brief["first_ids"] = [j["id"] for j in r["jobs"][:3]]
        brief["first_match"] = [j.get("match") for j in r["jobs"][:3]]
        brief["first_deadlines"] = [j["deadline"] for j in r["jobs"][:3]]
    return {"tool": tool, "arguments": args, "result": brief}


q1 = run("jobs_search", city="杭州", graduation_year="2027届", major="计算机类", education="硕士")
ids = q1["result"]["first_ids"]
Q = {
    "Q01": [q1],
    "Q02": [run("jobs_search", company="字节跳动", job_category="产品"),
            run("jobs_stats", company="字节跳动", job_category="产品", group_by="city", top=5)],
    "Q03": [run("jobs_search", recruitment_type="校园招聘", deadline_within_days=7, sort="deadline_asc")],
    "Q04": [run("jobs_search", city="北京", industry="国企/央企", major="不限")],
    "Q05": [run("jobs_detail", ids=ids[1])],
    "Q06": [run("jobs_search", recruitment_type="实习招聘", city="上海", keyword="转正")],
    "Q07": [run("jobs_search", graduation_year="2026届", industry="国企/央企")],
    "Q08": [run("jobs_search", job_category="产品", deadline_within_days=19, sort="deadline_asc")],
    "Q09": [run("jobs_search", company="腾讯,阿里巴巴", city="深圳", keyword="算法")],
    "Q10": [run("jobs_stats", job_category="产品", graduation_year="2027届", group_by="city", top=10)],
    "Q11": [run("jobs_stats", recruitment_type="校园招聘", group_by="industry", top=5)],
    "Q12": [run("jobs_stats", industry="国企/央企", major="计算机类", group_by="company", top=5)],
    "Q13": [run("jobs_stats", education="本科"), run("jobs_stats", education="硕士"),
            run("jobs_stats", group_by="education")],
    "Q14": [run("jobs_stats", major="计算机类"), run("jobs_stats", group_by="major_category", top=13)],
    "Q15": [run("jobs_search", city="上海", job_category="技术/研发", deadline_within_days=14, sort="deadline_asc",
                page_size=20)],
    "Q16": [run("jobs_detail", ids=",".join(ids[:2]))],
    "Q17": [run("jobs_stats", group_by="company", top=1)],
    "Q18": [run("jobs_stats", company="字节跳动", group_by="city", top=5),
            run("jobs_stats", company="字节跳动", group_by="job_category")],
    "Q19": [run("jobs_search", city="新加坡"), run("jobs_stats", group_by="city", top=100)],
    "Q20": [run("jobs_search", graduation_year="2027届", explicit_only=True)],
}
# Q19 只保留海外城市相关的组，避免输出过长
Q["Q19"][1]["result"]["groups"] = [g for g in Q["Q19"][1]["result"]["groups"] if g[0] in ("新加坡", "圣何塞", "海外", "全国", "未注明")]
out = {"data_as_of": AS_OF, "today": L.TODAY.isoformat(), "questions": Q}
(L.ROOT / "evidence" / "acceptance_expected.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
