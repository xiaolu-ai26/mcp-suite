"""Regenerate research/qiuzhao-v4-interface-20260911/examples/ from the real v4 implementation.

usage (from the code root):
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python research/qiuzhao-v4-impl/scripts/make_examples_v4.py
Normal results come from qiuzhao/tools.py in-process (tests/test_v4_tools.py proves the HTTP server
returns exactly the same JSON); errors and unknown-argument cases come from a real uvicorn process
through tests/_mcp_harness.py, so their texts are what a client sees. "Today" is 2026-09-11.
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT)]

import _mcp_harness as H  # noqa: E402
from qiuzhao.tools import Jobs  # noqa: E402

TODAY = H.TODAY
jobs = Jobs(H.JOBS_PATH, today=date.fromisoformat(TODAY))
EX = ROOT / "research" / "qiuzhao-v4-interface-20260911" / "examples"
NOTE = ("由 feat/v4 的 qiuzhao/tools.py 对 2026-09-11 拉取的 jobs.json 实际运行生成（去重、去测试记录后 25,458 条）；"
        "“今天”固定为 2026-09-11。response 就是线上 content[0].text 的内容：单份返回，没有 structuredContent。"
        "为便于阅读，page_size 取 2–5，真实默认值是 10。")
OPS = {"jobs_search": jobs.search, "jobs_stats": jobs.stats, "jobs_detail": jobs.detail}


def dump(name, tool, args, extra=""):
    response = OPS[tool](**args)
    obj = {"_说明": NOTE + extra, "request": {"tool": tool, "arguments": args}, "response": response}
    (EX / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    return response


def main():
    for old in ("jobs_search.2_explicit_unspecified_boundary.json", "compat_and_errors.json"):
        (EX / old).unlink(missing_ok=True)
    today = date.fromisoformat(TODAY)
    a1 = {"city": "成都", "graduation_year": "2027届", "major": "计算机类", "page_size": 3}
    s1 = dump("jobs_search.1_city_year_major.json", "jobs_search", {**a1, "page_size": 5},
              " 成都 + 2027届 + 计算机类（Max 给的排序示例，page_size 取 5）：同一档内先按匹配的具体程度排，"
              "写明成都的岗位排在依据“全国”的岗位之前，其后才按发布时间。")
    res, _ = jobs.evaluate(jobs.dataset(), jobs.check_filters({k: v for k, v in a1.items() if k != "page_size"}, []),
                           today)
    split = next(i for i, (_, b, _) in enumerate(jobs.order(res, "published_desc")) if b["city"] == "全国")
    dump("jobs_search.1b_city_then_nationwide.json", "jobs_search", {**a1, "offset": split - 1, "page_size": 2},
         f" offset 取 {split - 1}：明确匹配里写明成都的岗位共 {split} 条，排完之后才是依据“全国”的岗位。")
    dump("jobs_search.2_explicit_inferred_boundary.json", "jobs_search",
         {**a1, "offset": s1["explicit_total"] - 1},
         " offset 取 explicit_total-1：同一页里先是最后一条明确匹配，再是最前面的推断匹配。")
    dump("jobs_search.2b_inferred_unspecified_boundary.json", "jobs_search",
         {**a1, "offset": s1["explicit_total"] + s1["inferred_total"] - 1},
         " offset 取 explicit_total+inferred_total-1：推断匹配之后接着含未注明的岗位。")
    dump("jobs_search.3_deadline_7d.json", "jobs_search",
         {"recruitment_type": "校园招聘", "deadline_within_days": 7, "sort": "deadline_asc", "page_size": 3})
    dump("jobs_search.4_tencent_2027_source_scope.json", "jobs_search",
         {"company": "腾讯", "graduation_year": "2027届", "page_size": 2, "offset": 2},
         " 腾讯校招岗位原文和活动标题都没写届别、也没有发布时间，按来源登记（sources_registry.jsonl 的"
         " scope_graduation_year=2027届）推断，依据“来源专场注明”；按届别筛选时社招岗位不返回，见 excluded_social_total。")
    q07 = {"graduation_year": "2026届", "industry": "国企/央企"}
    r7, _ = jobs.evaluate(jobs.dataset(), jobs.check_filters(q07, []), today)
    at = next(i for i, (_, b, _) in enumerate(jobs.order(r7, "published_desc"))
              if b["graduation_year"] == "推断为其他届别")
    dump("jobs_search.5_2026_inferred_other_year.json", "jobs_search", {**q07, "offset": at, "page_size": 2},
         f" Q07 的调用，offset 取 {at}：含未注明档里第一条“推断为其他届别”。这类岗位原文和活动标题都没写届别，"
         "按招聘季或来源专场推断为 2027届；查 2026届 时不排除，归入含未注明并标注（2026-09-12 Max 决定）。")
    dump("jobs_stats.1_product_2027_by_city.json", "jobs_stats",
         {"job_category": "产品", "graduation_year": "2027届", "group_by": "city", "top": 10})
    dump("jobs_stats.2_soe_cs_by_company.json", "jobs_stats",
         {"industry": "国企/央企", "major": "计算机类", "group_by": "company", "top": 10})
    dump("jobs_stats.3_campus_by_education.json", "jobs_stats", {"recruitment_type": "校园招聘", "group_by": "education"},
         " education 分组是岗位写明的最低学历；把“本科”填回 jobs_search.education 时按“门槛不高于本科”匹配，"
         "返回数会大于本组计数（SPEC 3.2）。")
    dump("jobs_stats.4_by_graduation_year.json", "jobs_stats", {"group_by": "graduation_year"},
         " “实习未写届别”“社招不限届别”两组不是届别取值，不能填回 graduation_year。")
    ids = ",".join(j["id"] for j in s1["jobs"][:2])
    dump("jobs_detail.1_two_ids.json", "jobs_detail", {"ids": ids})
    dump("jobs_detail.2_not_found.json", "jobs_detail", {"ids": s1["jobs"][0]["id"] + ",gp-000000000000000000"},
         " 第二个 id 是故意编的不存在的 id。")

    cases = []
    server = H.Server("qiuzhao", label="make-examples").start()
    try:
        def http(label, tool, args, keep_jobs=0):
            result = server.call(tool, args)
            if result.get("isError"):
                response = {"isError": True, "content": result["content"]}
            else:
                response = H.payload(result)
                if "jobs" in response:
                    response = {**response, "jobs": response["jobs"][:keep_jobs],
                                "_jobs_省略": f"只保留前 {keep_jobs} 条以便阅读"}
            cases.append({"场景": label, "request": {"tool": tool, "arguments": args}, "response": response})

        http("同义词自动归一（产品经理→产品，校招→校园招聘，27届→2027届，研究生→硕士），notices 说明", "jobs_search",
             {"job_category": "产品经理", "recruitment_type": "校招", "graduation_year": "27届", "education": "研究生",
              "page_size": 1})
        http("page_size 超过 20：按 20 返回并说明", "jobs_search", {"page_size": 50})
        http("枚举外的值", "jobs_search", {"job_category": "游戏策划"})
        http("explicit_only 与 未注明 矛盾", "jobs_search", {"graduation_year": "未注明", "explicit_only": True})
        http("deadline_within_days 超范围", "jobs_search", {"deadline_within_days": 400})
        http("ids 超过 10 个", "jobs_detail", {"ids": ",".join(it["id"] for it in jobs.dataset().items[:11])})
        http("group_by 枚举外", "jobs_stats", {"group_by": "salary"})
        http("v3 参数名 limit：v4 不做兼容，FastMCP 在进入工具函数前拒绝", "jobs_search", {"limit": 5})
        http("v3 参数名 cohort：同上", "jobs_search", {"cohort": "2027"})
        http("v3 工具 jobs_deadlines：已并入 jobs_search，没有别名", "jobs_deadlines", {"days": 7})
    finally:
        server.stop()
    (EX / "errors.json").write_text(json.dumps({"_说明": NOTE + " 本文件的 response 都是真实 HTTP 调用的返回。",
                                               "cases": cases}, ensure_ascii=False, indent=2) + "\n")
    print("examples:", sorted(p.name for p in EX.glob("*.json")))


if __name__ == "__main__":
    main()
