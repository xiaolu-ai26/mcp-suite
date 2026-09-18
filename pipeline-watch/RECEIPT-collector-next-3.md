# RECEIPT — collector-next-3：字节/美的 + 外企第二批合并 + 累积部署件 20260918k（不部署）

**结论先行**：`feat/bytedance-daily`（字节跳动/美的集团接入，20260918i）与
`feat/foreign-batch2`（四大 + 24 家外企 + 大易/51job 适配器，20260918j）已依次合并到
`feat/collector-next-3`，两边的 `p1_pipeline.py` 注册块**全部保留**，
`p1_platform_companies.json` 合并所有段且无覆盖、无改名。默认集合
`DEFAULT_COMPANIES` = **948 家**（20260918h 的 924 + 24 家新增，`REGISTRY` 同名唯一、无重复）。
调度归类完成：**大易（hotjob.cn）与 51job 归平台模块**（受 `PlatformGate` 同平台并发上限
与启动间隔约束，默认三 scope），**字节跳动、美的集团是每天必跑的专用适配器**（不进平台
模块集合，各自独立 gate 组，三 scope；美的 social 按设计 `blocked`）。`pytest tests/`
失败清单相对 `feat/collector-next-2` 基线**不新增**（3 条既有失败完全相同），零网络探针
`PROBE OK`。累积部署件 `pipeline-watch/deploy-artifacts/20260918k/`（17 个运行时文件 +
`SHA256SUMS.txt` + `PROD-BACKUP-MANIFEST.txt` + `DEPLOY-NOTES.md`）`shasum -c` 全 OK
且与分支源码逐字节一致。**未部署、未 SSH、未碰阿里云、未调飞书、未读取/打印令牌、
未登录、未 push、未合并、未终止任何进程。**

工作区：`/Volumes/臭垃圾桶/生财MCP/_worktrees/collector-next-3`（分支 `feat/collector-next-3`）。
Python：`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python`。外接盘 `._*`（AppleDouble）未纳入提交。

## 0. 分支与提交

| 项 | 值 |
|---|---|
| 起点 | `feat/collector-next-2` = `bcdfd09`（已审 20260918h，924 家） |
| `feat/bytedance-daily` | `dc73be9` → **Fast-forward** 并入（i 版：字节/美的 + `stable_id_prefix`） |
| `feat/foreign-batch2` | `b76bb78` → merge **`dfd97aa`**（冲突：`p1_pipeline.py` 注册块、`test_collector_next_integration.py` 顺序断言） |
| 整合改动 + 单测 + 探针 + 部署件 + 本收据 | 本收据所在提交 |

未 push、未合并 main、未部署。

## 1. 合并说明

- **顺序**：先 FF 并入 `feat/bytedance-daily`，再 `--no-ff` 合并 `feat/foreign-batch2`。
  合并提交 `dfd97aa` 的两个父提交是 `dc73be9`（i）与 `b76bb78`（j）。
- **`p1_pipeline.py` 注册块**：冲突段是"两边各自在飞书块之后追加注册块"，按任务要求
  **两块全部保留**，最终顺序为：
  `硬编码 50 → beisen → 银行 → 阿里 → 腾讯音乐 → Workday → SuccessFactors → 飞书(setdefault)
   → 字节跳动 → 美的集团 → 大易(p1_foreign_01) → 51job(p1_platform_51job)`。
  硬编码 `COMPANIES` 列表、i 的 `validate_result` 稳定 id 规则一字未改。
- **`p1_platform_companies.json`**：自动合并成功（无冲突），`_README` 采用 j 版并含
  `dayee` 说明；段规模 beisen 478 / moka 317 / feishu 78 / **dayee 7** / **job51 1** /
  workday 10 / successfactors 3。与 `feat/foreign-batch2` 相对 h 的 diff 逐字节相同
  （`diff <(git diff next-2..j -- cfg) <(git diff next-2 -- cfg)` 无输出）。
- **顺序类断言统一**：`tests/test_collector_next_integration.py` 的块顺序断言合并为
  9 块连续顺序（beisen → moka → banks → ali → tencent_music → workday/SF → feishu →
  字节/美的 public_api → dayee → 51job），并把 `covered` 变量改名为与语义一致的
  `coverage_blocks`；`test_p1_bytedance_public.py` / `test_p1_midea_public.py` 原样保留。
- **合并后无既有模块被顶替**：以 `feat/collector-next-2` 的 924 家 REGISTRY 为基线逐名比对，
  既有名字的模块归属 **0 处变化**、**0 家丢失**，只新增 24 个名字。

## 2. 调度归类

