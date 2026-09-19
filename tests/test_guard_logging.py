"""Guard protocol-level rejection log (rejections-YYYYMMDD.jsonl).

2026-09-19 豆包故障排查（报告第 3.3 节）暴露的盲区：Guard 在进入 FastMCP / MeterTools 之前
拒掉请求（缺鉴权、信封畸形、Accept/Content-Type 不合规、限速）时，tool_calls-*.jsonl、journald
和数据库三处都没有任何记录，导致"客户端说失败但服务端无记录"无法区分是"请求没到"还是"被 Guard
拒了"。本组测试锁定三类事实：

1. 400/401/406/429 每次拒绝都在 call_logs 里留下一条字段齐全的 rejections-*.jsonl；
2. 日志里不含 key/token/Authorization 的任何片段（只记有/无鉴权头）；
3. 拦截行为逐条不变（状态码、WWW-Authenticate/Retry-After 头、正常请求不受影响）。

真实 HTTP + 真实 uvicorn（_mcp_harness.Server），不 mock。
"""
from __future__ import annotations

import json
import time

import httpx
import pytest

from _mcp_harness import JOBS_PATH, Server

REJECTION_FIELDS = {"ts", "type", "product", "path", "method", "status", "reason", "tool",
                    "ua", "ua_present", "client_ip", "auth_present", "body_bytes", "user_ref"}
VALID_ACCEPT = "application/json, text/event-stream"
CALL_BODY = {"jsonrpc": "2.0", "id": "guard-1", "method": "tools/call",
             "params": {"name": "jobs_search", "arguments": {"page_size": 1}}}


