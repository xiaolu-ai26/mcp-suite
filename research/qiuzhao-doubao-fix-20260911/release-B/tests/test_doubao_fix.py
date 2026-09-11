"""Doubao compatibility, identical in release A and B.

Strict-schema clients drop parameters whose schema lacks a top-level "type". Every tool
must therefore expose flat schemas, accept omitted / null / real values, echo the filters
it applied, and log one line per call with argument names only.
"""
import json

from _mcp_harness import error_text, structured

JOB_CATEGORIES = {"技术/研发", "产品", "运营", "设计", "市场/营销", "销售", "职能/支持", "金融",
                  "咨询", "医疗/医药", "制造/生产", "科研", "教育/培训", "法律/合规", "其他"}
GRADUATION_YEARS = {"2027届", "2026届", "2025届", "未披露"}
BENCH_TEXT = ("topic", "format", "tag", "platform", "time_window", "keyword")


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def assert_flat(tool):
    schema = tool["inputSchema"]
    for node in walk(schema):
        assert not {"anyOf", "oneOf", "allOf"} & set(node), (tool["name"], node)
    for name, prop in schema.get("properties", {}).items():
        assert isinstance(prop.get("type"), str) and prop["type"] != "null", (tool["name"], name, prop)


def test_qiuzhao_schemas_are_flat(qz):
    tools = qz.list_tools()
    assert set(tools) == {"jobs_search", "jobs_deadlines", "jobs_detail"}
    for tool in tools.values():
        assert_flat(tool)


def test_bench_schemas_are_flat(bench_server):
    tools = bench_server.list_tools()
    assert set(tools) == {"bench_search", "bench_detail", "bench_taxonomy"}
    for tool in tools.values():
        assert_flat(tool)


def test_enums_and_limit(qz, valid_rows):
    props = qz.list_tools()["jobs_search"]["inputSchema"]["properties"]
    assert props["job_category"]["type"] == "string" and set(props["job_category"]["enum"]) == {""} | JOB_CATEGORIES
    assert props["graduation_year"]["type"] == "string" and set(props["graduation_year"]["enum"]) == {""} | GRADUATION_YEARS
    # Enum values are exactly the values present in the dataset, so no filter value is unreachable.
    assert {r["job_category_normalized"] for r in valid_rows} == JOB_CATEGORIES
    assert {r["graduation_year_normalized"] for r in valid_rows} == GRADUATION_YEARS
    assert props["limit"]["default"] == 10 and props["limit"]["maximum"] == 100


def test_jobs_search_omitted(qz, valid_rows):
    out = structured(qz.call("jobs_search", {}))
    assert out["applied_filters"] == {}
    assert len(out["jobs"]) == 10 and out["total"] == len(valid_rows) and out["next_offset"] == 10


def test_jobs_search_all_text_params_null(qz, valid_rows):
    props = qz.list_tools()["jobs_search"]["inputSchema"]["properties"]
    nulls = {name: None for name, prop in props.items() if prop["type"] == "string"}
    assert len(nulls) >= 8
    out = structured(qz.call("jobs_search", nulls))
    assert out["applied_filters"] == {}
    assert len(out["jobs"]) == 10 and out["total"] == len(valid_rows)


def test_jobs_search_values_and_applied_filters(qz):
    out = structured(qz.call("jobs_search", {"job_category": "产品", "graduation_year": 2027,
                                             "city": " 北京 ", "keyword": "   ", "limit": 5}))
    assert out["applied_filters"] == {"job_category": "产品", "graduation_year": "2027届", "city": "北京"}
    assert 0 < len(out["jobs"]) <= 5 and out["total"] > 0
    for job in out["jobs"]:
        assert "产品" in f"{job.get('job_category_normalized')}{job.get('job_category')}"
        assert "北京" in json.dumps([job.get("city_normalized"), job.get("cities")], ensure_ascii=False)


def test_graduation_year_spellings_normalize(qz):
    totals = set()
    for raw in ("2027", 2027, "2027届", " 2027 届 ", "2027年"):
        out = structured(qz.call("jobs_search", {"graduation_year": raw, "limit": 1}))
        assert out["applied_filters"] == {"graduation_year": "2027届"}, raw
        totals.add(out["total"])
    assert len(totals) == 1


def test_out_of_enum_value_is_rejected(qz):
    assert "job_category" in error_text(qz.call("jobs_search", {"job_category": "产品经理"}))
    assert "graduation_year" in error_text(qz.call("jobs_search", {"graduation_year": "2030届"}))


def test_limit_bounds(qz):
    assert len(structured(qz.call("jobs_search", {"limit": 100}))["jobs"]) == 100
    assert error_text(qz.call("jobs_search", {"limit": 101}))


def test_search_returns_full_records(qz):
    job = structured(qz.call("jobs_search", {"limit": 1}))["jobs"][0]
    assert job == structured(qz.call("jobs_detail", {"id": job["id"]}))["jobs"][0]
    assert len(job) >= 25 and "description_raw" in job


def test_industry_description_current_and_filter_works(qz):
    prop = qz.list_tools()["jobs_search"]["inputSchema"]["properties"]["industry"]
    assert "暂返回空结果" not in prop["description"] and "互联网/科技" in prop["description"]
    out = structured(qz.call("jobs_search", {"industry": "互联网/科技", "limit": 1}))
    assert out["total"] > 0 and out["applied_filters"] == {"industry": "互联网/科技"}


def test_instructions_mention_applied_filters(qz):
    assert "applied_filters" in qz.initialize()["instructions"]


def test_call_log_has_names_not_values(qz):
    sentinel = "SENTINEL产品值9f3c"
    agent = "DoubaoWork/9.9 " + "x" * 300
    structured(qz.call("jobs_search", {"keyword": sentinel, "limit": 1, "city": None}, user_agent=agent))
    entry = [e for e in qz.log_entries("mcp_tool_call") if e["ua"].startswith("DoubaoWork/9.9")][-1]
    assert entry == {"tool": "jobs_search", "args": ["city", "keyword", "limit"], "ua": agent[:100]}
    text = qz.log_text()
    assert sentinel not in text and qz.token not in text and "Bearer" not in text


def test_bench_search_null_omitted_and_value(bench_server):
    omitted = structured(bench_server.call("bench_search", {}))
    nulls = structured(bench_server.call("bench_search", dict.fromkeys(BENCH_TEXT)))
    assert omitted["total"] == nulls["total"] == 2
    # Output unchanged from baseline: unspecified filters are still reported as null.
    assert omitted["filters"] == nulls["filters"] == dict.fromkeys(BENCH_TEXT)
    hit = structured(bench_server.call("bench_search", {"platform": "抖音"}))
    assert [r["id"] for r in hit["records"]] == ["c"] and hit["filters"]["platform"] == "抖音"
    entry = bench_server.log_entries("mcp_tool_call")[-1]
    assert entry == {"tool": "bench_search", "args": ["platform"], "ua": "doubao-fix-harness/1.0"}
