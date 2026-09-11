"""v4 tools over real HTTP (uvicorn subprocess, 2026-09-11 jobs.json, today pinned to 2026-09-11).

Single copy of the result, pagination and the 60 KB budget, synonym normalization, Chinese errors,
explicit_only, the three match tiers, 社招 exclusion, stats fill-back, detail, test-record filtering,
and every acceptance question: the HTTP result must equal the in-process result exactly.
"""
import json
import re
from datetime import date, timedelta

import pytest

from _mcp_harness import TODAY, error_text, structured
from acceptance_cases import CASES, resolve
from qiuzhao import tools as T
from qiuzhao import v4_fields as V

LEVELS = {"明确匹配": 0, "推断匹配": 1, "含未注明": 2}
TEST_IDS = ["gp-208198996248757008", "gp_开开心心有限公司2-213282367253512230", "gp_梧桐科技-150370747208958449",
            "gp_洛阳前钱有限企业-109204351230152857", "guopin-109204351230152857"]


def jobs_bytes(out):
    return len(json.dumps(out["jobs"], ensure_ascii=False, separators=(",", ":")).encode())


def test_single_copy_content_only(qz):
    result, body = qz.call("jobs_search", {"page_size": 3}, raw=True)
    assert result.get("structuredContent") is None and "structuredContent" not in json.loads(body)["result"]
    assert len(result["content"]) == 1 and result["content"][0]["type"] == "text"
    out = json.loads(result["content"][0]["text"])
    assert out["returned"] == 3
    # The result JSON appears once, as escaped text inside the JSON-RPC body, never as an object.
    assert body.count(b'\\"total\\":') == 1 and body.count(b'"total":') == 0
    for name in ("jobs_stats", "jobs_detail"):
        args = {"group_by": "city"} if name == "jobs_stats" else {"ids": out["jobs"][0]["id"]}
        res = qz.call(name, args)
        assert res.get("structuredContent") is None and len(res["content"]) == 1


def test_default_search_shape(qz, jobs_inproc):
    out = structured(qz.call("jobs_search"))
    assert list(out) == ["applied_filters", "total", "explicit_total", "inferred_total", "unspecified_total",
                         "sort", "offset", "page_size", "returned", "has_next", "next_offset", "truncated",
                         "data_as_of", "jobs"]
    assert out["total"] == out["explicit_total"] == len(jobs_inproc.dataset().items)
    assert (out["page_size"], out["returned"], out["has_next"], out["next_offset"], out["truncated"]) == (10, 10, True, 10, False)
    assert out["data_as_of"] == jobs_inproc.dataset().data_as_of
    for job in out["jobs"]:
        assert "match" not in job and set(V.CORE) <= set(job)
        assert not {"city_normalized", "cities_normalized", "overseas_flag", "cohort_filter_scope",
                    "recruitment_unit", "evidence_path", "source_record_id"} & set(job)


def test_pagination_chain(qz):
    a = structured(qz.call("jobs_search", {"keyword": "算法", "page_size": 10}))
    b = structured(qz.call("jobs_search", {"keyword": "算法", "page_size": 10, "offset": a["next_offset"]}))
    c = structured(qz.call("jobs_search", {"keyword": "算法", "page_size": 20}))
    assert [j["id"] for j in a["jobs"] + b["jobs"]] == [j["id"] for j in c["jobs"]]
    end = structured(qz.call("jobs_search", {"keyword": "算法", "page_size": 20, "offset": c["total"] - 3}))
    assert end["returned"] == 3 and end["has_next"] is False and end["next_offset"] is None
    past = structured(qz.call("jobs_search", {"keyword": "算法", "offset": c["total"] + 5}))
    assert past["returned"] == 0 and past["jobs"] == [] and past["has_next"] is False


