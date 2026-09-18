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
