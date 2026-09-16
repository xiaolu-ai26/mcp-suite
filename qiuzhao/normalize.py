"""秋招岗位数据归一化模块:补齐 jobs.json 记录中缺失/为空的归一化字段。

接口契约:
    normalize_records(records) -> {field: 本次补齐条数}
    normalize_file(path, check=False) -> 统计 dict

CLI:
    python -m qiuzhao.normalize --path <jobs.json> [--check]

行为:
- 旧归一化字段只补缺失值；graduation_years/basis/note 每次依据 v4 真源重算，避免单值缓存丢失多届。
- 补值优先级:对照表(复合键优先) -> 关键词规则 -> 兜底值。
- 完全确定:同一输入永远同一输出,重复运行幂等。
- 对照表从 Path(__file__).parent / "normalize_tables.json" 加载;
  表文件缺失时降级为只用内置规则 + 兜底值,不崩。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat as stat_mod
import tempfile
from pathlib import Path

NORMALIZED_FIELDS = [
    "graduation_years", "graduation_year_basis", "graduation_year_note", "graduation_year_constraints", "major_categories",
    "job_category_normalized", "graduation_year_normalized", "major_normalized",
    "city_normalized", "cities_normalized", "industry", "country",
    "overseas_flag", "region", "recruitment_type",
]

KEY_SEP = "\x1f"

TABLES_PATH = Path(__file__).parent / "normalize_tables.json"

# 表文件缺失时的降级取值集合(均来自现有数据,不新增类别)
_EMBEDDED_VALUE_SETS = {
    "job_category_normalized": [
        "技术/研发", "产品", "设计", "运营", "市场/营销", "销售", "金融",
        "职能/支持", "制造/生产", "医疗/医药", "科研", "咨询", "教育/培训",
        "法律/合规", "其他",
    ],
    "graduation_year_normalized": ["2025届", "2026届", "2027届", "未披露"],
    "major_normalized": [
        "计算机类", "电子信息类", "金融经济类", "机械制造类", "管理类",
        "文科类", "医药生物类", "理科类", "农业类", "设计艺术类",
        "其他", "未披露",
    ],
    "city_normalized": ["全国", "海外", "未披露"],
    "cities_normalized": ["全国", "海外", "未披露"],
    "industry": [
        "互联网/科技", "国企/央企", "制造/工业", "能源/电力", "金融",
        "医药/医疗", "教育", "物流/运输", "消费/零售", "传媒/广告",
        "农业", "房地产", "其他",
    ],
    "country": ["中国", "海外", "美国", "英国", "爱尔兰", "西班牙", "德国", "瑞士", "捷克"],
    "overseas_flag": ["True", "False"],
    "region": ["mainland", "overseas", "海外", "内地", "中国大陆", "中国", "全国"],
    "recruitment_type": ["校园招聘", "社会招聘", "实习招聘"],
}


def _load_tables():
    if not TABLES_PATH.exists():
        return {}, {k: set(v) for k, v in _EMBEDDED_VALUE_SETS.items()}
    with TABLES_PATH.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    tables = payload.get("tables", {})
    raw_sets = payload.get("value_sets") or _EMBEDDED_VALUE_SETS
    value_sets = {f: set(raw_sets.get(f, _EMBEDDED_VALUE_SETS.get(f, []))) for f in NORMALIZED_FIELDS}
    return tables, value_sets


_TABLES, _VALUE_SETS = _load_tables()


def _known(field):
    return _VALUE_SETS.get(field, set())


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _key(*parts) -> str:
    return KEY_SEP.join(_s(p) for p in parts)


def _lookup(table_name, *parts):
    entry = _TABLES.get(table_name, {}).get(_key(*parts))
    if entry is None:
        return None
    return entry["v"]


def _is_empty(v) -> bool:
    return v is None or v == "" or v == []


def _set(record, field, value, stats) -> bool:
    """仅在字段为空时写入;非空字段绝不改动。"""
    if not _is_empty(record.get(field)):
        return False
    record[field] = value
    stats[field] += 1
    return True


# ---------------------------------------------------------------- 城市

_CJK_RE = re.compile(r"[一-鿿]")


def _clean_city_element(raw):
    """单个原始城市写法 -> 归一化城市;无法识别返回 None(丢弃)。"""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or s.startswith("-"):
        return None
    v = _lookup("city_element", s)
    if v is not None:
        return v
    known = _known("cities_normalized")
    cand = s[:-1] if s.endswith("市") else s
    if cand in known:
        return cand
    if "-" in cand:
        head = cand.split("-", 1)[0]
        if head.endswith("市"):
            head = head[:-1]
        if head in known:
            return head
    if cand in ("中国", "全国"):
        return "全国"
    if cand in ("未知", "未披露"):
        return "未披露"
    return "未披露"


def _fill_cities(record, stats):
    # cities_normalized
    if _is_empty(record.get("cities_normalized")):
        raw = record.get("cities")
        cleaned = []
        if isinstance(raw, list):
            for e in raw:
                v = _clean_city_element(e)
                if v is not None and v not in cleaned:
                    cleaned.append(v)
        if cleaned:
            _set(record, "cities_normalized", cleaned, stats)
        else:
            _set(record, "cities_normalized", ["未披露"], stats)
    # city_normalized
    if _is_empty(record.get("city_normalized")):
        v = None
        raw = record.get("cities")
        if isinstance(raw, list) and raw:
            v = _lookup("cities_tuple_to_city", raw)
        if v is None:
            cn = record.get("cities_normalized")
            if isinstance(cn, list) and cn:
                v = cn[0]
        if v is None:
            v = "未披露"
        _set(record, "city_normalized", v, stats)


# ---------------------------------------------------------------- country / region / overseas_flag

def _fill_country(record, stats):
    if not _is_empty(record.get("country")):
        return
    city = _s(record.get("city_normalized"))
    v = _lookup("city_source_to_country", city, record.get("source_name"))
    if v is None:
        v = _lookup("city_to_country", city)
    if v is None:
        if city in ("", "全国", "未披露"):
            v = "中国"
        elif _CJK_RE.search(city):
            v = "中国"
        elif city:
            v = "海外"
        else:
            v = "中国"
    _set(record, "country", v, stats)


def _fill_region(record, stats):
    if not _is_empty(record.get("region")):
        return
    city = _s(record.get("city_normalized"))
    country = _s(record.get("country"))
    v = _lookup("city_to_region", city)
    if v is None:
        if country and country != "中国":
            # 数据中中文海外城市用 "overseas",英文写法用 "海外"
            v = "overseas" if _CJK_RE.search(city) else "海外"
        else:
            v = "mainland"
    _set(record, "region", v, stats)


def _fill_overseas_flag(record, stats):
    if record.get("overseas_flag") is not None:
        return
    region = _s(record.get("region"))
    country = _s(record.get("country"))
    if region in ("overseas", "海外"):
        v = True
    elif region:
        v = False
    elif country and country != "中国":
        v = True
    else:
        v = False
    _set(record, "overseas_flag", v, stats)


# ---------------------------------------------------------------- 毕业年份

_YEAR_RE = re.compile(r"(20\d{2})\s*届")


def _fill_graduation_year(record, stats):
    if not _is_empty(record.get("graduation_year_normalized")):
        return
    v = _lookup("cohort_to_grad", record.get("cohort_raw"), record.get("cohort_scope"))
    if v is None:
        known = _known("graduation_year_normalized")
        m = _YEAR_RE.search(_s(record.get("cohort_raw")))
        if m:
            cand = f"{m.group(1)}届"
            if cand in known:
                v = cand
    if v is None:
        v = "未披露"
    _set(record, "graduation_year_normalized", v, stats)


# ---------------------------------------------------------------- 岗位大类

_JCN_RULES = [
    (re.compile(r"法律|法务|合规"), "法律/合规"),
    (re.compile(r"算法|后端|前端|开发|研发|工程师|技术|测试|运维|数据|架构|软件|硬件|信息安全|人工智能"), "技术/研发"),
    (re.compile(r"科研|研究员|课题|博士后"), "科研"),
    (re.compile(r"产品"), "产品"),
    (re.compile(r"设计"), "设计"),
    (re.compile(r"运营"), "运营"),
    (re.compile(r"市场|营销|品牌|策划"), "市场/营销"),
    (re.compile(r"柜员|银行|证券|基金|保险|金融|投资|风控|信贷|理财"), "金融"),
    (re.compile(r"销售|商务|客户经理|导购|渠道"), "销售"),
    (re.compile(r"咨询|顾问"), "咨询"),
    (re.compile(r"教师|讲师|教育|培训|教学"), "教育/培训"),
    (re.compile(r"医|药|护理|临床"), "医疗/医药"),
    (re.compile(r"生产|制造|车间|工艺|技工|操作工|焊接|数控"), "制造/生产"),
    (re.compile(r"人力|行政|财务|会计|审计|采购|文秘|前台|后勤|职能|党务|党建"), "职能/支持"),
]


def _fill_job_category(record, stats):
    if not _is_empty(record.get("job_category_normalized")):
        return
    cat = record.get("job_category")
    title = record.get("job_title")
    v = _lookup("cat_title_to_jcn", cat, title)
    if v is None:
        v = _lookup("title_to_jcn", title)
    if v is None and not _is_empty(cat):
        v = _lookup("cat_to_jcn", cat)
    if v is None:
        text = f"{_s(cat)} {_s(title)}"
        for pattern, value in _JCN_RULES:
            if pattern.search(text):
                v = value
                break
    if v is None:
        v = "其他"
    _set(record, "job_category_normalized", v, stats)


# ---------------------------------------------------------------- 专业

_MAJOR_RULES = [
    (re.compile(r"计算机|软件|网络工程|信息安全|人工智能|大数据|物联网|网络空间"), "计算机类"),
    (re.compile(r"电子|通信|自动化|电气|集成电路|微电子|信息工程|光电|电信"), "电子信息类"),
    (re.compile(r"金融|经济|会计|财务|财政|保险|投资|国贸|税收|审计"), "金融经济类"),
    (re.compile(r"机械|车辆|材料|能源|动力|土木|化工|仪器|船舶|航空|矿业|冶金|测控|工程"), "机械制造类"),
    (re.compile(r"管理|工商|人力资源|物流|市场营销|公共事业"), "管理类"),
    (re.compile(r"医学|药学|生物|临床|护理|制药|基础医"), "医药生物类"),
    (re.compile(r"数学|物理|化学|统计|天文|地理|大气"), "理科类"),
    (re.compile(r"中文|新闻|语言|法学|法律|历史|哲学|文学|外语|英语|翻译|社会学|政治"), "文科类"),
    (re.compile(r"农|林学|畜牧|兽医|水产|园艺"), "农业类"),
    (re.compile(r"设计|艺术|美术|音乐|舞蹈|影视"), "设计艺术类"),
]


def _fill_major(record, stats):
    if not _is_empty(record.get("major_normalized")):
        return
    raw = record.get("major_requirements_raw")
    v = _lookup("major_raw_to_major", raw)
    if v is None:
        text = _s(raw)
        if text.strip():
            for pattern, value in _MAJOR_RULES:
                if pattern.search(text):
                    v = value
                    break
            if v is None:
                v = "其他"
        else:
            v = "未披露"
    _set(record, "major_normalized", v, stats)


# ---------------------------------------------------------------- 行业

_INDUSTRY_RULES = [
    (re.compile(r"银行|证券|基金|保险|期货|信托|金融|投资|资产管理|融资租赁"), "金融"),
    (re.compile(r"医院|医药|制药|医疗|生物医药|卫生"), "医药/医疗"),
    (re.compile(r"大学|学院|学校|教育|研究院|研究所|科学院"), "教育"),
    (re.compile(r"电力|能源|电网|核电|石油|石化|煤炭|燃气|新能源"), "能源/电力"),
    (re.compile(r"物流|运输|航空|航运|铁路|港口|快递|船运|机场"), "物流/运输"),
    (re.compile(r"房地产|地产|置业|物业|建筑|建设|工程局"), "房地产"),
    (re.compile(r"传媒|广告|出版|广电|文化|影视|报业"), "传媒/广告"),
    (re.compile(r"农业|农发|林业|畜牧|水产|农垦|饲料"), "农业"),
    (re.compile(r"科技|互联网|软件|信息技术|数据|智能|网络|通信|电子|半导体|计算机"), "互联网/科技"),
    (re.compile(r"制造|汽车|工业|机械|电器|家电|钢铁|化工|材料|装备|集团有限.*厂"), "制造/工业"),
    (re.compile(r"零售|商贸|食品|饮料|日化|服装|商超|消费"), "消费/零售"),
]


def _fill_industry(record, stats):
    if not _is_empty(record.get("industry")):
        return
    unit = record.get("recruitment_unit")
    title = record.get("job_title")
    v = _lookup("unit_title_source_to_industry", unit, title, record.get("source_name"))
    if v is None:
        v = _lookup("unit_title_to_industry", unit, title)
    if v is None:
        v = _lookup("unit_to_industry", unit)
    if v is None:
        text = _s(unit)
        for pattern, value in _INDUSTRY_RULES:
            if pattern.search(text):
                v = value
                break
    if v is None:
        v = "其他"
    _set(record, "industry", v, stats)


# ---------------------------------------------------------------- 招聘类型

def _fill_recruitment_type(record, stats):
    if not _is_empty(record.get("recruitment_type")):
        return
    src = record.get("source_name")
    cohort = record.get("cohort_raw")
    title = record.get("job_title")
    v = _lookup("rt_full", src, cohort, title, record.get("recruiting_unit_raw"))
    if v is None:
        v = _lookup("rt_sct", src, cohort, title)
    if v is None:
        text = f"{_s(title)} {_s(cohort)}"
        if "实习" in text:
            v = "实习招聘"
        elif _YEAR_RE.search(_s(cohort)) or "应届" in _s(cohort):
            v = "校园招聘"
    if v is None:
        v = "校园招聘"
    _set(record, "recruitment_type", v, stats)


# ---------------------------------------------------------------- 入口

def _sync_graduation_fields(record, stats):
    """Persist the same multi-value result served by v4, retaining source evidence."""
    from qiuzhao.v4_fields import graduation_of, major_categories_of, graduation_constraints_of
    years, basis, note, rule = graduation_of(record)
    for field, value in [('graduation_years', years), ('graduation_year_basis', basis),
                         ('graduation_year_note', note), ('graduation_year_constraints', graduation_constraints_of(record, (years,basis,note,rule))),
                         ('major_categories', major_categories_of(record))]:
        if record.get(field) != value:
            record[field] = value
            stats[field] += 1


def _normalize_one(record, stats):
    _fill_cities(record, stats)
    _fill_country(record, stats)
    _fill_region(record, stats)
    _fill_overseas_flag(record, stats)
    _fill_graduation_year(record, stats)
    _fill_job_category(record, stats)
    _fill_major(record, stats)
    _fill_industry(record, stats)
    _fill_recruitment_type(record, stats)
    _sync_graduation_fields(record, stats)


def normalize_records(records: list[dict]) -> dict:
    """原地补齐缺失/为空的归一化字段;返回 {field: 本次补齐条数} 统计。"""
    stats = {f: 0 for f in NORMALIZED_FIELDS}
    for record in records:
        if isinstance(record, dict):
            _normalize_one(record, stats)
    return stats


def normalize_file(path, check: bool = False) -> dict:
    """读文件 -> normalize_records -> 写回(check=True 时只统计不写)。返回统计。"""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        records = json.load(f)

    # 快照已有非空值,用于验证"已有非空值将被改动的数量"
    before = [
        {f: r.get(f) for f in NORMALIZED_FIELDS if not _is_empty(r.get(f))}
        if isinstance(r, dict) else {}
        for r in records
    ]

    stats = normalize_records(records)

    would_change_existing = 0
    for r, snap in zip(records, before):
        if not isinstance(r, dict):
            continue
        for f, old in snap.items():
            if r.get(f) != old:
                would_change_existing += 1

    result = {
        "path": str(p),
        "check": bool(check),
        "records": len(records),
        "filled": stats,
        "filled_total": sum(stats.values()),
        "would_change_existing": would_change_existing,
        "tables_loaded": bool(_TABLES),
    }

    if not check:
        st = os.stat(p)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False)
            os.chmod(tmp, stat_mod.S_IMODE(st.st_mode))
            try:
                os.chown(tmp, st.st_uid, st.st_gid)
            except (PermissionError, AttributeError):
                pass
            os.replace(tmp, p)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        result["written"] = True
    else:
        result["written"] = False
    return result


OBSERVATION_FIELDS = frozenset({
    'reviewed_at', 'checked_at', 'fetched_at', 'collected_at', 'retrieved_at',
    'verified_at', 'list_checked_at', 'detail_checked_at',
    'last_attempt_at', 'run_id', 'evidence_path', 'announcement_evidence_path',
    'list_evidence_path', 'detail_evidence_path', 'evidence_files', 'evidence',
})


def business_value(value):
    """Source observations do not constitute a change in the advertised job."""
    if isinstance(value, dict):
        return {k: business_value(v) for k, v in value.items()
                if k not in OBSERVATION_FIELDS and not k.endswith('_evidence_path')}
    if isinstance(value, list):
        return [business_value(v) for v in value]
    return value


def main(argv=None):
    ap = argparse.ArgumentParser(description="补齐 jobs.json 缺失的归一化字段")
    ap.add_argument("--path", required=True, help="jobs.json 路径")
    ap.add_argument("--check", action="store_true", help="只统计会补多少,不写文件")
    args = ap.parse_args(argv)
    result = normalize_file(args.path, check=args.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
