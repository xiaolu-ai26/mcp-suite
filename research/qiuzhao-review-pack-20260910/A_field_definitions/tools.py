"""Read public, source-linked recruitment records. No generated job facts."""
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from core.store import TZ


class Jobs:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.is_file():
            raise FileNotFoundError("岗位数据尚未就绪")
        rows = json.loads(self.path.read_text())
        if not isinstance(rows, list):
            raise ValueError("岗位库格式异常，请稍后重试")
        # An unavailable or malformed dataset must never silently turn into fake jobs.
        valid = [row for row in rows if row.get("source_url") and row.get("application_url")]
        cutoff = max((r.get("reviewed_at") or "" for r in valid), default="") or None
        return valid, cutoff

    @staticmethod
    def public(row):
        item = {k: v for k, v in row.items() if not k.endswith("evidence_path")}
        item["cohort_filter_scope"] = (item.get("cohort_scope") or "role_record") if item.get("cohort_raw") else ("campaign_title_only" if item.get("campaign_cohort_raw") else "undisclosed")
        deadline = item.get("deadline")
        if deadline and item.get("status") != "removed" and deadline[:10] < datetime.now(TZ).date().isoformat():
            item["status"] = "expired"
        return item

    def envelope(self, rows, cutoff, **extra):
        return {"data_as_of": cutoff, "数据截至时间": cutoff,
                "source_urls": sorted({r["source_url"] for r in rows}),
                "jobs": [self.public(r) for r in rows], **extra}

    def search(self, city=None, major=None, cohort=None, keyword=None, limit=50, offset=0):
        rows, cutoff = self.load()
        def matches(row):
            pairs = [(city, [row.get("cities", [])]),
                     (major, [row.get("major_requirements_raw"), row.get("major_tags")]),
                     (cohort, [row.get("cohort_raw") or row.get("campaign_cohort_raw")]),
                     (keyword, [row.get(k) for k in ("recruitment_unit", "contracting_entity", "recruiting_unit_raw", "parent_unit_raw", "hiring_department_raw", "job_title", "job_category", "description_raw")])]
            return all(not query or query.strip().casefold() in json.dumps(values, ensure_ascii=False).casefold()
                       for query, values in pairs)
        rows = [r for r in rows if matches(r)]
        rows.sort(key=lambda r: (r.get("published_at") or "", r.get("id") or ""), reverse=True)
        total = len(rows)
        page = rows[offset:offset+limit]
        return self.envelope(page, cutoff, total=total, offset=offset,
                             next_offset=offset+limit if offset+limit < total else None,
                             suggestion="可放宽专业或届别条件、换城市，或仅按关键词搜索。未披露条件不会被推断。" if not rows else None)

    def deadlines(self, days=7, limit=100, offset=0):
        rows, cutoff = self.load()
        today = datetime.now(TZ).date()
        end = today + timedelta(days=days)
        selected = []
        for row in rows:
            if row.get("deadline_type") != "explicit" or row.get("status") in {"removed", "expired", "unverified"}:
                continue
            try:
                deadline = date.fromisoformat(row.get("deadline", "")[:10])
            except (ValueError, TypeError):
                continue
            if today <= deadline <= end:
                selected.append(row)
        selected.sort(key=lambda r: (r["deadline"], r.get("id", "")), reverse=True)
        total = len(selected)
        return self.envelope(selected[offset:offset+limit], cutoff, total=total, days=days,
                             order="deadline_desc", next_offset=offset+limit if offset+limit < total else None,
                             suggestion="未来窗口内没有已披露且有效的截止日期，可扩大天数或用 jobs_search 查询未披露截止日的岗位。" if not selected else None)

    def detail(self, job_id):
        rows, cutoff = self.load()
        found = [r for r in rows if r.get("id") == job_id]
        return self.envelope(found, cutoff, found=bool(found),
                             suggestion="未找到该岗位，请先用 jobs_search 获取最新 id；可放宽条件或换城市。" if not found else None)
