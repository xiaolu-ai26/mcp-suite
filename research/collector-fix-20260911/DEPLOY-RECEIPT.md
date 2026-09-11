# 秋招采集修复部署收据（DEPLOY-RECEIPT）

部署时间：2026-09-12 00:02–00:55（北京时间）　执行：Kimi Code 主代理（经 Max 批准）
目标：`root@114.215.188.109`，代码 `/opt/mcp-suite`，数据 `/var/lib/mcp-suite/jobs.json`
部署版本：分支 fix/collector-normalize @ **3d5cff6**（含第 0 步新提交）；基线 main @ 1127cf7（21:26 生产快照）
全程未重启任何服务（mcp-suite.service 每次调用重读 jobs.json），未碰 core/、nginx、bench 服务及其他站点。

## 第 0 步：collector-daily.sh 改造（本地）

改动：run.py 非零退出（来源告警语义）不再中断链条——记退出码继续 auto_collect → normalize；auto_collect / normalize 失败仍照原逻辑记录状态并中断；cron-status.json 新增 `steps` 字段（逐步退出码），run.py 部分失败时写 `success:false` + `exit_code` + 说明"部分失败、是哪一步"的 `alert`。

- `bash -n` 通过；桩测试（flock 桩化、三步骤换 true/false 桩）四场景全部符合预期：全成功（exit 0, success:true, steps 全 0）；仅 run.py 失败（exit 1, success:false, alert=Partial failure: step collector.run exited 1..., steps {1,0,0}，后续两步照跑）；normalize 失败（exit 1, alert 指名 normalize）；auto_collect 失败（中断，normalize 未执行）。
- 提交：`3d5cff6 deploy: continue chain when run.py reports source alerts`
- 新 sha256：`1c863beb90ebc9546b99cf99a4ff20809081cdf84800eb7e4b74ab02e3f0f012  deploy/collector-daily.sh`

## 第 1 步：部署前检查（全部通过）

- 服务器 4 个文件 sha256 与 `git show 1127cf7:<path>` 逐一相等：run.py `f2404cfb…df27`、auto_collect.py `8251026d…3a8b`、collector-daily.sh `94f4fc86…ed1e`、/etc/cron.d/mcp-suite-qiuzhao `62fdcc78…5d39`。
- root crontab 确认含 `0 3 * * * /usr/bin/python3 /opt/mcp-suite/qiuzhao/collector/auto_collect.py >> ...`。
- `df -h /`：59%（< 85%）；`du -sh /var/lib/mcp-suite`：985M。
- 无采集进程；`flock -n /var/lib/mcp-suite/collector.lock true` 拿到锁。

## 第 2 步：备份

- 目录 `/opt/mcp-suite/deploy/backup-pre-collector-fix-20260912-000220/`：run.py、auto_collect.py、collector-daily.sh、mcp-suite-qiuzhao（cron）、root-crontab.txt、SHA256SUMS。
- 数据备份 `/var/lib/mcp-suite/jobs.json.bak.pre-collector-fix-20260912-000220`（81,814,583 B，mcp-suite:mcp-suite 600，cp -a 保留属主权限）。

## 第 3 步：安装（sha256 全部等于工作副本）

| 文件 | sha256 | 属主:权限 |
|---|---|---|
| qiuzhao/normalize.py | f2f8af1d…45f4 | root:root 644 |
| qiuzhao/normalize_tables.json | a936edef…43ef | root:root 644 |
| qiuzhao/build_normalize_tables.py | 4942ed90…7276 | root:root 644 |
| qiuzhao/collector/run.py | f500b215…a7ce | 501:staff 644（沿用原属主） |
| qiuzhao/collector/auto_collect.py | b28a9b0c…3ab2 | root:root **755**（原 711 mcp-suite 不可读，放宽） |
| deploy/collector-daily.sh | **1c863beb…f012**（第 0 步新版） | 501:staff 755 |
| /etc/cron.d/mcp-suite-qiuzhao | f379a5d7…d2f4 | root:root 644 |

## 第 4 步：删除 root crontab 03:00 条目（00:03 完成，早于 02:45 红线）

`crontab -l | grep -v -F '/opt/mcp-suite/qiuzhao/collector/auto_collect.py' | crontab -`；与备份 diff 仅 `12d11` 一行（即目标行），其余条目（宝塔任务、acme.sh、aihot 同步等）原样保留。

## 第 5 步：属主清理

清理前列出的 root 属主文件 14 个。改为 mcp-suite:mcp-suite 的 11 个采集产物：
jobs.json.bak.20260910-233514、jobs.json.bak.20260911-050031、jobs.json.bak_beisen2/3/4/5、jobs.json.bak.codex.20260911-103312、jobs.json.bak.normalized.20260911-145313、jobs.json.bak.normalized_v2.20260911-151149、jobs.json.bak.priority1.20260911-111258、jobs.json.bak.quality.20260911-050114。
保留 root 属主不动（非采集产物）：access.sqlite3.bak.20260911-184425、companies_latest.csv、jobs_export_latest.csv。