| 模块 | 家数 | 归类 | gate 组 | 默认 scope | 依据 |
|---|---|---|---|---|---|
| `p1_foreign_01`（大易 hotjob.cn） | 7 | **平台模块** | `hotjob.cn` | `campus,intern,social` | 多租户同一上游主机，必须与同 host 单元共享并发/间隔约束 |
| `p1_platform_51job` | 1 | **平台模块** | `51job.com` | `campus,intern,social` | 同上；非 campus 由适配器返回 `success/0 条 + note` |
| `p1_bytedance_public` | 1 | **每天必跑专用适配器** | `company:字节跳动` | `campus,intern,social` | 独立站点、单公司一条链，不受平台限流；social 触接口 1 万上限只能 `partial` |
| `p1_midea_public` | 1 | **每天必跑专用适配器** | `company:美的集团` | `campus,intern,social` | social 按设计 `blocked`（公开校招接口无社招），空集 ≠ 没有岗位 |

- 具体改动：`PLATFORM_MODULES` 增加 `p1_foreign_01`、`p1_platform_51job`；
  `PLATFORM_HOST_GROUPS` 增加 `hotjob.cn`、`51job.com`；`_load_scope_opt_ins()` 的段列表
  增加 `dayee`、`job51`（将来可用 `"scopes": [...]` 收窄）。`ROTATING_MODULES` 未动，
  两者都不轮转。
- 限流参数：代码常量 `PLATFORM_WORKERS=2`、`PLATFORM_MIN_INTERVAL=1.0`；精灵 p1 步
  传 `--platform-workers 3`，因此**生产实际同平台并发 ≤3、同平台单元启动间隔 ≥1s**。
- 字节/美的各自独立 gate 组（`company:<名称>`），组内只有自己，且 `plan_chains()`
  每公司一条链、scope 串行，所以不受平台限流也不拖慢其他公司。
- 单测锁定：见第 4 节 `test_dayee_and_51job_companies_join_the_platform_gate`、
  `test_gate_caps_concurrency_across_dayee_tenants`、
  `test_bytedance_and_midea_are_daily_dedicated_adapters`。

## 3. 默认集合规模与分组（实测）

**948 家 = 20260918h 的 924 + 字节跳动 + 美的集团 + 外企第二批新增 22 家**，
`len(DEFAULT_COMPANIES) == len(set(DEFAULT_COMPANIES)) == len(REGISTRY) == 948`。

| 连续块（按 DEFAULT 顺序） | 家数 |
|---|---|
| 硬编码 `COMPANIES` | 50 |
| `p1_platform_beisen` | 478 |
| `p1_platform_moka` | 313（另有 3 家在硬编码槽内，模块共 316） |
| `p1_banks_01` | 5 |
| `alibaba_headless` | 6 |
| `tencent_music` | 1 |
| `p1_platform_workday` | 10 |
| `p1_platform_successfactors` | 3 |
| `p1_feishu_public` | 72 |
| `p1_bytedance_public` | 1 |
| `p1_midea_public` | 1 |
| `p1_foreign_01`（大易） | 7 |
| `p1_platform_51job` | 1 |

**外企第二批净增 22 家**：基恩士（beisen）；安永、普华永道、高露洁棕榄、德州仪器、拜耳、
特斯拉、大众汽车集团(CARIAD)、达能、达美乐中国、伊顿、阿特拉斯科普柯、神龙汽车（moka）；
英特尔（workday）；德勤、康师傅、ZARA、广汽集团、益海嘉里、迪卡侬、ZURU（大易）；
百事（51job）。配置里 `kpmg/74356`（毕马威）是第 23 条新行，但"毕马威"已由更早的
`kpmg/76195` 注册，故净增 22 家（见第 8 节遗留）。

**四大全部在集合内**：德勤（大易）、安永 / 普华永道 / 毕马威（moka）。

**同名风险**：`高露洁`（beisen，存量）与 `高露洁棕榄`（moka，本批新增）是两个不同官方名，
REGISTRY 各占一条、互不覆盖；守护单测断言 REGISTRY/默认集合无重名、且任何一个配置段
都不能顶替别的段或硬编码槽已注册的模块。

## 4. 单测

命令（两个 worktree 相同）：`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest tests/ -q -rf -p no:randomly`

| 分支 | 结果 | 失败清单 |
|---|---|---|
| `feat/collector-next-2`（`bcdfd09`，基线） | 3 failed, 449 passed, 55 skipped | ① `test_core.py::test_role_cohort_and_campaign_title_bases` ② `test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint` ③ `test_schema.py::test_enum_check_fails_when_data_drifts` |
| `feat/collector-next-3`（合并后） | 3 failed, 498 passed, 55 skipped | 与基线**完全相同**，无新增；偶发 `test_codes_kind` 本次未触发 |

新增/更新测试：

