"""Formal vs test redemption codes and the early-bird count (qiuzhao plans only; bench unchanged).

Store tests use a throwaway SQLite file under tmp_path. HTTP tests run core.server under uvicorn in
a subprocess against throwaway paths (access DB, distribution DB, call logs, admin log) with a
random admin token that only travels through the child's environment. Nothing here touches
private/, /var/lib/mcp-suite or a production database.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from core.store import AccessError, Store, digest, price_state

ROOT = Path(__file__).resolve().parents[1]
PLAN = "qiuzhao-2026"
BENCH_PLAN = "bench-monthly"
TRIGGERS = {"redemption_codes_kind_required", "redemption_codes_kind_fixed", "redemption_codes_formal_kept"}

# Schema as created before code_plain existed (bf28b19). Production got code_plain by hand later,
# so both shapes are migrated below.
OLD_SCHEMA = """
  CREATE TABLE api_keys (
    id TEXT PRIMARY KEY, key_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL, activated_at TEXT NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0);
  CREATE TABLE entitlements (
    key_id TEXT NOT NULL REFERENCES api_keys(id), product TEXT NOT NULL,
    expires_at TEXT NOT NULL, daily_limit INTEGER NOT NULL CHECK(daily_limit > 0),
    PRIMARY KEY (key_id, product));
  CREATE TABLE redemption_codes (
    code_hash TEXT PRIMARY KEY, plan TEXT NOT NULL, created_at TEXT NOT NULL,
    redeemed_at TEXT, key_id TEXT REFERENCES api_keys(id));
  CREATE TABLE daily_usage (
    key_id TEXT NOT NULL, product TEXT NOT NULL, day TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(key_id, product, day));
  CREATE TABLE usage_log (
    key_id TEXT NOT NULL, product TEXT NOT NULL, tool TEXT NOT NULL, at TEXT NOT NULL);