## 第 6 步：装完核验（通过）

`runuser -u mcp-suite -- python -m qiuzhao.normalize --path jobs.json --check`：
records 28616，**would_change_existing = 0**，filled_total = **2846**（overseas_flag 1110、region 1735、cities_normalized 1，其余 0），tables_loaded true，check 模式未写文件。
`curl 127.0.0.1:8768/health` → `{"status":"ok","jobs":27506,"data_as_of":"2026-09-11T12:00:00+08:00"}`。

## 第 7 步：手动完整采集（00:04 启动，00:52 结束，约 48 分钟）

`nohup runuser -u mcp-suite -- /opt/mcp-suite/deploy/collector-daily.sh`。postal 27 页 → chnenergy 422 条详情 → boc/ccb/guopin（zgyd/ceec/cgnpc/cam2027/casicjob/zglt）→ auto_collect → normalize，三步全部 exit 0（run.py 本次无来源告警）。

**cron-status.json（最终内容）**：
```json
{"success": true, "completed_at": "2026-09-11T16:52:46.689574+00:00", "steps": {"collector.run": 0, "auto_collect": 0, "normalize": 0}}
```

**运行前后对比**：

| 指标 | 运行前 | 运行后 |
|---|---|---|
| jobs.json 记录数（原始行数） | 28,616 | 26,749 |
| 去重后唯一 id 记录 | 26,273（+297 无 id） | 26,452（+297 无 id） |
| 10 字段非空条数 | 7 字段全满；cities_normalized 28,615、overseas_flag 27,506、region 26,881 | **10 字段全部 26,749/26,749（100%）** |
| jobs.json 属主权限 | mcp-suite:mcp-suite 600 | mcp-suite:mcp-suite 600（未变） |

- 两侧都存在（按 id）的 26,273 条记录逐字段比对：**changed = 0，lost = 0**；唯一 id 记录 removed = 0。
- 原始行数减少 1,867 全部为 run.py 按 id 去重合并（与 23:22 本地实跑验证的 28,616→26,739 行为一致；本次源数据略异得 26,749），无任何唯一记录丢失。
- 新增 179 条记录 10 字段全部补齐；297 条无 id 记录前后均满。
- normalize 收尾日志：filled_total 0、would_change_existing 0（run.py/auto_collect 已就地归一化）。
- `/health` → `{"status":"ok","jobs":25642,"data_as_of":"2026-09-12T00:52:36+08:00"}`。
- 只读搜索：`Jobs('/var/lib/mcp-suite/jobs.json').search(job_category='产品')` → **total 1281**，正常。
- 采集运行未产生新的 root 属主文件。
- 日志中两个按设计的 best-effort 警告（不影响退出码，服务侧重读 jobs.json 故无需重启）：changelog 同步 core/static 因权限被拒（仅告警）；`systemctl restart mcp-suite.service` 在 mcp-suite 账号下被拒（仅告警、忽略）。

## 第 8 步：回滚（未触发，留存命令备查）

```bash
BK=/opt/mcp-suite/deploy/backup-pre-collector-fix-20260912-000220
cp -a $BK/run.py /opt/mcp-suite/qiuzhao/collector/run.py
cp -a $BK/auto_collect.py /opt/mcp-suite/qiuzhao/collector/auto_collect.py
cp -a $BK/collector-daily.sh /opt/mcp-suite/deploy/collector-daily.sh
cp -a $BK/mcp-suite-qiuzhao /etc/cron.d/mcp-suite-qiuzhao
crontab $BK/root-crontab.txt        # 恢复 root 03:00 条目
rm -f /opt/mcp-suite/qiuzhao/normalize.py /opt/mcp-suite/qiuzhao/normalize_tables.json /opt/mcp-suite/qiuzhao/build_normalize_tables.py
# jobs.json 损坏时：
cp -a /var/lib/mcp-suite/jobs.json.bak.pre-collector-fix-20260912-000220 /var/lib/mcp-suite/jobs.json
```

## 第 9 步：本地 main 同步

`git -C /Users/maxzhl/Projects/mcp-suite merge --ff-only fix/collector-normalize`：1127cf7 → **3d5cff6** 快进成功。本收据在 main 上提交。

## 后续观察点

- 次日 06:10 cron 首次自动跑后，复查 `/var/lib/mcp-suite/cron-status.json`（应为 success:true + steps 全 0）与 collector-cron.log。
- run.py 将来若再有来源告警（exit 1），链条会照跑完且 cron-status 记 success:false + steps——属预期语义，看 steps.collector.run 即可定位。
- changelog 同步 static 需要 core/static 对 mcp-suite 可写，或接受该告警（当前行为）。
