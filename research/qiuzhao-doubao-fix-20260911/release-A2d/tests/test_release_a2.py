"""Release A2: structured JSONL call log (argument values, user_ref, outcome, counts).

The log file is the only per-call record. It must never contain the Authorization header,
the key, the redemption code or the internal key id, must keep every line whole under
concurrency, and must never break a tool call when it cannot be written.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from _mcp_harness import JOBS_PATH, RELEASE, TMP, WORKDIR, Server, error_text, structured

FIELDS = {"ts", "product", "tool", "args", "ua", "user_ref", "outcome", "error_type",
          "result_total", "returned", "duration_ms"}
USER_REF_PREFIX = "mcp-suite/user_ref/v1:"  # the documented derivation; must match core.server
HEADER_SENTINEL = "SENTINEL-HDR-7f3a9c"
ANALYZE = WORKDIR / "scripts" / "analyze_call_logs.py"


def key_id(server, token):
    from core.store import Store
    return Store(server.db).authorize(token, server.product)["key_id"]


def test_call_log_line_fields_and_values(qz):
    agent = "TruncUA/1.0 " + "u" * 300
    out = structured(qz.call("jobs_search", {"keyword": "产品", "graduation_year": 2027, "city": None,
                                             "limit": 3}, user_agent=agent))
    entry = [e for e in qz.call_log_entries() if e["ua"].startswith("TruncUA/1.0")][-1]
    assert set(entry) == FIELDS
    assert entry["product"] == "qiuzhao" and entry["tool"] == "jobs_search"
    # Values exactly as the client sent them: int 2027 stays int, null stays null.
    assert entry["args"] == {"keyword": "产品", "graduation_year": 2027, "city": None, "limit": 3}
    assert entry["ua"] == agent[:100] and entry["outcome"] == "ok" and entry["error_type"] is None
    assert entry["result_total"] == out["total"] > 3 and entry["returned"] == len(out["jobs"]) == 3
    assert isinstance(entry["duration_ms"], int) and entry["duration_ms"] >= 0
    ts = datetime.fromisoformat(entry["ts"])
    assert entry["ts"].endswith("+08:00")
    assert f"tool_calls-{ts:%Y%m%d}.jsonl" in {p.name for p in qz.call_log_files()}


def test_overlong_string_is_logged_cut_to_200_even_when_rejected(qz):
    # keyword allows 200 chars, so a longer value is refused by validation; the log still keeps
    # what the client sent, cut to 200 characters.
    keyword = "ARGMARK" + "长" * 300
    error_text(qz.call("jobs_search", {"keyword": keyword, "limit": 1}, user_agent="LongArgUA/1.0"))
    entry = [e for e in qz.call_log_entries() if e["ua"] == "LongArgUA/1.0"][-1]
    assert entry["args"] == {"keyword": keyword[:200], "limit": 1} and len(entry["args"]["keyword"]) == 200
    assert entry["outcome"] == "error" and entry["error_type"] == "invalid_arguments"
    assert entry["result_total"] is None and entry["returned"] is None


def test_call_log_bounds_lists_dicts_and_redacts_pasted_credentials(qz):
    fake_code = "QZ-" + "AB12" * 8
    args = {"keyword": [f"k{i}-" + "v" * 300 for i in range(30)],
            "city": {f"c{i}": i for i in range(30)},
            "company": f"见 {qz.token} 或 Bearer abc.def 或 {fake_code.lower()}",
            "api_key": "anything", "limit": 1}
    error_text(qz.call("jobs_search", args, user_agent="BoundsUA/1.0"))
    entry = [e for e in qz.call_log_entries() if e["ua"] == "BoundsUA/1.0"][-1]
    assert entry["outcome"] == "error" and entry["error_type"] == "invalid_arguments"
    assert entry["result_total"] is None and entry["returned"] is None
    keyword = entry["args"]["keyword"]
    assert len(keyword) == 21 and keyword[-1] == "…(+10)" and all(len(v) == 200 for v in keyword[:20])
    assert len(entry["args"]["city"]) == 21 and entry["args"]["city"]["…"] == "+10"
    assert entry["args"]["api_key"] == "[redacted]"
    assert entry["args"]["company"] == "见 [redacted] 或 [redacted] 或 [redacted]"
    text = qz.call_log_text() + qz.log_text()
    assert qz.token not in text and fake_code not in text.upper() and "abc.def" not in text
    assert "Bearer" not in text


def test_call_log_has_no_credentials_and_private_modes(qz):
    from core.store import digest
    structured(qz.call("jobs_search", {"limit": 1},
                       headers={"X-Api-Key": HEADER_SENTINEL, "Cookie": f"sid={HEADER_SENTINEL}"}))
    text = qz.call_log_text() + qz.log_text()
    for secret in (qz.token, qz.code, key_id(qz, qz.token), digest(qz.token), HEADER_SENTINEL, "Bearer"):
        assert secret not in text
    assert stat.S_IMODE(qz.call_log_dir.stat().st_mode) == 0o700
    assert qz.call_log_files() and all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in qz.call_log_files())


def test_user_ref_stable_distinct_and_not_a_credential(qz):
    code2, token2 = qz.new_key()
    for token, agent in ((qz.token, "RefUA/a1"), (qz.token, "RefUA/a2"), (token2, "RefUA/b1")):
        structured(qz.call("jobs_search", {"limit": 1}, user_agent=agent, token=token))
    entries = {e["ua"]: e for e in qz.call_log_entries() if e["ua"].startswith("RefUA/")}
    refs = {agent: e["user_ref"] for agent, e in entries.items()}
    assert refs["RefUA/a1"] == refs["RefUA/a2"] != refs["RefUA/b1"]
    assert all(e["result_total"] > 1 and e["returned"] == 1 for e in entries.values())
    for token, agent in ((qz.token, "RefUA/a1"), (token2, "RefUA/b1")):
        internal = key_id(qz, token)
        assert refs[agent] == hashlib.sha256((USER_REF_PREFIX + internal).encode()).hexdigest()[:12]
        assert re.fullmatch(r"[0-9a-f]{12}", refs[agent])
        # The internal key id is not a credential: presenting it as the Bearer key is refused.
        with httpx.Client(trust_env=False, timeout=30) as http:
            response = http.post(qz.base + "/mcp", json={"jsonrpc": "2.0", "id": "x", "method": "tools/list"},
                                 headers={"Authorization": f"Bearer {internal}",
                                          "Accept": "application/json, text/event-stream"})
        assert response.status_code == 401
    text = qz.call_log_text()
    assert token2 not in text and code2 not in text


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory modes")
def test_unwritable_log_dir_keeps_calls_working():
    locked = TMP / f"locked-call-logs-{uuid.uuid4().hex[:8]}"
    locked.mkdir(parents=True)
    locked.chmod(0o500)
    server = Server("qiuzhao", call_log_dir=locked, label=f"{RELEASE.name}-qiuzhao-unwritable-logdir")
    try:
        server.start()
        for _ in range(2):
            out = structured(server.call("jobs_search", {"keyword": "产品", "limit": 1}))
            assert out["total"] > 0 and len(out["jobs"]) == 1
        warnings = [line for line in server.log_text().splitlines() if line.startswith("mcp_call_log_warning ")]
        assert len(warnings) == 1  # warned once, not per call
        assert json.loads(warnings[0].split(" ", 1)[1])["error"] == "PermissionError"
        assert list(locked.iterdir()) == []
    finally:
        server.stop()
        locked.chmod(0o700)
        shutil.rmtree(locked, ignore_errors=True)


def test_concurrent_http_calls_write_whole_lines(bench_server):
    words = [f"并发{i:02d}-" + "长" * 90 for i in range(32)]  # bench keyword allows 100 chars
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda w: bench_server.call("bench_search", {"keyword": w},
                                                             user_agent="ConcurrentUA/1.0"), words))
    assert not any(r.get("isError") for r in results)
    entries = [json.loads(line) for line in bench_server.call_log_text().splitlines()]  # every line whole
    hits = [e for e in entries if e["ua"] == "ConcurrentUA/1.0"]
    assert sorted(e["args"]["keyword"] for e in hits) == sorted(words)


@pytest.fixture(scope="module")
def server_module():
    """Import core.server in-process against throwaway paths (no uvicorn, no HTTP)."""
    TMP.mkdir(exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    env = {"MCP_PRODUCT": "qiuzhao", "MCP_DB_PATH": str(TMP / f"inproc-{tag}.sqlite3"),
           "MCP_DIST_DB_PATH": str(TMP / f"inproc-dist-{tag}.db"), "MCP_JOBS_PATH": str(JOBS_PATH),
           "MCP_CALL_LOG_DIR": str(TMP / f"inproc-call_logs-{tag}")}
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        yield importlib.import_module("core.server")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for suffix in ("", "-wal", "-shm"):
            Path(env["MCP_DB_PATH"] + suffix).unlink(missing_ok=True)
        Path(env["MCP_DIST_DB_PATH"]).unlink(missing_ok=True)
        shutil.rmtree(env["MCP_CALL_LOG_DIR"], ignore_errors=True)


def test_threaded_writes_keep_long_lines_whole(server_module, tmp_path):
    big = {f"p{i:02d}": "并" * 50 for i in range(40)}  # ~6 KB per line, far above PIPE_BUF

    def worker(n):
        for j in range(100):
            entry = {"ts": "2026-09-11T12:00:00.000+08:00", "product": "qiuzhao", "tool": "jobs_search",
                     "args": dict(big, id=f"{n}-{j}"), "ua": "", "user_ref": None, "outcome": "ok",
                     "error_type": None, "result_total": None, "returned": None, "duration_ms": 0}
            assert server_module.write_call_log(entry, tmp_path)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(worker, range(16)))
    lines = (tmp_path / "tool_calls-20260911.jsonl").read_text(encoding="utf-8").splitlines()
    ids = sorted(json.loads(line)["args"]["id"] for line in lines)
    assert ids == sorted(f"{n}-{j}" for n in range(16) for j in range(100))


def test_value_bounds_and_line_cap(server_module, tmp_path):
    s = server_module
    assert s._log_value("x" * 500) == "x" * 200
    assert s._log_value(2**70) == "<int>" and s._log_value(float("nan")) == "nan"
    assert s._log_value([[["deep"]], {"k": {"d": 1}}]) == [["<list>"], {"k": "<dict>"}]
    assert s._log_args({"Authorization": "x", "q": "Bearer abc"}) == {"Authorization": "[redacted]",
                                                                      "q": "[redacted]"}
    # 40 arguments x 20 items x 200 chars would be ~160k chars: each value degrades to <=200 chars.
    huge = {f"a{i:02d}": s._log_value(["y" * 300] * 25) for i in range(40)}
    entry = {"ts": "2026-09-11T12:00:00.000+08:00", "args": huge}
    assert s.write_call_log(entry, tmp_path)
    line = (tmp_path / "tool_calls-20260911.jsonl").read_text(encoding="utf-8")
    assert len(line) <= s.LOG_LINE_MAX
    assert all(isinstance(v, str) and len(v) <= 200 for v in json.loads(line)["args"].values())


def test_analyze_script_reports_repeats_and_zero_results(bench_server):
    for _ in range(3):
        structured(bench_server.call("bench_search", {"topic": "不存在的分类"}, user_agent="LoopUA/1.0"))
    out = subprocess.run([sys.executable, str(ANALYZE), str(bench_server.call_log_dir), "--json"],
                         capture_output=True, text=True, check=True)
    report = json.loads(out.stdout)
    loop = [g for g in report["repeats"]["groups"] if g["args"] == {"topic": "不存在的分类"}]
    assert len(loop) == 1 and loop[0]["repeats"] == 2 and loop[0]["tool"] == "bench_search"
    assert report["by_ua"]["LoopUA/1.0"] == 3 and report["bad_lines"] == 0
    assert report["zero_results"]["by_tool"]["bench/bench_search"]["zero"] >= 3
    assert report["top_values"]["bench/bench_search"]["topic"][0] == ["不存在的分类", 3]
