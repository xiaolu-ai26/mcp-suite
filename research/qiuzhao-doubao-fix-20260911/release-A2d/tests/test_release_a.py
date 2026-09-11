"""Release A only: same 13 parameters and the same matching semantics as the live baseline."""
import json

from _mcp_harness import structured

A_PARAMS = {"city", "major", "cohort", "keyword", "company", "recruitment_type", "industry", "region",
            "job_category", "graduation_year", "major_category", "limit", "offset"}


def test_jobs_search_keeps_all_13_parameters(qz):
    props = qz.list_tools()["jobs_search"]["inputSchema"]["properties"]
    assert set(props) == A_PARAMS
    assert all(props[name]["type"] == "string" for name in A_PARAMS - {"limit", "offset"})
    assert props["limit"]["type"] == props["offset"]["type"] == "integer"


def test_job_category_still_substring_match(qz, valid_rows):
    def has(q, values):
        return q.casefold() in json.dumps(values, ensure_ascii=False).casefold()
    expected = sum(1 for r in valid_rows if has("产品", [r.get("job_category_normalized"), r.get("job_category")]))
    assert structured(qz.call("jobs_search", {"job_category": "产品", "limit": 1}))["total"] == expected


def test_legacy_parameters_still_filter(qz):
    out = structured(qz.call("jobs_search", {"cohort": "2027", "region": "北京",
                                             "major_category": "计算机类", "limit": 1}))
    assert out["applied_filters"] == {"cohort": "2027", "region": "北京", "major_category": "计算机类"}
    assert out["total"] > 0
