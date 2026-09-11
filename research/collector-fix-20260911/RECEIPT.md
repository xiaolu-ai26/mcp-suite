# 秋招采集流程修复收据（collector-fix-20260911）

日期：2026-09-11　分支：fix/collector-normalize（worktree: /Users/maxzhl/Projects/mcp-suite-wt-collector）　基线：main @ 1127cf7

## 问题

- 现有 jobs.json 里的 10 个归一化字段由外部一次性处理加入，仓库和服务器上没有生成代码；`run.py` 合并时整条替换旧记录、明早 06:10 运行后这些字段会丢；`auto_collect.py` 追加的记录本就没有这些字段。
- 两个定时入口（06:10 mcp-suite 的 collector-daily.sh、root 03:00 的 auto_collect.py）写同一个 jobs.json，后者无锁、直接截断写、用系统 Python（缺 bs4，子采集器静默失败）、备份和日志属主污染为 root。
- run.py 仍残留对 legacy 记录（无 id / 无 reviewed_at）的 KeyError 风险。

## 改动文件（commits e0c8933 / f7688e1 / f30d5f5 / fe2bdc1）

| 文件 | 改动 |
|---|---|
| qiuzhao/normalize.py（新） | 归一化库 + CLI。`NORMALIZED_FIELDS`、`normalize_records()`、`normalize_file()`；`python -m qiuzhao.normalize --path <jobs.json> [--check]`。只补缺失/空值，已有非空值绝不改动；补值顺序：对照表（复合键优先）→ 关键词规则 → 兜底（"其他"/"未披露"）。原子写（tempfile + os.replace），恢复 mode、best-effort 恢复属主。表文件缺失时降级为规则+兜底，不崩。 |
| qiuzhao/normalize_tables.json（新，18MB） | 15 张对照表 + 各字段合法取值集合，由生成脚本从当前 jobs.json 产出；冲突键取多数值并记录冲突数。 |
| qiuzhao/build_normalize_tables.py（新） | 对照表生成脚本：`python -m qiuzhao.build_normalize_tables --path qiuzhao/data/jobs.json --out qiuzhao/normalize_tables.json`。 |
| qiuzhao/collector/run.py | 合并替换前把旧记录的归一化字段带到新记录（新记录缺/空时；False/0 类值也会被继承）；最终写 jobs.json 前对全部记录调 `normalize_records`。另外按 12:28 修复的同款风格修掉四处残留 KeyError：removal 标记改用 merged 的键、summary 的 `updated_at`/`added_jobs` 改用 `j.get(...)`（6922 条记录无 reviewed_at 键、297 条无 id，原代码必崩）、telecom 历史链接刷新改用 `j.get('id')`（实跑复现）。 |
| qiuzhao/collector/auto_collect.py | 合并腾讯记录后、写文件前调 `normalize_records`；jobs.json 和 changelog.json 改原子写（恢复 mode/属主）；新增 `--skip-basic-collectors` 开关（cron 链里 run.py 已单独跑过）；changelog 同步 static、systemctl 重启改 best-effort（mcp-suite 账号可能无权）；import 兼容直接路径运行。 |
| deploy/collector-daily.sh | 同一把 flock（/var/lib/mcp-suite/collector.lock）、同一 mcp-suite 账号、同一 venv，顺序执行 run.py → auto_collect --skip-basic-collectors → normalize。任一步失败写 cron-status.json（含步骤名、exit code，原子写）并以非零退出，后续步骤不执行；全部成功写 success:true。 |
| deploy/mcp-suite-qiuzhao.cron | 仍只有 06:10 mcp-suite 一个入口；注释标明 root 03:00 条目已废弃、部署时删除。 |

未改动：core/server.py、qiuzhao/tools.py、core/store.py、main 分支、主目录。

## 测试结果（qiuzhao/data/jobs.json，28,616 条；脚本 research/collector-fix-20260911/run_tests.py，结果 test-results.json）

**T1 幂等**：对当前数据跑 normalize，已有非空归一化值改动数 = **0**（CLI `--check` 输出 `would_change_existing: 0`）；第二次运行补齐数 = 0。当前数据只会补：overseas_flag 1110 条、region 1735 条、cities_normalized 1 条（原数据里本就空着的记录），共 2846 条。

**T2 复现率**（清空全部归一化字段后重算，与原值一致比例）：