def test_budget_cuts_at_a_whole_job(qz, jobs_inproc):
    offset = next(k for k in range(0, 25_000, 20) if jobs_inproc.search(page_size=20, offset=k)["truncated"])
    out = structured(qz.call("jobs_search", {"page_size": 20, "offset": offset}))
    assert out["truncated"] is True and 1 <= out["returned"] < 20
    assert jobs_bytes(out) <= T.BUDGET_BYTES < jobs_bytes(out) + 20_000
    assert out["next_offset"] == offset + out["returned"] and out["has_next"]
    following = structured(qz.call("jobs_search", {"page_size": 1, "offset": out["next_offset"]}))
    expected = jobs_inproc.search(page_size=20, offset=offset + out["returned"])["jobs"][0]["id"]
    assert following["jobs"][0]["id"] == expected


def test_page_size_over_20_is_clamped_with_notice(qz):
    out = structured(qz.call("jobs_search", {"page_size": 50}))
    assert out["page_size"] == 20 and out["returned"] <= 20
    assert any("上限 20" in n for n in out["notices"])
    top = structured(qz.call("jobs_stats", {"group_by": "company", "top": 150}))
    assert top["returned_groups"] == 100 and any("上限 100" in n for n in top["notices"])


def test_synonyms_normalize_with_notice(qz):
    out = structured(qz.call("jobs_search", {"job_category": "产品经理", "recruitment_type": "校招", "education": "研究生",
                                             "industry": "央企", "graduation_year": "27届", "city": "北京市",
                                             "page_size": 1}))
    assert out["applied_filters"] == {"job_category": "产品", "recruitment_type": "校园招聘", "education": "硕士",
                                      "industry": "国企/央企", "graduation_year": "2027届", "city": "北京"}
    assert len(out["notices"]) >= 6 and all("已按" in n for n in out["notices"][:6])
    totals = set()
    for raw in ("2027", 2027, "2027届", " 2027 届 ", "2027年", "27届"):
        res = structured(qz.call("jobs_search", {"graduation_year": raw, "page_size": 1}))
        assert res["applied_filters"] == {"graduation_year": "2027届"}, raw
        totals.add(res["total"])
    assert len(totals) == 1
    assert structured(qz.call("jobs_search", {"graduation_year": "未披露", "page_size": 1}))["applied_filters"] == {
        "graduation_year": "未注明"}


@pytest.mark.parametrize("tool,args,parts", [
    ("jobs_search", {"job_category": "游戏策划"}, ["不在可选范围", "可选：技术/研发", "keyword"]),
    ("jobs_search", {"graduation_year": "2030届"}, ["graduation_year", "不在可选范围"]),
    ("jobs_search", {"graduation_year": "实习未写届别"}, ["recruitment_type"]),
    ("jobs_search", {"education": "高职高专以上"}, ["education", "可选"]),
    ("jobs_search", {"page_size": 0}, ["page_size"]),
    ("jobs_search", {"offset": -1}, ["offset"]),
    ("jobs_search", {"deadline_within_days": 367}, ["deadline_within_days", "1–366"]),
    ("jobs_search", {"sort": "salary"}, ["sort", "published_desc"]),
    ("jobs_search", {"explicit_only": True, "graduation_year": "未注明"}, ["矛盾"]),
    ("jobs_search", {"explicit_only": True, "city": "北京,未注明"}, ["矛盾"]),
    ("jobs_stats", {"explicit_only": True, "education": "未注明"}, ["矛盾"]),
    ("jobs_stats", {"explicit_only": True, "major": "未注明"}, ["矛盾"]),
    ("jobs_stats", {"group_by": "salary"}, ["group_by", "company"]),
    ("jobs_stats", {"top": 0}, ["top"]),
    ("jobs_detail", {"ids": " , "}, ["不能为空"]),
    ("jobs_detail", {"ids": ",".join(str(i) for i in range(11))}, ["最多 10"]),
    ("jobs_search", {"keyword": "长" * 101}, ["keyword", "最长 100"]),
])
def test_errors_are_chinese_and_actionable(qz, tool, args, parts):
    text = error_text(qz.call(tool, args))
    assert all(p in text for p in parts), text
    assert re.search(r"[一-鿿]", text) and "validation error" not in text.lower()


