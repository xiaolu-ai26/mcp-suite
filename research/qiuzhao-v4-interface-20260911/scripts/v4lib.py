"""秋招 MCP v4 说明书的参考规则实现。

只读 ../qiuzhao-doubao-fix-20260911/data/jobs.json，用来复现 SPEC.md 里的数字和生成 examples/。
这不是服务端代码，不部署。所有"修正后"的字段（届别依据、学历档、城市修复、类目修正、截止日统一、
状态统一）都是按 SPEC.md 第 6 节规则在本地模拟的，线上数据和代码还没有这些字段。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "qiuzhao-doubao-fix-20260911" / "data" / "jobs.json"
TODAY = dt.date(2026, 9, 11)  # 固定"今天"=jobs.json 拉取日，保证数字可复现

PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX = 10, 20
BUDGET_BYTES = 60_000  # jobs 数组的字节预算，超出在完整岗位边界截断
TOP_DEFAULT, TOP_MAX = 20, 100
DETAIL_MAX = 10

JOB_CATEGORIES = ["技术/研发", "产品", "运营", "设计", "市场/营销", "销售", "职能/支持", "金融", "咨询",
                  "医疗/医药", "制造/生产", "科研", "教育/培训", "法律/合规", "其他"]
RECRUITMENT_TYPES = ["校园招聘", "实习招聘", "社会招聘"]
INDUSTRIES = ["互联网/科技", "国企/央企", "制造/工业", "能源/电力", "金融", "医药/医疗", "教育", "物流/运输",
              "传媒/广告", "消费/零售", "农业", "房地产", "其他"]
EDUCATIONS = ["不限", "中专及以下", "大专", "本科", "硕士", "博士", "未注明"]
EDU_RANK = {"中专及以下": 1, "大专": 2, "本科": 3, "硕士": 4, "博士": 5}
MAJOR_CATEGORIES = ["计算机类", "电子信息类", "金融经济类", "机械制造类", "医药生物类", "管理类", "文科类",
                    "理科类", "设计艺术类", "农业类", "其他"]
SORTS = ["published_desc", "deadline_asc"]
# group_by 取值 -> 组值应填回 jobs_search 的哪个参数
GROUP_BY = {"company": "company", "city": "city", "job_category": "job_category",
            "graduation_year": "graduation_year", "education": "education", "major_category": "major",
            "industry": "industry", "recruitment_type": "recruitment_type"}
MULTI_VALUED = {"city", "graduation_year"}
EXPLICIT_BASES = {"岗位写明", "活动标题写明", "全国", "专业不限", "学历不限"}

# ---------------------------------------------------------------- 读取


def load_all():
    return json.loads(DATA.read_text())


def valid_rows(rows=None):
    """与线上 Jobs.load() 相同的过滤。"""
    rows = load_all() if rows is None else rows
    return [r for r in rows if r.get("source_url") and r.get("application_url")]


def dedupe(rows):
    seen, out = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return out


def data_as_of(rows):
    return max((r.get("reviewed_at") or "" for r in rows), default="") or None

# ---------------------------------------------------------------- 届别

_SEP = r"\s*(?:至|到|~|～|—|－|-)\s*"
DATE_WINDOW = re.compile(r"(20\d{2})[-./年](\d{1,2})(?:[-./月](\d{1,2})日?)?" + _SEP + r"(20\d{2})[-./年](\d{1,2})")
YEAR_RANGE = re.compile(r"(?<!\d)(20\d{2})" + _SEP + r"(20\d{2})\s*年")
YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
VALID_YEARS = range(2024, 2030)


def years_in(text):
    """从一段原文里抽届别年份。

    毕业时间窗（2026-11-01 至 2027-10-31）只算窗口覆盖了哪几年的 6-8 月毕业季；
    "2026-2027年8月毕业"算两年；其余单独出现的 20xx 都算。
    """
    text = text or ""
    found = set()

    def window(m):
        sy, sm, ey, em = int(m[1]), int(m[2]), int(m[4]), int(m[5])
        for y in range(sy, ey + 1):
            if (y > sy or sm <= 8) and (y < ey or em >= 6):
                found.add(y)
        return " "

    def year_range(m):
        found.update(range(int(m[1]), int(m[2]) + 1))
        return " "

    text = DATE_WINDOW.sub(window, text)
    text = YEAR_RANGE.sub(year_range, text)
    found.update(int(y) for y in YEAR.findall(text))
    return sorted(y for y in found if y in VALID_YEARS)


def graduation_of(r):
    """返回 (["2027届", ...], {"2027届": "岗位写明"|"活动标题写明"})。岗位原文优先，活动标题补充。"""
    basis = {}
    for y in years_in(r.get("cohort_raw")):
        basis[f"{y}届"] = "岗位写明"
    for y in years_in(r.get("campaign_cohort_raw") or r.get("batch_name")):
        basis.setdefault(f"{y}届", "活动标题写明")
    years = sorted(basis, reverse=True)
    return years, {y: basis[y] for y in years}

# ---------------------------------------------------------------- 学历

EDU_GARBAGE = re.compile(r"\d{2,3}[A-Za-z0-9]{4,6}")


def is_edu_garbage(raw):
    return bool(EDU_GARBAGE.fullmatch((raw or "").strip()))


def education_of(raw):
    s = (raw or "").strip()
    if not s or s == "未披露" or is_edu_garbage(s):
        return "未注明"
    if "无学历" in s or s == "不限":
        return "不限"
    if any(k in s for k in ("初中", "高中", "中专", "中技")):
        return "中专及以下"
    if "大专" in s or "专科" in s:
        return "大专"
    if "本科" in s or "Bachelor" in s or s == "本硕":
        return "本科"
    if "硕士" in s or "Master" in s:
        return "硕士"
    if "博士" in s or "PhD" in s:
        return "博士"
    return "未注明"


EDU_IN_TEXT = re.compile(r"(大专|专科|本科|学士|硕士|研究生|博士)(学历)?(及以上|以上)?")

# ---------------------------------------------------------------- 专业

MAJOR_PLACEHOLDER = {"", "未披露", "详见职位描述"}
MAJOR_UNLIMITED = re.compile(r"专业不限|不限专业|专业[：:]\s*不限|不限制专业")


def major_state(r):
    raw = (r.get("major_requirements_raw") or "").strip()
    if MAJOR_UNLIMITED.search(raw):
        return "不限"
    if raw in MAJOR_PLACEHOLDER and not r.get("major_tags"):
        return "未注明"
    return "写明"


def major_category_of(r):
    state = major_state(r)
    if state != "写明":
        return state
    mc = r.get("major_normalized")
    return mc if mc and mc != "未披露" else "其他"

# ---------------------------------------------------------------- 城市 / 地区

AREA_CN = re.compile(r"'area_cn':\s*'([^']+)'")
CITY_UNKNOWN = {"", "未披露", "未知"}


def cities_of(r):
    out = []
    for c in r.get("cities") or []:
        m = AREA_CN.search(str(c))
        if m:
            out.append(m.group(1).split("-")[0])
    for c in r.get("cities_normalized") or []:
        s = str(c)
        if "area_code" not in s:
            out.append(s)
    result = []
    for c in out:
        c = "全国" if c in ("中国", "全国") else c
        if c not in CITY_UNKNOWN and c not in result:
            result.append(c)
    return result


MAINLAND = {"mainland", "内地", "中国大陆", "中国", "全国"}
OVERSEAS = {"overseas", "海外"}


def region_of(r, cities):
    if r.get("overseas_flag") or (r.get("region") or "") in OVERSEAS or (r.get("country") or "中国") != "中国":
        return "海外"
    if any(c.startswith(("香港", "澳门", "台湾")) for c in cities):
        return "港澳台"
    return "中国大陆"


def norm_city(q):
    q = q.strip()
    return q[:-1] if q.endswith("市") and len(q) > 2 else q

# ---------------------------------------------------------------- 岗位大类

RAW_CATEGORY_RULES = [  # 只在归一化结果是"技术/研发"而原文类目明显不是技术岗时改判
    ("产品", lambda s: "产品" in s and "研发" not in s),
    ("运营", lambda s: "运营" in s and "生产" not in s),
    ("销售", lambda s: "销售" in s),
    ("市场/营销", lambda s: "市场" in s),
    ("职能/支持", lambda s: "人力" in s or s.upper().startswith("HR")),
    ("设计", lambda s: s in {"设计", "设计类", "艺术/设计"} or any(k in s for k in ("视觉", "交互", "UI", "UX", "美术"))),
]


def job_category_of(r, only=None):
    norm = r.get("job_category_normalized") or "其他"
    raw = (r.get("job_category") or "").strip()
    if norm != "技术/研发" or not raw:
        return norm
    for cat, hit in RAW_CATEGORY_RULES:
        if (only is None or cat in only) and hit(raw):
            return cat
    return norm

# ---------------------------------------------------------------- 截止日 / 状态 / 日期

UNTIL_FILLED = {"招满即止", "until_filled", "rolling"}
DATE10 = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


def parse_date(value):
    m = DATE10.match(str(value or ""))
    if not m:
        return None
    try:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def deadline_of(r):
    d = parse_date(r.get("deadline"))
    if d and d.year >= 2099:
        return None, "招满即止或长期"
    if d:
        return d, "明确日期"
    if r.get("deadline_type") in UNTIL_FILLED:
        return None, "招满即止或长期"
    return None, "未注明"


def status_of(r, d):
    s = r.get("status")
    if s == "removed":
        return "已下线"
    if s == "expired" or (d and d < TODAY):
        return "已截止"
    if s == "unverified":
        return "未核验"
    return "招聘中"


def date_of(value):
    d = parse_date(value)
    return d.isoformat() if d else None

# ---------------------------------------------------------------- v4 每条岗位

CORE = ["id", "job_title", "company", "job_category", "recruitment_type", "industry", "cities", "region",
        "graduation_years", "graduation_year_basis", "education", "major_category", "deadline", "deadline_kind",
        "status", "published_at", "description_raw", "application_url", "source_url", "source_name", "reviewed_at"]


def to_item(r):
    d, kind = deadline_of(r)
    cities = cities_of(r)
    years, basis = graduation_of(r)
    edu_raw = r.get("education_raw") or ""
    it = {
        "id": r["id"],
        "job_title": r.get("job_title") or r.get("title") or "",
        "company": r.get("recruitment_unit") or r.get("company") or "",
        "recruiting_unit_raw": r.get("recruiting_unit_raw") or "",
        "hiring_department_raw": r.get("hiring_department_raw") or "",
        "parent_unit_raw": r.get("parent_unit_raw") or "",
        "contracting_entity": r.get("contracting_entity") or "",
        "job_category": job_category_of(r),
        "job_category_raw": r.get("job_category") or r.get("category") or "",
        "recruitment_type": r.get("recruitment_type") or "",
        "industry": r.get("industry") or "",
        "industry_tags": r.get("industry_tags") or [],
        "cities": cities,
        "region": region_of(r, cities),
        "country": r.get("country") or "",
        "graduation_years": years,
        "graduation_year_basis": basis,
        "cohort_raw": r.get("cohort_raw") or "",
        "campaign_title": r.get("campaign_cohort_raw") or r.get("batch_name") or "",
        "education": education_of(edu_raw),
        "education_raw": "" if is_edu_garbage(edu_raw) else edu_raw,
        "major_category": major_category_of(r),
        "major_requirements_raw": r.get("major_requirements_raw") or "",
        "major_tags": r.get("major_tags") or [],
        "deadline": d.isoformat() if d else None,
        "deadline_kind": kind,
        "status": status_of(r, d),
        "status_note": r.get("status_note") or "",
        "published_at": date_of(r.get("published_at")),
        "job_code": r.get("job_code") or r.get("position_code") or "",
        "description_raw": r.get("description_raw") or "",
        "application_url": r.get("application_url") or "",
        "source_url": r.get("source_url") or "",
        "announcement_url": r.get("announcement_url") or "",
        "campaign_url": r.get("campaign_url") or "",
        "job_listing_url": r.get("job_listing_url") or "",
        "source_name": r.get("source_name") or "",
        "reviewed_at": r.get("reviewed_at") or None,
    }
    return {k: v for k, v in it.items() if k in CORE or v not in ("", [], {}, None)}


def v3_public(r):
    """线上 Jobs.public() 的输出（不含运行时 expired 改写，今天没有过期岗位）。"""
    item = {k: v for k, v in r.items() if not k.endswith("evidence_path")}
    item["cohort_filter_scope"] = (item.get("cohort_scope") or "role_record") if item.get("cohort_raw") else (
        "campaign_title_only" if item.get("campaign_cohort_raw") else "undisclosed")
    return item


def nbytes(obj):
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode())


def build(dedup=True):
    rows = valid_rows()
    rows = dedupe(rows) if dedup else rows
    return [to_item(r) for r in rows], data_as_of(rows)

# ---------------------------------------------------------------- 参数规范化（同义词 -> 枚举）

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
                  "未披露": "未注明"},
    "industry": {"互联网": "互联网/科技", "科技": "互联网/科技", "国企": "国企/央企", "央企": "国企/央企",
                 "制造": "制造/工业", "工业": "制造/工业", "能源": "能源/电力", "电力": "能源/电力",
                 "医药": "医药/医疗", "医疗": "医药/医疗", "物流": "物流/运输", "运输": "物流/运输",
                 "传媒": "传媒/广告", "广告": "传媒/广告", "消费": "消费/零售", "零售": "消费/零售"},
}


class ParamError(ValueError):
    pass


def grad_year_enum(items):
    years = sorted({y for it in items for y in it["graduation_years"]}, reverse=True)
    return years + ["未注明"]


def normalize_choice(name, value, allowed, hint=""):
    v = (value or "").strip() if isinstance(value, str) else value
    if v in ("", None):
        return ""
    if name == "graduation_year":
        if isinstance(v, int) and not isinstance(v, bool):
            v = str(v)
        m = re.fullmatch(r"\s*(20\d{2})\s*(?:届|年)?.*", v) if isinstance(v, str) else None
        if m and "未" not in v:
            v = f"{m.group(1)}届"
        elif v == "未披露":
            v = "未注明"
    v = SYNONYMS.get(name, {}).get(v, v)
    if v not in allowed:
        raise ParamError(f"参数 {name} 的值「{value}」不在可选范围。可选：{'、'.join(allowed)}。{hint}".rstrip())
    return v

# ---------------------------------------------------------------- 匹配


def split_multi(value):
    return [v.strip() for v in re.split(r"[,，、;；|]", value or "") if v.strip()]


def m_city(it, qs):
    cities = it["cities"]
    if qs == ["未注明"]:
        return "未注明" if not cities else None
    if any(q in cities for q in qs):
        return "岗位写明"
    if "全国" in cities:
        return "全国"
    if not cities:
        return "未注明"
    return None


def m_grad(it, q):
    years = it["graduation_years"]
    if q == "未注明":
        return "未注明" if not years else None
    if q in years:
        return it["graduation_year_basis"][q]
    return "未注明" if not years else None


def m_edu(it, q):
    e = it["education"]
    if q == "未注明":
        return "未注明" if e == "未注明" else None
    if q == "不限":
        return "学历不限" if e == "不限" else None
    if e == "不限":
        return "学历不限"
    if e == "未注明":
        return "未注明"
    return "岗位写明" if EDU_RANK[e] <= EDU_RANK[q] else None


def m_major(it, q):
    mc = it["major_category"]
    if q == "未注明":
        return "未注明" if mc == "未注明" else None
    if q == "不限":
        return "专业不限" if mc == "不限" else None
    if mc == "不限":
        return "专业不限"
    if mc == "未注明":
        return "未注明"
    core = q[:-1] if q.endswith("类") and len(q) > 2 else q
    text = (it.get("major_requirements_raw", "") + " " + " ".join(it.get("major_tags", []))).casefold()
    return "岗位写明" if mc == q or core.casefold() in text else None


KEYWORD_FIELDS = ["job_title", "job_category_raw", "description_raw", "company", "recruiting_unit_raw",
                  "parent_unit_raw", "hiring_department_raw", "contracting_entity"]
COMPANY_FIELDS = ["company", "recruiting_unit_raw", "parent_unit_raw", "contracting_entity"]


def contains(it, fields, q):
    q = q.casefold()
    return any(q in str(it.get(f, "")).casefold() for f in fields)


FILTER_DEFAULTS = {"keyword": "", "company": "", "city": "", "job_category": "", "graduation_year": "",
                   "major": "", "education": "", "recruitment_type": "", "industry": "",
                   "deadline_within_days": 0, "include_expired": False, "explicit_only": False}


def check_filters(f, items):
    f = {**FILTER_DEFAULTS, **{k: v for k, v in f.items() if k in FILTER_DEFAULTS}}
    f["job_category"] = normalize_choice("job_category", f["job_category"], JOB_CATEGORIES,
                                         "找具体岗位名（如游戏策划、UI设计）请用 keyword。")
    f["graduation_year"] = normalize_choice("graduation_year", f["graduation_year"], grad_year_enum(items))
    f["education"] = normalize_choice("education", f["education"], EDUCATIONS)
    f["recruitment_type"] = normalize_choice("recruitment_type", f["recruitment_type"], RECRUITMENT_TYPES)
    f["industry"] = normalize_choice("industry", f["industry"], INDUSTRIES)
    if not 0 <= int(f["deadline_within_days"] or 0) <= 366:
        raise ParamError("参数 deadline_within_days 取 1–366，不筛截止日时不传或传 0。")
    if f["explicit_only"] and "未注明" in (f["graduation_year"], f["education"], f["major"].strip(), f["city"].strip()):
        raise ParamError("explicit_only=true 与取值「未注明」矛盾：只看明确匹配时不能再筛未注明。")
    return f


def evaluate(items, f):
    """返回 [(item, basis, tier)]；tier 0=明确匹配，1=含未注明。"""
    end = (TODAY + dt.timedelta(days=int(f["deadline_within_days"]))).isoformat() if f["deadline_within_days"] else None
    today = TODAY.isoformat()
    cities = [norm_city(c) for c in split_multi(f["city"])]
    companies = split_multi(f["company"])
    major = f["major"].strip()
    out = []
    for it in items:
        if not f["include_expired"] and it["status"] in ("已截止", "已下线"):
            continue
        if f["keyword"].strip() and not contains(it, KEYWORD_FIELDS, f["keyword"].strip()):
            continue
        if companies and not any(contains(it, COMPANY_FIELDS, c) for c in companies):
            continue
        if f["job_category"] and it["job_category"] != f["job_category"]:
            continue
        if f["recruitment_type"] and it["recruitment_type"] != f["recruitment_type"]:
            continue
        if f["industry"] and it["industry"] != f["industry"]:
            continue
        if end and not (it["deadline"] and today <= it["deadline"] <= end):
            continue
        basis = {}
        for dim, q, fn in (("graduation_year", f["graduation_year"], m_grad), ("city", cities, m_city),
                           ("major", major, m_major), ("education", f["education"], m_edu)):
            if not q:
                continue
            b = fn(it, q)
            if b is None:
                break
            basis[dim] = b
        else:
            tier = 1 if "未注明" in basis.values() else 0
            if f["explicit_only"] and tier:
                continue
            out.append((it, basis, tier))
    return out


def applied(f):
    return {k: v for k, v in f.items() if v not in ("", 0, False, None)}

# ---------------------------------------------------------------- 三个工具


def jobs_search(items, as_of, sort="published_desc", page_size=PAGE_SIZE_DEFAULT, offset=0, notices=None, **filters):
    f = check_filters(filters, items)
    if sort not in SORTS:
        raise ParamError(f"参数 sort 的值「{sort}」不在可选范围。可选：{'、'.join(SORTS)}。")
    notices = list(notices or [])
    if page_size > PAGE_SIZE_MAX:
        notices.append(f"page_size={page_size} 超过上限 {PAGE_SIZE_MAX}，本次按 {PAGE_SIZE_MAX} 返回，用 next_offset 翻页。")
        page_size = PAGE_SIZE_MAX
    res = evaluate(items, f)
    if sort == "deadline_asc":
        res.sort(key=lambda x: (x[2], x[0]["deadline"] is None, x[0]["deadline"] or "", x[0]["id"]))
    else:
        res.sort(key=lambda x: x[0]["id"], reverse=True)
        res.sort(key=lambda x: x[0]["published_at"] or "", reverse=True)
        res.sort(key=lambda x: x[2])
    total, explicit = len(res), sum(1 for x in res if x[2] == 0)
    jobs, used, truncated = [], 2, False
    for it, basis, tier in res[offset:offset + page_size]:
        obj = {"id": it["id"]}
        if basis:
            obj["match"] = {"level": "明确匹配" if tier == 0 else "含未注明", **basis}
        obj.update((k, v) for k, v in it.items() if k != "id")
        size = nbytes(obj) + 1
        if jobs and used + size > BUDGET_BYTES:
            truncated = True
            break
        jobs.append(obj)
        used += size
    returned = len(jobs)
    next_offset = offset + returned if offset + returned < total else None
    out = {"applied_filters": applied({**f, **({"sort": sort} if sort != "published_desc" else {})}),
           "total": total, "explicit_total": explicit, "unspecified_total": total - explicit,
           "sort": sort, "offset": offset, "page_size": page_size, "returned": returned,
           "has_next": next_offset is not None, "next_offset": next_offset, "truncated": truncated,
           "data_as_of": as_of}
    if notices:
        out["notices"] = notices
    if not total:
        out["suggestion"] = "没有符合条件的岗位。可去掉 explicit_only、放宽城市/专业/届别，或先用 jobs_stats 看各条件下的数量。"
    out["jobs"] = jobs
    return out


def group_values(it, group_by):
    if group_by == "city":
        return it["cities"] or ["未注明"]
    if group_by == "graduation_year":
        return it["graduation_years"] or ["未注明"]
    return [it[group_by]]


def jobs_stats(items, as_of, group_by="", top=TOP_DEFAULT, **filters):
    f = check_filters(filters, items)
    if group_by and group_by not in GROUP_BY:
        raise ParamError(f"参数 group_by 的值「{group_by}」不在可选范围。可选：{'、'.join(GROUP_BY)}。")
    top = max(1, min(int(top), TOP_MAX))
    res = evaluate(items, f)
    total, explicit = len(res), sum(1 for x in res if x[2] == 0)
    out = {"applied_filters": applied(f), "total": total, "explicit_total": explicit,
           "unspecified_total": total - explicit, "data_as_of": as_of}
    if not group_by:
        return out
    counts, exp = Counter(), Counter()
    for it, _, tier in res:
        for v in group_values(it, group_by):
            counts[v] += 1
            exp[v] += tier == 0
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    out.update({"group_by": group_by, "fill_param": GROUP_BY[group_by], "multi_valued": group_by in MULTI_VALUED,
                "groups_total": len(ordered), "returned_groups": min(top, len(ordered)),
                "other_count": sum(c for _, c in ordered[top:]),
                "groups": [{"value": v, "count": c, "explicit_count": exp[v], "unspecified_count": c - exp[v]}
                           for v, c in ordered[:top]]})
    return out


def jobs_detail(items, as_of, ids):
    wanted = []
    for i in split_multi(ids):
        if i not in wanted:
            wanted.append(i)
    if not wanted:
        raise ParamError("参数 ids 不能为空：传 1–10 个 jobs_search 返回的 jobs[i].id，用英文逗号分隔。")
    if len(wanted) > DETAIL_MAX:
        raise ParamError(f"参数 ids 最多 {DETAIL_MAX} 个，本次收到 {len(wanted)} 个。请分批调用。")
    by_id = {it["id"]: it for it in items}
    found = [by_id[i] for i in wanted if i in by_id]
    missing = [i for i in wanted if i not in by_id]
    out = {"requested": len(wanted), "found": len(found), "not_found": missing, "data_as_of": as_of}
    if missing:
        out["suggestion"] = "not_found 里的 id 不存在或已下线，请重新用 jobs_search 查询最新 id。"
    out["jobs"] = found
    return out

# ---------------------------------------------------------------- 旧参数 / 旧工具兼容

LEGACY_PARAMS = {"jobs_search": {"cohort": "graduation_year", "region": "city", "major_category": "major",
                                 "limit": "page_size"},
                 "jobs_detail": {"id": "ids"}}


def map_legacy(tool, args):
    args, notices = dict(args), []
    if tool == "jobs_deadlines":
        notices.append("jobs_deadlines 已并入 jobs_search（deadline_within_days + sort=deadline_asc），"
                       "本版本保留别名，下个版本移除；排序已从截止日由远到近改为由近到远。")
        args = {"deadline_within_days": args.get("days", 7), "sort": "deadline_asc",
                "page_size": args.get("limit", 100), "offset": args.get("offset", 0)}
        tool = "jobs_search"
    for old, new in LEGACY_PARAMS.get(tool, {}).items():
        if old not in args:
            continue
        value = args.pop(old)
        if args.get(new) not in (None, "", 0):
            notices.append(f"同时收到旧参数 {old} 和新参数 {new}，已忽略 {old}。")
            continue
        if old == "cohort":
            m = re.search(r"(20\d{2})", str(value or ""))
            if not m:
                notices.append(f"旧参数 cohort=「{value}」里没有年份，已忽略。")
                continue
            value = f"{m.group(1)}届"
        args[new] = value
        notices.append(f"参数 {old} 已改名为 {new}，本次已自动转换。")
    return tool, args, notices
