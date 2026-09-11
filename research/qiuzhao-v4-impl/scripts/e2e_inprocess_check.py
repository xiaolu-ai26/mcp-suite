"""End-to-end check of the installed v4 code without any real key (KIMI-DEPLOY.md step 9).

Runs core.server inside this process (Starlette TestClient, lifespan included) on the live
jobs.json, with a throwaway access DB, distribution DB and call-log directory in one temporary
directory. A temporary key is issued in the throwaway DB; jobs_search and jobs_stats are called
once each through the ASGI app; the replies and the two call-log lines are checked for format.
No key or code is printed. The temporary directory is removed at the end, pass or fail; the
production access DB, distribution DB and call-log directory are never opened.

usage, on the server, from the code root (script via stdin; E2E_TMP defaults to /tmp):
  cd /opt/mcp-suite && runuser -u mcp-suite -- env MCP_JOBS_PATH=/var/lib/mcp-suite/jobs.json \
      nice -n 19 .venv/bin/python -B - < e2e_inprocess_check.py
Success: exit code 0 and the last line "RESULT OK []".
"""
import json
import os
import re
import shutil
import stat
import sys
import tempfile

sys.dont_write_bytecode = True
TMP = tempfile.mkdtemp(prefix="v4-e2e-", dir=os.environ.get("E2E_TMP", "/tmp"))
# Nothing from the caller's environment reaches the app: no admin token, no real DB or log path.
for _name in [k for k in os.environ if k.startswith("MCP_") and k not in ("MCP_JOBS_PATH", "MCP_TODAY")]:
    del os.environ[_name]
os.environ.update(MCP_PRODUCT="qiuzhao", MCP_DB_PATH=os.path.join(TMP, "access.sqlite3"),
                  MCP_DIST_DB_PATH=os.path.join(TMP, "distribution.db"),
                  MCP_CALL_LOG_DIR=os.path.join(TMP, "call_logs"))
os.environ.setdefault("MCP_JOBS_PATH", "/var/lib/mcp-suite/jobs.json")

UA = "v4-e2e-check/1.0"
FIELDS = ["ts", "product", "tool", "args", "ua", "user_ref", "outcome", "error_type", "result_total",
          "returned", "duration_ms"]
HEAD = ["applied_filters", "total", "explicit_total", "inferred_total", "unspecified_total"]
LEVELS = ["明确匹配", "推断匹配", "含未注明"]
RANK = {"岗位写明": 0, "全国": 1, "专业不限": 1, "学历不限": 1, "活动标题写明": 1,
        "按招聘季推断": 2, "来源专场注明": 2, "实习未写届别": 2, "社招不限届别": 2, "未注明": 3, "推断为其他届别": 3}
DIMS = ("city", "major", "education", "graduation_year")
CORE = ("id", "job_title", "company", "job_category", "recruitment_type", "industry", "cities", "region",
        "graduation_years", "graduation_year_basis", "education", "major_category", "deadline",
        "deadline_kind", "status", "published_at", "description_raw", "application_url", "source_url",
        "source_name", "reviewed_at")
CALLS = [("jobs_search", {"city": "成都", "graduation_year": "2027届", "major": "计算机类", "page_size": 5}),
         ("jobs_stats", {"graduation_year": "2027届", "group_by": "city", "top": 3})]
SECRETS = re.compile(r"bearer\s+\S+|\b(?:qz|bm)_[A-Za-z0-9_\-]{16,}|\b(?:QZ|BM)-[0-9A-F]{16,}", re.I)
problems, _secret = [], [""]


def redact(text):
    text = str(text)
    if _secret[0]:
        text = text.replace(_secret[0], "[redacted]")
    return SECRETS.sub("[redacted]", text)


def check(ok, what):
    if not ok:
        problems.append(redact(what)[:300])
    return ok


def check_search(out):
    keys = list(out)
    check(keys[:5] == HEAD and keys[-1] == "jobs", f"search keys {keys}")
    check(out["applied_filters"] == {k: v for k, v in CALLS[0][1].items() if k != "page_size"},
          f"applied_filters {out['applied_filters']}")
    check(out["total"] == out["explicit_total"] + out["inferred_total"] + out["unspecified_total"], "tier sum")
    check(out["returned"] == len(out["jobs"]) <= 5 and out["has_next"] == (out["next_offset"] is not None),
          "paging fields")
    ranks = []
    for job in out["jobs"]:
        match = job.get("match") or {}
        check(set(CORE) <= set(job), f"job {job.get('id')} misses {sorted(set(CORE) - set(job))}")
        check(match.get("level") in LEVELS and {"graduation_year", "city", "major"} <= set(match),
              f"match {match}")
        ranks.append((LEVELS.index(match.get("level", "含未注明")), [RANK.get(match.get(d), 0) for d in DIMS]))
    check(ranks == sorted(ranks), f"order {ranks}")