- `tests/test_collector_next_integration.py`：合并块顺序断言统一；
  新增 `test_default_set_is_h_baseline_plus_i_and_j_additions`（948 家、i/j 新增成员、
  既有模块归属）、`test_registry_names_are_unique_and_config_sections_never_hijack_a_module`
  （重名 / 跨段顶替 / 硬编码槽守护）。
- `tests/test_p1_scheduling.py`：新增 `test_dayee_and_51job_companies_join_the_platform_gate`、
  `test_gate_caps_concurrency_across_dayee_tenants`（4 家大易同 host，`platform_workers=2`
  时实测峰值 ≤2）、`test_bytedance_and_midea_are_daily_dedicated_adapters`。
- i/j 自带适配器单测（`test_p1_bytedance_public.py` 18 条、`test_p1_midea_public.py` 13 条、
  `test_p1_foreign_01.py` 7 条、`test_p1_platform_51job.py` 6 条）全部保留通过。

## 5. 零网络探针

`pipeline-watch/collector-next3-probe.py`（只 import，不发任何请求）：

```
/Users/maxzhl/Projects/mcp-suite/.venv/bin/python pipeline-watch/collector-next3-probe.py
```

关键输出（`PROBE OK`，exit 0）：

```json
{"hardcoded": 50, "h_baseline": 924, "default_total": 948, "added_since_h": 24,
 "duplicates": 0,
 "bytedance": {"module": "qiuzhao.collector.p1_bytedance_public", "scopes": ["campus","intern","social"],
               "gate_group": "company:字节跳动", "platform_gated": false},
 "midea": {"module": "qiuzhao.collector.p1_midea_public", "scopes": ["campus","intern","social"],
           "gate_group": "company:美的集团", "platform_gated": false},
 "big_four": {"德勤": "qiuzhao.collector.p1_foreign_01", "安永": "...p1_platform_moka",
              "普华永道": "...p1_platform_moka", "毕马威": "...p1_platform_moka"},
 "dayee_total": 7, "dayee_groups": ["hotjob.cn"], "job51_total": 1, "job51_groups": ["51job.com"],
 "platform_modules_without_group": [], "rotation_default": 1, "default_select_full": true,
 "probe_day_total": 948}
```

探针同时断言：22 家外企第二批新增 + 字节/美的全部在默认集合内；每个平台模块都有 host 组；
大易/51job 不进轮转；默认不轮转时全选 948 家。

## 6. 部署件 `pipeline-watch/deploy-artifacts/20260918k/`

17 个运行时文件（**不含**测试与夹具）+ `SHA256SUMS.txt` + `PROD-BACKUP-MANIFEST.txt` +
`DEPLOY-NOTES.md`：

| 来源 | 文件 |
|---|---|
| 20260918h 的 12 个（其中 2 个本次新版） | `p1_pipeline.py`（新：i+j 合并 + 调度归类）、`p1_platform_companies.json`（新：= j 版）、`windows_collector.py`（与 h **逐字节一致** 9eaf97cc…）、`guopin.py`、`alibaba_headless.py`、`p1_banks_01.py`、`p1_feishu_public.py`、`p1_platform_beisen.py`、`p1_platform_moka.py`、`p1_platform_successfactors.py`、`p1_platform_workday.py`、`tencent_music.py` |
| 新增运行时 | `bytedance.py`（新版 07922a51…）、`p1_bytedance_public.py`、`p1_midea_public.py`、`p1_foreign_01.py`、`p1_platform_51job.py` |

校验结果：`shasum -a 256 -c SHA256SUMS.txt` → **17 个文件全部 OK**；
与分支源码 `cmp` 逐个比对 → **全部一致**；`py_compile` 全部 `.py` 通过；
`p1_platform_companies.json` 可解析。`PROD-BACKUP-MANIFEST.txt` 按两种前提分别列出
每个文件的"部署前应有哈希"：①精灵仍是 20260918 现役；②精灵已是 20260918h。
`run.py` 不变，不在包内。

## 7. 部署步骤（沿用 `TASK-collector-next-2-deploy.md` 流程，文件数/路径按 k 更新）

1. **等空闲**：`runs\<今天>\receipt.json` 有 `completed_at`；无 `windows_collector.py` /
   `p1_pipeline` / `lark_sync` 的 python 进程；`data\lark-sync\status.json` 不是 `running`。
   正在跑就每 5 分钟看一次，最多等 3 小时；超时不部署。
2. **前置哈希核对**：按实际状态选前提 ①（20260918 现役）或 ②（已 h），逐文件对照
   `PROD-BACKUP-MANIFEST.txt`；不一致就停（drift）。注意 `bytedance.py` 在两种前提下都应
   存在（旧采集器版 609a241e…），`p1_feishu_public.py` 若已存在需备份而非删除。
