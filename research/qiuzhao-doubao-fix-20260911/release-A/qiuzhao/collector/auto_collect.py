#!/usr/bin/env python3
"""
秋招岗位库自动化采集脚本
整合所有适配器，每日定时运行，更新岗位数据。

用法:
    python3 /opt/mcp-suite/qiuzhao/collector/auto_collect.py

功能:
    1. 运行现有公共源采集（邮政、国家能源、电信、中行、建行、国聘）
    2. 运行腾讯API适配器
    3. 合并去重
    4. 记录更新日志
    5. 备份旧数据
"""
from __future__ import annotations
import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
DATA_DIR = Path("/var/lib/mcp-suite")
JOBS_FILE = DATA_DIR / "jobs.json"
CHANGELOG_FILE = DATA_DIR / "changelog.json"
COLLECTOR_DIR = Path("/opt/mcp-suite/qiuzhao/collector")
LOG_FILE = DATA_DIR / "auto_collect.log"

def log(message):
    """记录日志到文件和控制台"""
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def backup_jobs():
    """备份当前岗位数据"""
    if not JOBS_FILE.exists():
        log("警告: jobs.json不存在，跳过备份")
        return None
    timestamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    backup_file = DATA_DIR / f"jobs.json.bak.auto.{timestamp}"
    import shutil
    shutil.copy2(JOBS_FILE, backup_file)
    log(f"已备份岗位数据到 {backup_file}")
    return backup_file

def run_basic_collectors():
    """运行基础采集器（邮政、国家能源、电信、中行、建行、国聘）"""
    log("开始运行基础采集器...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "qiuzhao.collector.run",
             "--output-dir", str(DATA_DIR),
             "--source", "all"],
            cwd="/opt/mcp-suite",
            capture_output=True,
            text=True,
            timeout=1800  # 30分钟超时
        )
        if result.returncode == 0:
            log("基础采集器运行成功")
            if result.stdout:
                # 解析最后一行的JSON摘要
                lines = result.stdout.strip().split("\n")
                for line in reversed(lines):
                    try:
                        summary = json.loads(line)
                        log(f"基础采集结果: {summary.get('job_count', '?')}条岗位, "
                            f"新增{summary.get('added_jobs', '?')}条, "
                            f"刷新{summary.get('refreshed_jobs', '?')}条")
                        return summary
                    except json.JSONDecodeError:
                        continue
        else:
            log(f"基础采集器返回非零退出码: {result.returncode}")
            if result.stderr:
                log(f"错误输出: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        log("基础采集器超时（30分钟）")
    except Exception as e:
        log(f"基础采集器运行异常: {e}")
    return None

def run_tencent_collector():
    """运行腾讯API适配器"""
    log("开始运行腾讯API适配器...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "qiuzhao.collector.tencent",
             "--output-dir", str(DATA_DIR / "tencent_staging")],
            cwd="/opt/mcp-suite",
            capture_output=True,
            text=True,
            timeout=600  # 10分钟超时
        )
        if result.returncode == 0:
            log("腾讯适配器运行成功")
            # 检查输出
            tencent_file = DATA_DIR / "tencent_staging" / "jobs.json"
            if tencent_file.exists():
                with open(tencent_file) as f:
                    tencent_jobs = json.load(f)
                log(f"腾讯采集到 {len(tencent_jobs)} 条岗位")
                return tencent_jobs
        else:
            log(f"腾讯适配器返回非零退出码: {result.returncode}")
            if result.stderr:
                log(f"错误输出: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        log("腾讯适配器超时（10分钟）")
    except Exception as e:
        log(f"腾讯适配器运行异常: {e}")
    return []

def merge_tencent_jobs(tencent_jobs):
    """将腾讯岗位合并到主岗位库"""
    if not tencent_jobs:
        log("无腾讯岗位需要合并")
        return 0

    if not JOBS_FILE.exists():
        log("警告: jobs.json不存在，无法合并")
        return 0

    with open(JOBS_FILE) as f:
        all_jobs = json.load(f)

    existing_ids = set(str(j.get("id", "")) for j in all_jobs if j.get("id"))
    existing_urls = set(str(j.get("detail_url", "")) for j in all_jobs if j.get("detail_url"))

    added = 0
    for job in tencent_jobs:
        job_id = str(job.get("id", ""))
        detail_url = str(job.get("detail_url", ""))
        if job_id and job_id not in existing_ids:
            all_jobs.append(job)
            existing_ids.add(job_id)
            added += 1
        elif detail_url and detail_url not in existing_urls:
            all_jobs.append(job)
            existing_urls.add(detail_url)
            added += 1

    if added > 0:
        with open(JOBS_FILE, "w") as f:
            json.dump(all_jobs, f, ensure_ascii=False)
        log(f"腾讯岗位合并完成，新增 {added} 条")

    return added

def update_changelog(added_jobs, total_jobs, total_companies):
    """更新更新日志"""
    today = datetime.now(TZ).strftime("%Y-%m-%d")

    if CHANGELOG_FILE.exists():
        with open(CHANGELOG_FILE) as f:
            changelog = json.load(f)
    else:
        changelog = []

    # 检查今天是否已有日志
    today_entry = None
    for entry in changelog:
        if entry.get("date") == today:
            today_entry = entry
            break

    if today_entry:
        today_entry["stats"]["total_jobs"] = total_jobs
        today_entry["stats"]["total_companies"] = total_companies
        if added_jobs > 0:
            today_entry["changes"].append(f"自动采集新增 {added_jobs} 条岗位")
    else:
        new_entry = {
            "date": today,
            "version": "auto-update",
            "changes": [f"自动采集新增 {added_jobs} 条岗位"] if added_jobs > 0 else ["自动采集运行，无新增岗位"],
            "stats": {
                "total_jobs": total_jobs,
                "total_companies": total_companies
            }
        }
        changelog.insert(0, new_entry)

    with open(CHANGELOG_FILE, "w") as f:
        json.dump(changelog, f, ensure_ascii=False, indent=2)

    # 同步到static目录
    import shutil
    shutil.copy2(CHANGELOG_FILE, "/opt/mcp-suite/core/static/changelog.json")
    log("更新日志已更新")

def restart_service():
    """重启MCP服务"""
    try:
        subprocess.run(["systemctl", "restart", "mcp-suite.service"], check=True)
        log("MCP服务已重启")
    except Exception as e:
        log(f"服务重启失败: {e}")

def main():
    log("=" * 60)
    log("秋招岗位库自动化采集开始")
    log("=" * 60)

    # 1. 备份
    backup_jobs()

    # 2. 运行基础采集器
    basic_summary = run_basic_collectors()

    # 3. 运行腾讯适配器
    tencent_jobs = run_tencent_collector()
    tencent_added = merge_tencent_jobs(tencent_jobs)

    # 4. 统计
    if JOBS_FILE.exists():
        with open(JOBS_FILE) as f:
            all_jobs = json.load(f)
        total_jobs = len(all_jobs)
        total_companies = len(set(str(j.get("recruitment_unit", "")) for j in all_jobs))
    else:
        total_jobs = 0
        total_companies = 0

    total_added = tencent_added
    if basic_summary and basic_summary.get("added_jobs"):
        total_added += basic_summary["added_jobs"]

    log(f"采集完成: 总岗位 {total_jobs} 条, 总企业 {total_companies} 家, 本次新增 {total_added} 条")

    # 5. 更新日志
    update_changelog(total_added, total_jobs, total_companies)

    # 6. 重启服务
    restart_service()

    log("=" * 60)
    log("自动化采集完成")
    log("=" * 60)

if __name__ == "__main__":
    main()
