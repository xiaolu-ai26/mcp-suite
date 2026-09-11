#!/usr/bin/env python3
"""订单 → 兑换码分配台账（与生产鉴权库完全独立）。

设计依据：/tmp/v3pack/qiuzhao-delivery-v3/docs/FULFILLMENT.md

安全原则：
- 只保存兑换码的 SHA256 完整哈希（code_hash）、前 4 位明文前缀（code_prefix，仅人工核对）
  与哈希前 8 位引用（code_reference）；从不保存完整明文兑换码。
- 本台账数据库与 private/access.sqlite3 物理分开：不连接、不写入、不读取生产鉴权库内容。
- 分配走 SQLite 事务（BEGIN IMMEDIATE）+ UNIQUE 约束，幂等：
  同一 (channel, order_number) 重复 allocate 返回原绑定，绝不重复分码、绝不把码释放给别人。
- 发送失败标 retry，不释放码；正式码明文仅在调用方内存中临时存在。

套餐：39 元/秋招季，每日 200 次，有效至 2026-12-31（北京时间）。
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

CST = timezone(timedelta(hours=8))

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    order_number TEXT NOT NULL,
    product_sku TEXT,
    quantity INTEGER DEFAULT 1,
    code_reference TEXT,
    code_hash TEXT,
    status TEXT NOT NULL DEFAULT 'available',
    allocated_at TEXT,
    sent_at TEXT,
    sent_channel TEXT,
    redeemed_at TEXT,
    refund_status TEXT DEFAULT 'none',
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(channel, order_number)
);
CREATE TABLE IF NOT EXISTS code_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_hash TEXT UNIQUE NOT NULL,
    code_prefix TEXT,
    status TEXT DEFAULT 'available',
    order_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
"""

# 订单/库存允许的状态机
ORDER_STATES = {"available", "allocated", "sent", "redeemed", "retry", "refunded"}
CODE_STATES = {"available", "allocated", "sent", "redeemed"}


class LedgerError(Exception):
    pass


class InsufficientStock(LedgerError):
    pass


class OrderNotFound(LedgerError):
    pass


