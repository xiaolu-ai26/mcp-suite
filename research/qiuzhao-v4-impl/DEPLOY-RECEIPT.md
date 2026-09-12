# 秋招 MCP v4 接口部署收据（DEPLOY-RECEIPT）

部署时间：2026-09-12 12:39–12:47（北京时间，约 8 分钟）　执行：Claude（Opus 5）执行会话，经 Max 批准
目标：`root@114.215.188.109`，代码 `/opt/mcp-suite`（venv `.venv`），数据 `/var/lib/mcp-suite`，服务 `mcp-suite.service`（127.0.0.1:8768，公网 `https://savegems.top/qiuzhao/`）
部署版本：分支 feat/v4 @ **2f0f070**；基线 main @ 1127cf7（线上实际就是该版本，第 2 步已逐一核对）
依据：`research/qiuzhao-v4-impl/KIMI-DEPLOY.md`，逐步执行未跳步、未改命令。
范围：只替换 6 个文件、只重启 `mcp-suite.service`。未碰 `mcp-suite-bench.service`、nginx、cron、`jobs.json` 及其他站点。全程未使用任何真实 key、兑换码或管理员令牌。

> 执行者变更：任务书原写给 Kimi Code，Kimi 于 11:59 启动后因额度用尽退出（服务器未被改动），Max 明确要求改由 Claude 直接部署。除执行者身份外，任务书内容全部照此执行。

## 第 1 步：前置条件（三项全部通过）

**1a. 采集状态**

```
2026-09-12 12:39:43        # 北京时间，不在 05:55–07:30 禁止窗口
NO-COLLECTOR-PROCESS
LOCK-FREE
completed_at(北京) 2026-09-12T06:55:23+08:00 success True steps {'collector.run': 0, 'auto_collect': 0, 'normalize': 0}
PRECONDITION OK
```

当日 06:10 的自动采集已于 06:55:23（北京）正常结束，三步退出码全 0。

**1b. 本地仓库**

```
feat/v4
98ca784 docs: v4 wrap-up — SPEC, examples, evidence for decision 2 and the new order; Kimi deploy task book
C-IN-BRANCH
NO-CODE-CHANGE-SINCE-C
(core/qiuzhao/tests 无未提交改动，status 输出为空)
MAIN-IS-ANCESTOR
```

**1c. 部署包（`git archive 2f0f070`，不用工作区文件）**：6 个 sha256 与任务书“目标 sha256”逐一相同，见第 6 步表格。

## 第 2 步：线上现状核对（只读，全部符合）

5 个待替换文件的 sha256 与任务书“线上现状”（= main 1127cf7）逐一相同；`qiuzhao/v4_fields.py` 报 `No such file or directory`；`mcp-suite.service`、`mcp-suite-bench.service` 均 `active`。

- bench `ActiveEnterTimestamp=Thu 2026-09-10 15:41:37 CST`（第 8 步比对用）
- `free -m` available **992 MB**（≥ 600 MB 门槛）；`df -h /` → `/dev/vda3 40G 23G 16G 60% /`

**两个静态页线上未被改动**，因此未触发第 2 步的“重新套用 6 处替换”分支；`guide.html`、`app.js` 均为 **feat/v4 原样**，目标哈希不变。

## 第 3 步：枚举检查（用线上最新 jobs.json，只读，未写文件）

```json
{
 "items": 25631,
 "data_as_of": "2026-09-12T06:55:17+08:00",
 "problems": []
}
RESULT OK
```

items 25,631，`problems` 为空，数据中没有枚举外的新值。

## 第 4 步：备份

目录 `/opt/mcp-suite/deploy/backup-pre-v4-20260912-124139/`，`SHA256SUMS` 5 个值与第 2 步逐一相同：

```
08143798a78ca401be294c7d3425b7f6398cd200cf93bf57b12a0e31f191dccd  core/server.py
77ffdb613a746636314e31786b2a451b57dd061670abba2542695e406ece0d52  qiuzhao/tools.py
0348d335f28f8d11b81840e22aa25fedb7decb54f97745d0b227c90c5e3283c6  core/store.py
4afa8338dd26965607f47386dcd8520dae1ac9d1b0a5d588be7faa075839b4d4  core/static/guide.html
cb3d5e92940d90a28860c965b5e40803ef252077f04c3f43838a20eef8b4af10  core/static/app.js
```

数据库副本 `backup-pre-v4-20260912-124139/data/access.sqlite3`：`-rw------- mcp-suite mcp-suite 81920`，与源文件大小一致（源 81920 B，`mcp-suite:mcp-suite 600`）；`-wal`、`-shm` 均不存在，未复制。**仅 `cp -p` 复制，全程未读取内容**（未用 sqlite3/strings/cat/head/xxd/file）。此副本只供应急，恢复它需 Max 同意。

## 第 5 步：预建调用日志目录

```
mcp-suite:mcp-suite 700 /var/lib/mcp-suite/call_logs
```

## 第 6 步：安装（先暂存核对，通过后才装到位）

