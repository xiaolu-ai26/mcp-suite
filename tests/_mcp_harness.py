"""Run core.server under uvicorn in a subprocess and speak MCP JSON-RPC to it over HTTP.

Ported from research/qiuzhao-doubao-fix-20260911/release-A2/tests/_mcp_harness.py. Everything
the harness creates (access DB, distribution DB, uvicorn log, call-log directory) lives under
research/qiuzhao-v4-impl/tmp and is deleted on stop; the uvicorn log and the call-log files are
copied to research/qiuzhao-v4-impl/evidence/ first so the receipt can quote real lines. Never
touches a production DB, data file or log directory.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

RELEASE = Path(__file__).resolve().parents[1]           # the code tree under test
WORKDIR = RELEASE / "research" / "qiuzhao-v4-impl"
TMP = WORKDIR / "tmp"
EVIDENCE = WORKDIR / "evidence" / "pytest"
JOBS_PATH = Path(os.environ.get("MCP_JOBS_PATH", RELEASE / "qiuzhao" / "data" / "jobs.json"))
TODAY = os.environ.get("MCP_TODAY", "2026-09-11")        # the day jobs.json was pulled
USER_AGENT = "v4-harness/1.0"
INIT_PARAMS = {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "v4-harness", "version": "1.0"}}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def issue_key(db_path: Path, plan: str) -> tuple[str, str]:
    """Redeem a fresh code in a throwaway DB; return (redemption code, api key).

    store.py on main inserts redemption_codes.code_plain but its CREATE TABLE lacks the column,
    so a fresh DB needs it added here (a no-op once store.py migrates it itself).
    """
    from core.store import Store
    store = Store(db_path)
    with store.connect() as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(redemption_codes)")}
        if "code_plain" not in columns:
            db.execute("ALTER TABLE redemption_codes ADD COLUMN code_plain TEXT")
    code = store.generate_codes(1, plan)[0]
    return code, store.redeem(code)["api_key"]


def payload(result: dict) -> dict:
    """The tool's result object: structuredContent (bench) or the single JSON text (qiuzhao)."""
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    assert len(result["content"]) == 1 and result["content"][0]["type"] == "text", result["content"]
    return json.loads(result["content"][0]["text"])


def structured(result: dict) -> dict:
    assert not result.get("isError"), result["content"][0]["text"][:800]
    return payload(result)


def error_text(result: dict) -> str:
    assert result.get("isError"), "expected a tool error"
    return result["content"][0]["text"]


class Server:
    def __init__(self, product: str = "qiuzhao", bench_path: Path | None = None,
                 call_log_dir: Path | None = None, label: str | None = None, env: dict | None = None):
        self.product = product
        self.bench_path = bench_path
        self.label = label or product
        self._given_call_log_dir = call_log_dir
        self._extra_env = env or {}
        self.proc = None
        self._log = None

    @property
    def plan(self) -> str:
        return "qiuzhao-2026" if self.product == "qiuzhao" else "bench-monthly"

    def start(self) -> "Server":
        TMP.mkdir(parents=True, exist_ok=True)
        tag = f"{self.product}-{uuid.uuid4().hex[:8]}"
        self.db = TMP / f"access-{tag}.sqlite3"
        self.dist_db = TMP / f"dist-{tag}.db"
        self.log_path = TMP / f"uvicorn-{tag}.log"
        # Not created here: the server must create it itself (mode 700) on the first call.
        self.call_log_dir = Path(self._given_call_log_dir or TMP / f"call_logs-{tag}")
        self.code, self.token = issue_key(self.db, self.plan)
        env = {k: v for k, v in os.environ.items() if not k.startswith("MCP_")}
        env.update(MCP_PRODUCT=self.product, MCP_DB_PATH=str(self.db), MCP_DIST_DB_PATH=str(self.dist_db),
                   MCP_JOBS_PATH=str(JOBS_PATH), MCP_CALL_LOG_DIR=str(self.call_log_dir), MCP_TODAY=TODAY,
                   PYTHONUNBUFFERED="1", PYTHONWARNINGS="ignore", PYTHONDONTWRITEBYTECODE="1")
        if self.bench_path:
            env["MCP_BENCH_PATH"] = str(self.bench_path)
        env.update(self._extra_env)
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self._log = open(self.log_path, "wb")
        # Same entrypoint shape as mcp-suite.service: uvicorn core.server:app --no-access-log
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "core.server:app", "--host", "127.0.0.1",
             "--port", str(self.port), "--no-access-log"],
            cwd=RELEASE, env=env, stdout=self._log, stderr=subprocess.STDOUT)
        deadline = time.time() + 90
        with httpx.Client(trust_env=False, timeout=30) as http:
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    raise RuntimeError("uvicorn exited:\n" + self.log_text()[-3000:])
                try:
                    if http.get(self.base + "/config").status_code == 200:
                        return self
                except httpx.HTTPError:
                    pass
                time.sleep(0.3)
        raise RuntimeError("uvicorn did not start in time")

    def new_key(self) -> tuple[str, str]:
        """A second, independent key in the same throwaway DB the server reads."""
        return issue_key(self.db, self.plan)

    def log_text(self) -> str:
        if self._log and not self._log.closed:
            self._log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def call_log_files(self) -> list[Path]:
        return sorted(self.call_log_dir.glob("tool_calls-*.jsonl")) if self.call_log_dir.is_dir() else []

    def call_log_text(self) -> str:
        return "".join(path.read_text(encoding="utf-8") for path in self.call_log_files())

    def call_log_entries(self) -> list[dict]:
        return [json.loads(line) for line in self.call_log_text().splitlines()]

    def rpc(self, method: str, params: dict | None = None, user_agent: str = USER_AGENT,
            raw: bool = False, token: str | None = None, headers: dict | None = None):
        body = {"jsonrpc": "2.0", "id": uuid.uuid4().hex[:8], "method": method}
        if params is not None:
            body["params"] = params
        request_headers = {"Authorization": f"Bearer {token or self.token}", "User-Agent": user_agent,
                           "Accept": "application/json, text/event-stream",
                           "Content-Type": "application/json", **(headers or {})}
        with httpx.Client(trust_env=False, timeout=180) as http:
            response = http.post(self.base + "/mcp", json=body, headers=request_headers)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        return (data["result"], response.content) if raw else data["result"]

    def initialize(self) -> dict:
        return self.rpc("initialize", INIT_PARAMS)

    def list_tools(self) -> dict:
        return {tool["name"]: tool for tool in self.rpc("tools/list")["tools"]}

    def call(self, name: str, arguments: dict | None = None, user_agent: str = USER_AGENT,
             raw: bool = False, token: str | None = None, headers: dict | None = None):
        return self.rpc("tools/call", {"name": name, "arguments": arguments or {}},
                        user_agent=user_agent, raw=raw, token=token, headers=headers)

    def out(self, name: str, arguments: dict | None = None, **kw) -> dict:
        return structured(self.call(name, arguments, **kw))

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if self._log:
            self._log.close()
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists():
            shutil.copy(self.log_path, EVIDENCE / f"uvicorn-{self.label}.log")
            self.log_path.unlink()
        files = self.call_log_files()
        if files:
            target = EVIDENCE / f"call_logs-{self.label}"
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True)
            for path in files:
                shutil.copy(path, target / path.name)
        if self._given_call_log_dir is None:
            shutil.rmtree(self.call_log_dir, ignore_errors=True)
        for path in (self.db, Path(f"{self.db}-wal"), Path(f"{self.db}-shm"), self.dist_db):
            path.unlink(missing_ok=True)