def test_three_tiers_order_and_explicit_only(qz, jobs_inproc):
    full = structured(qz.call("jobs_search", {"graduation_year": "2027届", "page_size": 1}))
    e, i, u = full["explicit_total"], full["inferred_total"], full["unspecified_total"]
    assert e + i + u == full["total"] and min(e, i, u) > 0
    for boundary, levels in ((e - 1, ["明确匹配", "推断匹配"]), (e + i - 1, ["推断匹配", "含未注明"])):
        page = structured(qz.call("jobs_search", {"graduation_year": "2027届", "offset": boundary, "page_size": 2}))
        assert [j["match"]["level"] for j in page["jobs"]] == levels
    only = structured(qz.call("jobs_search", {"graduation_year": "2027届", "explicit_only": True, "page_size": 20}))
    assert only["total"] == only["explicit_total"] == e and only["inferred_total"] == only["unspecified_total"] == 0
    assert {j["match"]["level"] for j in only["jobs"]} == {"明确匹配"}
    assert "excluded_social_total" not in only
    # 全国 stays explicit under explicit_only (decision 4).
    city = structured(qz.call("jobs_search", {"city": "北京", "explicit_only": True, "page_size": 1}))
    stats = structured(qz.call("jobs_stats", {"city": "北京"}))
    assert city["total"] == stats["explicit_total"] and stats["unspecified_total"] > 0
    res, _ = jobs_inproc.evaluate(jobs_inproc.dataset(), jobs_inproc.check_filters(
        {"city": "北京", "explicit_only": True}, []), date.fromisoformat(TODAY))
    assert sum(1 for _, b, _ in res if b["city"] == "全国") > 900
    assert structured(qz.call("jobs_search", {"city": "新加坡", "page_size": 1}))["explicit_total"] < 100


def test_inferred_bases_are_labelled(qz, jobs_inproc):
    seen = {}
    res, _ = jobs_inproc.evaluate(jobs_inproc.dataset(), jobs_inproc.check_filters({"graduation_year": "2027届"}, []),
                                  date.fromisoformat(TODAY))
    for it, basis, tier in res:
        seen.setdefault(basis["graduation_year"], tier)
    assert seen == {"岗位写明": 0, "活动标题写明": 0, "按招聘季推断": 1, "来源专场注明": 1, "实习未写届别": 1, "未注明": 2}
    # Over HTTP: the first inferred job carries level + basis.
    full = structured(qz.call("jobs_search", {"graduation_year": "2027届", "page_size": 1}))
    first = structured(qz.call("jobs_search", {"graduation_year": "2027届", "page_size": 1,
                                               "offset": full["explicit_total"]}))["jobs"][0]
    assert first["match"]["level"] == "推断匹配" and first["match"]["graduation_year"] in ("按招聘季推断", "来源专场注明", "实习未写届别")


def test_social_recruitment_is_excluded_by_graduation_year(qz, jobs_inproc):
    today = TODAY
    social = [it for it in jobs_inproc.dataset().items if it.get("graduation_year_note") == V.NOTE_SOCIAL
              and not (it["deadline"] and it["deadline"] < today)]
    out = structured(qz.call("jobs_search", {"graduation_year": "2027届", "page_size": 1}))
    assert out["excluded_social_total"] == len(social) > 3000
    assert any("社会招聘" in n for n in out["notices"])
    soc = structured(qz.call("jobs_search", {"graduation_year": "2027届", "recruitment_type": "社会招聘", "page_size": 20}))
    assert "excluded_social_total" not in soc and soc["inferred_total"] >= len(social)
    assert "社招不限届别" in {j["match"]["graduation_year"] for j in structured(qz.call(
        "jobs_search", {"graduation_year": "2027届", "recruitment_type": "社会招聘", "page_size": 1,
                        "offset": soc["explicit_total"]}))["jobs"]}
    st = structured(qz.call("jobs_stats", {"graduation_year": "2027届"}))
    assert st["excluded_social_total"] == out["excluded_social_total"] and st["total"] == out["total"]


