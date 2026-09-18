#!/usr/bin/env python3
"""Render pipeline-watch/RECEIPT-xianyu-slugs.md from the committed artifacts."""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
from pathlib import Path

PLATFORM_LABEL = {'beisen': '北森(zhiye.com)', 'moka': 'Moka(mokahr.com)', 'feishu': '飞书招聘(jobs.feishu.cn)'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--batch-out', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    slugs = json.loads((args.root / 'pipeline-watch' / 'xianyu-ats-slugs.json').read_text(encoding='utf-8'))
    rejected = json.loads((args.root / 'pipeline-watch' / 'xianyu-ats-rejected.json').read_text(encoding='utf-8'))
    others = json.loads((args.root / 'pipeline-watch' / 'xianyu-ats-others.json').read_text(encoding='utf-8'))

    added = rejected.get('added') or {}
    extraction = slugs['stats']
    lines = []
    total_added = sum(len(v) for v in added.values())
    total_rejected = len(rejected['rejected'])
    total_skipped = len(rejected['skipped_existing'])

    lines.append('# 收据：闲鱼公司表 ATS 租户批量接入（Moka / 北森 / 飞书招聘）')
    lines.append('')
    lines.append(f'> 生成时间：{dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}（UTC）  ')
    lines.append('> 分支：`feat/xianyu-slugs`（基于 `feat/banks-batch1`）；**未部署、未 push、未合并、未写任何生产库/精灵**。  ')
    lines.append('> 只读：飞书 Base 用 `lark-cli` 只读分页；适配器全部只读采集，未登录、未绕过验证码/签名、未写库。  ')
    lines.append('')
    lines.append('## 1. 结论（TL;DR）')
    lines.append('')
    lines.append(f'- 闲鱼主表全量 **{slugs["source"]["records"]}** 条（去重后，未见重复行）；提取出 ATS 租户：'
                 f'北森 {extraction["beisen"]}、Moka {extraction["moka"]}、飞书 {extraction["feishu"]}、大易 {extraction["dayee"]}、'
                 f'其他域名 {extraction["other_domains"]} 个。')
    lines.append(f'- 与库内公司名去重后实测：**成功/部分且 ≥1 条岗位 → 写入配置 {total_added} 家**；'
                 f'被拒 {total_rejected} 家；库内已有跳过 {total_skipped} 家。')
    by_platform = ', '.join(f'{PLATFORM_LABEL[k]} {len(added.get(k) or [])} 家'
                            for k in ('beisen', 'moka', 'feishu'))
    lines.append(f'- 分平台加入：{by_platform}。')
    lines.append('- 飞书招聘已配置化：`p1_feishu_public.py` 新增 `feishu` 段读取与 `merged_registry()`，'
                 '`p1_pipeline.py` 仅追加一个独立注册块（`setdefault`，不覆盖硬编码/已注册公司）。')
    lines.append('- 大易与「其他」域名仅输出清单（见 `xianyu-ats-others.json`），不做适配器。')
    lines.append('')
    lines.append('## 2. 方法与口径')
    lines.append('')
    lines.append('- 全表拉取：`lark-cli base +record-list --format ndjson`，每页 2000 条、页间隔 1s，'
                 '共 4 页（2000/2000/2000/1801），未修改该表。')
    lines.append('- 链接提取：扫描每条记录所有字段中的 `http(s)://`；按域名归类 mokahr / zhiye / jobs.feishu.cn / hotjob.cn / 其他。')
    lines.append('- 去重：库内公司在精灵 `C:\\mcp-suite-collector\\data\\jobs.json` 的 company 系列字段去重（只读 SSH 传 stdin 脚本，'
                 '取回公司名去重清单），归一化后命中即跳过。')
    lines.append('- 实测：每租户用对应适配器跑一次 `campus` 只读采集，每租户请求上限 15 次（`max_requests=15`），'
                 '**租户之间 ≥2s**（任务书第 3 步的限速口径；单租户内为适配器自身的礼貌退避/0.2s 分页间隔）；不 `--apply`、不写库。')
    lines.append('- 保留口径：`status ∈ {success, partial}` 且已采集岗位 ≥1 条才写入配置；否则记入 `xianyu-ats-rejected.json`。')
    lines.append('- 公司名：优先官方站点显示名（飞书 `tenant_name` / 北森页面 title 去「招聘系统」等后缀），否则用表内名称。')
    lines.append('')
    lines.append('## 3. 加入配置的公司（实测通过）')
    lines.append('')
    lines.append('| # | 平台 | 公司（官方/表内） | slug | 岗位数 | status | 请求数 |')
    lines.append('|---|---|---|---|---|---|---|')
    index = 0
    for platform in ('beisen', 'moka', 'feishu'):
        for row in sorted(added.get(platform) or [], key=lambda r: -(r.get('jobs') or 0)):
            index += 1
            lines.append(f'| {index} | {PLATFORM_LABEL[platform]} | {row["company"]}（{row.get("company_table") or ""}） '
                         f'| `{row["slug"]}` | {row["jobs"]} | {row["status"]} | {row.get("requests")} |')
    lines.append('')
    lines.append('## 4. 被拒清单摘要')
    lines.append('')
    reason_counts = collections.Counter()
    for row in rejected['rejected']:
        reason_counts[f'{row["platform"]} / {row["reason"]}'] += 1
    lines.append('| 平台 / 原因 | 数量 |')
    lines.append('|---|---|')
    for reason, count in reason_counts.most_common():
        lines.append(f'| {reason} | {count} |')
    lines.append('')
    lines.append('完整逐租户原因（含错误样本）见 `pipeline-watch/xianyu-ats-rejected.json`。')
    lines.append('')
    lines.append('## 5. 大易（hotjob.cn）清单（不做适配器）')
    lines.append('')
    lines.append(f'共 **{others["dayee_count"]}** 个域名。')
    lines.append('')
    lines.append('| 域名 | 公司 | 示例链接 |')
    lines.append('|---|---|---|')
    for row in others['dayee']:
        lines.append(f'| `{row["domain"]}` | {"、".join(row["companies"][:4])} | {row["examples"][0] if row["examples"] else ""} |')
    lines.append('')
    lines.append(f'## 6. 「其他」域名 Top（共 {others["other_domain_count"]} 个，完整见 xianyu-ats-slugs.json）')
    lines.append('')
    lines.append('| 域名 | 公司数 | 代表公司 | 示例链接 |')
    lines.append('|---|---|---|---|')
    for row in others['other_top'][:40]:
        lines.append(f'| `{row["domain"]}` | {row["company_count"]} | {"、".join(row["companies"][:3])} | {row["examples"][0] if row["examples"] else ""} |')
    lines.append('')
    lines.append('## 7. 请求总数')
    lines.append('')
    totals = {}
    for platform in ('beisen', 'moka', 'feishu'):
        path = args.batch_out / f'{platform}.json'
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        totals[platform] = {
            'rows': len(data['rows']),
            'requests': sum(r.get('requests') or 0 for r in data['rows']),
            'skipped': len(data['skipped']),
            'discovery_extra': len(data['rows']) if platform == 'feishu' else 0,
        }
    lines.append('| 平台 | 实测租户 | 采集请求数 | 飞书发现额外 1 次/租户 | 库内跳过 |')
    lines.append('|---|---|---|---|---|')
    grand = 0
    for platform in ('beisen', 'moka', 'feishu'):
        t = totals.get(platform)
        if not t:
            continue
        grand += t['requests'] + t['discovery_extra']
        lines.append(f'| {PLATFORM_LABEL[platform]} | {t["rows"]} | {t["requests"]} | {t["discovery_extra"]} | {t["skipped"]} |')
    lines.append(f'| **合计** | | **{sum(t["requests"] for t in totals.values())}** | **{sum(t["discovery_extra"] for t in totals.values())}** | **{total_skipped}** |')
    lines.append('')
    lines.append('## 8. 单测与基线')
    lines.append('')
    lines.append('- 新增 `tests/test_p1_platform_feishu.py`（6 项）：配置驱动注册、默认项保留、站点解析、缺站点 blocked、'
                 'pipeline 追加注册块、请求预算早停。')
    lines.append('- 全量 `pytest tests/` 各跑 3 次（基线 `feat/banks-batch1` 与本次）：确定性失败集合**完全一致**，'
                 '均为既有环境性 3 项：`test_core.py::test_role_cohort_and_campaign_title_bases`、'
                 '`test_p1_pipeline.py::test_timeout_publishes_only_validated_partial_checkpoint`、'
                 '`test_schema.py::test_enum_check_fails_when_data_drifts`。')
    lines.append('- 通过数：基线 388 → 本次 394（+6 = 新增 `test_p1_platform_feishu.py`）。')
    lines.append('- 第 4 项 `test_codes_kind.py::test_migration_is_safe_when_both_services_start_together` 为**两分支共有的 flaky**'
                 '（多进程并起 sqlite 迁移偶发 database is locked）：基线 3 次中出现 1 次、本次出现 2 次，隔离复跑基线 5 次 3 过 2 败、'
                 '本次 5 次 1 过 4 败，与本次改动无关（`core/store.py` 未改）。')
    lines.append('')
    lines.append('## 9. 部署件')
    lines.append('')
    lines.append('`pipeline-watch/deploy-artifacts/20260918d/`：须**叠加在 20260918c 之后**。')
    lines.append('')
    lines.append('| 文件 | 说明 |')
    lines.append('|---|---|')
    lines.append('| `p1_feishu_public.py` | 新增配置驱动 `feishu` 段 + `collect_platform` + `merged_registry` + 可选 `max_requests` 预算 |')
    lines.append('| `p1_pipeline.py` | 仅在现注册块之后追加飞书注册块（`setdefault`） |')
    lines.append('| `p1_platform_companies.json` | 现有 6 家飞书迁入 `feishu` 段 + 本次实测通过的租户 |')
    lines.append('| `tests/test_p1_platform_feishu.py`（可选） | 新增单测 |')
    lines.append('| `tests/test_collector_next_integration.py`、`tests/test_p1_banks.py`（可选） | '
                 '因追加飞书注册块，顺序断言由「银行在末尾」改为「银行紧随 beisen/moka 之后、允许后续追加块」 |')
    lines.append('')
    lines.append('## 10. 遗留与风险')
    lines.append('')
    lines.append('- 北森 `PortalId` 缺失（WAF/多门户落地页）与 Moka 404/`orgId` 参数错误是主要被拒原因；不代表公司没有校招，只是当前公开入口不可稳定采集。')
    lines.append('- 每租户 15 次请求是礼貌上限：大型租户在列表顺序不利时可能因预算提前停止而记 0 条（被拒），属**假阴性**，后续可提高预算复测。')
    lines.append('- 飞书 `collect_feishu` 对未知 `recruit_type` 一律记错误、不猜测；未知枚举较多的租户会被判 blocked。')
    lines.append('- 其他域名中含自定义域名的飞书招聘站点（如商汤/叠纸/得物/小米），仍由既有专用适配器覆盖，未纳入本次 `*.jobs.feishu.cn` 配置化范围。')
    lines.append('- 新增数百家平台公司会让每日整批的 `DEFAULT_COMPANIES` 变大，需在调度侧评估每轮耗时与限速。')
    lines.append('')
    args.output.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'added': total_added, 'rejected': total_rejected,
                      'skipped': total_skipped}, ensure_ascii=False))


if __name__ == '__main__':
    main()