| 字段 | 一致/原值非空 | 复现率 |
|---|---|---|
| job_category_normalized | 28616/28616 | 100% |
| graduation_year_normalized | 28511/28616 | 99.63% |
| major_normalized | 27639/28616 | 96.59% |
| city_normalized | 28616/28616 | 100% |
| cities_normalized | 28615/28615 | 100% |
| industry | 28575/28616 | 99.86% |
| country | 28616/28616 | 100% |
| overseas_flag | 27461/27506 | 99.84% |
| region | 25666/26881 | 95.48% |
| recruitment_type | 28606/28616 | 99.97% |

**T3 合并还原**：驱动真实 `Collector.run()`（stub postal 源返回 500 条摘掉归一化字段的已有记录），合并+归一化后 500 条的归一化字段 **100% 还原**（mismatch = 0）。

**T4 新记录**：3 条取值没见过的新记录（新单位名、新城市写法"深圳-南山区"、英文城市、空 cities、空 cohort），归一化字段全部非空且都在现有取值集合内（overseas_flag 为布尔）。示例：深圳-南山区→深圳/中国/mainland；NewYork→美国/海外/overseas_flag=true；cities=[]→未披露。

**T5 耗时**：28,616 条记录 `normalize_records` 0.2 秒；CLI 文件级（读+算+原子写 81MB）1.4 秒；对照表生成 1.3 秒。

**仓库已有测试**：`pytest` = 3 passed / 7 failed。7 个失败全部是 redemption_codes 缺 code_plain 列的既有问题（core/store.py，按要求未修）；qiuzhao 相关 2 个测试通过。

**真实采集验证**（`python -m qiuzhao.collector.run --output-dir /tmp/live-run`，jobs.json 副本做底，实际联网，23:22–23:45 共 23 分钟）：
- 完成 postal（27 页）、chnenergy（422 条详情）、boc、ccb、guopin（zgyd/ceec/cgnpc/cam2027/casicjob/zglt 各 campaign）真实抓取：refreshed 9358 条、新增 466 条、job_count 26739、removed 6。
- 收尾对全部记录调 normalize 的日志：`{'job_category_normalized': 169, 'graduation_year_normalized': 169, 'major_normalized': 169, 'city_normalized': 169, 'cities_normalized': 170, 'industry': 169, 'country': 169, 'overseas_flag': 10454, 'region': 1882, 'recruitment_type': 169}`。overseas_flag 补得多是因为旧版 carry 逻辑把 `False` 当缺失（已在 fe2bdc1 修复为按"非 None/空串/空列表"判断，False 也会被继承）。
- **端到端字段保全**：对比运行前后 jobs.json，26,273 条两侧都存在的记录，10 个归一化字段全部 **changed=0、lost=0**。
- telecom 源报 `KeyError: 'id'`（run.py:164 对无 id 的 legacy 记录下标访问，属 12:28 同类既有 bug，已修复）；因该 alert 进程以退出码 1 结束（原有语义）。除 telecom 外各源正常。
- 退出码 1 时新 cron 脚本会记 cron-status.json 并中断后续步骤——见"需要人决定的事项"。

## 已知误差

- 对照表冲突键取多数值的固有误差（仅在复合键 miss 时承担）：cat_to_jcn 343 冲突键/7891 条、unit_to_industry 431 键/921 条、major_raw_to_major 1 键/977 条、city_to_region 82 键/1215 条、title_to_jcn 157 键/284 条、cohort_to_grad 1 键/105 条（cohort_raw 为字符串 "None" 时多数值是"未披露"）。
- region 复现率最低（95.48%）：原数据 region 有 144 种写法（混有"佛山-禅城区"等脏值），规则按"中文海外城市→overseas、英文写法→海外、内地→mainland"统一，个别记录与原值不同。
- major_normalized 96.59%：major_requirements_raw 原文脏，少数记录只能兜底。
- 无 source_name 且城市未披露的记录，country 多数值是"海外"，表优先语义下可能补成"海外"。
- recruitment_type 规则不含"社会人才招聘"关键词，未知 cohort 兜底为"校园招聘"（与现有数据 75% 为校园招聘一致）。
- overseas_flag/region 原数据大量留空（1110/1735 条），补值是推断的生成意图，非原始事实。
- 背景资料提到的 `campaign_cohort_raw`/`recruitment_type_raw`/`nature_raw` 在实际数据中不存在，实际键用的是 `cohort_raw`/`cohort_scope`。

## 部署方案（由他人执行；所有替换文件取分支 fix/collector-normalize @ fe2bdc1）

目标 sha256（部署前后核对）：

