"""Shared product entitlements. Never persist bearer secrets or redemption codes."""
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
                     "ended_message": "该套餐已停售，请联系卖家续费。"},
    "bench-monthly": {"product": "bench", "price_cny": 29, "daily_limit": 200, "days": 30,
                      "sale_ends_at": "2027-12-31T00:00:00+08:00",
                      "code_prefix": "BM-", "key_prefix": "bm_",
                      "ended_message": "该套餐已停售，请联系卖家续费。"},
}
CODE_BODY = 32


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
                redeemed_at TEXT, key_id TEXT REFERENCES api_keys(id));
              CREATE TABLE IF NOT EXISTS daily_usage (
                key_id TEXT NOT NULL, product TEXT NOT NULL, day TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(key_id, product, day));
              CREATE TABLE IF NOT EXISTS usage_log (
                key_id TEXT NOT NULL, product TEXT NOT NULL, tool TEXT NOT NULL, at TEXT NOT NULL);
            """)

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

    def generate_codes(self, count: int, plan: str = "qiuzhao-2026") -> list[str]:
        if plan not in PLANS or not 1 <= count <= 10000:
            raise ValueError("未知套餐或数量超出范围")
        if now() >= datetime.fromisoformat(PLANS[plan]["sale_ends_at"]):
            raise ValueError("套餐已结束，不能生成兑换码")
        prefix = PLANS[plan]["code_prefix"]
        codes = [prefix + secrets.token_hex(CODE_BODY // 2).upper() for _ in range(count)]
        with self.connect() as db:
            db.executemany("INSERT INTO redemption_codes(code_hash,plan,created_at,code_plain) VALUES(?,?,?,?)",
                           [(digest(c), plan, now().isoformat(), c) for c in codes])
        return codes

    def delete_code(self, code_hash: str) -> bool:
        """删除未兑换的兑换码。已兑换的不能删。"""
        with self.connect() as db:
            cur = db.execute("DELETE FROM redemption_codes WHERE code_hash=? AND redeemed_at IS NULL",
                           (code_hash,))
            return cur.rowcount > 0

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
