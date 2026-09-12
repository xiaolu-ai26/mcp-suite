"""v4 recruitment queries over public, source-linked records. No generated job facts.

Three operations share one filter set (SPEC 3.0–3.3): search (jobs + match basis), stats (the same
filters, counted and grouped) and detail (by id). The dataset is parsed and converted to v4 fields
(qiuzhao/v4_fields.py) once per jobs.json version: the cache key is the file's mtime and size, so
an unchanged file is never re-read and a replaced file is picked up on the next call. Search
results are ordered by match tier, then by how specific the match is, then by the requested sort
(Jobs.order).
"""
from __future__ import annotations

import gc
import json
import re
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from core.store import TZ
from qiuzhao import v4_fields as V

MISSING_QUERIES_FILE = Path("/var/lib/mcp-suite/missing_queries.jsonl")

PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX = 10, 20
BUDGET_BYTES = 60_000  # bytes of the jobs array; cut at a whole job beyond this
TOP_DEFAULT, TOP_MAX = 20, 100
DETAIL_MAX = 10
DEADLINE_DAYS_MAX = 366
SORTS = ["published_desc", "deadline_asc"]
GROUP_BY = {"company": "company", "city": "city", "job_category": "job_category",
            "graduation_year": "graduation_year", "education": "education", "major_category": "major",
            "industry": "industry", "recruitment_type": "recruitment_type"}
MULTI_VALUED = {"city", "graduation_year"}
TEXT_LIMITS = {"keyword": 100, "company": 100, "city": 100, "major": 50}
GRADUATION_YEAR_CHOICES = V.GRADUATION_YEARS + [V.UNSPECIFIED]

# Spoken forms -> schema values; applied before validation (SPEC 3.0).
SYNONYMS = {
    "job_category": {"技术": "技术/研发", "研发": "技术/研发", "开发": "技术/研发", "技术岗": "技术/研发",
                     "产品经理": "产品", "产品岗": "产品", "市场": "市场/营销", "营销": "市场/营销",
                     "职能": "职能/支持", "支持": "职能/支持", "医疗": "医疗/医药", "医药": "医疗/医药",
                     "制造": "制造/生产", "生产": "制造/生产", "教育": "教育/培训", "培训": "教育/培训",
                     "法律": "法律/合规", "合规": "法律/合规", "法务": "法律/合规"},
    "recruitment_type": {"校招": "校园招聘", "校园": "校园招聘", "秋招": "校园招聘", "春招": "校园招聘",
                         "实习": "实习招聘", "日常实习": "实习招聘", "暑期实习": "实习招聘",
                         "社招": "社会招聘", "社会": "社会招聘"},
    "education": {"研究生": "硕士", "硕士研究生": "硕士", "博士研究生": "博士", "专科": "大专", "高职": "大专",
                  "学士": "本科", "大学本科": "本科", "中专": "中专及以下", "高中": "中专及以下", "无要求": "不限",
                  "未披露": V.UNSPECIFIED},
    "industry": {"互联网": "互联网/科技", "科技": "互联网/科技", "国企": "国企/央企", "央企": "国企/央企",
                 "制造": "制造/工业", "工业": "制造/工业", "能源": "能源/电力", "电力": "能源/电力",
                 "医药": "医药/医疗", "医疗": "医药/医疗", "物流": "物流/运输", "运输": "物流/运输",
                 "传媒": "传媒/广告", "广告": "传媒/广告", "消费": "消费/零售", "零售": "消费/零售"},
    "graduation_year": {"未披露": V.UNSPECIFIED},
}
CATEGORY_HINT = "找具体岗位名（如游戏策划、UI设计）请用 keyword。"
FILTER_DEFAULTS = {"keyword": "", "company": "", "city": "", "job_category": "", "graduation_year": "",
                   "major": "", "education": "", "recruitment_type": "", "industry": "",
                   "deadline_within_days": 0, "explicit_only": False, "include_expired": False}
