"""Release A2d: jobs_deadlines returns the nearest deadlines first, 10 per page by default.

Which rows are included (deadline_type == "explicit", valid status, within N days) is unchanged.
"""
from datetime import date, datetime, timedelta

from core.store import TZ
from _mcp_harness import structured


def eligible(valid_rows, days=7):
    """Same inclusion rule as Jobs.deadlines(); used to check total and the nearest date."""
    today = datetime.now(TZ).date()
    selected = []
    for row in valid_rows:
        if row.get("deadline_type") != "explicit" or row.get("status") in {"removed", "expired", "unverified"}:
            continue
        try:
            deadline = date.fromisoformat((row.get("deadline") or "")[:10])
        except ValueError:
            continue
        if today <= deadline <= today + timedelta(days=days):
            selected.append(row)
    return selected


def test_deadlines_schema_default_limit_and_description(qz):
    tool = qz.list_tools()["jobs_deadlines"]
    limit = tool["inputSchema"]["properties"]["limit"]
    assert limit["default"] == 10 and limit["maximum"] == 100
    assert "从近到远" in tool["description"] and "倒排" not in tool["description"]


def test_deadlines_default_returns_ten_nearest_first(qz, valid_rows):
    out = structured(qz.call("jobs_deadlines", {}))
    rows = eligible(valid_rows)
    days = [job["deadline"][:10] for job in out["jobs"]]
    assert len(out["jobs"]) == 10 and out["order"] == "deadline_asc" and out["total"] == len(rows)
    assert days[0] <= days[-1] and days == sorted(days)
    # The first row closes on the nearest date in the window: today whenever anything closes today.
    assert days[0] == min(row["deadline"][:10] for row in rows)
    entry = [e for e in qz.call_log_entries() if e["tool"] == "jobs_deadlines"][-1]
    assert entry["args"] == {} and entry["returned"] == 10 and entry["result_total"] == out["total"]


def test_deadlines_pages_are_contiguous(qz):
    first = structured(qz.call("jobs_deadlines", {"offset": 0}))
    second = structured(qz.call("jobs_deadlines", {"offset": 10}))
    both = structured(qz.call("jobs_deadlines", {"limit": 20}))
    assert first["next_offset"] == 10
    assert first["jobs"] + second["jobs"] == both["jobs"]
    assert first["jobs"][-1]["deadline"][:10] <= second["jobs"][0]["deadline"][:10]