def _now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Ledger:
    """独立订单台账。路径默认 order_ledger/order_ledger.sqlite3，权限 0600。"""

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        os.chmod(self.path, 0o600)
        with self.connect() as db:
            db.executescript(SCHEMA)
        # WAL 边车文件同样收紧（本实现默认不用 WAL，但兜底收紧一次）
        for suffix in ("-wal", "-shm", "-journal"):
            side = Path(str(self.path) + suffix)
            if side.exists():
                try:
                    os.chmod(side, 0o600)
                except OSError:
                    pass

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    # ---------- a. 入库 ----------
    def add_code(self, code: str) -> dict:
        """把一枚兑换码加入库存：仅存 SHA256 哈希 + 前 4 位前缀，不存明文。

        重复添加同一枚码（哈希已存在）视为幂等成功，不报错。
        """
        code = code.strip()
        code_hash = sha256_hex(code)
        prefix = code[:4]
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO code_inventory(code_hash, code_prefix, status) VALUES(?,?,'available')",
                (code_hash, prefix),
            )
        return {"code_hash": code_hash, "code_reference": code_hash[:8], "code_prefix": prefix}

    # ---------- b. 原子分配 ----------
    def allocate(self, channel: str, order_number: str, quantity: int = 1,
                 product_sku: str | None = None, notes: str | None = None) -> dict:
        """把 quantity 枚可用码原子绑定到 (channel, order_number)。

        幂等：同 (channel, order_number) 再次调用直接返回原绑定，不分配新码、不释放旧码。
        库存不足抛 InsufficientStock（整事务回滚）。
        """
        channel = channel.strip()
        order_number = order_number.strip()
        if not channel or not order_number:
            raise LedgerError("channel 与 order_number 不能为空")
        if quantity < 1:
            raise LedgerError("quantity 必须 >= 1")

        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM orders WHERE channel=? AND order_number=?",
                (channel, order_number),
            ).fetchone()
            if existing:
                linked = db.execute(
                    "SELECT id, code_prefix, code_hash, status, order_id FROM code_inventory WHERE order_id=?",
                    (existing["id"],),
                ).fetchall()
                db.execute("UPDATE orders SET updated_at=? WHERE id=?", (_now_iso(), existing["id"]))
                return {
                    "order_id": existing["id"],
                    "reused": True,
                    "status": existing["status"],
                    "codes": [
                        {"code_reference": r["code_hash"][:8], "code_prefix": r["code_prefix"], "status": r["status"]}
                        for r in linked
                    ],
                }

            picked = db.execute(
                "SELECT code_hash FROM code_inventory WHERE status='available' ORDER BY id LIMIT ?",
                (quantity,),
            ).fetchall()
            if len(picked) < quantity:
                raise InsufficientStock(
                    f"可用码不足：需要 {quantity}，仅剩 {len(picked)}"
                )

            now = _now_iso()
            cur = db.execute(
                """INSERT INTO orders(channel, order_number, product_sku, quantity, status,
                                       allocated_at, notes, created_at, updated_at)
                   VALUES(?,?,?,?, 'allocated', ?, ?, ?, ?)""",
                (channel, order_number, product_sku, quantity, now, notes, now, now),
            )
            order_id = cur.lastrowid

            claimed = []
            for row in picked:
                upd = db.execute(
                    "UPDATE code_inventory SET status='allocated', order_id=? WHERE code_hash=? AND status='available'",
                    (order_id, row["code_hash"]),
                )
                if upd.rowcount != 1:
                    raise LedgerError("分配竞争失败，整单回滚")
                claimed.append(row["code_hash"])

            first_hash = claimed[0]
            db.execute(
                "UPDATE orders SET code_hash=?, code_reference=? WHERE id=?",
                (first_hash, first_hash[:8], order_id),
            )
            db.commit()
            return {
                "order_id": order_id,
                "reused": False,
                "status": "allocated",
                "codes": [
                    {"code_reference": h[:8], "code_prefix": self._prefix_of(db, h), "status": "allocated"}
                    for h in claimed
                ],
            }

    @staticmethod
    def _prefix_of(db, code_hash: str) -> str | None:
        r = db.execute("SELECT code_prefix FROM code_inventory WHERE code_hash=?", (code_hash,)).fetchone()
        return r["code_prefix"] if r else None

    # ---------- c. 标记已发送 ----------
    def mark_sent(self, order_id: int, sent_channel: str) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                raise OrderNotFound(f"订单 {order_id} 不存在")
            now = _now_iso()
            db.execute(
                "UPDATE orders SET status='sent', sent_at=?, sent_channel=?, updated_at=? WHERE id=?",
                (now, sent_channel.strip(), now, order_id),
            )
            db.execute(
                "UPDATE code_inventory SET status='sent' WHERE order_id=? AND status='allocated'",
                (order_id,),
            )
            db.commit()
            return {"order_id": order_id, "status": "sent", "sent_at": now, "sent_channel": sent_channel.strip()}

    def mark_send_failed(self, order_id: int, reason: str = "") -> dict:
        """发送失败：标 retry，码仍绑定该订单，绝不释放回可售库存。"""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                raise OrderNotFound(f"订单 {order_id} 不存在")
            now = _now_iso()
            note = (row["notes"] or "") + f" | send_retry@{now}: {reason}"
            db.execute(
                "UPDATE orders SET status='retry', notes=?, updated_at=? WHERE id=?",
                (note.strip(" |"), now, order_id),
            )
            db.commit()
            return {"order_id": order_id, "status": "retry", "note": reason}

    # ---------- d. 兑换状态只读核对 ----------
    def check_redeemed(self, order_id: int, probe: Callable[[str], bool] | None = None) -> dict:
        """核对订单下的码是否已被兑换。

        probe: 入参 code_hash，返回该码在**权威服务端**是否已兑换。
               生产环境应由服务端只读接口/只读连接提供；本台账绝不直接读生产鉴权库明文。
               若不传 probe，则只返回台账自身记录的状态。
        核对为已兑换时，把订单与关联码流转到 redeemed（服务端事实为准，台账只读落账）。
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                raise OrderNotFound(f"订单 {order_id} 不存在")
            codes = db.execute(
                "SELECT code_hash FROM code_inventory WHERE order_id=?", (order_id,)
            ).fetchall()
            redeemed_hashes = []
            pending_hashes = []
            for c in codes:
                h = c["code_hash"]
                if probe is None:
                    done = row["status"] == "redeemed"
                else:
                    done = bool(probe(h))
                (redeemed_hashes if done else pending_hashes).append(h)

            if redeemed_hashes and row["status"] != "redeemed":
                now = _now_iso()
                db.execute(
                    "UPDATE orders SET status='redeemed', redeemed_at=?, updated_at=? WHERE id=?",
                    (now, now, order_id),
                )
                qmarks = ",".join("?" for _ in redeemed_hashes)
                db.execute(
                    f"UPDATE code_inventory SET status='redeemed' WHERE code_hash IN ({qmarks})",
                    redeemed_hashes,
                )
            db.commit()
            fresh = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            return {
                "order_id": order_id,
                "status": fresh["status"],
                "redeemed_at": fresh["redeemed_at"],
                "redeemed_codes": [h[:8] for h in redeemed_hashes],
                "pending_codes": [h[:8] for h in pending_hashes],
                "probe_used": probe is not None,
            }

    # ---------- e. 状态统计 ----------
    def list_status(self) -> dict:
        with self.connect() as db:
            orders_by_status = {
                r["status"]: r["n"]
                for r in db.execute("SELECT status, COUNT(*) n FROM orders GROUP BY status")
            }
            codes_by_status = {
                r["status"]: r["n"]
                for r in db.execute("SELECT status, COUNT(*) n FROM code_inventory GROUP BY status")
            }
            total = db.execute("SELECT COUNT(*) n FROM code_inventory").fetchone()["n"]
            return {
                "orders": orders_by_status,
                "code_inventory": codes_by_status,
                "code_total": total,
            }

    # ---------- f. 公开视图（不含明文、不含完整哈希） ----------
    def export_public_view(self) -> list[dict]:
        rows = []
        with self.connect() as db:
            for r in db.execute(
                """SELECT id, channel, order_number, product_sku, quantity, code_reference,
                          status, allocated_at, sent_at, sent_channel, redeemed_at, refund_status, notes
                   FROM orders ORDER BY id"""
            ):
                rows.append({k: r[k] for k in r.keys()})
        return rows

    def write_public_view(self, out_path: str | Path) -> Path:
        import json
        out = Path(out_path)
        out.write_text(json.dumps(self.export_public_view(), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(out, 0o600)
        except OSError:
            pass
        return out


# ---------- 简易 CLI ----------
def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="订单→兑换码分配台账管理")
    ap.add_argument("--db", default=str(Path(__file__).resolve().parent / "order_ledger.sqlite3"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="各状态统计")
    sub.add_parser("export", help="导出公开视图到 public_view.json")

    p_add = sub.add_parser("add-code", help="入库一枚码（仅哈希）")
    p_add.add_argument("code")

    p_alloc = sub.add_parser("allocate", help="原子分配（幂等）")
    p_alloc.add_argument("channel")
    p_alloc.add_argument("order_number")
    p_alloc.add_argument("--qty", type=int, default=1)
    p_alloc.add_argument("--sku", default=None)

    p_sent = sub.add_parser("mark-sent")
    p_sent.add_argument("order_id", type=int)
    p_sent.add_argument("sent_channel")

    args = ap.parse_args(argv)
    led = Ledger(args.db)
    if args.cmd == "status":
        import json
        print(json.dumps(led.list_status(), ensure_ascii=False, indent=2))
    elif args.cmd == "export":
        p = led.write_public_view(Path(args.db).parent / "public_view.json")
        print(f"已导出: {p}")
    elif args.cmd == "add-code":
        print(led.add_code(args.code))
    elif args.cmd == "allocate":
        import json
        print(json.dumps(led.allocate(args.channel, args.order_number, args.qty, args.sku),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "mark-sent":
        print(led.mark_sent(args.order_id, args.sent_channel))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
