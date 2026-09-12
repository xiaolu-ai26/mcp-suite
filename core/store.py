"""Shared product entitlements.

API keys are stored only as SHA-256 digests. Redemption codes are stored as a digest (the lookup
key) plus the plaintext in redemption_codes.code_plain, which the admin page lists so a code can
be copied and delivered to a buyer.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
# One plan per sellable package. Code prefix, key prefix, entitlement length and the
# sold-out message are all derived from here, so adding a product never edits the flow.
# "expires_at" = fixed season end; "days" = N days counted from activation.
PLANS = {
    "qiuzhao-2026": {"product": "qiuzhao", "price_cny": 59.9, "daily_limit": 999999,
                     "days": 30,
                     "sale_ends_at": "2027-12-31T00:00:00+08:00",
                     "code_prefix": "QZ-", "key_prefix": "qz_",
                     "ended_message": "该套餐已停售，请联系卖家续费。",
                     # Codes are "formal" (sold, never deleted) or "test" (deletable at any time).
                     "code_kinds": True,
                     # Early-bird tiers as (last rank, monthly price); price_cny applies after the
                     # last tier. Only redeemed formal codes of this plan take a rank. The redemption
                     # page and the admin page both read this through /api/pricing.
                     "early_bird": ((10, 29.9), (50, 39.9), (100, 49.9))},
    "bench-monthly": {"product": "bench", "price_cny": 29, "daily_limit": 200, "days": 30,
                      "sale_ends_at": "2027-12-31T00:00:00+08:00",
                      "code_prefix": "BM-", "key_prefix": "bm_",
                      "ended_message": "该套餐已停售，请联系卖家续费。"},
}
CODE_BODY = 32
CODE_KINDS = ("test", "formal")
# redemption_codes.code_kind is nullable only because ALTER TABLE cannot add a NOT NULL column
# without a default, and a default is exactly what must not decide a code's kind. The triggers
# make it mandatory on insert, permanent once set, and keep formal codes from ever being deleted.
KIND_COLUMN = "code_kind TEXT CHECK(code_kind IN ('test','formal'))"
KIND_TRIGGERS = """
  CREATE TRIGGER IF NOT EXISTS redemption_codes_kind_required
    BEFORE INSERT ON redemption_codes WHEN NEW.code_kind IS NULL
    BEGIN SELECT RAISE(ABORT, 'redemption_codes.code_kind is required'); END;
  CREATE TRIGGER IF NOT EXISTS redemption_codes_kind_fixed
    BEFORE UPDATE OF code_kind ON redemption_codes
    WHEN OLD.code_kind IS NOT NULL AND NEW.code_kind IS NOT OLD.code_kind
    BEGIN SELECT RAISE(ABORT, 'redemption_codes.code_kind cannot change'); END;
  CREATE TRIGGER IF NOT EXISTS redemption_codes_formal_kept
    BEFORE DELETE ON redemption_codes WHEN OLD.code_kind = 'formal'
    BEGIN SELECT RAISE(ABORT, 'formal redemption codes cannot be deleted'); END;