def test_stats_groups_fill_back(qz, jobs_inproc):
    st = structured(qz.call("jobs_stats", {"job_category": "产品", "graduation_year": "2027届", "group_by": "city",
                                           "top": 5}))
    assert st["fill_param"] == "city" and st["multi_valued"] is True and st["returned_groups"] == 5
    for g in st["groups"]:
        assert g["count"] == g["explicit_count"] + g["inferred_count"] + g["unspecified_count"]
    value = st["groups"][0]["value"]
    back = structured(qz.call("jobs_search", {"job_category": "产品", "graduation_year": "2027届", "city": value,
                                              "page_size": 1}))
    assert back["total"] >= st["groups"][0]["count"]
    # Exact relation: the group counts rows whose own cities contain the value.
    res, _ = jobs_inproc.evaluate(jobs_inproc.dataset(), jobs_inproc.check_filters(
        {"job_category": "产品", "graduation_year": "2027届", "city": value}, []), date.fromisoformat(TODAY))
    assert sum(1 for _, b, _ in res if b["city"] == "岗位写明") == st["groups"][0]["count"]
    years = structured(qz.call("jobs_stats", {"group_by": "graduation_year", "top": 20}))
    values = {g["value"] for g in years["groups"]}
    assert {"2027届", "2026届", "未注明", "实习未写届别", "社招不限届别"} <= values and years["multi_valued"]
    edu = structured(qz.call("jobs_stats", {"group_by": "education"}))
    assert edu["fill_param"] == "education" and {g["value"] for g in edu["groups"]} == set(V.EDUCATIONS)
    maj = structured(qz.call("jobs_stats", {"group_by": "major_category", "top": 13}))
    assert maj["fill_param"] == "major" and "groups" not in structured(qz.call("jobs_stats", {}))


def test_detail(qz):
    ids = [j["id"] for j in structured(qz.call("jobs_search", {"page_size": 2}))["jobs"]]
    out = structured(qz.call("jobs_detail", {"ids": f"{ids[0]}, {ids[1]},{ids[0]},made-up-id"}))
    assert (out["requested"], out["found"], out["not_found"]) == (3, 2, ["made-up-id"]) and out["suggestion"]
    assert [j["id"] for j in out["jobs"]] == ids and all("match" not in j for j in out["jobs"])
    # A search row (no match when no dimension is used) is the same record as its detail row.
    assert structured(qz.call("jobs_search", {"page_size": 1}))["jobs"][0] == out["jobs"][0]


def test_test_records_are_gone(qz):
    out = structured(qz.call("jobs_detail", {"ids": ",".join(TEST_IDS)}))
    assert out["found"] == 0 and out["not_found"] == TEST_IDS
    for kw in ("test50", "联调测试修改职位", "测试职位请勿投递", "参与单位数据统计"):
        assert structured(qz.call("jobs_search", {"keyword": kw}))["total"] == 0, kw


def test_deadline_window_and_order(qz, jobs_inproc):
    today = date.fromisoformat(TODAY)
    end = (today + timedelta(days=7)).isoformat()
    expected = [it for it in jobs_inproc.dataset().items if it["recruitment_type"] == "校园招聘"
                and it["deadline"] and TODAY <= it["deadline"] <= end]
    out = structured(qz.call("jobs_search", {"recruitment_type": "校园招聘", "deadline_within_days": 7,
                                             "sort": "deadline_asc", "page_size": 20}))
    assert out["total"] == len(expected)
    deadlines = [j["deadline"] for j in out["jobs"]]
    assert deadlines == sorted(deadlines) and deadlines[0] == TODAY
    assert all(j["deadline_kind"] == "明确日期" and TODAY <= j["deadline"] <= end for j in out["jobs"])
    assert out["applied_filters"]["sort"] == "deadline_asc"


def test_acceptance_http_equals_in_process(qz, jobs_inproc):
    call = {"jobs_search": jobs_inproc.search, "jobs_stats": jobs_inproc.stats, "jobs_detail": jobs_inproc.detail}
    first = {}
    for qid, (_, steps) in CASES.items():
        for n, (tool, args) in enumerate(steps):
            args = resolve(args, first)
            http = structured(qz.call(tool, args))
            local = call[tool](**args)
            assert http == json.loads(json.dumps(local, ensure_ascii=False)), (qid, tool, args)
            if n == 0:
                first[qid] = local