EMPTY_SUGGESTION = ("没有符合条件的岗位。可去掉 explicit_only、放宽城市/专业/届别，"
                    "或先用 jobs_stats 看各条件下的数量。")


class ParamError(ValueError):
    """A caller-fixable argument problem; the message is shown to the model as is."""


def split_multi(value):
    return [v.strip() for v in re.split(r"[,，、;；|]", value or "") if v.strip()]


def nbytes(obj):
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode())


iter_json_file = V.iter_json_file  # chunked reader: one raw row alive at a time


class Dataset:
    """One immutable, fully converted version of jobs.json."""
    __slots__ = ("key", "items", "by_id", "keyword_text", "company_text", "data_as_of", "report",
                 "build_seconds", "loaded_at")

    def __init__(self, key, items, data_as_of, report, build_seconds):
        # Published date desc, then id desc: the default order, so filtering keeps it for free.
        items.sort(key=lambda it: (it["published_at"] or "", it["id"]), reverse=True)
        self.key = key
        self.items = items
        self.by_id = {it["id"]: it for it in items}
        # Case-folded haystacks, built once instead of on every keyword/company query.
        self.keyword_text = ["\n".join(str(it.get(f, "")) for f in V.KEYWORD_FIELDS).casefold() for it in items]
        self.company_text = ["\n".join(str(it.get(f, "")) for f in V.COMPANY_FIELDS).casefold() for it in items]
        self.data_as_of = data_as_of
        self.report = report
        self.build_seconds = build_seconds
        self.loaded_at = datetime.now(TZ).isoformat(timespec="seconds")


