"""分销链接记录与佣金统计。

独立于 access.sqlite3 的小账本：谁（推荐人微信号）推来的兑换，按计划售价的
20% 记一笔待结算佣金。只在兑换成功后追加一条记录；从不落兑换码、API key。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
COMMISSION_RATE = 0.20
# 拒绝会破坏展示/注入风险的字符；微信号本身不会出现这些字符。
FORBIDDEN = set('<>"\'`&;\\\n\r\t')


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def clean_referrer(value: str) -> str:
    """清洗推荐人微信号：去空白、限长、拒绝危险字符。"""
    if not isinstance(value, str):
        raise ValueError("推荐人微信号格式非法")
    ref = " ".join(value.split())
    if not ref:
        raise ValueError("推荐人微信号为空")
    if len(ref) > 64:
        raise ValueError("推荐人微信号过长")
    if any(ch in FORBIDDEN for ch in ref):
        raise ValueError("推荐人微信号包含非法字符")
    return ref


class DistributionStore:
    """轻量 sqlite 账本。连接按需建立，首次调用时建表（幂等）。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        # 延迟建库：导入本模块不触碰文件，避免以其他用户启动时把库文件属主写错。
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS distribution_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_wechat TEXT NOT NULL,
                plan TEXT,
                amount_cny REAL,
                commission_cny REAL,
                status TEXT DEFAULT 'pending',
                redeemed_at TEXT,
                created_at TEXT
              );
              CREATE INDEX IF NOT EXISTS idx_distribution_referrer
                ON distribution_records(referrer_wechat);
              CREATE INDEX IF NOT EXISTS idx_distribution_status
                ON distribution_records(status);
            """)
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def commission(amount_cny: float) -> float:
        return round(float(amount_cny) * COMMISSION_RATE, 2)

    def record_referral(self, ref_wechat: str, plan: str, amount_cny: float) -> int:
        """兑换成功后记一条待结算记录，返回新行 id。"""
        ref = clean_referrer(ref_wechat)
        amount = round(float(amount_cny), 2)
        commission = self.commission(amount)
        now = _now()
        with self.connect() as db:
            cur = db.execute(
                """INSERT INTO distribution_records
                   (referrer_wechat, plan, amount_cny, commission_cny, status, redeemed_at, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (ref, plan, amount, commission, "pending", now, now),
            )
            return int(cur.lastrowid)

    def list_records(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, referrer_wechat, plan, amount_cny, commission_cny,
                          status, redeemed_at, created_at
                   FROM distribution_records ORDER BY id DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> dict:
        with self.connect() as db:
            rows = db.execute(
                "SELECT status, COUNT(*) AS n, COALESCE(SUM(commission_cny),0) AS c "
                "FROM distribution_records GROUP BY status"
            ).fetchall()
        agg = {r["status"]: (int(r["n"]), float(r["c"])) for r in rows}
        pending_n, pending_c = agg.get("pending", (0, 0.0))
        settled_n, settled_c = agg.get("settled", (0, 0.0))
        total_n = pending_n + settled_n
        total_c = round(pending_c + settled_c, 2)
        return {
            "total_commission": total_c,
            "settled_commission": round(settled_c, 2),
            "pending_commission": round(pending_c, 2),
            "total_count": total_n,
            "settled_count": settled_n,
            "pending_count": pending_n,
        }
