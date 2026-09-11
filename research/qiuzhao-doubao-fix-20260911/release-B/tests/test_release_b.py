"""Release B only: 10 parameters, exact normalized matching, legacy names mapped in middleware."""
import json

from _mcp_harness import error_text, structured

B_PARAMS = {"city", "major", "keyword", "company", "recruitment_type", "industry",
            "job_category", "graduation_year", "limit", "offset"}


def has(query, values):
    return query.casefold() in json.dumps(values, ensure_ascii=False).casefold()


def test_jobs_search_has_10_parameters(qz):
    tool = qz.list_tools()["jobs_search"]
    assert set(tool["inputSchema"]["properties"]) == B_PARAMS
    assert "找某类岗位用 job_category，找具体岗位名或单位用 keyword，找公司用 company" in tool["description"]
    assert "计算机类" in tool["inputSchema"]["properties"]["major"]["description"]


def test_job_category_exact_on_normalized_field(qz, valid_rows):
    for category in ("产品", "技术/研发"):
        expected = sum(1 for r in valid_rows if r["job_category_normalized"] == category)
        out = structured(qz.call("jobs_search", {"job_category": category, "limit": 20}))
        assert out["total"] == expected, category
        assert all(job["job_category_normalized"] == category for job in out["jobs"])


def test_graduation_year_exact_on_normalized_field(qz, valid_rows):
    expected = sum(1 for r in valid_rows if r["graduation_year_normalized"] == "2027届")
    out = structured(qz.call("jobs_search", {"graduation_year": "2027", "limit": 1}))
    assert out["total"] == expected and out["applied_filters"] == {"graduation_year": "2027届"}


def test_major_also_matches_normalized_category(qz, valid_rows):
    fields = ("major_requirements_raw", "major_tags", "major_normalized")
    expected = sum(1 for r in valid_rows if has("计算机类", [r.get(f) for f in fields]))
    assert structured(qz.call("jobs_search", {"major": "计算机类", "limit": 1}))["total"] == expected
    assert expected >= sum(1 for r in valid_rows if r["major_normalized"] == "计算机类")


def test_legacy_names_map_to_new_parameters(qz):
    pairs = [({"cohort": "2027"}, {"graduation_year": "2027届"}),
             ({"region": "北京"}, {"city": "北京"}),
             ({"major_category": "计算机类"}, {"major": "计算机类"})]
    for legacy, modern in pairs:
        old = structured(qz.call("jobs_search", {**legacy, "limit": 1}))
        new = structured(qz.call("jobs_search", {**modern, "limit": 1}))
        assert old["applied_filters"] == modern and old["total"] == new["total"], legacy
    entries = qz.log_entries("mcp_legacy_args")
    assert {"tool": "jobs_search", "mapped": {"cohort": "graduation_year"}, "ignored": []} in entries
    assert {"tool": "jobs_search", "mapped": {"region": "city"}, "ignored": []} in entries
    assert {"tool": "jobs_search", "mapped": {"major_category": "major"}, "ignored": []} in entries


def test_legacy_name_ignored_when_new_one_given(qz):
    out = structured(qz.call("jobs_search", {"city": "上海", "region": "北京", "cohort": None, "limit": 1}))
    assert out["applied_filters"] == {"city": "上海"}
    entry = qz.log_entries("mcp_legacy_args")[-1]
    assert entry == {"tool": "jobs_search", "mapped": {}, "ignored": ["cohort", "region"]}
    assert "北京" not in qz.log_text() and "上海" not in qz.log_text()


def test_unmappable_legacy_value_fails_loudly(qz):
    # cohort used to be free text; a value that is not a cohort must not silently turn into "no filter".
    assert "graduation_year" in error_text(qz.call("jobs_search", {"cohort": "2027届校园招聘"}))


def test_unknown_parameter_is_rejected_by_fastmcp(qz):
    # What an unmapped legacy name would hit: FastMCP 2.14.7 refuses unknown names, it does not ignore them.
    assert "Unexpected keyword argument" in error_text(qz.call("jobs_search", {"not_a_param": "x"}))
