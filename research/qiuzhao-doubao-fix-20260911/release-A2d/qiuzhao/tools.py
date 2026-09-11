"""Read public, source-linked recruitment records. No generated job facts."""
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from core.store import TZ

MISSING_QUERIES_FILE = Path("/var/lib/mcp-suite/missing_queries.jsonl")


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

    def _record_missing_query(self, **kwargs):
        """记录用户查询但未找到结果的请求，用于后续数据补充。"""
        try:
            query = {k: v for k, v in kwargs.items() if v is not None}
            if not query:
                return
            record = {
                "timestamp": datetime.now(TZ).isoformat(timespec="seconds"),
                "query": query,
                "status": "pending"
            }
            with open(MISSING_QUERIES_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 记录失败不影响查询功能

    def search(self, city=None, major=None, cohort=None, keyword=None, limit=10, offset=0,
               company=None, recruitment_type=None, industry=None, region=None,
               job_category=None, graduation_year=None, major_category=None):
        rows, cutoff = self.load()
        # Echo exactly the conditions the server filters on (blank = no filter), so a caller can
        # tell when its client silently dropped arguments instead of retrying the same call.
        requested = {"city": city, "major": major, "cohort": cohort, "keyword": keyword,
                     "company": company, "recruitment_type": recruitment_type, "industry": industry,
                     "region": region, "job_category": job_category,
                     "graduation_year": graduation_year, "major_category": major_category}
        applied_filters = {k: v.strip() for k, v in requested.items() if isinstance(v, str) and v.strip()}

        def has(query, values):
            return (not query) or (query.strip().casefold() in json.dumps(values, ensure_ascii=False).casefold())

        def matches(row):
            pairs = [
                # city: 同时匹配归一化后的城市和原始城市列表
                (city, [row.get("city_normalized"), row.get("cities", [])]),
                (major, [row.get("major_requirements_raw"), row.get("major_tags")]),
                (cohort, [row.get("cohort_raw") or row.get("campaign_cohort_raw")]),
                (keyword, [row.get(k) for k in ("recruitment_unit", "contracting_entity", "recruiting_unit_raw", "parent_unit_raw", "hiring_department_raw", "job_title", "job_category", "description_raw")]),
                # v3 optional filters; empty/None => no filtering, unknown value not inferred
                (company, [row.get("recruitment_unit"), row.get("contracting_entity"), row.get("recruiting_unit_raw"), row.get("parent_unit_raw")]),
                (recruitment_type, [row.get("recruitment_type"), row.get("recruitment_type_raw"), row.get("nature_raw")]),
                # industry: 匹配企业主体行业标签（industry / industry_tags），不使用job_category岗位职能。
                (industry, [row.get("industry"), row.get("industry_tags")]),
                # region 数据源：使用 cities（城市列表）做地域/城市匹配。
                (region, [row.get("cities", [])]),
                # job_category: 匹配归一化后的岗位大类（技术/研发、产品、运营等）
                (job_category, [row.get("job_category_normalized"), row.get("job_category")]),
                # graduation_year: 匹配归一化后的毕业届别（2025届、2026届、2027届、未披露）
                (graduation_year, [row.get("graduation_year_normalized"), row.get("graduation_year"), row.get("cohort_raw")]),
                # major_category: 匹配归一化后的专业大类（计算机类、电子信息类等）
                (major_category, [row.get("major_normalized"), row.get("major_requirements_raw"), row.get("major_tags")]),
            ]
            return all(has(query, values) for query, values in pairs)
        rows = [r for r in rows if matches(r)]
        rows.sort(key=lambda r: (r.get("published_at") or "", r.get("id") or ""), reverse=True)
        total = len(rows)
        page = rows[offset:offset+limit]

        # 当结果为空且有查询条件时，记录缺失查询
        if not rows and offset == 0 and any([city, major, cohort, keyword, company, recruitment_type, industry, region, job_category, graduation_year, major_category]):
            self._record_missing_query(
                city=city, major=major, cohort=cohort, keyword=keyword,
                company=company, recruitment_type=recruitment_type, industry=industry, region=region,
                job_category=job_category, graduation_year=graduation_year, major_category=major_category
            )

        # applied_filters goes first so clients that truncate long tool output still see it.
        return {"applied_filters": applied_filters,
                **self.envelope(page, cutoff, total=total, offset=offset,
                                next_offset=offset+limit if offset+limit < total else None,
                                suggestion="可放宽专业或届别条件、换城市，或仅按关键词搜索。未披露条件不会被推断。您的查询需求已记录，我们将尽快补充相关企业和岗位数据。" if not rows else None)}

    def deadlines(self, days=7, limit=10, offset=0):
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
        # Nearest deadline first, so what closes today leads page 1; date, full value, then id
        # give a stable order for paging.
        selected.sort(key=lambda r: (r["deadline"][:10], r["deadline"], r.get("id") or ""))
        total = len(selected)
        return self.envelope(selected[offset:offset+limit], cutoff, total=total, days=days,
                             order="deadline_asc", next_offset=offset+limit if offset+limit < total else None,
                             suggestion="未来窗口内没有已披露且有效的截止日期，可扩大天数或用 jobs_search 查询未披露截止日的岗位。" if not selected else None)

    def detail(self, job_id):
        rows, cutoff = self.load()
        found = [r for r in rows if r.get("id") == job_id]
        return self.envelope(found, cutoff, found=bool(found),
                             suggestion="未找到该岗位，请先用 jobs_search 获取最新 id；可放宽条件或换城市。" if not found else None)