def check_stats(out):
    keys = list(out)
    check(keys[:5] == HEAD and keys[-1] == "groups", f"stats keys {keys}")
    check((out["group_by"], out["fill_param"], out["multi_valued"]) == ("city", "city", True), "group fields")
    check(len(out["groups"]) == out["returned_groups"] <= 3, "returned_groups")
    for g in out["groups"]:
        check(g["count"] == g["explicit_count"] + g["inferred_count"] + g["unspecified_count"], f"group {g}")


def check_log(replies):
    log_dir = os.environ["MCP_CALL_LOG_DIR"]
    files = sorted(f for f in os.listdir(log_dir) if f.startswith("tool_calls-")) if os.path.isdir(log_dir) else []
    if not check(files, "no call-log file"):
        return
    modes = (oct(stat.S_IMODE(os.stat(log_dir).st_mode)),
             sorted({oct(stat.S_IMODE(os.stat(os.path.join(log_dir, f)).st_mode)) for f in files}))
    check(modes == ("0o700", ["0o600"]), f"call-log modes {modes}")
    text = "".join(open(os.path.join(log_dir, f), encoding="utf-8").read() for f in files)
    check(not (_secret[0] and _secret[0] in text) and not SECRETS.search(text), "call log holds a credential")
    entries = [json.loads(line) for line in text.splitlines()]
    check(len(entries) == len(CALLS), f"{len(entries)} call-log lines")
    for entry, (tool, args), out in zip(entries, CALLS, replies):
        items = out.get("jobs", out.get("groups"))
        check(list(entry) == FIELDS, f"log fields {list(entry)}")
        check((entry["product"], entry["tool"], entry["outcome"], entry["error_type"])
              == ("qiuzhao", tool, "ok", None), f"log {tool} outcome")
        check(entry["args"] == args and entry["ua"] == UA, f"log {tool} args/ua")
        check(re.fullmatch(r"[0-9a-f]{12}", entry["user_ref"] or "") is not None, "log user_ref")
        check(entry["result_total"] == out["total"] and entry["returned"] == len(items), f"log {tool} counts")
        check(type(entry["duration_ms"]) is int and entry["ts"][:2] == "20", f"log {tool} ts/duration")
    if entries:
        print("call log  lines", len(entries), "modes", modes, "last", redact(json.dumps(entries[-1], ensure_ascii=False)))


def main():
    from core.store import Store
    store = Store(os.environ["MCP_DB_PATH"])
    _secret[0] = store.redeem(store.generate_codes(1, "qiuzhao-2026")[0])["api_key"]  # throwaway, never printed
    import core.server as server
    from starlette.testclient import TestClient
    check(str(server.CALL_LOG_DIR).startswith(TMP) and str(server.store.path).startswith(TMP), "paths not temporary")
    headers = {"Authorization": "Bearer " + _secret[0], "User-Agent": UA,
               "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    replies = []
    with TestClient(server.app, base_url="http://127.0.0.1") as client:
        health = client.get("/health").json()
        print("health   ", health)
        for n, (tool, args) in enumerate(CALLS, 1):
            resp = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": n, "method": "tools/call",
                                                            "params": {"name": tool, "arguments": args}})
            check(resp.status_code == 200, f"{tool}: HTTP {resp.status_code}")
            result = resp.json().get("result") or {}
            content = result.get("content") or []
            check(not result.get("isError"), f"{tool}: isError {content[:1]}")
            check(result.get("structuredContent") is None, f"{tool}: structuredContent present")
            check(len(content) == 1 and content[0].get("type") == "text", f"{tool}: not one text item")
            out = json.loads(content[0]["text"])
            check(out.get("data_as_of") == health.get("data_as_of"), f"{tool}: data_as_of")
            replies.append(out)
    check_search(replies[0])
    check_stats(replies[1])
    s, st = replies
    print("search   ", {k: s[k] for k in ("total", "explicit_total", "inferred_total", "unspecified_total",
                                          "excluded_social_total") if k in s})
    for job in s["jobs"]:
        print("          ", job["job_title"][:24], "|", ",".join(job["cities"]), "|", json.dumps(job["match"], ensure_ascii=False))
    print("stats    ", st["total"], [(g["value"], g["count"]) for g in st["groups"]])
    check_log(replies)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # report and still clean up
        problems.append(redact(f"{type(exc).__name__}: {exc}")[:300])
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("tmp removed", not os.path.exists(TMP))
    print("RESULT", "FAIL" if problems else "OK", problems)
    sys.exit(1 if problems else 0)
