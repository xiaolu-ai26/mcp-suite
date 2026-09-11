"""生成 examples/ 下的返回示例。

用法（在 qiuzhao-v4-interface-20260911/ 下）：python3 scripts/make_examples.py
全部用 data/jobs.json 的真实记录，经 v4lib 的修正规则和匹配规则模拟；每个文件的 _说明 写明哪些是模拟的。
为便于阅读，示例的 page_size 取 2–3；真实默认值是 10。
"""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import v4lib as L  # noqa: E402

items, AS_OF = L.build()
EX = L.ROOT / "examples"
EX.mkdir(exist_ok=True)
NOTE = ("模拟：用 data/jobs.json（2026-09-11 拉取，去重后）按 SPEC.md 第 6 节修正规则与第 3 节匹配规则在本地生成，"
        "线上尚未实现。按规则模拟的字段：match、graduation_years、graduation_year_basis、education、major_category"
        "（含 不限/未注明）、cities（修复 area_code）、job_category（修正错分）、deadline/deadline_kind、status（中文）、"
        "region、company/campaign_title（改名）。其余字段是原始数据。“今天”固定为 2026-09-11。"
        "response 是工具结果 JSON（线上为 content[0].text 的内容）。")
TOOLS = {"jobs_search": L.jobs_search, "jobs_stats": L.jobs_stats, "jobs_detail": L.jobs_detail}


def call(tool, args, notices=None):
    try:
        if notices:
            return TOOLS[tool](items, AS_OF, notices=notices, **args)
        return TOOLS[tool](items, AS_OF, **args)
    except L.ParamError as exc:
        return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}


def dump(name, tool, args, response, extra=""):
    obj = {"_说明": NOTE + extra, "request": {"tool": tool, "arguments": args}, "response": response}
    (EX / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    return response


# ---------------- jobs_search
base = {"graduation_year": "2027届", "major": "计算机类", "page_size": 3}
city = "成都"
for c in ("成都", "西安", "合肥", "长沙", "南京"):  # 选一个第一页就能看到“全国”依据的城市
    r = L.jobs_search(items, AS_OF, city=c, **base)
    if any(j.get("match", {}).get("city") == "全国" for j in r["jobs"]):
        city = c
        break
a1 = {"city": city, **base}
s1 = dump("jobs_search.1_city_year_major.json", "jobs_search", a1, call("jobs_search", a1),
          f" 城市取 {city}：候选城市里第一个在第 1 页就出现“全国”依据的。")
edge = {**a1, "offset": max(s1["explicit_total"] - 1, 0)}
dump("jobs_search.2_explicit_unspecified_boundary.json", "jobs_search", edge, call("jobs_search", edge),
     " offset 取 explicit_total-1，让同一页同时出现最后一条明确匹配和最前面的含未注明岗位。")
a3 = {"recruitment_type": "校园招聘", "deadline_within_days": 7, "sort": "deadline_asc", "page_size": 3}
dump("jobs_search.3_deadline_7d.json", "jobs_search", a3, call("jobs_search", a3))

# ---------------- jobs_stats
dump("jobs_stats.1_product_2027_by_city.json", "jobs_stats",
     t1 := {"job_category": "产品", "graduation_year": "2027届", "group_by": "city", "top": 10},
     call("jobs_stats", t1))
dump("jobs_stats.2_soe_cs_by_company.json", "jobs_stats",
     t2 := {"industry": "国企/央企", "major": "计算机类", "group_by": "company", "top": 10}, call("jobs_stats", t2))
dump("jobs_stats.3_campus_by_education.json", "jobs_stats",
     t3 := {"recruitment_type": "校园招聘", "group_by": "education"}, call("jobs_stats", t3),
     " education 分组是岗位写明的最低学历；把“本科”填回 jobs_search.education 时按“门槛不高于本科”匹配，"
     "明确匹配数会大于本组计数（见 SPEC 3.2 与待决第 3 条）。")

# ---------------- jobs_detail
ids = ",".join(j["id"] for j in s1["jobs"][:2])
dump("jobs_detail.1_two_ids.json", "jobs_detail", d1 := {"ids": ids}, call("jobs_detail", d1))
dump("jobs_detail.2_not_found.json", "jobs_detail", d2 := {"ids": s1["jobs"][0]["id"] + ",gp-000000000000000000"},
     call("jobs_detail", d2), " 第二个 id 是故意编的不存在的 id。")

# ---------------- 兼容与报错
cases = []


def legacy(tool, args, keep_jobs=None):
    new_tool, new_args, notices = L.map_legacy(tool, args)
    resp = call(new_tool, new_args, notices)
    if keep_jobs is not None and "jobs" in resp:
        resp = {**resp, "jobs": resp["jobs"][:keep_jobs], "_jobs_省略": f"只保留前 {keep_jobs} 条以便阅读"}
    cases.append({"场景": f"旧调用 {tool}", "request": {"tool": tool, "arguments": args},
                  "服务端映射为": {"tool": new_tool, "arguments": new_args}, "response": resp})


legacy("jobs_deadlines", {"days": 7, "limit": 3}, keep_jobs=1)
legacy("jobs_search", {"cohort": "2027", "region": "北京", "limit": 50}, keep_jobs=1)
legacy("jobs_detail", {"id": s1["jobs"][0]["id"]}, keep_jobs=0)
legacy("jobs_search", {"cohort": "2027届", "graduation_year": "2026届", "page_size": 1}, keep_jobs=0)


def direct(label, tool, args, keep_jobs=0):
    resp = call(tool, args)
    if "jobs" in resp:
        resp = {**resp, "jobs": resp["jobs"][:keep_jobs], "_jobs_省略": f"只保留前 {keep_jobs} 条以便阅读"}
    cases.append({"场景": label, "request": {"tool": tool, "arguments": args}, "response": resp})


direct("同义词自动归一（产品经理→产品，校招→校园招聘，2027→2027届）", "jobs_search",
       {"job_category": "产品经理", "recruitment_type": "校招", "graduation_year": 2027, "page_size": 1})
direct("枚举外的值", "jobs_search", {"job_category": "游戏策划"})
direct("explicit_only 与 未注明 矛盾", "jobs_search", {"graduation_year": "未注明", "explicit_only": True})
direct("ids 超过 10 个", "jobs_detail", {"ids": ",".join(it["id"] for it in items[:11])})
direct("group_by 枚举外", "jobs_stats", {"group_by": "salary"})
cases.append({"场景": "未知参数（FastMCP 在进入工具函数前拒绝，非本脚本模拟）",
              "request": {"tool": "jobs_search", "arguments": {"salary": "20k"}},
              "response": {"isError": True, "content": [{"type": "text", "text":
                           "1 validation error for call[jobs_search]\nsalary\n  Unexpected keyword argument "
                           "[type=unexpected_keyword_argument, input_value='20k', input_type=str]"}]},
              "出处": "格式引自 ../qiuzhao-doubao-fix-20260911/probes/probe_unknown_param.out.txt 第 12–15 行"})
(EX / "compat_and_errors.json").write_text(json.dumps({"_说明": NOTE, "cases": cases}, ensure_ascii=False, indent=2) + "\n")
print("examples:", sorted(p.name for p in EX.glob("*.json")))
