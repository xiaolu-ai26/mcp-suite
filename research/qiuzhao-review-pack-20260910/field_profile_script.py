#!/usr/bin/env python3
"""全量 jobs.json 字段覆盖率统计 — 基于全量快照，非样本推算。"""
import json
import collections
from pathlib import Path

JOBS_PATH = Path("/Users/maxzhl/Projects/mcp-suite/qiuzhao/data/jobs.json")
OUT_PATH = Path("/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-review-pack-20260910/B_data_samples/field_profile.json")

# 来源前缀到企业名称映射
SOURCE_MAP = {
    "postal": "中国邮政",
    "chn": "国家能源",
    "telecom": "电信",
    "boc": "中行",
    "ccb": "建行",
    "guopin": "国聘平台(含移动/能建/中广核/机械总院/航天科工/联通)",
}

# 国聘子来源
GUOPIN_SUB = {
    "zgyd": "移动",
    "ceec": "能建",
    "cgnpc": "中广核",
    "cam2027": "机械总院",
    "casicjob": "航天科工",
    "zglt": "联通",
}

def source_of(job):
    pid = job.get("id", "")
    prefix = pid.split("-")[0]
    if prefix == "guopin":
        sub = job.get("source_group_key", "unknown")
        return GUOPIN_SUB.get(sub, f"guopin-{sub}")
    return SOURCE_MAP.get(prefix, f"unknown-{prefix}")

def is_missing(value):
    """判断缺失：null、空字符串、空数组。0和false不算缺失。"""
    if value is None:
        return "null"
    if isinstance(value, str) and value.strip() == "":
        return "empty_string"
    if isinstance(value, list) and len(value) == 0:
        return "empty_array"
    return None

def field_stats(jobs, field):
    """统计单个字段的覆盖情况。"""
    total = len(jobs)
    present = 0  # 键存在
    valid = 0    # 键存在且非缺失
    missing_key = 0
    null_count = 0
    empty_str = 0
    empty_arr = 0
    types = collections.Counter()
    for j in jobs:
        if field not in j:
            missing_key += 1
            continue
        present += 1
        val = j[field]
        types[type(val).__name__] += 1
        miss = is_missing(val)
        if miss == "null":
            null_count += 1
        elif miss == "empty_string":
            empty_str += 1
        elif miss == "empty_array":
            empty_arr += 1
        else:
            valid += 1
    return {
        "total_records": total,
        "key_present": present,
        "key_present_rate": round(present / total * 100, 2) if total else 0,
        "valid_non_empty": valid,
        "valid_rate": round(valid / total * 100, 2) if total else 0,
        "missing_key": missing_key,
        "null": null_count,
        "empty_string": empty_str,
        "empty_array": empty_arr,
        "value_types": dict(types),
    }