暂存目录 `/opt/mcp-suite/deploy/v4-pkg-20260912-124139/` 的 6 个 sha256 = 目标哈希；装到位后再次核对仍相同，属主权限全部 `root:root 644`。

| 文件 | 部署前 sha256（线上旧版） | 部署后 sha256（= 目标，2f0f070） | 属主:权限 |
|---|---|---|---|
| `core/server.py` | `08143798a78c…dccd` | `09e831800ab674f36e0e855b22ec1befd261d71133b6c78d55c4d73e2ab6f7c8` | root:root 644 |
| `qiuzhao/tools.py` | `77ffdb613a74…0d52` | `5fe3d3d60e06b21ea5ea6ae73f327da6a2c8ba976859d8087a7e6bedeecc9d5b` | root:root 644 |
| `qiuzhao/v4_fields.py` | 不存在（新文件） | `ceb411808794ee6d742c73e4143cb15ea0b7ee52690e5d277e37368e80c25bd7` | root:root 644 |
| `core/store.py` | `0348d335f28f…83c6` | `a43fe29325064352bbe69028359563d6dbc9dc3e162c7663acc94110e7f43c07` | root:root 644 |
| `core/static/guide.html` | `4afa8338dd26…4dd4` | `a1e03aeaaf915bb72523f6a4cc3058fd66bc49804f367e7541d8cebec12813ec` | root:root 644 |
| `core/static/app.js` | `cb3d5e92940d…4af0` | `cd30fbfd46544fefd28bcb117b2f540f4e9ed826f41ecbc4ccb3f0e050e9aa15` | root:root 644 |

静态页来源：**feat/v4 原样**（线上未被改过，无需重新套用 6 处替换）。

## 第 7 步：重启前 schema 核验（临时库与临时日志目录均在 /tmp，用完删除）

与本地 `evidence/verify_schema_v4.txt` 完全一致：

```
qiuzhao jobs_detail: params=1 anyOf/oneOf=False missing_type=[]
qiuzhao jobs_search: params=15 anyOf/oneOf=False missing_type=[]
qiuzhao jobs_stats: params=14 anyOf/oneOf=False missing_type=[]
RESULT OK []
tmp-cleaned
bench bench_detail: params=1 anyOf/oneOf=False missing_type=[]
bench bench_search: params=8 anyOf/oneOf=False missing_type=[]
bench bench_taxonomy: params=0 anyOf/oneOf=False missing_type=[]
RESULT OK []
tmp-cleaned
```

## 第 8 步：只重启 mcp-suite.service（12:44:07–12:44:09）

```
active            # mcp-suite.service
active            # mcp-suite-bench.service
ActiveEnterTimestamp=Thu 2026-09-10 15:41:37 CST
```

bench 的 `ActiveEnterTimestamp` 与第 2 步**完全相同**，bench 未被重启。journal 最近 3 分钟无 `Traceback`、`Error`、`mcp_call_log_warning`：停机 → 新进程 PID 1827727 → `Application startup complete` → `Uvicorn running on http://127.0.0.1:8768`。

## 第 9 步：/health 与内存

| 来源 | 返回 |
|---|---|
| `http://127.0.0.1:8768/health`（首次，含缓存构建 2.59s） | `{"status":"ok","jobs":25631,"data_as_of":"2026-09-12T06:55:17+08:00"}` |
| `https://savegems.top/qiuzhao/health` | `{"status":"ok","jobs":25631,"data_as_of":"2026-09-12T06:55:17+08:00"}` |

`jobs` = 25,631，与第 3 步 items 一致（v4 按去重、去测试记录后的条数计；v3 报有效行数 25,642）。

内存：重启前 available **992 MB** → 重启后 available **874 MB**（12:46 复测 891 MB）。qiuzhao uvicorn（PID 1827727，:8768）RSS **222,284 KB ≈ 217 MB**。bench（:8769，PID 1709267）RSS 7,700 KB，未动。

## 第 10 步：端到端核验（服务器上、mcp-suite 身份、进程内，临时库签发临时 key，不用任何真实 key）

```
health    {'status': 'ok', 'jobs': 25631, 'data_as_of': '2026-09-12T06:55:17+08:00'}
search    {'total': 1933, 'explicit_total': 244, 'inferred_total': 24, 'unspecified_total': 1665, 'excluded_social_total': 167}
           技术类校招岗位(2027届) | 成都,天津,北京,上海,深圳 | {"level": "明确匹配", "graduation_year": "岗位写明", "city": "岗位写明", "major": "岗位写明"}
           27届博士(J13367) | 成都 | {"level": "明确匹配", "graduation_year": "岗位写明", "city": "岗位写明", "major": "岗位写明"}
           成都市武侯区分公司-金融柜员 | 成都 | {"level": "明确匹配", "graduation_year": "岗位写明", "city": "岗位写明", "major": "岗位写明"}
           成都市金牛区分公司-金融柜员 | 成都 | {"level": "明确匹配", "graduation_year": "岗位写明", "city": "岗位写明", "major": "岗位写明"}
           成都市青羊区分公司-金融柜员 | 成都 | {"level": "明确匹配", "graduation_year": "岗位写明", "city": "岗位写明", "major": "岗位写明"}
stats     22525 [('北京', 5519), ('上海', 2907), ('深圳', 1609)]
call log  lines 2 modes ('0o700', ['0o600']) last {"ts": "2026-09-12T12:45:27.333+08:00", "product": "qiuzhao", "tool": "jobs_stats", "args": {"graduation_year": "2027届", "group_by": "city", "top": 3}, "ua": "v4-e2e-check/1.0", "user_ref": "644cb6fca3e0", "outcome": "ok", "error_type": null, "result_total": 22525, "returned": 3, "duration_ms": 101}
tmp removed True
RESULT OK []
```