3. **备份**：`robocopy C:\mcp-suite-collector\deploy C:\mcp-suite-backup-<YYYYMMDD-HHmm>\deploy /E /R:2 /W:5`
   与 `...\qiuzhao ...\qiuzhao /E /R:2 /W:5`（退出码 ≤7 成功；**不要**全目录 robocopy）。
   核对备份里 4 个现役文件（+ 若存在的 `bytedance.py` / `p1_feishu_public.py`）哈希与前提一致。
4. **Playwright Chromium**（阿里系 + 飞书 headless 依赖）：先
   `Test-Path "$env:LOCALAPPDATA\ms-playwright"`；缺则
   `C:\mcp-suite-collector\.venv\Scripts\python.exe -m playwright install chromium`，
   并用 `python -c "from playwright.sync_api import sync_playwright; ..."` 做一次不访问外网的
   最小启动验证。失败不阻塞部署，但要在收据标注"阿里系/飞书首日 blocked"。
   大易/51job/字节/美的/北森/Moka/Workday/SF/银行/腾讯音乐都是纯 HTTP，不需要浏览器。
5. **传输并校验**：17 个文件传到 `C:\mcp-suite-deploy-20260918k\`，逐字节与
   `SHA256SUMS.txt` 一致后才允许下一步。
6. **覆盖 17 个目标路径**：12 个 h 目标（`deploy\windows_collector.py`；
   `qiuzhao\collector\{guopin.py, p1_pipeline.py, p1_feishu_public.py, p1_banks_01.py,
   alibaba_headless.py, tencent_music.py, p1_platform_beisen.py, p1_platform_moka.py,
   p1_platform_workday.py, p1_platform_successfactors.py, p1_platform_companies.json}`）
   + 5 个新文件（`qiuzhao\collector\{bytedance.py, p1_bytedance_public.py,
   p1_midea_public.py, p1_foreign_01.py, p1_platform_51job.py}`）。覆盖后再各算一次 sha256；
   `py_compile` 全部 `.py`；用正式 venv（cwd=`C:\mcp-suite-collector`）跑
   `python -c "import deploy.windows_collector, qiuzhao.collector.p1_pipeline as P; print(len(P.DEFAULT_COMPANIES), len(P.REGISTRY))"`
   → 预期 **`948 948`**。不重启任何服务、不改计划任务。
7. **不手动补跑**：以次日 06:10 的正常运行为首次实测。
8. **收尾**：部署记录（时间、备份路径、覆盖前后哈希、import 输出、Playwright 结果）
   追加到本收据的"F. 部署记录"；在 worktree
   `/Volumes/臭垃圾桶/生财MCP/_worktrees/collector-next-3` 的分支上 commit，不 push、不合并。
9. **回滚**（任一校验失败）：按 `PROD-BACKUP-MANIFEST.txt` 的对应前提恢复/删除，
   回滚后逐字节校验 = 前提值并写明触发原因。

## 8. 次日观察项补充

相对 20260918h 的观察项（`TASK-collector-next-2-deploy.md` 已列）之外，重点看：

- **字节跳动**：`p1` 状态里 `字节跳动/campus` 应约 **2663 条**、`intern` 约 5578 条、
  `social` 命中接口 1 万上限 → `partial`（**永不**触发缺席下线）。合并后应为
  **原 `bytedance-<id>` 原地更新、0 重复**：`p1` 合并后 `source_name=字节跳动` 的行数
  不应暴增；新增约 441 条、2222 条原地更新（预演值），且首跑不会删除那 22 条未覆盖的
  存量校园行（它们还没有 `p1_company`/`p1_scope`）。
- **美的集团**：`campus` 应 **214 条**、`intern` 应 **321 条**，均 `success + complete`；
  `social` 应为 `blocked`（设计如此，不是故障）；`midea-<positionId>` 原 id 原地更新
  （146 条存量不重复）。
- **大易（德勤等 7 家）**：第一次跑要看 `coverage.status`；`campus/intern/social`
  三 scope 各自结果，7 家同 host 受平台 gate（同平台并发 ≤3、启动间隔 ≥1s）约束，
  预计排在平台段中后部；`QIUZHAO_PLATFORM_REQUEST_BUDGET` 生产不限。
- **51job（百事）**：`campus` 正常出岗位；`intern/social` 预期 `success/0 条 + note`
  （官网只发布校招），不要当成失败。
- **集合规模**：`runs\<次日>\` 的 p1 status 里公司数应为 **948**；若看到 924/926/947
  说明覆盖不完整或配置段丢失。
- 其余沿用 h 的观察项：`guopin.discovered`（约 14）、`fallback_used=false`、
  `data\p1-retry-queue.json`、平台公司尝试数、各平台 blocked 比例、飞书同步 `changed` 量级、
  p1 起止时间（三 scope、8 路并发）。

## 9. 遗留

1. **毕马威第 2 个 moka 租户是惰性配置行**：`kpmg/74356`（本批）与 `kpmg/76195`（存量）
   同名，`NAME_TO_SLUG` 反转后"后写覆盖"，实测解析到 `kpmg/76195`。因此新租户当前不会
   被采集；若 76195 停更，需要显式删掉旧行或改名区分（REGISTRY 只有一个"毕马威"）。
   守护单测保证它不会顶替别的段，但无法自动判断该取哪个租户。
2. **`p1_platform_companies.json` 的 workday 段 `intel/wd1/External` 后多一个空行**
   （j 分支带入，纯格式，不影响解析）；下次动该文件时顺手清理。
3. **美的 social / 字节 social 的口径**：前者永久 `blocked`，后者恒 `partial`；
   两者都不参与缺席下线，属预期，不要按"失败"处理。
4. **i/j 的部署件仍留在仓库**（`20260918i/`、`20260918j/`，j 含测试与夹具）：
   它们已被 k 完全覆盖，保留仅作审计；实际部署只需 k。
5. **Playwright 未验证**：精灵 `%LOCALAPPDATA%\ms-playwright` 是否存在、阿里系与飞书
   首日是否 blocked，仍需部署执行者在部署时确认（本任务未 SSH、未验证）。
6. **本任务未部署**：k 的首次真实运行数据（948 家的耗时、`--max-run-seconds 18000`
   是否够、各平台 blocked 比例）要等次日 06:10 那次运行才能确认。

## 10. 部署记录（20260918k 叠加部署到精灵，2026-09-18 20:19–20:31）

**结论先行：部署成功，未触发回滚。** 执行者按任务书把累积部署件
`pipeline-watch/deploy-artifacts/20260918k/`（分支 `feat/collector-next-3`，
`git log -1 --format=%h feat/collector-next-3` = **`f423084`**）叠加覆盖到精灵
`C:\mcp-suite-collector` 的 **17 个目标路径**。部署前按 `PROD-BACKUP-MANIFEST.txt`
的**前提②**（精灵已是 20260918h）逐文件核对现役哈希：**17/17 一致、零漂移**，
确认精灵确为 h 状态，未出现 i/j 越权上线或旁路改动。四道哈希（部署前前提 / 备份内容 /
覆盖后目标 / 暂存区对清单）全部通过；`py_compile` 退出码 0，
`IMPORT_OK 948 948`，REGISTRY 抽查 `字节跳动→p1_bytedance_public`、
`美的集团→p1_midea_public`、`德勤→p1_foreign_01`、`百事→p1_platform_51job`。
Playwright `chromium-1187` 已在位，**只做启动验证、未重装**。

硬约束遵守情况：未重启任何服务、未改计划任务定义、未碰 `.venv` 内 Playwright 以外内容、
未碰 `data\` 与 `runs\`、未碰 `run.py`、未碰阿里云、未手动跑飞书同步、未读取或打印任何
令牌、未删除精灵上任何目录、未 push、未合并、**未终止任何进程**。

### 10.1 时间线（Asia/Shanghai，均为远端/本地实测值）

| 时刻 | 步骤 | 实测结果 |
|---|---|---|
| 20:19:32 | 步骤1 等空闲判定 | **通过** |
| 20:19:5x | 部署前前提②逐文件核对 | **17/17 一致**（ok=17 bad=0） |
| 20:20:12 | 步骤2 robocopy 备份结束 | deploy 退出码 **1**、qiuzhao 退出码 **1**（≤7 = 成功） |
| 20:20:2x | 备份内容按前提②复核 | **17/17 一致**（ok=17 bad=0） |
| 20:20:5x | 步骤3 Playwright 确认 | `chromium-1187` 在，最小启动 **`LAUNCH_OK`**，未重装 |
| 20:21:5x–20:26:59 | 步骤4 分片 base64 传输 17 文件 | **17/17 `XFER_OK`**（每片 ≤1300 字节，两片一次调用） |
| 20:27:0x | 暂存区按远端 `SHA256SUMS.txt` 独立复核 | **`STAGE-VERIFY ok=17 bad=0`**，`_tmp` 无残留 |
| **20:27:41** | 步骤5 覆盖 17 个目标路径 | `COPY_DONE`（新增文件 CreationTime=20:27:41 实测） |
| 20:27:5x | 覆盖后目标路径复核哈希 | **`PROD-AFTER-K ok=17 bad=0`** |
| 20:28:0x | `py_compile` + import + REGISTRY 校验 | **全通过**（见 10.5） |
| 20:28:19 | 收尾核查（`run.py`、计划任务、`runs\`/`data\` 未动） | **通过**（见 10.6） |

### 10.2 步骤1 等空闲（判定：空闲，未等待）

| 判据 | 实测 |
|---|---|
| `runs\<今天>\receipt.json` 有 `completed_at` | `runs\20260918\receipt.json`（注意目录名是 `20260918`，不是 `2026-09-18`）`completed_at = 2026-09-18T20:03:53.883036+08:00`，`started_at = 2026-09-18T06:10:01`，`steps = {basic:2, tencent:0, p1:2, normalize:0}` |
| 无 `windows_collector.py` / `p1_pipeline` / `lark_sync` 的 python 进程 | 全机仅 1 个 python 进程：`pythonw.exe "C:\jack-asr\bridge.py"`（PID 20956，与秋招无关），标记匹配结果 `NO-MATCH` |
| `data\lark-sync\status.json` 不是 `running` | `status = "success"`，`phase = "complete"`，`finished_at = 12:03:53Z`（= 20:03:53+08），mtime 20:03:53 |

当日 06:10 那一轮已在 20:03:53 全部收尾，20:19 判定空闲成立，**未发生 5 分钟轮询等待**。

### 10.3 步骤2 备份（新时间戳，未覆盖既有备份）

- 备份目录：**`C:\mcp-suite-backup-20260918-2020`**（CreationTime 实测 2026-09-18 20:20:12）。
  既有的 `C:\mcp-suite-backup-20260918`（13:06）与 `C:\mcp-suite-backup-20260918-2010`
  （h 那次部署，20:10）**原样保留、未被触碰**。
- 命令与结果（只备份 `deploy` 与 `qiuzhao` 两棵树，**未**做全目录 robocopy）：
  - `robocopy C:\mcp-suite-collector\deploy C:\mcp-suite-backup-20260918-2020\deploy /E /R:2 /W:5` → 退出码 **1**（94.6 k）
  - `robocopy C:\mcp-suite-collector\qiuzhao C:\mcp-suite-backup-20260918-2020\qiuzhao /E /R:2 /W:5` → 退出码 **1**（2.12 m）
- 备份内容复核（根 `C:\mcp-suite-backup-20260918-2020` + 同一张 17 行前提②表）：
  **`ok=17 bad=0`**，即 13 个现役文件哈希与前提②逐一相等，4 个文件确认 ABSENT。

### 10.4 步骤4/5 哈希对照（覆盖前 = 前提②，覆盖后 = k 清单）

| 目标路径（相对 `C:\mcp-suite-collector`） | 覆盖前 sha256（前提②实测） | 覆盖后 sha256（= k 清单） | 覆盖后字节 |
|---|---|---|---|
| `qiuzhao\collector\p1_pipeline.py` | `c48dbf94c13f03394897a767f2fb918d1afcd06658ae93d32975d42cf98310a9` | `ff96be4d772847a0273003e2db0466d3ad698dc5cd719d968f40fb96abc8dc76` | 60357 |
| `qiuzhao\collector\p1_platform_companies.json` | `ee0f288cf6213da356f9f0dcaf03e54374472ab3519b2a1a4f91e8b9ee86349b` | `bf592f62cd644a20d16e948027832763da268d236439be6dba1d95dc1980f843` | 91766 |
| `deploy\windows_collector.py` | `9eaf97cc5d4e968c062aaa65468ab34c584534a4ced5523d75c7c26229ec8312` | 同左（k 与 h **逐字节一致**，覆盖后哈希不变） | 14311 |
| `qiuzhao\collector\guopin.py` | `add0d50c715e06eb968bb7671bc2e9787e81d9ad39be008e66731337f16b6c03` | 同左 | 17499 |
| `qiuzhao\collector\alibaba_headless.py` | `dab17686cf251f220950b8c8e13984d39dcbb07b8a3eeeea84bdea3ca3be7db2` | 同左 | 27404 |
| `qiuzhao\collector\p1_banks_01.py` | `25e2399812f64ee1762b7686849bf7241c8e1353d7203347562f9794223ffb19` | 同左 | 31314 |
| `qiuzhao\collector\p1_feishu_public.py` | `e9855205ad1cc9494855d1357ab93c68f6e6ead646e7441bd6032c7311a8ca4f` | 同左 | 25593 |
| `qiuzhao\collector\p1_platform_beisen.py` | `3faeb5686aa7bf05a7b6754b35a607c50a9666e8247dd5b46d430307b9eb33a5` | 同左 | 15571 |
| `qiuzhao\collector\p1_platform_moka.py` | `569e0865d96ba7f91a4803330975ac76f9f35277b9f1bf312092c598c636a777` | 同左 | 15737 |
| `qiuzhao\collector\p1_platform_successfactors.py` | `658c81c07bd4ebda62735662dfac54722dccc830517072e3a40d9329701f1216` | 同左 | 22012 |
| `qiuzhao\collector\p1_platform_workday.py` | `d95e11b29f30368a1f4657d22fdb1c10d88495bd1ccac03f8a15c613caeb706b` | 同左 | 19966 |
| `qiuzhao\collector\tencent_music.py` | `7d19cbc34b45dfc5e31c3d9b7ed41dd51c638c5adb6c62bf6e0330904f3d3787` | 同左 | 14631 |
| `qiuzhao\collector\bytedance.py` | `609a241e2a6f0d80e31e6c1a5e8abfeb2979404f6f2efffdbc4edb6fb3e16a00`（旧采集器版，实测存在，与两种前提预期一致） | `07922a5111dd6356d97d289d472ae78bf177dd95bf8f401db6284e8e18140c8d` | 13890 |
| `qiuzhao\collector\p1_bytedance_public.py` | **ABSENT**（实测） | `bc2926472037e24c212f47a0d62750ca9cd921a7b01df5af6dbe0f56d5c160e6` | 16885 |
| `qiuzhao\collector\p1_midea_public.py` | **ABSENT**（实测） | `509b9a502d7e1010c478896fc1312ae380aa97a3847412bdef8cb48bc2c97186` | 18023 |
| `qiuzhao\collector\p1_foreign_01.py` | **ABSENT**（实测） | `549481bbe540a7633c080a519617bbe7e23dc4d95d5bb1f4ec127b771460a052` | 15043 |
| `qiuzhao\collector\p1_platform_51job.py` | **ABSENT**（实测） | `f19201fe4340e802216f8fb1428cece2457aba611cdf798bd9cce42441bc32bb` | 12696 |

- 传输暂存目录：**`C:\mcp-suite-deploy-20260918k\`**（17 个运行时文件 + `SHA256SUMS.txt`；
  该清单远端 sha256 = `239052ea6b163983579912ef7e392011d8d8aa6db2bdb25a3a103bb4ccf6d19b`
  = 本地 `git show` 版本，逐字节一致）。分片入参是
  `C:\mcp-suite-deploy-20260918k\_tmp\*.b64`，全部解码后已自删，**`_tmp` 目录保留为空目录**
  （硬约束：不删除精灵上任何目录）。
- `p1_feishu_public.py` 的 CAVEAT：实测**存在**且哈希 = 前提②值 `e9855205…`（属 h 的 12 个
  之一），因此回滚口径是**还原备份**，不是删除。
- **异常与恢复（如实记录）**：第一次跑传输循环时，`ssh` 继承了 `while read` 的 stdin，
  把 `expected.tsv` 余下各行吃掉，只传完 `alibaba_headless.py` 就跳到结束。已在 ssh 调用上
  加 `< /dev/null` 后整体重跑；第二次 17/17 全部 `XFER_OK`，覆盖前对暂存区的独立复核为
  `STAGE-VERIFY ok=17 bad=0`。第一次的残留只是暂存区里一个随后被正确覆盖的同名文件，
  生产目录当时未被触碰。

### 10.5 步骤5 覆盖后校验（正式 venv，cwd=`C:\mcp-suite-collector`）

```
PY_COMPILE_EXIT=0                       # 16 个 .py 全部 py_compile 通过（json 不参与）
IMPORT_OK 948 948                       # 预期 948 948 ✔
REGISTRY3 qiuzhao.collector.p1_bytedance_public qiuzhao.collector.p1_midea_public qiuzhao.collector.p1_foreign_01
MODS {"字节跳动": "qiuzhao.collector.p1_bytedance_public",
      "美的集团": "qiuzhao.collector.p1_midea_public",
      "德勤": "qiuzhao.collector.p1_foreign_01",
      "百事": "qiuzhao.collector.p1_platform_51job"}