def main():
    with open(JOBS_PATH, encoding="utf-8") as f:
        jobs = json.load(f)

    total = len(jobs)
    # 所有出现过的键
    all_keys = sorted(set().union(*[set(j.keys()) for j in jobs]))

    # 按来源分组
    by_source = collections.defaultdict(list)
    for j in jobs:
        by_source[source_of(j)].append(j)

    # 全量统计
    overall = {}
    for field in all_keys:
        overall[field] = field_stats(jobs, field)

    # 按来源分组统计
    by_source_stats = {}
    for src, rows in sorted(by_source.items()):
        by_source_stats[src] = {"record_count": len(rows)}
        for field in all_keys:
            by_source_stats[src][field] = field_stats(rows, field)

    # 15列同行字段映射分析
    peer_15 = {
        "公司名称": {
            "actual_fields": ["recruitment_unit", "recruiting_unit_raw", "contracting_entity", "parent_unit_raw"],
            "note": "recruitment_unit=集团全称(每条都有); recruiting_unit_raw=招聘单位/分公司标签; contracting_entity=签约主体(始终空字符串,不推断); parent_unit_raw=上级单位(部分源有)"
        },
        "公司类型": {
            "actual_fields": [],
            "note": "无此字段。国聘源有 nature_raw(校招/社招性质) 和 recruitment_type_raw(校园招聘), 但这是招聘性质不是公司类型(央企/国企/民企)"
        },
        "所属行业": {
            "actual_fields": [],
            "note": "无此字段。可从 recruitment_unit 推断但未结构化存储"
        },
        "招聘类型": {
            "actual_fields": ["nature_raw", "recruitment_type_raw", "record_kind"],
            "note": "nature_raw=校招/社招(仅国聘源); recruitment_type_raw=校园招聘(仅国聘源); record_kind=记录类型(announcement_explicit_role/official_plan_post/official_job_id); 所有记录均为校招范围但非结构化统一字段"
        },
        "招聘对象": {
            "actual_fields": ["cohort_raw", "campaign_cohort_raw", "cohort_scope", "education_raw"],
            "note": "cohort_raw=岗位级届别描述; campaign_cohort_raw=活动标题届别(如2027校园招聘); cohort_scope=届别来源范围; education_raw=学历要求; 注意: 招聘性质(campus) vs 招聘季(2026秋招) vs 毕业届别(2027届) 是不同维度"
        },
        "工作地点": {
            "actual_fields": ["cities"],
            "note": "cities=数组, 每个元素为城市/地区字符串(如'北京','北京-东城区','阿拉善左旗')"
        },
        "岗位": {
            "actual_fields": ["job_title", "job_category", "job_title_scope", "hiring_department_raw"],
            "note": "job_title=岗位名称; job_category=岗位类别; hiring_department_raw=招聘部门; 不为复刻同行表格把全部岗位合并为一条公司记录"
        },
        "投递进度": {
            "actual_fields": ["status", "status_note"],
            "note": "status=公共招聘事实(open/expired/unverified/removed), 不是用户私有投递进度。无用户投递状态字段。status_note=状态说明(仅telecom有)"
        },
        "更新时间": {
            "actual_fields": ["reviewed_at", "published_at", "published_at_scope"],
            "note": "reviewed_at=本次采集复核时间(今日复核); published_at=来源发布日期; published_at_scope=发布日期来源。注意: 今日新增(first_seen_at)不存在; 今日复核=reviewed_at; 来源发布日期=published_at, 三者不混用"
        },
        "投递截止": {
            "actual_fields": ["deadline", "deadline_type", "deadline_scope"],
            "note": "deadline=截止日期(YYYY-MM-DD或null); deadline_type=explicit/undisclosed/until_filled; deadline_scope=截止日期来源范围"
        },
        "相关链接": {
            "actual_fields": ["source_url", "application_url", "campaign_url", "announcement_url", "job_listing_url"],
            "note": "source_url=原公告/岗位详情链接; application_url=直接投递入口; campaign_url=活动主页; announcement_url=公告页; job_listing_url=岗位列表页。注意: 原链接(source_url) vs 直接投递入口(apply_url) 不把一个URL复制成三个字段"
        },
        "招聘公告": {
            "actual_fields": ["announcement_url", "announcement_evidence_path", "description_raw"],
            "note": "announcement_url=公告链接; description_raw=岗位描述/公告内容原文; announcement_evidence_path=公告证据文件路径(不返回给客户端)"
        },
        "笔试情况": {
            "actual_fields": [],
            "note": "无此字段。未采集笔试信息"
        },
        "公司规模": {
            "actual_fields": [],
            "note": "无此字段。未采集公司规模(人数/营收等)"
        },
        "备注": {
            "actual_fields": ["status_note", "description_raw"],
            "note": "无独立备注字段。status_note仅telecom源有状态说明; description_raw包含岗位描述可视为备注信息"
        },
    }

    profile = {
        "snapshot_path": str(JOBS_PATH),
        "snapshot_file_mtime": JOBS_PATH.stat().st_mtime,
        "data_as_of": max((j.get("reviewed_at") or "") for j in jobs),
        "total_records": total,
        "source_group_counts": {src: len(rows) for src, rows in sorted(by_source.items())},
        "all_fields": all_keys,
        "overall_field_stats": overall,
        "by_source_field_stats": by_source_stats,
        "peer_15_column_mapping": peer_15,
        "status_distribution": dict(collections.Counter(j.get("status") for j in jobs)),
        "deadline_type_distribution": dict(collections.Counter(j.get("deadline_type") for j in jobs)),
        "statistical_method": "全量快照逐条统计, 非样本推算。缺失分类: 缺键/None/空字符串/空数组分开统计。0与false不算缺失。",
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    print(f"Total records: {total}")
    print(f"Data as of: {profile['data_as_of']}")
    print(f"Source groups: {profile['source_group_counts']}")
    print(f"Status distribution: {profile['status_distribution']}")
    print(f"Deadline type distribution: {profile['deadline_type_distribution']}")
    print(f"\nAll fields ({len(all_keys)}):")
    for field in all_keys:
        s = overall[field]
        print(f"  {field}: present={s['key_present_rate']}%, valid={s['valid_rate']}%, types={s['value_types']}")
    print(f"\nOutput written to: {OUT_PATH}")

if __name__ == "__main__":
    main()
