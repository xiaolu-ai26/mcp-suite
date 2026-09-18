# 部署件 20260919b：外企补齐 A（Eightfold + Phenom 两个平台适配器，13 家外企）

**叠加顺序：叠在 `20260918k` 之上，一步覆盖 4 个文件。** 精灵现役 = `20260918k`
（2026-09-18 20:27 上线，17 文件、948 家）。本包只动 4 个运行时文件：

| 文件 | 目标路径 | 类型 | 部署前（= 20260918k 包内同名文件） |
|---|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖 | `ff96be4d772847a0…`（k 版；本包 = k + 1 个追加注册块 + 2 个平台分组项） |
| `p1_platform_companies.json` | `qiuzhao/collector/p1_platform_companies.json` | 覆盖 | `bf592f62cd644a20…`（k 版；本包 = k + `eightfold`/`phenom` 两段） |
| `p1_platform_eightfold.py` | `qiuzhao/collector/` | **新增** | 不存在 |
| `p1_platform_phenom.py` | `qiuzhao/collector/` | **新增** | 不存在 |

逐文件部署前/后哈希见 `PROD-BACKUP-MANIFEST.tsv`。校验用 `shasum -a 256 -c SHA256SUMS.txt`
（在本包目录内执行）。本包**未部署、未 SSH、未碰阿里云、未调飞书、未写库、未 push**。

## 本包不包含 `windows_collector.py`（重要）

`windows_collector.py` 必须以**精灵现役版**为准（末尾同步段调 `lark_sync_daemon`；
main 上的版本调 `lark_sync_index`，精灵上没有该模块，整文件覆盖会炸）。本次改动完全
不涉及每日链入口，因此**故意不打包**该文件。`run.py` 同样未改（仍 `5e94f91b…`）。

## 为什么不新增依赖

两条适配器的**主路径只用 `requests`**——它们直接请求公开 careers 页面自己发出的那个
URL（详见收据 §「接口契约」）。Playwright 只在被 401/403/429 拒绝时作为**兜底**惰性
导入，精灵已装 `chromium-1187`，无需重装或新增 pip 包。

## 为什么 k → b 是一次覆盖而不是两个包

本批只追加一块独立注册块（Eightfold → Phenom，位于 51job 块之后），并且
`PLATFORM_MODULES` / `PLATFORM_HOST_GROUPS` 各加两项；`p1_platform_companies.json`
只在文件末尾追加两个段。既有注册块、既有公司、既有配置行**一字未动**，所以单包覆盖
即可，不需要拆分。

## 调度归类

- 两个模块都进 `PLATFORM_MODULES`，各自一个 host 组（`eightfold` / `phenom`）：
  同平台并发 ≤ `--platform-workers`（线上 3）、同平台单元启动间隔 ≥
  `PLATFORM_MIN_INTERVAL`（1.0s），默认三 scope（campus / intern / social）。
- 都不进 `ROTATING_MODULES`：每天全跑，不轮转。
- 不新增专用 gate 组：13 家全部挂在平台 gate 上。

## 默认集合规模

- `DEFAULT_COMPANIES` = **961 家** = k 的 948 + 本批 13（Eightfold 5 + Phenom 8）。
- 13 个名字在 `REGISTRY` 中此前均不存在，无重名、无覆盖、无顶替。
- 零网络探针 `pipeline-watch/foreign-ats-a-probe.py` 输出 `PROBE OK`。

## 请求量（生产默认不限预算，按平台 gate 串行）

| 平台 | 每次全量 listing | 每 scope 详情 | 三 scope 合计（约） |
|---|---|---|---|
| Eightfold（5 家） | 36 次（10 条/页，start 游标） | 每个岗位恰好落一个 scope | ≈ 430 次/天 |
| Phenom（8 家） | 19 次（500 条/页，from 游标） | 同上 | ≈ 1 220 次/天 |

合计约 1 650 次/天，按无间隔约 10–15 分钟，且被平台 gate 压到同平台最多 2 家并发，
不会挤压其它公司。`QIUZHAO_PLATFORM_REQUEST_BUDGET` / `..._INTERVAL` 仍可随时收紧。

## 上线后观察项

1. `runs\<日期>\receipt.json` 里 13 家的 `coverage.status`：预期
   `success`（小租户全量）/ `partial`（大租户详情多，属正常）。
2. 13 家**不应**出现 `blocked`；若出现，先看 401/403/429 与 `mode` 字段
   （`direct` = 直连，`headless` = 走了兜底）。
3. `data\p1-last-attempt.json` 与 `data\p1-retry-queue.json` 里这 13 家的耗时。
