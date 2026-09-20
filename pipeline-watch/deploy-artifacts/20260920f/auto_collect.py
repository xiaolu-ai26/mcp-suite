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
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from qiuzhao.normalize import normalize_records
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from qiuzhao.normalize import normalize_records

TZ = timezone(timedelta(hours=8))
DATA_DIR = Path(os.environ.get("QIUZHAO_DATA_DIR", "/var/lib/mcp-suite"))
PROJECT_DIR = Path(__file__).resolve().parents[2]
JOBS_FILE = DATA_DIR / "jobs.json"
CHANGELOG_FILE = DATA_DIR / "changelog.json"
COLLECTOR_DIR = PROJECT_DIR / "qiuzhao" / "collector"
LOG_FILE = DATA_DIR / "auto_collect.log"

def log(message):
    """记录日志到文件和控制台"""
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def atomic_write_json(path, data, indent=None):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    if path.exists():
        st = os.stat(path)
        os.chmod(tmp, st.st_mode)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except (PermissionError, AttributeError):
            pass
    os.replace(tmp, path)

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
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8", errors="replace",  # a GBK byte must not kill the reader thread
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
    # A new directory prevents a successful exit from reusing yesterday's files.
    try:
        with tempfile.TemporaryDirectory(prefix="tencent-run-", dir=DATA_DIR) as staging:
            result = subprocess.run(
                [sys.executable, "-m", "qiuzhao.collector.tencent",
                 "--output-dir", staging],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                encoding="utf-8", errors="replace",  # ditto (see portable_runtime.child_output)
                timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(f"exit={result.returncode}; {(result.stderr or '')[-500:]}")
            staging_path = Path(staging)
            with open(staging_path / "source_state.json", encoding="utf-8") as f:
                state = json.load(f).get("tencent", {})
            with open(staging_path / "jobs.json", encoding="utf-8") as f:
                jobs = json.load(f)
            # The adapter may exit 0 even after catching a source/API error.
            if (state.get("status") != "success" or state.get("complete") is not True
                    or state.get("errors") or not isinstance(jobs, list)
                    or any(not isinstance(job, dict) for job in jobs)
                    or state.get("collected_jobs") != len(jobs)
                    or state.get("expected_total") != len(jobs)):
                raise RuntimeError(f"invalid or incomplete source result: {state}")
            log(f"腾讯采集成功: {len(jobs)} 条岗位")
            return jobs
    except subprocess.TimeoutExpired:
        log("腾讯适配器失败: 超时（10分钟）")
    except Exception as e:
        log(f"腾讯适配器失败: {e}")
    # None means failure; [] is a verified successful empty result.
    return None

def merge_tencent_jobs(tencent_jobs):
    """将腾讯岗位合并到主岗位库"""
    if not tencent_jobs:
        log("无腾讯岗位需要合并")
        return 0

    if not JOBS_FILE.exists():
        log("警告: jobs.json不存在，无法合并")
        return 0

    with open(JOBS_FILE, encoding="utf-8") as f:
        all_jobs = json.load(f)

    # Keep legacy rows (including rows without IDs) in place. URLs are only a
    # conservative alias when exactly one Tencent identity owns that URL.
    volatile = {'reviewed_at', 'checked_at', 'collected_at', 'updated_at',
                'last_seen_at', 'last_attempt_at', 'evidence_path'}
    by_id, by_url = {}, {}

    def index_row(index, row):
        for identity in {str(row.get('id') or ''), *(row.get('collector_identity_aliases') or [])}:
            if identity:
                by_id.setdefault(identity, set()).add(index)
        if row.get('detail_url') and row.get('id') and (
                str(row['id']).startswith('tencent-')
                or row.get('source_name') == '腾讯校园招聘官方网站'):
            by_url.setdefault(row['detail_url'], set()).add(index)

    for index, row in enumerate(all_jobs):
        index_row(index, row)
    added = updated = 0
    for job in tencent_jobs:
        job_id = str(job.get("id") or "")
        if not job_id:
            continue
        matches = sorted(by_id.get(job_id, ()))
        if len(matches) > 1:
            log(f"腾讯身份歧义，保留现有记录: {job_id}")
            continue
        if not matches:
            url = job.get('detail_url')
            matches = sorted(by_url.get(url, ())) if url else []
            if len(matches) > 1:
                log(f"腾讯 URL 身份歧义，保留现有记录: {job_id}")
                continue
        incoming = dict(job)
        normalize_records([incoming])
        if not matches:
            all_jobs.append(incoming)
            index_row(len(all_jobs) - 1, incoming)
            added += 1
            continue
        index = matches[0]
        old = all_jobs[index]
        incoming['id'] = old['id']
        aliases = set(old.get('collector_identity_aliases') or [])
        if job_id != str(old['id']):
            aliases.add(job_id)
        if aliases:
            incoming['collector_identity_aliases'] = sorted(aliases)
        # Preserve fields this adapter does not supply, but refresh supplied
        # business values. Observation timestamps alone must not rewrite jobs.
        refreshed = dict(old)
        refreshed.update(incoming)
        if old.get('source_is_active') is False and incoming.get('source_is_active') is not True:
            for field in ('status', 'status_note', 'source_is_active', 'source_status_raw',
                          'source_list_status_raw', 'source_detail_status_raw', 'source_status_evidence'):
                if field in old:
                    refreshed[field] = old[field]
        if ({k: v for k, v in old.items() if k not in volatile}
                == {k: v for k, v in refreshed.items() if k not in volatile}):
            continue
        if old.get('detail_url') != refreshed.get('detail_url'):
            by_url.get(old.get('detail_url'), set()).discard(index)
        all_jobs[index] = refreshed
        index_row(index, refreshed)
        updated += 1

    # This wrapper receives no durable company/scope snapshot evidence. Missing
    # IDs, including a successful empty result, never imply removal here.
    if added or updated:
        atomic_write_json(JOBS_FILE, all_jobs)
        log(f"腾讯岗位合并完成，新增 {added} 条，更新 {updated} 条")
    return added


def update_changelog(added_jobs, total_jobs, total_companies):
    """更新更新日志"""
    today = datetime.now(TZ).strftime("%Y-%m-%d")

    if CHANGELOG_FILE.exists():
        with open(CHANGELOG_FILE, encoding="utf-8") as f:
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

    atomic_write_json(CHANGELOG_FILE, changelog, indent=2)

    # 同步到static目录
    import shutil
    try:
        shutil.copy2(CHANGELOG_FILE, PROJECT_DIR / "core" / "static" / "changelog.json")
    except Exception as e:
        log(f"警告: 同步changelog到static失败: {e}")
    log("更新日志已更新")

def restart_service():
    """重启MCP服务"""
    if os.environ.get("QIUZHAO_SKIP_SERVICE_RESTART") == "1":
        return
    try:
        subprocess.run(["systemctl", "restart", "mcp-suite.service"], check=True)
        log("MCP服务已重启")
    except Exception as e:
        log(f"警告: 服务重启失败（忽略）: {e}")

def main():
    skip_basic = "--skip-basic-collectors" in sys.argv

    log("=" * 60)
    log("秋招岗位库自动化采集开始")
    log("=" * 60)

    # 1. 备份
    backup_jobs()

    # 2. 运行基础采集器
    basic_summary = None if skip_basic else run_basic_collectors()

    # 3. 运行腾讯适配器
    tencent_jobs = run_tencent_collector()
    if tencent_jobs is None or (not skip_basic and basic_summary is None):
        log("自动化采集失败；跳过腾讯合并、成功日志和服务重启；基础采集器可能已更新数据")
        return 1
    tencent_added = merge_tencent_jobs(tencent_jobs)

    # 4. 统计
    if JOBS_FILE.exists():
        with open(JOBS_FILE, encoding="utf-8") as f:
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

    return 0

if __name__ == "__main__":
    sys.exit(main())
