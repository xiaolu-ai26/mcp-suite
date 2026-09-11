"""从 jobs.json 生成归一化对照表 normalize_tables.json。

用法:
    python -m qiuzhao.build_normalize_tables \
        --path qiuzhao/data/jobs.json --out qiuzhao/normalize_tables.json

生成规则:
- 某键在数据里只对应一个归一化值时直接收录;
- 对应多个值时取出现次数最多的值(并列时取字典序最小者,保证确定性),
  并在该键条目里记录冲突记录数 "c";
- 只收录归一化目标字段非空的记录。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

KEY_SEP = "\x1f"

NORMALIZED_FIELDS = [
    "job_category_normalized", "graduation_year_normalized", "major_normalized",
    "city_normalized", "cities_normalized", "industry", "country",
    "overseas_flag", "region", "recruitment_type",
]


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _key(*parts) -> str:
    return KEY_SEP.join(_s(p) for p in parts)


def _build_table(records, key_fields, target, skip_empty_target=True):
    """key_fields: 字段名列表;返回 (table, stats)。"""
    buckets = defaultdict(Counter)
    for r in records:
        t = r.get(target)
        if skip_empty_target and (t is None or t == "" or t == []):
            continue
        buckets[_key(*[r.get(f) for f in key_fields])][t if not isinstance(t, list) else json.dumps(t, ensure_ascii=False, sort_keys=True)] += 1
    table = {}
    conflict_keys = 0
    conflict_records = 0
    for k, counter in buckets.items():
        top = counter.most_common(1)[0]
        value, count = top
        rest = sum(counter.values()) - count
        if len(counter) > 1:
            conflict_keys += 1
            conflict_records += rest
            # 并列时取字典序最小值,保证与记录遍历顺序无关
            best = sorted(v for v, c in counter.items() if c == count)
            value = best[0]
        table[k] = {"v": value, "c": rest}
    stats = {
        "entries": len(table),
        "conflict_keys": conflict_keys,
        "conflict_records": conflict_records,
    }
    return table, stats


def _build_city_element_table(records):
    """cities 列表逐元素 -> cities_normalized 逐元素(仅等长 zip)。"""
    buckets = defaultdict(Counter)
    for r in records:
        c, cn = r.get("cities"), r.get("cities_normalized")
        if not isinstance(c, list) or not isinstance(cn, list) or len(c) != len(cn):
            continue
        for raw, norm in zip(c, cn):
            if isinstance(raw, str):
                buckets[raw][_s(norm)] += 1
    table = {}
    conflict_keys = 0
    conflict_records = 0
    for k, counter in buckets.items():
        value, count = counter.most_common(1)[0]
        rest = sum(counter.values()) - count
        if len(counter) > 1:
            conflict_keys += 1
            conflict_records += rest
            value = sorted(v for v, c in counter.items() if c == count)[0]
        table[k] = {"v": value, "c": rest}
    return table, {
        "entries": len(table),
        "conflict_keys": conflict_keys,
        "conflict_records": conflict_records,
    }


def _build_value_sets(records):
    sets = {f: set() for f in NORMALIZED_FIELDS}
    for r in records:
        for f in NORMALIZED_FIELDS:
            v = r.get(f)
            if v is None or v == "" or v == []:
                continue
            if isinstance(v, list):
                for e in v:
                    sets[f].add(e)
            else:
                sets[f].add(v)
    return {f: sorted(s, key=str) for f, s in sets.items()}


def build_tables(records):
    tables = {}
    stats = {}

    def add(name, key_fields, target):
        t, s = _build_table(records, key_fields, target)
        tables[name] = t
        stats[name] = s

    # 城市
    t, s = _build_city_element_table(records)
    tables["city_element"] = t
    stats["city_element"] = s
    add("cities_tuple_to_city", ["cities"], "city_normalized")
    add("city_to_region", ["city_normalized"], "region")
    add("city_source_to_country", ["city_normalized", "source_name"], "country")
    add("city_to_country", ["city_normalized"], "country")
    # 毕业年份
    add("cohort_to_grad", ["cohort_raw", "cohort_scope"], "graduation_year_normalized")
    # 岗位大类
    add("cat_title_to_jcn", ["job_category", "job_title"], "job_category_normalized")
    add("title_to_jcn", ["job_title"], "job_category_normalized")
    add("cat_to_jcn", ["job_category"], "job_category_normalized")
    # 专业
    add("major_raw_to_major", ["major_requirements_raw"], "major_normalized")
    # 行业
    add("unit_title_source_to_industry", ["recruitment_unit", "job_title", "source_name"], "industry")
    add("unit_title_to_industry", ["recruitment_unit", "job_title"], "industry")
    add("unit_to_industry", ["recruitment_unit"], "industry")
    # 招聘类型
    add("rt_full", ["source_name", "cohort_raw", "job_title", "recruiting_unit_raw"], "recruitment_type")
    add("rt_sct", ["source_name", "cohort_raw", "job_title"], "recruitment_type")

    value_sets = _build_value_sets(records)
    return tables, stats, value_sets


def main(argv=None):
    ap = argparse.ArgumentParser(description="从 jobs.json 生成归一化对照表")
    ap.add_argument("--path", required=True, help="jobs.json 路径")
    ap.add_argument("--out", required=True, help="输出的 normalize_tables.json 路径")
    args = ap.parse_args(argv)

    src = Path(args.path)
    with src.open("r", encoding="utf-8") as f:
        records = json.load(f)

    tables, stats, value_sets = build_tables(records)

    payload = {
        "version": 1,
        "generated_from": str(src),
        "record_count": len(records),
        "key_sep": KEY_SEP,
        "value_sets": value_sets,
        "stats": stats,
        "tables": tables,
    }
    out = Path(args.out)
    with out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    summary = {
        "records": len(records),
        "out": str(out),
        "tables": stats,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
