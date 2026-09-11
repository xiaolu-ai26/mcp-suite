"""Run core.server under uvicorn in a subprocess and speak MCP JSON-RPC to it over HTTP.

Everything the harness creates (access DB, distribution DB, uvicorn log) lives under
<workdir>/tmp and is deleted on stop; the uvicorn log is copied to <workdir>/evidence first
so the receipt can quote real log lines. Never touches a production DB or data file.
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

RELEASE = Path(__file__).resolve().parents[1]
WORKDIR = RELEASE.parent
TMP = WORKDIR / "tmp"
EVIDENCE = WORKDIR / "evidence"
JOBS_PATH = Path(os.environ.get("MCP_JOBS_PATH", WORKDIR / "data" / "jobs.json"))
USER_AGENT = "doubao-fix-harness/1.0"
INIT_PARAMS = {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "doubao-fix-harness", "version": "1.0"}}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def issue_key(db_path: Path, plan: str) -> str:
    """Redeem a fresh code in a throwaway DB.

    The live store.py inserts redemption_codes.code_plain, but its CREATE TABLE lacks that
    column (it was added to the production DB by hand), so a fresh DB needs it added here.
    """
    from core.store import Store
    store = Store(db_path)
    with store.connect() as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(redemption_codes)")}
        if "code_plain" not in columns:
            db.execute("ALTER TABLE redemption_codes ADD COLUMN code_plain TEXT")
    return store.redeem(store.generate_codes(1, plan)[0])["api_key"]


def structured(result: dict) -> dict:
    assert not result.get("isError"), result["content"][0]["text"][:800]
    return result["structuredContent"]


def error_text(result: dict) -> str:
    assert result.get("isError"), "expected a tool error"
    return result["content"][0]["text"]


class Server:
    def __init__(self, product: str = "qiuzhao", bench_path: Path | None = None):
        self.product = product
        self.bench_path = bench_path
        self.proc = None
        self._log = None

    def start(self) -> "Server":
        TMP.mkdir(exist_ok=True)
        tag = f"{RELEASE.name}-{self.product}-{uuid.uuid4().hex[:8]}"
        self.db = TMP / f"access-{tag}.sqlite3"
        self.dist_db = TMP / f"dist-{tag}.db"
        self.log_path = TMP / f"uvicorn-{tag}.log"
        self.token = issue_key(self.db, "qiuzhao-2026" if self.product == "qiuzhao" else "bench-monthly")
        env = {k: v for k, v in os.environ.items() if not k.startswith("MCP_")}
        env.update(MCP_PRODUCT=self.product, MCP_DB_PATH=str(self.db), MCP_DIST_DB_PATH=str(self.dist_db),
                   MCP_JOBS_PATH=str(JOBS_PATH), PYTHONUNBUFFERED="1", PYTHONWARNINGS="ignore")
        if self.bench_path:
            env["MCP_BENCH_PATH"] = str(self.bench_path)
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

    def log_text(self) -> str:
        if self._log and not self._log.closed:
            self._log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def log_entries(self, prefix: str) -> list[dict]:
        marker = prefix + " "
        return [json.loads(line[len(marker):]) for line in self.log_text().splitlines()
                if line.startswith(marker)]

    def rpc(self, method: str, params: dict | None = None, user_agent: str = USER_AGENT,
            raw: bool = False):
        body = {"jsonrpc": "2.0", "id": uuid.uuid4().hex[:8], "method": method}
        if params is not None:
            body["params"] = params
        headers = {"Authorization": f"Bearer {self.token}", "User-Agent": user_agent,
                   "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        with httpx.Client(trust_env=False, timeout=180) as http:
            response = http.post(self.base + "/mcp", json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return (payload["result"], response.content) if raw else payload["result"]

    def initialize(self) -> dict:
        return self.rpc("initialize", INIT_PARAMS)

    def list_tools(self) -> dict:
        return {tool["name"]: tool for tool in self.rpc("tools/list")["tools"]}

    def call(self, name: str, arguments: dict | None = None, user_agent: str = USER_AGENT,
             raw: bool = False):
        return self.rpc("tools/call", {"name": name, "arguments": arguments or {}},
                        user_agent=user_agent, raw=raw)

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
        EVIDENCE.mkdir(exist_ok=True)
        if self.log_path.exists():
            shutil.copy(self.log_path, EVIDENCE / f"uvicorn-{RELEASE.name}-{self.product}.log")
            self.log_path.unlink()
        for path in (self.db, Path(f"{self.db}-wal"), Path(f"{self.db}-shm"), self.dist_db):
            path.unlink(missing_ok=True)