```
f2f8af1d31d52f39f978a25596ba20dcf3195e49e8e1c7cb228da626094545f4  qiuzhao/normalize.py
a936edefd0ca3ace46dadf41237774e91c55cf428e77c8bee9d267554c5443ef  qiuzhao/normalize_tables.json
4942ed900356fe962d573ec5417c4b7f91fff8dd28279ab846b93ef6eb977276  qiuzhao/build_normalize_tables.py
f500b215565e973882c67de841ab891b5dc3ac9f6b1d3e0a91fb36e6cdaca7ce  qiuzhao/collector/run.py
b28a9b0ccd67bf7bd8e41ea0382583f2aa6954d54cb1d05760ff440f353ab1b2  qiuzhao/collector/auto_collect.py
d7ff220ab0289f7a5bbb4b12b8c0f196a3b66485c2aa3dc689aa483363776172  deploy/collector-daily.sh
f379a5d797bd8a6f881339bda6a286ef39d435766d9aae9f2a6e0c44faddd2f4  deploy/mcp-suite-qiuzhao.cron（安装到 /etc/cron.d/mcp-suite-qiuzhao）
```

1. **部署前核对**：确认服务器上 qiuzhao/collector/run.py、qiuzhao/collector/auto_collect.py、deploy/collector-daily.sh、/etc/cron.d/mcp-suite-qiuzhao 仍等于 main @ 1127cf7 的版本（今天 21:26 从服务器拉回的即此版本）；若服务器文件已被改动，先 diff 再决定是否合并。
2. **备份**：`cp -a /opt/mcp-suite /opt/mcp-suite.bak.$(date +%Y%m%d)`（至少备份 qiuzhao/、deploy/、/etc/cron.d/mcp-suite-qiuzhao）；`cp -a /var/lib/mcp-suite/jobs.json /var/lib/mcp-suite/jobs.json.bak.pre-normalize`；`crontab -l > ~/root-crontab.bak.$(date +%Y%m%d)`。
3. **安装**：rsync 上表 6 个文件到 /opt/mcp-suite 对应路径 + cron 文件到 /etc/cron.d/mcp-suite-qiuzhao（root:root 644）；确认 collector-daily.sh 有可执行位；sha256sum 逐一对照上表；`ls -ld /var/lib/mcp-suite` 确认 mcp-suite:mcp-suite 700；确认 /opt/mcp-suite/core/static 对 mcp-suite 可写（auto_collect 同步 changelog 需要；不可写也只是警告不失败）。
4. **删除 root crontab 03:00 条目**：`crontab -l` 确认 `0 3 * * * /usr/bin/python3 /opt/mcp-suite/qiuzhao/collector/auto_collect.py ...` 行 → `crontab -e` 只删该行 → `crontab -l` 复查。
5. **清理属主污染**：root 跑 auto_collect 留下的 root 属主文件（jobs.json、jobs.json.bak.auto.*、auto_collect_cron.log 等）一律 `chown mcp-suite:mcp-suite`。
6. **部署后验证**：
   - `sudo -u mcp-suite /opt/mcp-suite/.venv/bin/python -m qiuzhao.normalize --path /var/lib/mcp-suite/jobs.json --check`（在 /opt/mcp-suite 下运行），报告会补多少——预期 overseas_flag 1110、region 1735、cities_normalized 1，would_change_existing 必须为 0；
   - `sudo -u mcp-suite flock -n /var/lib/mcp-suite/collector.lock -c 'echo lock-ok'` 验证锁路径；
   - 可选：手动 `sudo -u mcp-suite /opt/mcp-suite/deploy/collector-daily.sh` 完整跑一遍，查 cron-status.json 为 success:true、jobs.json 属主仍为 mcp-suite；
   - 次日 06:10 后复查 cron-status.json 与 collector-cron.log。
7. **回滚**：`rsync` 回 /opt/mcp-suite.bak 的 qiuzhao/ 与 deploy/；恢复 /etc/cron.d/mcp-suite-qiuzhao 旧版；jobs.json 如有问题用 jobs.json.bak.pre-normalize 恢复；如需恢复 03:00 任务，`crontab ~/root-crontab.bak.*`。

## 需要人决定的事项

- auto_collect 的 `systemctl restart mcp-suite.service` 在 mcp-suite 账号下会失败（已改 best-effort 仅警告）。若服务不会在 jobs.json 变更后自动重读，需要加 sudoers 规则（`mcp-suite ALL=(root) NOPASSWD: /bin/systemctl restart mcp-suite.service`）或改由服务侧 watch 文件。
- run.py 任一来源告警即以退出码 1 结束（原有语义），新脚本按失败处理并中断后续步骤——auto_collect/normalize 当天不会执行，但 jobs.json 已是原子写好的完整文件。若希望"部分来源失败仍继续后续步骤"，需再改脚本。
