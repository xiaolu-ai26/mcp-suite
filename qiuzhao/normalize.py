"""秋招岗位数据归一化模块:补齐 jobs.json 记录中缺失/为空的归一化字段。

接口契约:
    normalize_records(records) -> {field: 本次补齐条数}
    normalize_file(path, check=False) -> 统计 dict

CLI:
    python -m qiuzhao.normalize --path <jobs.json> [--check]

行为:
- 旧归一化字段只补缺失值；graduation_years/basis/note 与地点字段(LOCATION_FIELDS)每次依据 v4 真源重算，
  避免单值缓存丢失多届、旧占位地点盖住新原始地点。
- 补值优先级:对照表(复合键优先) -> 关键词规则 -> 兜底值。
- 公司名三层字段(canonical_company/company/company_name)走 `qiuzhao.company_names`:
  展示名一律对齐到规范名,recruitment_unit/recruiting_unit_raw 只单向补齐。
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

from qiuzhao import company_names as CN

NORMALIZED_FIELDS = [
    "graduation_years", "graduation_year_basis", "graduation_year_note", "graduation_year_constraints", "major_categories",
    "job_category_normalized", "graduation_year_normalized", "major_normalized",
    "industry", "recruitment_type",
]

# 地点字段:每次依据原始地点(cities / locations_raw / location_country_raw ...)经
# v4_fields.location_of 重算,不只补空值,也**不**并入 NORMALIZED_FIELDS——collector/run.py
# 会把 NORMALIZED_FIELDS 的上一轮取值带进刷新行,旧的"未披露/中国/mainland"占位就会盖住新原始值。
# 国家未知时 country 为空串、region 为空串、overseas_flag 为 None,不默认中国。
# country_basis 与 countries 一一对应:source(来源字段)/place(地名知识)/legacy(旧值:没有来源
# 字段支持也未被推翻,属不确定值)。州省与多地点存为 location_state / locations_normalized,不占用原始
# 字段名(state 在别处可能是招聘状态)。
LOCATION_FIELDS = [
    "cities_normalized", "city_normalized", "country", "country_basis", "location_state", "work_mode",
    "locations_normalized", "region", "overseas_flag",
]

# 采集器写下的原始地点证据。新一轮缺这些字段时,只有它们从旧记录带过来(见 carry_forward_location)。
LOCATION_RAW_FIELDS = [
    "cities", "locations_raw", "location_country_raw", "location_state_raw",
    "country_raw", "province_raw", "work_mode_raw", "location_raw_provenance",
]

# 公司名三层字段:由 qiuzhao.company_names 规范化(展示名对齐 canonical,用人单位层单向补齐)。
# 故意**不**并入 NORMALIZED_FIELDS:collector/run.py 会把 NORMALIZED_FIELDS 里的上一轮取值
# 带进刷新行,公司名一旦那样继承,改别名表就会留下改不动的旧名。这里每次重新推导。
COMPANY_FIELDS = [
    "canonical_company", "company", "company_name",
    "recruitment_unit", "recruiting_unit_raw",
]

# 统计与"会改动已有非空值"自检覆盖的字段全集。
REPORTED_FIELDS = [*NORMALIZED_FIELDS, *LOCATION_FIELDS, *COMPANY_FIELDS]

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
    value_sets = {f: set(raw_sets.get(f, _EMBEDDED_VALUE_SETS.get(f, []))) for f in [*NORMALIZED_FIELDS, *LOCATION_FIELDS]}
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


# ---------------------------------------------------------------- 地点

def _sync_location(record, stats):
    """地点字段 = v4_fields.location_of(原始地点);未知保持未知(空串/None),不默认中国。

    不读 normalize_tables.json 的 city_* 表:那几张表来自旧库,含 未披露->mainland、
    未披露->海外 这类默认值,而且采集机上缺表时整批城市会退化成"未披露"。
    """
    from qiuzhao.v4_fields import location_of
    loc = location_of(record)
    cities = loc["cities"]
    region = loc["region"]
    values = {
        "cities_normalized": cities or ["未披露"],
        "city_normalized": cities[0] if cities else "未披露",
        "country": "、".join(loc["countries"]),
        "country_basis": loc["country_basis"],
        "location_state": "、".join(loc["states"]),
        "work_mode": "、".join(loc["work_modes"]),
        "locations_normalized": loc["locations"],
        "region": region,
        "overseas_flag": ("海外" in region) if region else None,
    }
    for field, value in values.items():
        if record.get(field) != value or field not in record:
            record[field] = value
            stats[field] += 1


def sync_location(record) -> None:
    """Recompute only the location fields of one record (merge paths that must not re-run the
    other normalizers)."""
    _sync_location(record, {f: 0 for f in LOCATION_FIELDS})


def carry_forward_location(new, old) -> bool:
    """新一轮缺原始地点时,只把旧记录的原始地点证据带过来;不复活旧整行,也不改任何时间戳。

    - 新行完全没有原始地点(cities 为空或只有 未知/未披露 这类占位):整组 LOCATION_RAW_FIELDS 带过来。
    - 新行有同一组城市、只是缺国家/州/多地点关联:只补缺的那几个字段。
    返回是否带了值;带值时记 location_carried_from_reviewed_at(旧证据的复核时间)。
    """
    from qiuzhao.v4_fields import has_raw_location, location_of
    if not isinstance(old, dict):
        return False
    old_loc = location_of(old)
    if not has_raw_location(old) and not old_loc["countries"]:
        return False
    if not has_raw_location(new):
        fields = [f for f in LOCATION_RAW_FIELDS if not _is_empty(old.get(f))]
    else:
        new_loc = location_of(new)
        if set(new_loc["cities"]) != set(old_loc["cities"]):
            return False                      # a different place: the new evidence stands alone
        record_level = () if new.get("locations_raw") else (   # new triples: old record fields stay out
            "location_country_raw", "location_state_raw", "country_raw", "province_raw")
        fields = [f for f in ("locations_raw", *record_level, "location_raw_provenance")
                  if _is_empty(new.get(f)) and not _is_empty(old.get(f))]
    legacy = [c for c, b in zip(old_loc["countries"], old_loc["country_basis"]) if b == "legacy"]
    carry_legacy = len(legacy) == 1 and not new.get("locations_raw") and not any(
        f in ("locations_raw", "location_country_raw", "country_raw") for f in fields)
    if not fields and not carry_legacy:
        return False
    for f in fields:
        new[f] = json.loads(json.dumps(old[f], ensure_ascii=False))
    if carry_legacy and not location_of(new)["countries"]:
        new["country"], new["country_basis"] = legacy[0], ["legacy"]
    new["location_carried_from_reviewed_at"] = (old.get("location_carried_from_reviewed_at")
                                                or old.get("reviewed_at"))
    return True


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


def _sync_company(record, stats):
    """公司名三层字段:canonical_company(品牌/集团层) + company/company_name(展示名)。

    见 qiuzhao/company_names.py 的判定顺序与保守规则;不确定就保留原名。
    """
    CN.apply_to_record(record, stats)


def _normalize_one(record, stats):
    _sync_company(record, stats)
    _sync_location(record, stats)
    _fill_graduation_year(record, stats)
    _fill_job_category(record, stats)
    _fill_major(record, stats)
    _fill_industry(record, stats)
    _fill_recruitment_type(record, stats)
    _sync_graduation_fields(record, stats)


def normalize_records(records: list[dict]) -> dict:
    """原地补齐缺失/为空的归一化字段;返回 {field: 本次补齐条数} 统计。"""
    stats = {f: 0 for f in REPORTED_FIELDS}
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
        {f: r.get(f) for f in REPORTED_FIELDS if not _is_empty(r.get(f))}
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
        "company_tables": CN.table_info(),
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
    'verified_at', 'list_checked_at', 'detail_checked_at', 'detail_cache_reused',
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