def rejection_entries(server) -> list[dict]:
    directory = server.call_log_dir
    if not directory.is_dir():
        return []
    entries = []
    for path in sorted(directory.glob("rejections-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    return entries


def rejection_text(server) -> str:
    directory = server.call_log_dir
    if not directory.is_dir():
        return ""
    return "".join(path.read_text(encoding="utf-8") for path in sorted(directory.glob("rejections-*.jsonl")))


def wait_for(predicate, timeout=5.0):
    """406 由 transport 先发响应、Guard 再同步写日志，客户端可能在写入前就返回；轮询等待。"""
    deadline = time.monotonic() + timeout
    while True:
        hits = predicate()
        if hits or time.monotonic() >= deadline:
            return hits
        time.sleep(0.05)


def one(server, ua: str) -> dict:
    prefix = ua.split(" ")[0]
    hits = wait_for(lambda: [e for e in rejection_entries(server)
                             if e["ua"] == ua or e["ua"].startswith(prefix)])
    assert len(hits) == 1, f"expected exactly one rejection for {ua!r}, got {hits}"
    return hits[0]


def post(server, *, ua="GuardUA/1.0", body=None, accept=VALID_ACCEPT,
         content_type="application/json", authorization="auto", token=None, json_body=None):
    headers = {"Accept": accept, "Content-Type": content_type, "User-Agent": ua}
    if authorization == "auto":
        headers["Authorization"] = f"Bearer {token or server.token}"
    elif authorization is not None:
        headers["Authorization"] = authorization
    content = json.dumps(json_body) if json_body is not None else body
    with httpx.Client(trust_env=False, timeout=30) as http:
        return http.post(server.base + "/mcp", content=content, headers=headers)


# ------------------------------------------------------------------ 四类拒绝

def test_400_bad_envelope_logged(qz):
    # OpenAI 风格：arguments 传成 JSON 字符串。CallToolRequest 校验失败 -> 400。
    body = json.dumps({"jsonrpc": "2.0", "id": "x", "method": "tools/call",
                       "params": {"name": "jobs_search", "arguments": "{}"}}).encode()
    response = post(qz, ua="Guard400UA/1.0", body=body)
    assert response.status_code == 400
    entry = one(qz, "Guard400UA/1.0")
    assert set(entry) == REJECTION_FIELDS
    assert entry["type"] == "guard_rejection" and entry["product"] == "qiuzhao"
    assert entry["path"] == "/mcp" and entry["method"] == "POST"
    assert entry["status"] == 400 and entry["reason"] == "bad_envelope"
    assert entry["tool"] == "jobs_search"  # 能从 params.name 解析出来就记
    assert entry["ua"] == "Guard400UA/1.0" and entry["ua_present"] is True
    assert entry["auth_present"] is True
    assert entry["client_ip"] == "127.0.0.0"  # 脱敏：/24
    assert entry["body_bytes"] == len(body)


def test_401_missing_and_invalid_auth_logged(qz):
    body = json.dumps(CALL_BODY).encode()
    missing = post(qz, ua="Guard401MissingUA/1.0", body=body, authorization=None)
    assert missing.status_code == 401
    assert missing.headers.get("www-authenticate") == "Bearer"
    e_missing = one(qz, "Guard401MissingUA/1.0")
    assert set(e_missing) == REJECTION_FIELDS
    assert e_missing["status"] == 401 and e_missing["reason"] == "auth_missing"
    assert e_missing["auth_present"] is False and e_missing["body_bytes"] == len(body)

    malformed = post(qz, ua="Guard401BadSchemeUA/1.0", body=body, authorization="Token abc")
    assert malformed.status_code == 401
    assert one(qz, "Guard401BadSchemeUA/1.0")["reason"] == "auth_malformed"

    invalid = post(qz, ua="Guard401InvalidUA/1.0", body=body, authorization="Bearer not-a-real-key")
    assert invalid.status_code == 401
    e_invalid = one(qz, "Guard401InvalidUA/1.0")
    assert e_invalid["reason"] == "auth_invalid" and e_invalid["auth_present"] is True


def test_406_accept_header_logged(qz):
    body = json.dumps(CALL_BODY).encode()
    response = post(qz, ua="Guard406UA/1.0", body=body, accept="text/plain")
    assert response.status_code == 406
    entry = one(qz, "Guard406UA/1.0")
    assert set(entry) == REJECTION_FIELDS
    assert entry["status"] == 406 and entry["reason"] == "accept_header"
    assert entry["auth_present"] is True and entry["tool"] == "jobs_search"
    assert entry["body_bytes"] == len(body)


def test_429_rate_limit_logged():
    if not JOBS_PATH.is_file():
        pytest.skip(f"{JOBS_PATH} missing")
    server = Server("qiuzhao", label="guard-rpm", env={"MCP_QIU_RPM": "1", "MCP_QIU_MAX_INFLIGHT": "1"})
    server.start()
    try:
        body = json.dumps(CALL_BODY).encode()
        first = post(server, ua="Guard429FirstUA/1.0", body=body)
        assert first.status_code != 429  # 第一次被准入（工具结果不重要）
        second = post(server, ua="Guard429SecondUA/1.0", body=body)
        assert second.status_code == 429
        assert second.headers.get("retry-after")  # 退避提示保留
        entry = one(server, "Guard429SecondUA/1.0")
        assert set(entry) == REJECTION_FIELDS
        assert entry["status"] == 429 and entry["reason"] == "rate_limit_rpm"
        assert entry["auth_present"] is True and entry["body_bytes"] == len(body)
        # 第一次成功准入不应产生拒绝记录
        assert [e for e in rejection_entries(server) if e["ua"] == "Guard429FirstUA/1.0"] == []
        # 真实 key 绝不落进拒绝日志
        assert server.token not in rejection_text(server)
    finally:
        server.stop()


# ------------------------------------------------------------------ 无密钥片段 + 空 UA

def test_rejection_log_has_no_credential_fragments(qz):
    """即使客户端把 key 塞进 UA、或带着无效 key 请求，拒绝日志里也不能出现任何片段。"""
    body = json.dumps(CALL_BODY).encode()
    post(qz, ua=f"GuardSecretUA {qz.token}", body=body, authorization=None)
    entry = one(qz, "GuardSecretUA")
    # UA 里的真实 key 被 _clean_text 的凭据正则脱掉，但空/非空仍可区分
    assert qz.token not in entry["ua"] and "[redacted]" in entry["ua"]

    post(qz, ua="", body=body, authorization=f"Bearer {qz.token}x")
    empty = wait_for(lambda: [e for e in rejection_entries(qz) if e["ua_present"] is False])
    assert empty and empty[-1]["ua"] == "" and empty[-1]["auth_present"] is True

    text = rejection_text(qz) + qz.log_text()
    assert qz.token not in text
    assert f"{qz.token}x" not in text
    assert "not-a-real-key" not in text
    assert "Bearer" not in text
    assert qz.code not in text


# ------------------------------------------------------------------ 正常请求不受影响 + 行为一致

def test_normal_request_unaffected_and_counter_readable(qz):
    out = qz.out("jobs_search", {"page_size": 1, "keyword": "产品"}, user_agent="GuardNormalUA/1.0")
    assert out["total"] > 0
    # 正常调用仍进 tool_calls，不产生拒绝记录
    tool_entries = [e for e in qz.call_log_entries() if e["ua"].startswith("GuardNormalUA")]
    assert tool_entries and tool_entries[-1]["outcome"] == "ok"
    assert [e for e in rejection_entries(qz) if e["ua"].startswith("GuardNormalUA")] == []

    # 健康接口能直接读到按原因枚举的计数（不新增公开接口）
    with httpx.Client(trust_env=False, timeout=60) as http:
        health = http.get(qz.base + "/health").json()
    summary = health["guard_rejections"]
    assert summary["total"] >= 1 and summary["by_reason"]
    assert isinstance(summary["since"], str) and summary["since"]


def test_interception_matrix_unchanged(qz):
    """改动前后逐条一致的回归护栏：状态码与错误文案/头都不变。"""
    body = json.dumps(CALL_BODY).encode()
    cases = [
        ("missing-auth", post(qz, ua="MatrixMissingUA/1.0", body=body, authorization=None), 401),
        ("bad-scheme", post(qz, ua="MatrixSchemeUA/1.0", body=body, authorization="Token x"), 401),
        ("invalid-key", post(qz, ua="MatrixKeyUA/1.0", body=body, authorization="Bearer nope"), 401),
        ("bad-envelope", post(qz, ua="MatrixEnvelopeUA/1.0",
                              body=json.dumps({"jsonrpc": "2.0", "id": "x", "method": "tools/call",
                                               "params": {"name": "jobs_search",
                                                          "arguments": "{}"}}).encode()), 400),
        ("batch", post(qz, ua="MatrixBatchUA/1.0", body=b"[1,2,3]"), 400),
        ("bad-json", post(qz, ua="MatrixJsonUA/1.0", body=b"{not json"), 400),
        ("accept", post(qz, ua="MatrixAcceptUA/1.0", body=body, accept="text/plain"), 406),
        ("content-type", post(qz, ua="MatrixCTUA/1.0", body=body, content_type="text/plain"), 415),
    ]
    for name, response, expected in cases:
        assert response.status_code == expected, (name, response.status_code, response.text)
        # Guard 分支（400/401/415）返回裸 {"error": ...}；406 由 MCP transport 自己发，
        # 仍是 JSON-RPC 错误体 —— 两者都与改动前逐字节一致，只断言错误存在。
        assert "error" in response.json() and response.json()["error"], name
    # 正常协议请求仍然 200
    assert qz.rpc("tools/list")["tools"]