- 与任务书列出的 00:52 期望值**逐项相同**（search total 1933 / explicit 244 / inferred 24 / unspecified 1665 / excluded_social 167；stats total 22525，北京 5519、上海 2907、深圳 1609）。
- 前 5 条城市依据全部为“岗位写明”，没有“全国”——同一档内按匹配的具体程度排序符合预期。
- 调用日志 2 行，目录 700、文件 600。
- 清理：`/tmp/v4-e2e-*` → `tmp-cleaned`；生产 `/var/lib/mcp-suite/call_logs/` 为空（本步写临时目录，不写生产日志）。
- 输出中未出现任何 key、兑换码或 Bearer 令牌（`user_ref` 为临时库内临时 key 的不可逆引用，该库已随临时目录删除）。

## 第 11 步：回滚

**未触发**。命令留存备查：

```bash
BK=/opt/mcp-suite/deploy/backup-pre-v4-20260912-124139
OLD="core/server.py qiuzhao/tools.py core/store.py core/static/guide.html core/static/app.js"
ssh root@114.215.188.109 "set -e; cd /opt/mcp-suite; for f in $OLD; do cp -p $BK/\$f \$f; done; rm -f qiuzhao/v4_fields.py; sha256sum $OLD; systemctl restart mcp-suite.service; sleep 5; systemctl is-active mcp-suite.service; curl -s http://127.0.0.1:8768/health"
```

数据库无需回滚：线上库本来就有 `code_plain` 列，新 `store.py` 的迁移只在列不存在时执行。

## 第 12 步：收尾

- **12a**：暂存目录 `/opt/mcp-suite/deploy/v4-pkg-20260912-124139` 已删除（`STG-REMOVED`）；备份目录 `/opt/mcp-suite/deploy/backup-pre-v4-20260912-124139` 保留。
- **12b**：`prepare_main_ff.py` dry run → `blockers=18 safe=18 different=0` / `dry run: nothing moved`；`--apply` → `moved 18 file(s) to /Users/maxzhl/Projects/mcp-suite-preff-backup-20260912-124630`（18 个全部 `identical-to-commit`：`research/qiuzhao-v4-interface-20260911/` 下 17 个未跟踪文件 + 改过未提交的 `scripts/v4lib.py`）。
  `git merge --ff-only feat/v4` → `Updating 6d580e1..98ca784  Fast-forward`，72 files changed, 22337 insertions(+), 221 deletions(-)。
  **main 快进：`6d580e1db2f6f45dfba73c115f7f00170f4d468d` → `98ca784a7a696f878556dd209509f97cd7dff194`**，与 feat/v4 的 HEAD 相同。
- **12c**：本收据在 main 上提交。未 push，未改 feat/v4 以外的任何分支。

## 与任务书不一致之处 / 备注

1. **执行者**：任务书写给 Kimi Code，实际由 Claude 执行（Kimi 额度用尽，Max 明确改派）。Kimi 未改动服务器，无需回滚。
2. **stderr 噪声**：第 7、10 步输出中有 venv 自带库的 `AuthlibDeprecationWarning`（authlib.jose、httpx）和 starlette 的 `DeprecationWarning`，任务书期望块未列出。这些来自依赖包的 import 期告警，与本次部署的 6 个文件无关，重启日志中同样出现且部署前就存在，不影响 `RESULT OK []`。
3. **qiuzhao RSS 217 MB**，低于任务书预估的 250–350 MB（偏省内存，非失败条件）；available 874 MB 远高于 400 MB 门槛。
4. **静态页未触发重新套用分支**：线上 `guide.html`、`app.js` 自 2026-09-11 21:26 后未被改动，直接用 feat/v4 原样。
5. 兑换码功能（feat/codes-kind）本次未部署，未触碰该分支及其任务书。

## 后续观察点

- 次日 06:10 cron 自动采集后复查 `/var/lib/mcp-suite/cron-status.json` 与 `/health` 的 `jobs`、`data_as_of`（v4 口径为去重后条数，与 v3 的有效行数不可直接比较）。
- 首批真实调用产生后，检查 `/var/lib/mcp-suite/call_logs/` 的文件权限（应为 600）与 journal 是否出现 `mcp_call_log_warning`。
- 备份目录 `/opt/mcp-suite/deploy/backup-pre-v4-20260912-124139`（含未读取的 `data/access.sqlite3` 副本）建议在确认 v4 稳定运行后由 Max 决定清理时机。
