#!/usr/bin/env python3
"""
秋招岗位库数据导出脚本
将岗位数据导出为CSV格式，可直接导入飞书多维表格。

用法:
    python3 /opt/mcp-suite/qiuzhao/collector/export_csv.py
    python3 /opt/mcp-suite/qiuzhao/collector/export_csv.py --output /path/to/output.csv
    python3 /opt/mcp-suite/qiuzhao/collector/export_csv.py --limit 1000

输出字段:
    id, recruitment_unit, job_title, cities, industry, recruitment_type,
    job_category, education_raw, major_raw, graduation_years, graduation_year_basis, graduation_year_note, deadline,
    status, detail_url, source_url, verified_at, description_raw
"""
from __future__ import annotations
import argparse
import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from qiuzhao.v4_fields import graduation_of

TZ = timezone(timedelta(hours=8))
DATA_DIR = Path("/var/lib/mcp-suite")
JOBS_FILE = DATA_DIR / "jobs.json"

# 导出字段定义
FIELDS = [
    ("id", "岗位ID"),
    ("recruitment_unit", "企业名称"),
    ("job_title", "岗位名称"),
    ("cities", "工作地点"),
    ("industry", "行业"),
    ("recruitment_type", "招聘类型"),
    ("job_category", "岗位类别"),
    ("education_raw", "学历要求"),
    ("major_raw", "专业要求"),
    ("graduation_years", "毕业届别"),
    ("graduation_year_basis", "届别依据"),
    ("graduation_year_note", "届别说明"),
    ("deadline", "截止日期"),
    ("status", "状态"),
    ("detail_url", "详情链接"),
    ("source_url", "来源链接"),
    ("verified_at", "核实时间"),
    ("description_raw", "岗位职责"),
]

def clean_value(value):
    """清理字段值，适配CSV"""
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

def export_jobs(output_path, limit=None, industry_filter=None, recruitment_type_filter=None):
    """导出岗位数据到CSV"""
    if not JOBS_FILE.exists():
        print(f"错误: 岗位数据文件不存在 {JOBS_FILE}")
        return False

    with open(JOBS_FILE, encoding="utf-8") as f:
        jobs = json.load(f)

    # 应用筛选
    if industry_filter:
        jobs = [j for j in jobs if industry_filter in str(j.get("industry", ""))]
    if recruitment_type_filter:
        jobs = [j for j in jobs if recruitment_type_filter in str(j.get("recruitment_type", ""))]

    # 限制数量
    if limit and limit > 0:
        jobs = jobs[:limit]

    # 写入CSV
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        # 写入表头（中文）
        writer.writerow([label for _, label in FIELDS])
        # 写入数据
        for job in jobs:
            # Recompute from the canonical extractor, also supporting older jobs.json
            # snapshots whose new array fields have not yet been persisted.
            years, basis, note, _ = graduation_of(job)
            values = dict(job, graduation_years=years, graduation_year_basis=basis,
                          graduation_year_note=note)
            row = []
            for field, _ in FIELDS:
                value = values.get(field, "")
                row.append(clean_value(value))
            writer.writerow(row)

    print(f"导出完成: {len(jobs)} 条岗位 -> {output_path}")
    print(f"文件大小: {Path(output_path).stat().st_size / 1024:.1f} KB")
    return True

def export_companies(output_path):
    """导出企业清单到CSV"""
    if not JOBS_FILE.exists():
        print(f"错误: 岗位数据文件不存在 {JOBS_FILE}")
        return False

    with open(JOBS_FILE, encoding="utf-8") as f:
        jobs = json.load(f)

    # 按企业聚合
    companies = {}
    for job in jobs:
        comp = str(job.get("recruitment_unit", "未知"))
        if comp not in companies:
            companies[comp] = {
                "企业名称": comp,
                "行业": clean_value(job.get("industry", "")),
                "岗位数量": 0,
                "在招岗位": 0,
                "工作地点": set(),
                "招聘类型": set(),
                "最新核实时间": "",
            }
        companies[comp]["岗位数量"] += 1
        if job.get("status") == "open":
            companies[comp]["在招岗位"] += 1
        cities = job.get("cities", [])
        if isinstance(cities, list):
            companies[comp]["工作地点"].update(cities)
        rt = job.get("recruitment_type", "")
        if rt:
            companies[comp]["招聘类型"].add(rt)
        verified = job.get("verified_at", "")
        if verified and verified > companies[comp]["最新核实时间"]:
            companies[comp]["最新核实时间"] = verified

    # 写入CSV
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["企业名称", "行业", "岗位数量", "在招岗位", "工作地点", "招聘类型", "最新核实时间"])
        for comp in sorted(companies.keys()):
            data = companies[comp]
            writer.writerow([
                data["企业名称"],
                data["行业"],
                data["岗位数量"],
                data["在招岗位"],
                "、".join(sorted(data["工作地点"])),
                "、".join(sorted(data["招聘类型"])),
                data["最新核实时间"],
            ])

    print(f"企业清单导出完成: {len(companies)} 家企业 -> {output_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="秋招岗位库数据导出")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径")
    parser.add_argument("--limit", type=int, default=None, help="导出数量限制")
    parser.add_argument("--industry", type=str, default=None, help="行业筛选")
    parser.add_argument("--recruitment-type", type=str, default=None, help="招聘类型筛选")
    parser.add_argument("--companies-only", action="store_true", help="仅导出企业清单")
    args = parser.parse_args()

    timestamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")

    if args.companies_only:
        output = args.output or str(DATA_DIR / f"companies_{timestamp}.csv")
        export_companies(output)
    else:
        output = args.output or str(DATA_DIR / f"jobs_export_{timestamp}.csv")
        export_jobs(output, limit=args.limit,
                   industry_filter=args.industry,
                   recruitment_type_filter=args.recruitment_type)

    print("\n飞书多维表格导入指南:")
    print("1. 打开飞书多维表格，新建或选择表格")
    print("2. 点击右上角「...」->「导入」->「CSV」")
    print("3. 选择导出的CSV文件")
    print("4. 确认字段映射后完成导入")
    print("5. 如需自动同步，可配置飞书开放平台API（需要APP_ID和APP_SECRET）")

if __name__ == "__main__":
    main()
