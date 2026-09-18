"""tools/list shape for both products (ported from release-A2 tests/test_doubao_fix.py).

Strict-schema clients (豆包) drop parameters whose schema lacks a top-level "type". Every tool
must expose flat schemas (no anyOf/oneOf/allOf anywhere), accept omitted / null / real values,
and echo the filters it applied. v4: exactly three recruitment tools, no outputSchema, enums
that equal the values present in the data.
"""
import json
import subprocess
import sys

from _mcp_harness import RELEASE, error_text, structured
from qiuzhao import v4_fields as V

QZ_TOOLS = {"jobs_search", "jobs_stats", "jobs_detail"}
FILTERS = {"keyword", "company", "city", "job_category", "graduation_year", "major", "education",
           "recruitment_type", "industry", "written_test", "deadline_within_days", "explicit_only",
           "include_expired"}
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


def test_qiuzhao_tools_list_is_three_flat_tools_without_output_schema(qz):
    tools = qz.rpc("tools/list")["tools"]
    assert {t["name"] for t in tools} == QZ_TOOLS and len(tools) == 3
    text = json.dumps(tools, ensure_ascii=False)
    assert not any(k in text for k in ('"anyOf"', '"oneOf"', '"allOf"'))
    for tool in tools:
        assert_flat(tool)
        assert "outputSchema" not in tool, tool["name"]


def test_bench_schemas_are_flat(bench_server):
    tools = bench_server.list_tools()
    assert set(tools) == {"bench_search", "bench_detail", "bench_taxonomy"}
    assert not any(k in json.dumps(list(tools.values())) for k in ('"anyOf"', '"oneOf"', '"allOf"'))
    for tool in tools.values():
        assert_flat(tool)


def test_search_and_stats_share_the_same_filters(qz):
    tools = qz.list_tools()
    search = set(tools["jobs_search"]["inputSchema"]["properties"])
    stats = set(tools["jobs_stats"]["inputSchema"]["properties"])
    assert search == FILTERS | {"sort", "page_size", "offset"}
    assert stats == FILTERS | {"group_by", "top"}
    assert tools["jobs_detail"]["inputSchema"]["required"] == ["ids"]
    for name in FILTERS:  # identical definitions, not just identical names
        assert tools["jobs_search"]["inputSchema"]["properties"][name] == tools["jobs_stats"]["inputSchema"]["properties"][name]


def test_enum_values_and_defaults(qz):
    props = qz.list_tools()["jobs_search"]["inputSchema"]["properties"]
    expected = {"job_category": V.JOB_CATEGORIES,
                "education": V.EDUCATIONS, "recruitment_type": V.RECRUITMENT_TYPES, "industry": V.INDUSTRIES}
    for name, values in expected.items():
        assert props[name]["type"] == "string" and props[name]["enum"] == [""] + values and props[name]["default"] == ""
    assert props["graduation_year"]["pattern"] == r"^(?:|20[0-9]{2}届|未注明)$"
    assert props["graduation_year"]["type"] == "string"
    assert props["sort"]["enum"] == ["published_desc", "deadline_asc"] and props["sort"]["default"] == "published_desc"
    assert props["page_size"] == {**props["page_size"], "type": "integer", "default": 10, "minimum": 1, "maximum": 20}
    assert props["deadline_within_days"]["maximum"] == 366 and props["explicit_only"]["type"] == "boolean"


def test_enums_equal_the_values_in_the_data(jobs_inproc):
    """SPEC 9.15: the deploy check. Enum values with no data, or data values outside the enum, fail."""
    assert V.enum_report(jobs_inproc.dataset().items)["problems"] == []
    out = subprocess.run([sys.executable, "-m", "qiuzhao.v4_fields", "check", str(jobs_inproc.path)],
                         cwd=RELEASE, capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip().endswith("RESULT OK"), out.stdout + out.stderr


def test_enum_check_fails_when_data_drifts(tmp_path):
    row = dict(id="x", source_url="https://example.org/s", application_url="https://example.org/a",
               cohort_raw="2029届", industry="航天", recruitment_type="校园招聘")
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps([row], ensure_ascii=False))
    out = subprocess.run([sys.executable, "-m", "qiuzhao.v4_fields", "check", str(path)],
                         cwd=RELEASE, capture_output=True, text=True)
    assert out.returncode == 1 and "RESULT FAIL" in out.stdout
    assert "2029届" in out.stdout and "航天" in out.stdout


def test_jobs_search_omitted(qz, jobs_inproc):
    out = structured(qz.call("jobs_search", {}))
    assert list(out)[0] == "applied_filters" and list(out)[-1] == "jobs"
    assert out["applied_filters"] == {}
    assert len(out["jobs"]) == 10 and out["total"] == len(jobs_inproc.dataset().items) and out["next_offset"] == 10


def test_all_params_null(qz, jobs_inproc):
    for tool in ("jobs_search", "jobs_stats"):
        props = qz.list_tools()[tool]["inputSchema"]["properties"]
        out = structured(qz.call(tool, dict.fromkeys(props)))
        assert out["applied_filters"] == {} and out["total"] == len(jobs_inproc.dataset().items)
    assert len(structured(qz.call("jobs_search", dict.fromkeys(["page_size", "offset", "sort"])))["jobs"]) == 10


def test_unknown_parameters_are_rejected_by_fastmcp(qz):
    # No compatibility layer in v4: v3 names are plain unknown arguments.
    for tool, args in (("jobs_search", {"limit": 1}), ("jobs_search", {"cohort": "2027"}),
                       ("jobs_search", {"region": "北京"}), ("jobs_search", {"major_category": "计算机类"}),
                       ("jobs_detail", {"id": "x"})):
        assert "Unexpected keyword argument" in error_text(qz.call(tool, args)), (tool, args)


def test_instructions(qz):
    text = qz.initialize()["instructions"]
    assert "applied_filters" in text and "推断匹配" in text and "未注明" in text and "data_as_of" in text


def test_bench_search_null_omitted_and_value(bench_server):
    omitted = structured(bench_server.call("bench_search", {}))
    nulls = structured(bench_server.call("bench_search", dict.fromkeys(BENCH_TEXT)))
    assert omitted["total"] == nulls["total"] == 2
    # Output unchanged from baseline: unspecified filters are still reported as null.
    assert omitted["filters"] == nulls["filters"] == dict.fromkeys(BENCH_TEXT)
    hit = structured(bench_server.call("bench_search", {"platform": "抖音"}))
    assert [r["id"] for r in hit["records"]] == ["c"] and hit["filters"]["platform"] == "抖音"
    entry = [e for e in bench_server.call_log_entries() if e["args"] == {"platform": "抖音"}][-1]
    assert entry["product"] == "bench" and entry["tool"] == "bench_search"
    assert entry["ua"] == "v4-harness/1.0" and entry["result_total"] == entry["returned"] == 1
    # bench keeps its v3 result shape (structuredContent plus the text copy).
    raw = bench_server.call("bench_search", {})
    assert raw["structuredContent"]["total"] == 2
