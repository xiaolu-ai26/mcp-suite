"""Shared product entitlements.

API keys are stored only as SHA-256 digests. Redemption codes are stored as a digest (the lookup
key) plus the plaintext in redemption_codes.code_plain, which the admin page lists so a code can
be copied and delivered to a buyer.
"""
from __future__ import annotations

import base64
import hmac
import math
import tempfile
import re
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
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
    "qiuzhao-trial": {"product": "qiuzhao", "price_cny": 9.9, "daily_limit": 100, "days": 7,
                      "sale_ends_at": "2027-12-31T00:00:00+08:00",
                      "code_prefix": "QT-", "key_prefix": "qt_",
                      "ended_message": "试用已结束，请购买正式会员。",
                      "code_kinds": True},
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


NOTE_MAX = 500
# A test code may carry a fixed absolute deadline and/or a total call quota; both are stored on
# the code and copied onto the entitlement it produces. None means "the original plan rule".


def benefit_expiry(value) -> str | None:
    """Fixed Beijing-time deadline for a test code. A bare date means the end of that Beijing day;
    a naive datetime is Beijing wall time; an offset is normalized to Beijing. Rejects anything
    else instead of guessing."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("固定截止时间必须是日期时间字符串。")
    text = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            moment = datetime.combine(date.fromisoformat(text), time(23, 59, 59), tzinfo=TZ)
        else:
            moment = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("固定截止时间无效，请使用 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM（北京时间）。") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=TZ)
    return moment.astimezone(TZ).isoformat(timespec="seconds")


def benefit_total(value) -> int | None:
    """Total business-call quota. Strictly a positive int: bools, floats (even 5.0), strings,
    zero and negatives are rejected, never silently truncated."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("总调用次数必须是正整数。")
    return value