"""


def make_old_db(path: Path, with_code_plain: bool):
    """An access DB as production had it: one pending and one redeemed qiuzhao code, one bench code."""
    codes = {"qz_pending": "QZ-" + "A" * 32, "qz_redeemed": "QZ-" + "B" * 32, "bench_pending": "BM-" + "C" * 32}
    token = "qz_" + secrets.token_urlsafe(32)
    db = sqlite3.connect(path)
    db.executescript(OLD_SCHEMA)
    if with_code_plain:
        db.execute("ALTER TABLE redemption_codes ADD COLUMN code_plain TEXT")
    db.execute("INSERT INTO api_keys VALUES('k1',?,'2026-09-11T11:00:00+08:00','2026-09-11T11:00:00+08:00',0)",
               (digest(token),))
    db.execute("INSERT INTO entitlements VALUES('k1','qiuzhao','2099-01-01T00:00:00+08:00',999999)")
    for name, code in codes.items():
        redeemed = name == "qz_redeemed"
        db.execute("INSERT INTO redemption_codes(code_hash,plan,created_at,redeemed_at,key_id) VALUES(?,?,?,?,?)",
                   (digest(code), BENCH_PLAN if code.startswith("BM-") else PLAN, "2026-09-11T10:00:00+08:00",
                    "2026-09-11T11:00:00+08:00" if redeemed else None, "k1" if redeemed else None))
    db.commit()
    db.close()
    return codes, token


def read(path: Path, sql: str, args=()):
    db = sqlite3.connect(path)
    try:
        return db.execute(sql, args).fetchall()
    finally:
        db.close()


def kinds(path: Path) -> dict:
    return dict(read(path, "SELECT code_hash, code_kind FROM redemption_codes"))


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "access.sqlite3")


# ------------------------------------------------------------------ migration

@pytest.mark.parametrize("with_code_plain", [False, True], ids=["without-code_plain", "with-code_plain"])
def test_migration_makes_every_existing_code_a_test_code_once(tmp_path, with_code_plain):
    path = tmp_path / "access.sqlite3"
    codes, token = make_old_db(path, with_code_plain)
    store = Store(path)
    columns = {row[1] for row in read(path, "PRAGMA table_info(redemption_codes)")}
    assert {"code_plain", "code_kind"} <= columns
    assert kinds(path) == {digest(code): "test" for code in codes.values()}  # redeemed ones included
    assert {row[0] for row in read(path, "SELECT name FROM sqlite_master WHERE type='trigger'")} == TRIGGERS
    assert store.authorize(token)["key_id"] == "k1"      # keys are untouched
    assert store.early_bird(PLAN)["sold"] == 0            # the old redeemed code is a test code

    formal = store.generate_codes(2, PLAN, "formal")
    store.redeem(formal[0])
    before = kinds(path)
    assert before[digest(formal[0])] == before[digest(formal[1])] == "formal"
    for _ in range(3):                                    # restarts never change a kind
        Store(path)
    assert kinds(path) == before
    assert store.early_bird(PLAN)["sold"] == 1
    store.redeem(codes["qz_pending"])                     # an old code still redeems, still a test code
    assert kinds(path)[digest(codes["qz_pending"])] == "test"
    assert Store(path).early_bird(PLAN)["sold"] == 1


def test_migration_is_safe_when_both_services_start_together(tmp_path):
    path = tmp_path / "access.sqlite3"
    codes, _ = make_old_db(path, with_code_plain=True)
    script = "import sys; from core.store import Store; Store(sys.argv[1])"
    procs = [subprocess.Popen([sys.executable, "-c", script, str(path)], cwd=ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT) for _ in range(4)]
    outputs = [(p.wait(timeout=60), p.stdout.read().decode()) for p in procs]
    assert all(code == 0 for code, _ in outputs), outputs
    assert kinds(path) == {digest(code): "test" for code in codes.values()}


def test_database_requires_a_kind_keeps_it_and_keeps_formal_codes(store):
    formal = store.generate_codes(1, PLAN, "formal")[0]
    test = store.generate_codes(1, PLAN, "test")[0]
    with pytest.raises(sqlite3.IntegrityError, match="code_kind is required"):
        with store.connect() as db:
            db.execute("INSERT INTO redemption_codes(code_hash,plan,created_at) VALUES('x',?,'t')", (PLAN,))
    for code, other in ((formal, "test"), (test, "formal")):
        with pytest.raises(sqlite3.IntegrityError, match="cannot change"):
            with store.connect() as db:
                db.execute("UPDATE redemption_codes SET code_kind=? WHERE code_hash=?", (other, digest(code)))
    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        with store.connect() as db:
            db.execute("DELETE FROM redemption_codes WHERE code_hash=?", (digest(formal),))
    with pytest.raises(ValueError, match="类别"):
        store.generate_codes(1, PLAN, "vip")
    with pytest.raises(ValueError, match="不区分"):
        store.generate_codes(1, BENCH_PLAN, "formal")
    assert kinds(store.path) == {digest(formal): "formal", digest(test): "test"}


# ------------------------------------------------------------------ delete rules

def test_formal_codes_cannot_be_deleted_redeemed_or_not(store):
    pending, redeemed = store.generate_codes(2, PLAN, "formal")
    token = store.redeem(redeemed)["api_key"]
    for code in (pending, redeemed):
        with pytest.raises(AccessError, match="正式码不能删除") as refused:
            store.delete_code(digest(code))
        assert refused.value.status == 409
    assert set(kinds(store.path)) == {digest(pending), digest(redeemed)}
    assert store.authorize(token)["remaining_today"] == 999999


def test_unredeemed_test_code_is_deleted(store):
    code = store.generate_codes(1, PLAN, "test")[0]
    assert store.delete_code(digest(code)) == {"code_hash_prefix": digest(code)[:12], "plan": PLAN,
                                               "code_kind": "test", "redeemed": False, "key_revoked": False}
    assert kinds(store.path) == {}
    with pytest.raises(AccessError, match="不存在") as missing:
        store.delete_code(digest(code))
    assert missing.value.status == 404


def test_deleting_a_redeemed_test_code_disables_its_key(store):
    code, other = store.generate_codes(2, PLAN, "test")
    token, other_token = store.redeem(code)["api_key"], store.redeem(other)["api_key"]
    store.consume(token, "qiuzhao", "jobs_search")
    entry = store.delete_code(digest(code))
    assert entry["redeemed"] is True and entry["key_revoked"] is True
    with pytest.raises(AccessError, match="无效或已停用"):
        store.authorize(token)
    with pytest.raises(AccessError, match="无效或已停用"):
        store.consume(token, "qiuzhao", "jobs_search")
    assert store.authorize(other_token)["remaining_today"] == 999999  # only that one key


def test_a_failed_audit_write_cancels_the_delete(store):
    code = store.generate_codes(1, PLAN, "test")[0]
    token = store.redeem(code)["api_key"]

    def audit(entry):
        raise OSError("disk full")
    with pytest.raises(OSError):
        store.delete_code(digest(code), audit=audit)
    assert digest(code) in kinds(store.path)
    assert store.authorize(token)["remaining_today"] == 999999


def test_bench_codes_keep_the_old_delete_rule(store):
    pending, redeemed = store.generate_codes(2, BENCH_PLAN)
    token = store.redeem(redeemed)["api_key"]
    assert store.delete_code(digest(pending))["key_revoked"] is False
    with pytest.raises(AccessError, match="已被兑换") as refused:
        store.delete_code(digest(redeemed))
    assert refused.value.status == 400
    assert store.consume(token, "bench", "bench_search")["remaining_today"] == 199
    assert store.early_bird(PLAN)["sold"] == 0


# ------------------------------------------------------------------ early-bird count

@pytest.mark.parametrize("sold,tier,price,remaining", [
    (0, 1, 29.9, 10), (10, 2, 39.9, 40), (11, 2, 39.9, 39),
    (50, 3, 49.9, 50), (100, None, 59.9, 0), (101, None, 59.9, 0)])
def test_price_state_at_the_tier_boundaries(sold, tier, price, remaining):
    state = price_state(PLAN, sold)
    assert (state["current_tier"], state["current_price_cny"], state["remaining"]) == (tier, price, remaining)
    assert state["early_bird_active"] is (tier is not None)
    assert state["standard_price_cny"] == 59.9
    assert [(t["rank_from"], t["rank_to"], t["price_cny"]) for t in state["tiers"]] == [
        (1, 10, 29.9), (11, 50, 39.9), (51, 100, 49.9)]


def test_only_redeemed_formal_codes_take_a_place(store):
    formal = store.generate_codes(101, PLAN, "formal")
    tests = store.generate_codes(3, PLAN, "test")
    bench = store.generate_codes(1, BENCH_PLAN)
    assert store.early_bird(PLAN)["sold"] == 0            # generating never counts
    for code in tests + bench:
        store.redeem(code)
    assert store.early_bird(PLAN)["sold"] == 0            # test and bench redemptions never count
    expected = {0: (1, 29.9, 10), 10: (2, 39.9, 40), 11: (2, 39.9, 39), 50: (3, 49.9, 50),
                100: (None, 59.9, 0), 101: (None, 59.9, 0)}
    done = 0
    for target, (tier, price, remaining) in expected.items():
        while done < target:
            store.redeem(formal[done])
            done += 1
        state = store.early_bird(PLAN)
        assert (state["sold"], state["current_tier"], state["current_price_cny"], state["remaining"]) == (
            target, tier, price, remaining)
    store.delete_code(digest(tests[0]))                   # deleting a redeemed test code changes nothing
    assert store.early_bird(PLAN)["sold"] == 101


# ------------------------------------------------------------------ HTTP

def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LocalServer:
    """core.server under uvicorn with every path in a temp dir and a random admin token."""

    def __init__(self, tmp: Path, product: str):
        self.tmp, self.product = tmp, product
        self.db, self.admin_log = tmp / "access.sqlite3", tmp / "admin_actions.jsonl"
        self.admin_token = secrets.token_urlsafe(24)
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"

    def start(self) -> "LocalServer":
        bench_path = self.tmp / "bench.json"
        bench_path.write_text(json.dumps({"data_as_of": "2026-09-03", "records": []}))
        env = {k: v for k, v in os.environ.items() if not k.startswith("MCP_")}
        env.update(MCP_PRODUCT=self.product, MCP_DB_PATH=str(self.db), MCP_DIST_DB_PATH=str(self.tmp / "dist.db"),
                   MCP_JOBS_PATH=str(self.tmp / "jobs-not-needed.json"), MCP_BENCH_PATH=str(bench_path),
                   MCP_CALL_LOG_DIR=str(self.tmp / "call_logs"), MCP_ADMIN_LOG_PATH=str(self.admin_log),
                   MCP_DIST_ADMIN_TOKEN=self.admin_token, PYTHONDONTWRITEBYTECODE="1", PYTHONWARNINGS="ignore")
        self.log = open(self.tmp / "uvicorn.log", "wb")
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "core.server:app", "--host", "127.0.0.1",
                                      "--port", str(self.port), "--no-access-log"],
                                     cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError((self.tmp / "uvicorn.log").read_text()[-3000:])
            try:
                if httpx.get(self.base + "/config", trust_env=False).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise RuntimeError("uvicorn did not start")

    def stop(self):
        self.proc.terminate()
        self.proc.wait(timeout=15)
        self.log.close()

    def get(self, path, **kw):
        return httpx.get(self.base + path, trust_env=False, **kw)

    def admin(self, method, path, token=None, **kw):
        headers = {"Authorization": f"Bearer {token or self.admin_token}"}
        return httpx.request(method, self.base + path, headers=headers, trust_env=False, **kw)

    def delete(self, code):
        return self.admin("POST", "/api/admin/delete_code", json={"code_hash": digest(code)})


@pytest.fixture(scope="module")
def qz(tmp_path_factory):
    server = LocalServer(tmp_path_factory.mktemp("qz"), "qiuzhao").start()
    yield server
    server.stop()


@pytest.fixture(scope="module")
def bench(tmp_path_factory):
    server = LocalServer(tmp_path_factory.mktemp("bench"), "bench").start()
    yield server
    server.stop()


def test_admin_routes_refuse_a_missing_or_wrong_token(qz):
    before = kinds(qz.db)
    routes = [("GET", "/api/admin/stats", None), ("GET", "/api/admin/codes", None),
              ("POST", f"/api/admin/generate?count=1&plan={PLAN}&kind=formal", None),
              ("GET", f"/api/admin/generate?count=1&plan={PLAN}&kind=test", None),
              ("POST", "/api/admin/delete_code", {"code_hash": "0" * 64})]
    for method, path, body in routes:
        assert httpx.request(method, qz.base + path, json=body, trust_env=False).status_code == 401
        assert qz.admin(method, path, token="wrong-" + qz.admin_token, json=body).status_code == 401
        assert httpx.request(method, qz.base + path + ("&" if "?" in path else "?") + "token=wrong",
                             json=body, trust_env=False).status_code == 401
    assert kinds(qz.db) == before                         # nothing generated or deleted
    assert qz.admin("GET", "/api/admin/stats").status_code == 200


def test_pricing_is_public_no_store_and_aggregate_only(qz):
    store = Store(qz.db)
    formal = store.generate_codes(3, PLAN, "formal")
    tests = store.generate_codes(2, PLAN, "test")
    keys = [store.redeem(code)["api_key"] for code in formal[:2] + tests[:1]]
    response = qz.get("/api/pricing")                     # no Authorization at all
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"plan", "currency", "standard_price_cny", "tiers", "sold", "early_bird_active",
                         "current_tier", "current_tier_rank_to", "current_price_cny", "remaining"}
    assert body == store.early_bird(PLAN)
    sold = read(qz.db, "SELECT COUNT(*) FROM redemption_codes WHERE code_kind='formal' AND redeemed_at IS NOT NULL")[0][0]
    assert body["sold"] == sold and body["remaining"] == 10 - sold and body["current_price_cny"] == 29.9
    secrets_in_db = [v for row in read(qz.db, "SELECT code_hash, code_plain FROM redemption_codes") for v in row if v]
    for value in secrets_in_db + keys:
        assert value not in response.text
    assert "QZ-" not in response.text and "qz_" not in response.text


def test_generate_needs_an_explicit_kind(qz):
    for query in (f"count=1&plan={PLAN}", f"count=1&plan={PLAN}&kind=", f"count=1&plan={PLAN}&kind=vip"):
        response = qz.admin("POST", "/api/admin/generate?" + query)
        assert response.status_code == 400 and "类别" in response.json()["error"]
    assert qz.admin("POST", f"/api/admin/generate?count=0&plan={PLAN}&kind=test").status_code == 400
    assert qz.admin("POST", f"/api/admin/generate?count=x&plan={PLAN}&kind=test").status_code == 400
    made = qz.admin("POST", f"/api/admin/generate?count=2&plan={PLAN}&kind=formal").json()
    assert made["code_kind"] == "formal" and len(made["codes"]) == 2
    assert {kinds(qz.db)[digest(code)] for code in made["codes"]} == {"formal"}
    legacy_get = qz.admin("GET", f"/api/admin/generate?count=1&plan={PLAN}&kind=test").json()
    assert kinds(qz.db)[digest(legacy_get["codes"][0])] == "test"


def test_delete_over_http_follows_the_kind_rules_and_leaves_a_trace(qz):
    store = Store(qz.db)
    formal_pending, formal_redeemed = store.generate_codes(2, PLAN, "formal")
    test_pending, test_redeemed = store.generate_codes(2, PLAN, "test")
    formal_key = store.redeem(formal_redeemed)["api_key"]
    test_key = store.redeem(test_redeemed)["api_key"]
    usage = lambda key: qz.get("/usage", headers={"Authorization": f"Bearer {key}"}).status_code
    assert usage(test_key) == 200

    for code in (formal_pending, formal_redeemed):
        refused = qz.delete(code)
        assert refused.status_code == 409 and "正式码不能删除" in refused.json()["error"]
    assert qz.delete(test_pending).json() == {"success": True, "code_kind": "test", "redeemed": False,
                                              "key_revoked": False}
    assert qz.delete(test_redeemed).json() == {"success": True, "code_kind": "test", "redeemed": True,
                                               "key_revoked": True}
    assert usage(test_key) == 401                         # the revoked key is refused ...
    mcp = httpx.post(qz.base + "/mcp", trust_env=False, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                     headers={"Authorization": f"Bearer {test_key}", "Accept": "application/json, text/event-stream"})
    assert mcp.status_code == 401                         # ... on the MCP endpoint too
    assert usage(formal_key) == 200

    assert qz.delete(test_pending).status_code == 404
    assert qz.admin("POST", "/api/admin/delete_code", json={"code_hash": "zz"}).status_code == 400
    assert qz.admin("POST", "/api/admin/delete_code", content=b"not json",
                    ).status_code == 400

    lines = [json.loads(line) for line in qz.admin_log.read_text().splitlines()]
    assert [(e["code_hash_prefix"], e["code_kind"], e["redeemed"], e["key_revoked"]) for e in lines[-2:]] == [
        (digest(test_pending)[:12], "test", False, False), (digest(test_redeemed)[:12], "test", True, True)]
    assert all(set(e) == {"ts", "action", "code_hash_prefix", "plan", "code_kind", "redeemed", "key_revoked"}
               and e["action"] == "delete_code" for e in lines)
    log_text = qz.admin_log.read_text()
    for secret in (test_pending, test_redeemed, test_key, digest(test_pending), digest(test_redeemed)):
        assert secret not in log_text
    assert oct(qz.admin_log.stat().st_mode & 0o777) == "0o600"


def test_admin_stats_and_list_carry_the_rules(qz):
    store = Store(qz.db)
    pending = store.generate_codes(1, PLAN, "test")[0]
    redeemed = store.generate_codes(1, PLAN, "test")[0]
    store.redeem(redeemed)
    stats = qz.admin("GET", "/api/admin/stats").json()
    counts = store.code_stats()
    assert (stats["total"], stats["redeemed"], stats["pending"]) == (
        counts["all"]["total"], counts["all"]["redeemed"], counts["all"]["pending"])
    assert stats["kinds"] == {k: counts[k] for k in ("formal", "test", "other")}
    assert stats["early_bird"] == store.early_bird(PLAN)
    rows = {row["code_hash"]: row for row in qz.admin("GET", "/api/admin/codes?limit=1000").json()["codes"]}
    assert all(not row["deletable"] for row in rows.values() if row["code_kind"] == "formal")
    assert rows[digest(pending)]["deletable"] and not rows[digest(pending)]["delete_revokes_key"]
    assert rows[digest(redeemed)]["deletable"] and rows[digest(redeemed)]["delete_revokes_key"]


def test_bench_process_keeps_its_behaviour(bench):
    assert bench.get("/api/pricing").status_code == 404   # no early-bird tiers for bench
    assert bench.get("/config").json()["mcp_url"].endswith("/bench/mcp")
    store = Store(bench.db)
    pending, redeemed = store.generate_codes(2, BENCH_PLAN)
    key = store.redeem(redeemed)["api_key"]
    assert bench.delete(pending).json()["key_revoked"] is False
    refused = bench.delete(redeemed)
    assert refused.status_code == 400 and refused.json()["error"] == "删除失败：码不存在或已被兑换"
    assert bench.get("/usage", headers={"Authorization": f"Bearer {key}"}).status_code == 200
    made = bench.admin("POST", f"/api/admin/generate?count=1&plan={BENCH_PLAN}").json()  # no kind needed
    assert kinds(bench.db)[digest(made["codes"][0])] == "test"
    assert bench.admin("POST", f"/api/admin/generate?count=1&plan={BENCH_PLAN}&kind=formal").status_code == 400