=== S5-CHECK-DONE ===
```

- 解释器：`C:\mcp-suite-collector\.venv\Scripts\python.exe` →
  `3.12.2 (tags/v3.12.2:6abddd9, Feb  6 2024) [MSC v.1937 64 bit (AMD64)]`。
- **未重启任何服务、未改计划任务定义、未手动补跑**（首次实测 = 次日 06:10 的
  `Qiuzhao-Collector-Daily`）。

### 10.6 步骤3 Playwright 与收尾核查

Playwright（阿里系 headless 依赖，**未重装**）：

```
MS_PW=C:\Users\-LZH-\AppData\Local\ms-playwright  EXISTS=True
  ENTRY .links / chromium_headless_shell-1187 / chromium-1187 / ffmpeg-1011 / winldd-1007
CHROMIUM_1187_EXISTS=True
  CHROME ...\chromium-1187\chrome-win\chrome.exe  3006976
PLAYWRIGHT_IMPORT_OK ...\.venv\Lib\site-packages\playwright\__init__.py
PW_PKG_VER 1.55.0
LAUNCH_OK ok
BROWSER_VERSION 140.0.7339.16
```

最小启动验证只用 `set_content()` 渲染一行 HTML、**未访问外网**。结论：阿里系 / 飞书
headless 路径可用，**不存在"首日 blocked"风险**。

收尾核查：

| 检查 | 实测 |
|---|---|
| `qiuzhao\collector\run.py` 未动 | sha256 = `5e94f91b770ef02bfad887e10bb6fab3405d8b184a81b98df9d14fe28c266b28`（前 8 位 `5e94f91b` 与前提一致），mtime 仍是 2026-09-18 13:36:00 |
| `runs\20260918\receipt.json` 未动 | mtime 仍是 2026-09-18 20:03:53 |
| `data\lark-sync\status.json` 未动 | mtime 仍是 2026-09-18 20:03:53 |
| 计划任务定义未改 | `Qiuzhao-Collector-Daily` = Ready、`Qiuzhao-Rebase-20260913` = Ready、`Qiuzhao-Resume-20260914` = Ready、`Qiuzhao-Followthrough-20260914` = Disabled（只读列举，未做任何写操作） |
| `qiuzhao\collector` 目录 | 只有 17 个目标文件 mtime 变为 20:22–20:27（`Copy-Item` 保留源 mtime，故显示为传输时刻；实际覆盖时刻以新增文件 CreationTime **20:27:41** 为准），其余文件 mtime 全部维持 2026-09-13/14/17；子目录只有既有的 `__pycache__` |

### 10.7 回滚件与回滚口径（本次未使用）

- 返回 h 状态：用 **`C:\mcp-suite-backup-20260918-2020`** 还原 17 个路径
  （恢复 13 个现役文件，删除 k 新增的 4 个：`p1_bytedance_public.py`、`p1_midea_public.py`、
  `p1_foreign_01.py`、`p1_platform_51job.py`；`p1_feishu_public.py` **还原而非删除**）。
- 触发条件：本任务书第 5 步任一校验失败（本次全部通过，**未触发**）。

### 10.8 次日（2026-09-19 06:10）观察项（供总控核对）

- `runs\20260919\receipt.json`：`steps` 出现 basic/p1 的 `0` 或 `2`、`step_changes.p1` 条数、
  p1 起止时间（不轮转、三 scope、8 路并发，预期 3–5 小时；若触顶 5 小时上限，看
  `status.pending` 与次日公平排序是否生效）。
- `runs\20260919\data\source_state.json`：`guopin.discovered`（预期约 14）、`fallback_used=false`。
- p1 status：**公司数应为 948**（看到 924/926/947 说明覆盖不完整或配置段丢失）；
  平台公司尝试数（应为全部 874 或受 5 小时上限截断的数量）、各平台 blocked 比例、
  银行/阿里/外企的 `coverage.status`。
- **字节跳动**：`campus` 约 2663 条、`intern` 约 5578 条、`social` 命中接口 1 万上限 →
  `partial`（设计如此，**永不**触发缺席下线）；应为原 `bytedance-<id>` 原地更新、
  0 重复（预演值：新增约 441 条、2222 条原地更新）。
- **美的集团**：`campus` 约 214 条、`intern` 约 321 条，均 `success + complete`；
  `social` 应为 `blocked`（设计如此，不是故障）；`midea-<positionId>` 原地更新。
- **大易（德勤等 7 家）**：首次要看三 scope 各自 `coverage.status`；7 家同 `hotjob.cn`
  受平台 gate（同平台并发 ≤3、单元启动间隔 ≥1s）约束，预计排在平台段中后部。
- **51job（百事）**：`campus` 正常出岗位；`intern/social` 预期 `success/0 条 + note`
  （官网只发布校招），**不要当成失败**。
- `data\p1-retry-queue.json` 是否生成；飞书同步 `changed` 量级。
- 阿里系 / 飞书：Playwright 已验证可用，首日**不应**因浏览器缺失而 blocked；
  若仍 blocked，按网络/门户改版排查，不要再怀疑 Chromium 安装。

### 10.9 本节的边界

- 本节只证明「文件已正确落盘 + 模块可导入 + 集合规模 = 948」，**不等于** k 的业务效果已验证：
  948 家的真实耗时、`--max-run-seconds 18000` 是否够、字节/美的/大易/51job 的真实产出，
  都要等次日 06:10 那次运行。
- 部署件里的 `DEPLOY-NOTES.md` 与 `PROD-BACKUP-MANIFEST.txt` **未**传到精灵暂存区
  （任务书只要求传运行时文件 + 清单）；回滚依据在本仓库内。