def admin_note(value) -> str | None:
    """Admin-only plain-text note, at most NOTE_MAX characters; empty means no note."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("备注必须是文本。")
    note = value.strip()
    if len(note) > NOTE_MAX:
        raise ValueError(f"备注不能超过{NOTE_MAX}字符。")
    return note or None


class AccessError(Exception):
    def __init__(self, message: str, status: int = 401, retry_after: int | None = None,
                 reason: str | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        # Machine-readable rejection category for the Guard rejection log. Purely additive:
        # it never changes whether a request is refused, only how the refusal is classified.
        self.reason = reason


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.limits = {name: int(os.environ.get(env, default)) for name, env, default in (
            ('rpm','MCP_QIU_RPM',30), ('inflight','MCP_QIU_MAX_INFLIGHT',3),
            ('lease_seconds','MCP_CALL_LEASE_SECONDS',120),
            ('recovery_ip_attempts','MCP_RECOVERY_IP_ATTEMPTS',10),
            ('recovery_ip_window','MCP_RECOVERY_IP_WINDOW_SECONDS',600),
            ('recovery_rotations','MCP_RECOVERY_ROTATIONS_PER_HOUR',3),
            ('recovery_retry_seconds','MCP_RECOVERY_RETRY_SECONDS',600))}
        if any(v <= 0 for v in self.limits.values()):
            raise ValueError('Access limit settings must be positive integers')
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
              CREATE TABLE IF NOT EXISTS call_admissions (
                key_id TEXT NOT NULL, product TEXT NOT NULL, at REAL NOT NULL);
              CREATE INDEX IF NOT EXISTS call_admissions_window ON call_admissions(key_id,product,at);
              CREATE TABLE IF NOT EXISTS call_leases (
                lease_id TEXT PRIMARY KEY, key_id TEXT NOT NULL, product TEXT NOT NULL, expires REAL NOT NULL);
              CREATE INDEX IF NOT EXISTS call_leases_account ON call_leases(key_id,product,expires);
              CREATE TABLE IF NOT EXISTS recovery_attempts (ip_hash TEXT NOT NULL, at REAL NOT NULL);
              CREATE INDEX IF NOT EXISTS recovery_attempts_window ON recovery_attempts(ip_hash,at);
              CREATE TABLE IF NOT EXISTS recovery_requests (
                key_id TEXT NOT NULL, request_hash TEXT NOT NULL, issued_hash TEXT NOT NULL, at REAL NOT NULL,
                PRIMARY KEY(key_id,request_hash));
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
            # Per-test-code benefits: a fixed absolute deadline, a total business-call quota and
            # an admin-only note live on the code; the entitlement it produces gets the expiry
            # type, the total quota and its cumulative usage. Every column is nullable or
            # defaulted, so rows that predate this block keep exactly their original rules. The
            # checks run inside the same write lock as the code_kind migration, so a concurrent
            # starter sees either the old or the finished state.
            benefits_ddl = (
                ("redemption_codes", "benefit_expires_at",
                 "ALTER TABLE redemption_codes ADD COLUMN benefit_expires_at TEXT"),
                ("redemption_codes", "benefit_total_calls",
                 "ALTER TABLE redemption_codes ADD COLUMN benefit_total_calls INTEGER"
                 " CHECK(benefit_total_calls > 0)"),
                ("redemption_codes", "admin_note",
                 "ALTER TABLE redemption_codes ADD COLUMN admin_note TEXT"),
                ("entitlements", "total_calls",
                 "ALTER TABLE entitlements ADD COLUMN total_calls INTEGER CHECK(total_calls > 0)"),
                ("entitlements", "total_used",
                 "ALTER TABLE entitlements ADD COLUMN total_used INTEGER NOT NULL DEFAULT 0"),
                ("entitlements", "expires_type",
                 "ALTER TABLE entitlements ADD COLUMN expires_type TEXT NOT NULL DEFAULT 'days'"
                 " CHECK(expires_type IN ('days','fixed'))"),
            )
            migrated = {}
            for table, column, ddl in benefits_ddl:
                if table not in migrated:
                    migrated[table] = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                if column not in migrated[table]:
                    db.execute(ddl)

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

    def generate_codes(self, count: int, plan: str = "qiuzhao-2026", kind: str = "test", *,
                       expires_at=None, total_calls=None, note=None) -> list[str]:
        """The kind is always written explicitly. The default only keeps old in-process callers
        working and is the harmless choice; the admin endpoint and the CLI require it.

        expires_at / total_calls / note are test-code-only benefits: a fixed absolute Beijing
        deadline (not re-anchored at redemption), a total business-call quota, and an admin-only
        note. A formal code never takes them — a formal code with custom benefits would silently
        change a sold entitlement, so it is refused outright."""
        if plan not in PLANS or not 1 <= count <= 10000:
            raise ValueError("未知套餐或数量超出范围")
        if kind not in CODE_KINDS:
            raise ValueError("兑换码类别只能是 test（测试）或 formal（正式）")
        if kind == "formal" and not PLANS[plan].get("code_kinds"):
            raise ValueError("该套餐不区分正式码和测试码")
        expires_at = benefit_expiry(expires_at)
        total_calls = benefit_total(total_calls)
        note = admin_note(note)
        if kind != "test" and (expires_at is not None or total_calls is not None or note is not None):
            raise ValueError("正式码不接受固定截止、总次数或备注等自定义权益；正式码始终按原套餐规则销售。")
        if now() >= datetime.fromisoformat(PLANS[plan]["sale_ends_at"]):
            raise ValueError("套餐已结束，不能生成兑换码")
        prefix = PLANS[plan]["code_prefix"]
        codes = [prefix + secrets.token_hex(CODE_BODY // 2).upper() for _ in range(count)]
        with self.connect() as db:
            db.executemany("INSERT INTO redemption_codes(code_hash,plan,created_at,code_plain,code_kind,"
                           "benefit_expires_at,benefit_total_calls,admin_note) VALUES(?,?,?,?,?,?,?,?)",
                           [(digest(c), plan, now().isoformat(), c, kind, expires_at, total_calls, note)
                            for c in codes])
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
        """Newest codes for the admin list, each with what the delete rule allows for it, plus the
        test-code benefits (fixed deadline, total quota, admin note) and, once redeemed, the
        entitlement's remaining total. Admin-only: admin_note never leaves these rows."""
        with self.connect() as db:
            rows = db.execute("""SELECT r.code_hash, r.code_plain, r.plan, r.code_kind, r.created_at,
                                        r.redeemed_at, r.benefit_expires_at, r.benefit_total_calls,
                                        r.admin_note, e.expires_type, e.total_calls, e.total_used
                                 FROM redemption_codes r
                                 LEFT JOIN entitlements e ON e.key_id = r.key_id
                                 ORDER BY r.created_at DESC LIMIT ?""", (limit,)).fetchall()
        codes = []
        for row in rows:
            code = dict(row)
            redeemed = row["redeemed_at"] is not None
            code["kind_applies"] = bool(PLANS.get(row["plan"], {}).get("code_kinds"))
            code["deletable"] = delete_refusal(row["plan"], row["code_kind"], redeemed) is None
            code["delete_revokes_key"] = code["deletable"] and redeemed and code["kind_applies"]
            code["remaining_total"] = (row["total_calls"] - row["total_used"]
                                       if row["total_calls"] is not None else None)
            codes.append(code)
        return codes

    def set_note(self, code_hash: str, note, audit=None) -> dict:
        """Edit one test code's admin note and nothing else: entitlements, expiry and usage are
        never touched. Formal codes cannot carry a note. audit(entry) runs before commit and may
        veto; the note text itself is not part of the audit entry."""
        note = admin_note(note)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT plan, code_kind FROM redemption_codes WHERE code_hash=?",
                             (code_hash,)).fetchone()
            if not row:
                raise AccessError("兑换码不存在或已删除。", 404)
            if row["code_kind"] != "test":
                raise AccessError("只有测试码可以编辑备注。", 409)
            db.execute("UPDATE redemption_codes SET admin_note=? WHERE code_hash=?", (note, code_hash))
            entry = {"code_hash_prefix": code_hash[:12], "plan": row["plan"],
                     "code_kind": row["code_kind"], "note_set": note is not None}
            if audit:
                audit(entry)
            return entry

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
            # A fixed deadline is absolute: it is never re-anchored at redemption, and a code
            # whose deadline already passed cannot be redeemed at all.
            fixed_end = row["benefit_expires_at"]
            if fixed_end and activated >= datetime.fromisoformat(fixed_end):
                raise AccessError("该兑换码的固定截止时间已过，不能兑换。", 403)
            expires_at = fixed_end or plan_expiry(plan, activated)
            expires_type = "fixed" if fixed_end else "days"
            total_calls = row["benefit_total_calls"]
            token = plan["key_prefix"] + secrets.token_urlsafe(32)
            key_id = secrets.token_hex(12)
            db.execute("INSERT INTO api_keys VALUES(?,?,?,?,0)",
                       (key_id, digest(token), activated.isoformat(), activated.isoformat()))
            db.execute("INSERT INTO entitlements(key_id,product,expires_at,daily_limit,"
                       "total_calls,total_used,expires_type) VALUES(?,?,?,?,?,0,?)",
                       (key_id, plan["product"], expires_at, plan["daily_limit"], total_calls, expires_type))
            db.execute("UPDATE redemption_codes SET redeemed_at=?,key_id=? WHERE code_hash=?",
                       (activated.isoformat(), key_id, digest(code)))
            return {"api_key": token, "product": plan["product"], "activated_at": activated.isoformat(),
                    "expires_at": expires_at, "expires_type": expires_type,
                    "valid_through": valid_through(expires_at),
                    "daily_limit": plan["daily_limit"], "remaining_today": plan["daily_limit"],
                    "total_calls": total_calls, "remaining_total": total_calls}

    def _authorize(self, db, token: str, product: str):
        row = db.execute("""SELECT k.id,k.disabled,e.expires_at,e.expires_type,e.daily_limit,
                                   e.total_calls,e.total_used FROM api_keys k
                            LEFT JOIN entitlements e ON k.id=e.key_id AND e.product=?
                            WHERE k.key_hash=?""", (product, digest(token))).fetchone()
        if not row or row["disabled"]:
            raise AccessError("API key 无效或已停用，请检查接入配置。", reason="auth_invalid")
        if row["expires_at"] is None:
            raise AccessError("当前 API key 没有该产品权限，请联系卖家开通。", 403,
                              reason="auth_no_entitlement")
        if now() >= datetime.fromisoformat(row["expires_at"]):
            raise AccessError("API key 已过期，请联系卖家续费并兑换新的 key。", 403,
                              reason="auth_expired")
        return row

    def authorize(self, token: str, product: str = "qiuzhao") -> dict:
        with self.connect() as db:
            row = self._authorize(db, token, product)
            used = db.execute("SELECT used FROM daily_usage WHERE key_id=? AND product=? AND day=?",
                              (row["id"], product, now().date().isoformat())).fetchone()
            return {"key_id": row["id"], "product": product, "expires_at": row["expires_at"],
                    "expires_type": row["expires_type"],
                    "valid_through": valid_through(row["expires_at"]),
                    "daily_limit": row["daily_limit"],
                    "remaining_today": max(0, row["daily_limit"] - (used[0] if used else 0)),
                    "total_calls": row["total_calls"],
                    "remaining_total": (max(0, row["total_calls"] - row["total_used"])
                                        if row["total_calls"] is not None else None)}

    def _consume_total(self, db, row, product: str) -> None:
        """Charge one call against the entitlement's total quota, atomically with the rest of the
        admission transaction. The quota is tied to the stable key_id, so it is shared across
        days, agents, processes and rotated keys, and the last call can never be oversold."""
        if row["total_calls"] is None:
            return
        counted = db.execute("UPDATE entitlements SET total_used=total_used+1"
                             " WHERE key_id=? AND product=? AND total_used<total_calls",
                             (row["id"], product))
        if counted.rowcount != 1:
            raise AccessError(f"该权益的总调用次数已用完（共{row['total_calls']}次），不能继续调用。", 403,
                              reason="total_quota")

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
                                  "北京时间 00:00 重置；如需更多额度请联系卖家。", 429,
                                  reason="daily_quota")
            self._consume_total(db, row, product)
            db.execute("INSERT INTO usage_log VALUES(?,?,?,?)", (row["id"], product, tool, current.isoformat()))
            used = db.execute("SELECT used FROM daily_usage WHERE key_id=? AND product=? AND day=?",
                              (row["id"], product, day)).fetchone()[0]
            return {"remaining_today": row["daily_limit"] - used, "daily_limit": row["daily_limit"],
                    "total_calls": row["total_calls"],
                    "remaining_total": (row["total_calls"] - (row["total_used"] + 1)
                                        if row["total_calls"] is not None else None)}

    def start_call(self, token, product, tool):
        """Atomically admit and meter one business call across processes and rotated keys."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._authorize(db, token, product)
            current = now(); stamp = current.timestamp(); day = current.date().isoformat()
            db.execute('DELETE FROM call_admissions WHERE at<=?', (stamp-60,))
            db.execute('DELETE FROM call_leases WHERE expires<=?', (stamp,))
            admitted = db.execute('SELECT COUNT(*),MIN(at) FROM call_admissions WHERE key_id=? AND product=? AND at>?',
                                  (row['id'], product, stamp-60)).fetchone()
            if admitted[0] >= self.limits['rpm']:
                raise AccessError(f"同一账号每滚动60秒最多{self.limits['rpm']}次业务请求，请稍后重试。", 429,
                                  max(1, math.ceil(admitted[1]+60-stamp)), reason="rate_limit_rpm")
            active = db.execute('SELECT COUNT(*) FROM call_leases WHERE key_id=? AND product=? AND expires>?',
                                (row['id'], product, stamp)).fetchone()[0]
            if active >= self.limits['inflight']:
                raise AccessError(f"同一账号最多同时执行{self.limits['inflight']}个业务请求，请等待当前请求完成。",429,1,
                                  reason="limit_inflight")
            db.execute('INSERT OR IGNORE INTO daily_usage VALUES(?,?,?,0)', (row['id'], product, day))
            changed = db.execute('UPDATE daily_usage SET used=used+1 WHERE key_id=? AND product=? AND day=? AND used<?',
                                 (row['id'], product, day, row['daily_limit']))
            if changed.rowcount != 1:
                raise AccessError('今日调用额度已用完，请按原套餐规则稍后重试。',429,60,
                                  reason="daily_quota")
            # The total quota is charged only here, after rate and daily checks passed, inside the
            # same write transaction: a 429 or protocol rejection never decrements it, and an
            # exhausted quota rolls back the daily charge above rather than touching it.
            self._consume_total(db, row, product)
            lease = secrets.token_hex(16)
            db.execute('INSERT INTO call_admissions VALUES(?,?,?)', (row['id'], product, stamp))
            db.execute('INSERT INTO call_leases VALUES(?,?,?,?)', (lease, row['id'], product, stamp+self.limits['lease_seconds']))
            db.execute('INSERT INTO usage_log VALUES(?,?,?,?)', (row['id'], product, tool, current.isoformat()))
            return lease

    def renew_call(self, lease):
        with self.connect() as db:
            return db.execute('UPDATE call_leases SET expires=? WHERE lease_id=?',
                              (now().timestamp()+self.limits['lease_seconds'], lease)).rowcount == 1

    def finish_call(self, lease):
        with self.connect() as db:
            db.execute('DELETE FROM call_leases WHERE lease_id=?', (lease,))

    def recovery_attempt(self, client_ip):
        """All recovery attempts, including malformed/invalid codes, share the IP budget."""
        stamp = now().timestamp(); window = self.limits['recovery_ip_window']
        ip_hash = digest('mcp-suite/recovery-ip/v1:' + client_ip)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM recovery_attempts WHERE at<=?', (stamp-window,))
            count, first = db.execute('SELECT COUNT(*),MIN(at) FROM recovery_attempts WHERE ip_hash=? AND at>?',
                                     (ip_hash, stamp-window)).fetchone()
            if count >= self.limits['recovery_ip_attempts']:
                raise AccessError('恢复请求过于频繁，请稍后重试。',429,max(1,math.ceil(first+window-stamp)))
            db.execute('INSERT INTO recovery_attempts VALUES(?,?)', (ip_hash,stamp))

    def _recovery_secret(self):
        configured = os.environ.get('MCP_RECOVERY_SECRET')
        if configured:
            if len(configured.encode()) < 32: raise ValueError('Recovery secret is too short')
            return configured.encode()
        path = Path(os.environ.get('MCP_RECOVERY_SECRET_FILE', str(self.path.with_suffix('.recovery-secret'))))
        if not path.exists():
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd, temporary = tempfile.mkstemp(prefix='.recovery-',dir=path.parent)
            try:
                with os.fdopen(fd,'wb') as out:
                    out.write(secrets.token_bytes(32)); out.flush(); os.fsync(out.fileno())
                try: os.link(temporary,path)  # Atomic initialization shared by all workers.
                except FileExistsError: pass
            finally: os.unlink(temporary)
        if path.stat().st_mode & 0o077: raise ValueError('Recovery secret file must be private')
        value = path.read_bytes()
        if len(value) < 32: raise ValueError('Recovery secret file is incomplete')
        return value

    def _recoverable(self, db, code, product):
        row = db.execute('''SELECT r.plan,r.redeemed_at,r.key_id,k.key_hash,k.disabled,k.activated_at,
                            e.expires_at,e.expires_type,e.daily_limit,e.total_calls,e.total_used
                            FROM redemption_codes r
                            JOIN api_keys k ON k.id=r.key_id
                            JOIN entitlements e ON e.key_id=k.id AND e.product=? WHERE r.code_hash=?''',
                         (product,digest(code.strip().upper()))).fetchone()
        if not row or not row['redeemed_at'] or PLANS[row['plan']]['product'] != product:
            raise AccessError('兑换码无效或尚未兑换，请核对原兑换码。',400)
        if row['disabled']:
            raise AccessError('该权限已停用，不能恢复；请联系原购买渠道。',403)
        if now() >= datetime.fromisoformat(row['expires_at']):
            raise AccessError('该权限已到期，恢复不会延长套餐；请联系原购买渠道。',403)
        return row

    def recover(self, code, product='qiuzhao', request_id=None):
        if not isinstance(code,str) or len(code)>80:
            raise AccessError('请输入有效兑换码。',400)
        if request_id is not None and (not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',request_id)):
            raise AccessError('恢复请求标识无效，请重新操作。',400)
        secret = self._recovery_secret() if request_id is not None else None
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._recoverable(db,code,product)
            current=now(); stamp=current.timestamp()
            used=db.execute('SELECT used FROM daily_usage WHERE key_id=? AND product=? AND day=?',
                            (row['key_id'],product,current.date().isoformat())).fetchone()
            # Recovery rotates the key only: expires_at/expires_type and total_used are read, never
            # written, so a recovered entitlement keeps its deadline and its consumed total quota.
            result={'product':product,'activated_at':row['activated_at'],'expires_at':row['expires_at'],
                    'expires_type':row['expires_type'],
                    'valid_through':valid_through(row['expires_at']),'daily_limit':row['daily_limit'],
                    'remaining_today':max(0,row['daily_limit']-(used[0] if used else 0)),
                    'total_calls':row['total_calls'],
                    'remaining_total':(max(0,row['total_calls']-row['total_used'])
                                       if row['total_calls'] is not None else None),
                    'can_recover':True}
            if request_id is None: return result
            request_hash=digest(request_id)
            token=PLANS[row['plan']]['key_prefix']+base64.urlsafe_b64encode(hmac.new(secret,
                ('mcp-suite/key-recovery/v1\0'+row['key_id']+'\0'+request_id).encode(),hashlib.sha256).digest()).decode().rstrip('=')
            issued_hash=digest(token)
            previous=db.execute('SELECT issued_hash,at FROM recovery_requests WHERE key_id=? AND request_hash=?',
                                (row['key_id'],request_hash)).fetchone()
            if previous:
                if previous['issued_hash']!=issued_hash or row['key_hash']!=issued_hash:
                    raise AccessError('该恢复请求已被后续恢复替代，请重新校验并操作；旧key不会重新生效。',409)
                if stamp-previous['at']>self.limits['recovery_retry_seconds']:
                    raise AccessError('此恢复重试窗口已结束，请重新校验并操作。',409)
                return {**result,'api_key':token,'replayed':True}
            count,first=db.execute('SELECT COUNT(*),MIN(at) FROM recovery_requests WHERE key_id=? AND at>?',
                                   (row['key_id'],stamp-3600)).fetchone()
            if count>=self.limits['recovery_rotations']:
                raise AccessError(f"同一账号每小时最多重新生成{self.limits['recovery_rotations']}次key，请稍后重试。",429,
                                  max(1,math.ceil(first+3600-stamp)))
            db.execute('UPDATE api_keys SET key_hash=? WHERE id=? AND disabled=0', (issued_hash,row['key_id']))
            db.execute('INSERT INTO recovery_requests VALUES(?,?,?,?)', (row['key_id'],request_hash,issued_hash,stamp))
            return {**result,'api_key':token,'replayed':False}