"""


def price_state(plan_name: str, sold: int) -> dict:
    """Public price for a plan after `sold` redeemed formal codes. Aggregates only."""
    plan = PLANS[plan_name]
    tiers, first = [], 1
    for number, (last, price) in enumerate(plan.get("early_bird", ()), 1):
        tiers.append({"tier": number, "rank_from": first, "rank_to": last, "price_cny": price})
        first = last + 1
    current = next((t for t in tiers if sold < t["rank_to"]), None)
    return {"plan": plan_name, "currency": "CNY", "standard_price_cny": plan["price_cny"],
            "tiers": tiers, "sold": sold, "early_bird_active": current is not None,
            "current_tier": current["tier"] if current else None,
            "current_tier_rank_to": current["rank_to"] if current else None,
            "current_price_cny": current["price_cny"] if current else plan["price_cny"],
            "remaining": current["rank_to"] - sold if current else 0}


def delete_refusal(plan_name: str, kind: str | None, redeemed: bool) -> tuple[str, int] | None:
    """Why a code may not be deleted (message, HTTP status), or None. The one place for the rule:
    plans with code kinds never lose a formal code and always let a test code go; other plans keep
    the original rule that only unredeemed codes can be deleted."""
    if PLANS.get(plan_name, {}).get("code_kinds"):
        if kind == "formal":
            return "正式码不能删除：正式码一经生成就永久保留，兑换后计入早鸟名额。", 409
        return None
    if redeemed:
        return "删除失败：码不存在或已被兑换", 400
    return None


def plan_expiry(plan: dict, activated: datetime) -> str:
    """Fixed-season plans keep their published end date; monthly plans run from activation."""
    if plan.get("expires_at"):
        return plan["expires_at"]
    return (activated + timedelta(days=plan["days"])).isoformat()


def valid_through(expires_at: str) -> str:
    """Last fully valid Beijing date, matching what the redemption page shows."""
    return (datetime.fromisoformat(expires_at) - timedelta(seconds=1)).date().isoformat()


def now() -> datetime:
    return datetime.now(TZ)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class AccessError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # SQLite journal inherits the database permissions; create private from first byte.
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        with self.connect() as db:
            db.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY, key_hash TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL, activated_at TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0);
              CREATE TABLE IF NOT EXISTS entitlements (
                key_id TEXT NOT NULL REFERENCES api_keys(id), product TEXT NOT NULL,
                expires_at TEXT NOT NULL, daily_limit INTEGER NOT NULL CHECK(daily_limit > 0),
                PRIMARY KEY (key_id, product));
              CREATE TABLE IF NOT EXISTS redemption_codes (
                code_hash TEXT PRIMARY KEY, plan TEXT NOT NULL, created_at TEXT NOT NULL,
                redeemed_at TEXT, key_id TEXT REFERENCES api_keys(id), code_plain TEXT,
                """ + KIND_COLUMN + """);
              CREATE TABLE IF NOT EXISTS daily_usage (
                key_id TEXT NOT NULL, product TEXT NOT NULL, day TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(key_id, product, day));
              CREATE TABLE IF NOT EXISTS usage_log (
                key_id TEXT NOT NULL, product TEXT NOT NULL, tool TEXT NOT NULL, at TEXT NOT NULL);
            """)
            # Databases created before code_plain was part of the schema (the production DB got the
            # column by hand): add it once. Safe to run on every start and from two processes.
            columns = {row[1] for row in db.execute("PRAGMA table_info(redemption_codes)")}
            if "code_plain" not in columns:
                try:
                    db.execute("ALTER TABLE redemption_codes ADD COLUMN code_plain TEXT")
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc):
                        raise
            # code_kind: every code that exists when the column is added becomes a test code (all
            # of them were the owner's own tests). Column, backfill and triggers commit together
            # under one write lock, and the column check runs inside that lock, so a second
            # process starting at the same moment finds the finished state and changes nothing.
            # The backfill only ever fills an empty kind (rows written by code that predates the
            # column, e.g. during a rollback); a kind that is set is never changed again, which
            # the kind_fixed trigger also enforces.
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(redemption_codes)")}
            if "code_kind" not in columns:
                db.execute("ALTER TABLE redemption_codes ADD COLUMN " + KIND_COLUMN)
            db.execute("UPDATE redemption_codes SET code_kind='test' WHERE code_kind IS NULL")
            for statement in KIND_TRIGGERS.split("END;")[:-1]:
                db.execute(statement + "END;")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def generate_codes(self, count: int, plan: str = "qiuzhao-2026", kind: str = "test") -> list[str]:
        """The kind is always written explicitly. The default only keeps old in-process callers
        working and is the harmless choice; the admin endpoint and the CLI require it."""
        if plan not in PLANS or not 1 <= count <= 10000:
            raise ValueError("未知套餐或数量超出范围")
        if kind not in CODE_KINDS:
            raise ValueError("兑换码类别只能是 test（测试）或 formal（正式）")
        if kind == "formal" and not PLANS[plan].get("code_kinds"):
            raise ValueError("该套餐不区分正式码和测试码")
        if now() >= datetime.fromisoformat(PLANS[plan]["sale_ends_at"]):
            raise ValueError("套餐已结束，不能生成兑换码")
        prefix = PLANS[plan]["code_prefix"]
        codes = [prefix + secrets.token_hex(CODE_BODY // 2).upper() for _ in range(count)]
        with self.connect() as db:
            db.executemany("INSERT INTO redemption_codes(code_hash,plan,created_at,code_plain,code_kind)"
                           " VALUES(?,?,?,?,?)",
                           [(digest(c), plan, now().isoformat(), c, kind) for c in codes])
        return codes

    def delete_code(self, code_hash: str, audit=None) -> dict:
        """Delete one code under delete_refusal()'s rule. Deleting a redeemed code of a plan with
        code kinds (necessarily a test code) disables the key it produced in the same transaction.
        audit(entry) runs before commit; if it raises, nothing is deleted or disabled."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT plan, code_kind, redeemed_at, key_id FROM redemption_codes"
                             " WHERE code_hash=?", (code_hash,)).fetchone()
            if not row:
                raise AccessError("兑换码不存在或已删除。", 404)
            redeemed = row["redeemed_at"] is not None
            refusal = delete_refusal(row["plan"], row["code_kind"], redeemed)
            if refusal:
                raise AccessError(*refusal)
            revoked = False
            if redeemed and row["key_id"] and PLANS.get(row["plan"], {}).get("code_kinds"):
                revoked = db.execute("UPDATE api_keys SET disabled=1 WHERE id=?",
                                     (row["key_id"],)).rowcount == 1
            db.execute("DELETE FROM redemption_codes WHERE code_hash=?", (code_hash,))
            entry = {"code_hash_prefix": code_hash[:12], "plan": row["plan"],
                     "code_kind": row["code_kind"], "redeemed": redeemed, "key_revoked": revoked}
            if audit:
                audit(entry)
            return entry

    def early_bird(self, plan_name: str) -> dict:
        """price_state() for the plan, counting only its redeemed formal codes."""
        with self.connect() as db:
            sold = db.execute("SELECT COUNT(*) FROM redemption_codes WHERE plan=? AND code_kind='formal'"
                              " AND redeemed_at IS NOT NULL", (plan_name,)).fetchone()[0]
        return price_state(plan_name, sold)

    def code_stats(self) -> dict:
        """Counts for the admin overview: all codes, and formal/test for plans with code kinds
        ("other" = plans without kinds, e.g. bench)."""
        empty = lambda: {"total": 0, "redeemed": 0, "pending": 0}
        stats = {"all": empty(), "formal": empty(), "test": empty(), "other": empty()}
        with self.connect() as db:
            rows = db.execute("SELECT plan, code_kind, COUNT(*) AS total, COUNT(redeemed_at) AS redeemed"
                              " FROM redemption_codes GROUP BY plan, code_kind").fetchall()
        for row in rows:
            kinded = PLANS.get(row["plan"], {}).get("code_kinds")
            group = ("formal" if row["code_kind"] == "formal" else "test") if kinded else "other"
            for name in ("all", group):
                stats[name]["total"] += row["total"]
                stats[name]["redeemed"] += row["redeemed"]
                stats[name]["pending"] += row["total"] - row["redeemed"]
        return stats

    def list_codes(self, limit: int = 100) -> list[dict]:
        """Newest codes for the admin list, each with what the delete rule allows for it."""
        with self.connect() as db:
            rows = db.execute("SELECT code_hash, code_plain, plan, code_kind, created_at, redeemed_at"
                              " FROM redemption_codes ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        codes = []
        for row in rows:
            code = dict(row)
            redeemed = row["redeemed_at"] is not None
            code["kind_applies"] = bool(PLANS.get(row["plan"], {}).get("code_kinds"))
            code["deletable"] = delete_refusal(row["plan"], row["code_kind"], redeemed) is None
            code["delete_revokes_key"] = code["deletable"] and redeemed and code["kind_applies"]
            codes.append(code)
        return codes

    def redeem(self, code: str) -> dict:
        code = code.strip().upper()
        # Format check is derived from the plan table; every product keeps prefix + 32 chars.
        if not any(code.startswith(p["code_prefix"]) and len(code) == len(p["code_prefix"]) + CODE_BODY
                   for p in PLANS.values()):
            raise AccessError("兑换码无效，请检查输入。", 400)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM redemption_codes WHERE code_hash=?", (digest(code),)).fetchone()
            if not row or row["redeemed_at"]:
                raise AccessError("兑换码无效或已使用，每个兑换码只能领取一次。", 400)
            plan = PLANS[row["plan"]]
            activated = now()
            if activated >= datetime.fromisoformat(plan["sale_ends_at"]):
                raise AccessError(plan["ended_message"], 403)
            expires_at = plan_expiry(plan, activated)
            token = plan["key_prefix"] + secrets.token_urlsafe(32)
            key_id = secrets.token_hex(12)
            db.execute("INSERT INTO api_keys VALUES(?,?,?,?,0)",
                       (key_id, digest(token), activated.isoformat(), activated.isoformat()))
            db.execute("INSERT INTO entitlements VALUES(?,?,?,?)",
                       (key_id, plan["product"], expires_at, plan["daily_limit"]))
            db.execute("UPDATE redemption_codes SET redeemed_at=?,key_id=? WHERE code_hash=?",
                       (activated.isoformat(), key_id, digest(code)))
            return {"api_key": token, "product": plan["product"], "activated_at": activated.isoformat(),
                    "expires_at": expires_at, "valid_through": valid_through(expires_at),
                    "daily_limit": plan["daily_limit"], "remaining_today": plan["daily_limit"]}

    def _authorize(self, db, token: str, product: str):
        row = db.execute("""SELECT k.id,k.disabled,e.expires_at,e.daily_limit FROM api_keys k
                            LEFT JOIN entitlements e ON k.id=e.key_id AND e.product=?
                            WHERE k.key_hash=?""", (product, digest(token))).fetchone()
        if not row or row["disabled"]:
            raise AccessError("API key 无效或已停用，请检查接入配置。")
        if row["expires_at"] is None:
            raise AccessError("当前 API key 没有该产品权限，请联系卖家开通。", 403)
        if now() >= datetime.fromisoformat(row["expires_at"]):
            raise AccessError("API key 已过期，请联系卖家续费并兑换新的 key。", 403)
        return row

    def authorize(self, token: str, product: str = "qiuzhao") -> dict:
        with self.connect() as db:
            row = self._authorize(db, token, product)
            used = db.execute("SELECT used FROM daily_usage WHERE key_id=? AND product=? AND day=?",
                              (row["id"], product, now().date().isoformat())).fetchone()
            return {"key_id": row["id"], "product": product, "expires_at": row["expires_at"],
                    "daily_limit": row["daily_limit"],
                    "remaining_today": max(0, row["daily_limit"] - (used[0] if used else 0))}

    def consume(self, token: str, product: str, tool: str) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._authorize(db, token, product)
            current = now()
            day = current.date().isoformat()
            db.execute("INSERT OR IGNORE INTO daily_usage VALUES(?,?,?,0)", (row["id"], product, day))
            changed = db.execute("""UPDATE daily_usage SET used=used+1
              WHERE key_id=? AND product=? AND day=? AND used<?""",
                                 (row["id"], product, day, row["daily_limit"]))
            if changed.rowcount != 1:
                raise AccessError(f"今日 {row['daily_limit']} 次调用额度已用完，"
                                  "北京时间 00:00 重置；如需更多额度请联系卖家。", 429)
            db.execute("INSERT INTO usage_log VALUES(?,?,?,?)", (row["id"], product, tool, current.isoformat()))
            used = db.execute("SELECT used FROM daily_usage WHERE key_id=? AND product=? AND day=?",
                              (row["id"], product, day)).fetchone()[0]
            return {"remaining_today": row["daily_limit"] - used, "daily_limit": row["daily_limit"]}