class Jobs:
    def __init__(self, path, today=None):
        self.path = Path(path)
        # Fixed "today" only for reproducible tests (MCP_TODAY); production follows the clock.
        self._today = date.fromisoformat(today) if isinstance(today, str) else today
        self._data = None
        self._failed_key = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ loading

    def today(self):
        return self._today or datetime.now(TZ).date()

    def dataset(self):
        """The converted dataset for the current file; rebuilt only when mtime/size change.

        A file that cannot be parsed (e.g. caught mid-write) never replaces a good cache: the last
        good version keeps serving and the broken version is not retried until the file changes.
        """
        try:
            st = self.path.stat()
        except FileNotFoundError:
            raise FileNotFoundError("岗位数据尚未就绪") from None
        key = (st.st_mtime_ns, st.st_size)
        data = self._data
        if data is not None and (data.key == key or self._failed_key == key):
            return data
        with self._lock:
            data = self._data
            if data is not None and (data.key == key or self._failed_key == key):
                return data
            started = time.perf_counter()
            try:
                items, as_of, report = V.build(iter_json_file(self.path))
            except (ValueError, OSError):
                if data is None:
                    raise
                self._failed_key = key
                return data
            self._data = None  # let the previous version go before the new one is indexed
            del data
            self._data = Dataset(key, items, as_of, report, round(time.perf_counter() - started, 3))
            self._failed_key = None
            gc.collect()
            return self._data

    def health(self):
        data = self.dataset()
        return {"status": "ok", "jobs": len(data.items), "data_as_of": data.data_as_of}

    # ------------------------------------------------------------ arguments

    @staticmethod
    def _text(name, value):
        value = "" if value is None else str(value).strip()
        if len(value) > TEXT_LIMITS[name]:
            raise ParamError(f"参数 {name} 最长 {TEXT_LIMITS[name]} 个字，本次 {len(value)} 个字。请缩短后重试。")
        return value

    @staticmethod
    def _choice(name, value, allowed, notices, hint=""):
        raw = "" if value is None else str(value).strip()
        if not raw:
            return ""
        v = raw
        if name == "graduation_year" and "未" not in v:
            m = re.match(r"(20)?(\d{2})(?!\d)\s*(?:届|年)?", v)
            if m:
                v = f"20{m.group(2)}届"
        v = SYNONYMS.get(name, {}).get(v, v)
        if v not in allowed and not (name == "graduation_year" and re.fullmatch(r"20\d{2}届", v)):
            if name == "graduation_year" and raw in (V.NOTE_INTERN, V.NOTE_SOCIAL):
                hint = "“实习未写届别”“社招不限届别”不是届别：要看这些岗位请改用 recruitment_type。"
            raise ParamError(f"参数 {name} 的值「{raw}」不在可选范围。可选：{'、'.join(allowed)}。{hint}".rstrip())
        if v != raw:
            notices.append(f"参数 {name} 的值「{raw}」已按「{v}」处理。")
        return v

    @staticmethod
    def _int(name, value, default, low, high=None):
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise ParamError(f"参数 {name} 应为整数。")
        if value < low or (high is not None and value > high):
            rng = f"{low}–{high}" if high is not None else f"不小于 {low} 的整数"
            raise ParamError(f"参数 {name} 取 {rng}，本次为 {value}。")
        return value

    def check_filters(self, args, notices):
        f = {**FILTER_DEFAULTS, **{k: v for k, v in args.items() if k in FILTER_DEFAULTS and v is not None}}
        for name in TEXT_LIMITS:
            f[name] = self._text(name, f[name])
        f["job_category"] = self._choice("job_category", f["job_category"], V.JOB_CATEGORIES, notices, CATEGORY_HINT)
        f["graduation_year"] = self._choice("graduation_year", f["graduation_year"], GRADUATION_YEAR_CHOICES, notices)
        f["education"] = self._choice("education", f["education"], V.EDUCATIONS, notices)
        f["recruitment_type"] = self._choice("recruitment_type", f["recruitment_type"], V.RECRUITMENT_TYPES, notices)
        f["industry"] = self._choice("industry", f["industry"], V.INDUSTRIES, notices)
        days = f["deadline_within_days"]
        if isinstance(days, bool) or not isinstance(days, int) or not 0 <= days <= DEADLINE_DAYS_MAX:
            raise ParamError(f"参数 deadline_within_days 取 1–{DEADLINE_DAYS_MAX}（今天起 N 天内截止），"
                             f"不筛截止日时不传或传 0。本次为 {days}。")
        f["explicit_only"] = bool(f["explicit_only"])
        f["include_expired"] = bool(f["include_expired"])
        cities = split_multi(f["city"])
        normalized = [V.norm_city(c) for c in cities]
        if normalized != cities:
            notices.append(f"参数 city 的值「{f['city']}」已按「{','.join(normalized)}」处理。")
        f["city"] = ",".join(normalized)
        if f["explicit_only"] and V.UNSPECIFIED in (f["graduation_year"], f["education"], f["major"], *normalized):
            raise ParamError("explicit_only=true 与取值「未注明」矛盾：只看明确匹配时不能再筛未注明。"
                             "请去掉其中一个再调用。")
        return f

    @staticmethod
    def applied(f, **extra):
        out = {k: v for k, v in f.items() if v not in ("", 0, False, None)}
        out.update((k, v) for k, v in extra.items() if v not in ("", None))
        return out

    # ------------------------------------------------------------ matching

    @staticmethod
    def _m_city(it, qs):
        cities = it["cities"]
        if qs == [V.UNSPECIFIED]:
            return V.UNSPECIFIED if not cities else None
        if any(q in cities for q in qs):
            return "岗位写明"
        # 全国 = mainland China: counts for a mainland city query, never for 新加坡/香港.
        if "全国" in cities and any(q not in ("全国", V.UNSPECIFIED) and V.city_region(q) == "中国大陆" for q in qs):
            return "全国"
        return V.UNSPECIFIED if not cities else None

    @staticmethod
    def _m_major(it, q):
        mc = it["major_category"]
        if q == V.UNSPECIFIED:
            return V.UNSPECIFIED if mc == V.UNSPECIFIED else None
        if q == "不限":
            return "专业不限" if mc == "不限" else None
        if mc == "不限":
            return "专业不限"
        if mc == V.UNSPECIFIED:
            return V.UNSPECIFIED
        core = q[:-1] if q.endswith("类") and len(q) > 2 else q
        text = (it.get("major_requirements_raw", "") + " " + " ".join(it.get("major_tags", []))).casefold()
        return "岗位写明" if mc == q or core.casefold() in text else None

    @staticmethod
    def _m_edu(it, q):
        e = it["education"]
        if q == V.UNSPECIFIED:
            return V.UNSPECIFIED if e == V.UNSPECIFIED else None
        if q == "不限":
            return "学历不限" if e == "不限" else None
        if e == "不限":
            return "学历不限"
        if e == V.UNSPECIFIED:
            return V.UNSPECIFIED
        return "岗位写明" if V.EDU_RANK[e] <= V.EDU_RANK[q] else None

    @staticmethod
    def _m_grad(it, q, social_ok):
        """Basis, None (no match) or the string 'excluded_social'."""
        years, note = it["graduation_years"], it.get("graduation_year_note", "")
        if q == V.UNSPECIFIED:
            return V.UNSPECIFIED if note == V.UNSPECIFIED else None
        constraints = it.get('graduation_year_constraints') or {}
        if constraints:
            year = int(q[:4])
            if year in constraints.get('excluded_years', []):
                return None
            if year >= constraints['min_year'] and (constraints.get('max_year') is None or year <= constraints['max_year']):
                return constraints['basis']
        if q in years:
            return it["graduation_year_basis"][q]
        if years:
            # Only an inferred 届 (season / source scope): the posting names no cohort, so another 届
            # is not ruled out and stays unspecified. A stated 届 rules the row out.
            if all(V.BASIS_TIER[b] == 1 for b in it["graduation_year_basis"].values()):
                return V.INFERRED_OTHER
            return None
        if note == V.NOTE_INTERN:
            return V.NOTE_INTERN
        if note == V.NOTE_SOCIAL:
            return V.NOTE_SOCIAL if social_ok else "excluded_social"
        return V.UNSPECIFIED

    def evaluate(self, data, f, today):
        """[(item, basis, tier)] in default order, plus how many 社招 rows the 届别 filter excluded."""
        today_s = today.isoformat()
        end = (today + timedelta(days=f["deadline_within_days"])).isoformat() if f["deadline_within_days"] else None
        cities = split_multi(f["city"])
        companies = [c.casefold() for c in split_multi(f["company"])]
        keyword = f["keyword"].casefold()
        major, edu, grad = f["major"], f["education"], f["graduation_year"]
        social_ok = f["recruitment_type"] == "社会招聘"
        jc, rt, ind = f["job_category"], f["recruitment_type"], f["industry"]
        include_expired, explicit_only = f["include_expired"], f["explicit_only"]
        out, excluded_social = [], 0
        kw_text, co_text = data.keyword_text, data.company_text
        for i, it in enumerate(data.items):
            if (jc and it["job_category"] != jc) or (rt and it["recruitment_type"] != rt) \
                    or (ind and it["industry"] != ind):
                continue
            deadline = it["deadline"]
            if not include_expired and deadline and deadline < today_s:
                continue
            if end and not (deadline and today_s <= deadline <= end):
                continue
            if companies and not any(c in co_text[i] for c in companies):
                continue
            if keyword and keyword not in kw_text[i]:
                continue
            basis = {}
            if cities:
                b = self._m_city(it, cities)
                if b is None:
                    continue
                basis["city"] = b
            if major:
                b = self._m_major(it, major)
                if b is None:
                    continue
                basis["major"] = b
            if edu:
                b = self._m_edu(it, edu)
                if b is None:
                    continue
                basis["education"] = b
            if grad:
                b = self._m_grad(it, grad, social_ok)
                if b is None:
                    continue
                if b == "excluded_social":
                    excluded_social += not explicit_only
                    continue
                basis = {"graduation_year": b, **basis}
            tier = max((V.BASIS_TIER[b] for b in basis.values()), default=0)
            if explicit_only and tier:
                continue
            out.append((it, basis, tier))
        return out, excluded_social

    @staticmethod
    def totals(res):
        tiers = Counter(t for _, _, t in res)
        return {"total": len(res), "explicit_total": tiers[0], "inferred_total": tiers[1],
                "unspecified_total": tiers[2]}

    @staticmethod
    def public(it, today, basis=None, tier=0):
        out = {"id": it["id"]}
        if basis:
            out["match"] = {"level": V.LEVELS[tier], **basis}
        out.update((k, v) for k, v in it.items() if k != "id")
        out["status"] = V.status_on(it, today)
        return out

    @staticmethod
    def _record_missing_query(query):
        """Zero-result searches, kept for later data collection. Never breaks a query."""
        try:
            if not query:
                return
            record = {"timestamp": datetime.now(TZ).isoformat(timespec="seconds"), "query": query,
                      "status": "pending"}
            with open(MISSING_QUERIES_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _social_notice(self, f, excluded, notices, out, verb):
        if f["graduation_year"] and not f["explicit_only"] and f["recruitment_type"] != "社会招聘":
            out["excluded_social_total"] = excluded
            if excluded:
                notices.append(f"另有 {excluded} 条社会招聘岗位未{verb}：社招不限届别，按届别筛选时不返回；"
                               "要看请加 recruitment_type=社会招聘。")

    @staticmethod
    def order(res, sort):
        """Tier, then how specific the match is (V.RANK_DIMENSIONS / V.BASIS_RANK), then ``sort``.

        ``res`` comes from evaluate() in the dataset's default order (published desc, id desc),
        which the stable sort keeps for published_desc; deadline_asc ends on the id, so both orders
        are total. Every row carries the query's dimensions, so they are read off the first row.
        """
        dims = [d for d in V.RANK_DIMENSIONS if d in res[0][1]] if res else []
        rank = V.BASIS_RANK
        if sort == "deadline_asc":
            return sorted(res, key=lambda x: (x[2], [rank[x[1][d]] for d in dims], x[0]["deadline"] is None,
                                              x[0]["deadline"] or "", x[0]["id"]))
        if not dims:
            return res  # no 届别/城市/专业/学历 condition: a single tier, already in default order
        return sorted(res, key=lambda x: (x[2], [rank[x[1][d]] for d in dims]))

    # ------------------------------------------------------------ the three operations

    def search(self, sort="published_desc", page_size=PAGE_SIZE_DEFAULT, offset=0, **filters):
        notices = []
        data = self.dataset()
        f = self.check_filters(filters, notices)
        sort = (sort or "published_desc").strip() if isinstance(sort, str) else sort
        if sort not in SORTS:
            raise ParamError(f"参数 sort 的值「{sort}」不在可选范围。可选：{'、'.join(SORTS)}。")
        page_size = self._int("page_size", page_size, PAGE_SIZE_DEFAULT, 1)
        offset = self._int("offset", offset, 0, 0)
        if page_size > PAGE_SIZE_MAX:
            notices.append(f"page_size={page_size} 超过上限 {PAGE_SIZE_MAX}，本次按 {PAGE_SIZE_MAX} 返回，"
                           "用 next_offset 翻页。")
            page_size = PAGE_SIZE_MAX
        today = self.today()
        res, excluded_social = self.evaluate(data, f, today)
        res = self.order(res, sort)
        jobs, used, truncated = [], 2, False
        for it, basis, tier in res[offset:offset + page_size]:
            obj = self.public(it, today, basis, tier)
            size = nbytes(obj) + 1
            if jobs and used + size > BUDGET_BYTES:
                truncated = True
                break
            jobs.append(obj)
            used += size
        counts = self.totals(res)
        returned = len(jobs)
        next_offset = offset + returned if offset + returned < counts["total"] else None
        applied = self.applied(f, sort=sort if sort != "published_desc" else "")
        out = {"applied_filters": applied, **counts}
        self._social_notice(f, excluded_social, notices, out, "返回")
        out.update({"sort": sort, "offset": offset, "page_size": page_size, "returned": returned,
                    "has_next": next_offset is not None, "next_offset": next_offset, "truncated": truncated,
                    "data_as_of": data.data_as_of})
        if notices:
            out["notices"] = notices
        if not counts["total"]:
            out["suggestion"] = EMPTY_SUGGESTION
            if offset == 0:
                self._record_missing_query(applied)
        out["jobs"] = jobs
        return out

    @staticmethod
    def group_values(it, group_by):
        if group_by == "city":
            return it["cities"] or [V.UNSPECIFIED]
        if group_by == "graduation_year":
            return it["graduation_years"] or [it.get("graduation_year_note") or V.UNSPECIFIED]
        return [it[group_by] or V.UNSPECIFIED]

    @staticmethod
    def group_tier(it, group_by, value):
        """How firmly the row has this group value: 未注明 groups are unspecified, and a 届别 group
        is as firm as the row's basis for that year (按招聘季推断 → inferred)."""
        if value == V.UNSPECIFIED:
            return 2
        if group_by == "graduation_year":
            basis = it["graduation_year_basis"].get(value)
            return V.BASIS_TIER[basis] if basis else V.BASIS_TIER.get(value, 0)
        return 0

    def stats(self, group_by="", top=TOP_DEFAULT, **filters):
        notices = []
        data = self.dataset()
        f = self.check_filters(filters, notices)
        group_by = (group_by or "").strip() if isinstance(group_by, str) else group_by
        if group_by and group_by not in GROUP_BY:
            raise ParamError(f"参数 group_by 的值「{group_by}」不在可选范围。可选：{'、'.join(GROUP_BY)}。"
                             "不分组时不传。")
        top = self._int("top", top, TOP_DEFAULT, 1)
        if top > TOP_MAX:
            notices.append(f"top={top} 超过上限 {TOP_MAX}，本次按 {TOP_MAX} 返回。")
            top = TOP_MAX
        res, excluded_social = self.evaluate(data, f, self.today())
        out = {"applied_filters": self.applied(f), **self.totals(res)}
        self._social_notice(f, excluded_social, notices, out, "计入")
        out["data_as_of"] = data.data_as_of
        if group_by:
            counts, tiers = Counter(), (Counter(), Counter(), Counter())
            for it, _, tier in res:
                for v in self.group_values(it, group_by):
                    counts[v] += 1
                    tiers[max(tier, self.group_tier(it, group_by, v))][v] += 1
            ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            out.update({"group_by": group_by, "fill_param": GROUP_BY[group_by],
                        "multi_valued": group_by in MULTI_VALUED, "groups_total": len(ordered),
                        "returned_groups": min(top, len(ordered)),
                        "other_count": sum(c for _, c in ordered[top:])})
            if notices:
                out["notices"] = notices
            out["groups"] = [{"value": v, "count": c, "explicit_count": tiers[0][v],
                              "inferred_count": tiers[1][v], "unspecified_count": tiers[2][v]}
                             for v, c in ordered[:top]]
        elif notices:
            out["notices"] = notices
        return out

    def detail(self, ids):
        data = self.dataset()
        wanted = []
        for i in split_multi(ids if isinstance(ids, str) else ""):
            if i not in wanted:
                wanted.append(i)
        if not wanted:
            raise ParamError("参数 ids 不能为空：传 1–10 个 jobs_search 返回的 jobs[i].id，用英文逗号分隔。")
        if len(wanted) > DETAIL_MAX:
            raise ParamError(f"参数 ids 最多 {DETAIL_MAX} 个，本次收到 {len(wanted)} 个。请分批调用。")
        today = self.today()
        found = [self.public(data.by_id[i], today) for i in wanted if i in data.by_id]
        missing = [i for i in wanted if i not in data.by_id]
        out = {"requested": len(wanted), "found": len(found), "not_found": missing, "data_as_of": data.data_as_of}
        if missing:
            out["suggestion"] = "not_found 里的 id 不存在或已下线，请重新用 jobs_search 查询最新 id。"
        out["jobs"] = found
        return out
