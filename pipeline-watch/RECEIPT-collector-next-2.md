# RECEIPT — collector-next-2：四线整合 + 905+ 家调度安全 + 累积部署件（不部署）

**结论先行**：三条"加公司"线（`feat/ali-tencent-gap` / `feat/foreign-companies` /
`feat/xianyu-slugs`）已合并到 `feat/collector-next-2`，`DEFAULT_COMPANIES` = **924 家**
（50 硬编码 + 874 平台/其它，无重复）。平台公司默认只跑 `campus`+`intern`；同平台并发 ≤2、
同平台单元启动间隔默认 ≥1s；`--platform-rotation` 默认 **2**（北森/Moka/飞书分日，
硬编码 50/银行/阿里-腾讯音乐/外企每天跑）。公司名清洗 60 家（58 取闲鱼表名 + 2 冲突回退）。
离线验证 live 10 家 `campus` 共 **38s**、每租户 ≤15 请求；零网络桩覆盖商汤/大华；
零网络探针通过。部署件 `pipeline-watch/deploy-artifacts/20260918g/` 就绪，`shasum -c` 全 OK。
**未部署、未 SSH、未碰阿里云、未调飞书、未改闲鱼表、未 push、未合并 main。**

工作区：`/Volumes/臭垃圾桶/生财MCP/_worktrees/collector-next-2`（`feat/collector-next-2`）。
外接盘 `._*` 为 AppleDouble 垃圾，未纳入提交。全程只在 worktree 操作。

## 0. 分支与提交

| 项 | 值 |
|---|---|
| 起点 | `feat/banks-batch1` = `fc18bd8` |
| `feat/ali-tencent-gap` | `91915ba`（Fast-forward） |
| `feat/foreign-companies` | `9c91698` → merge `131e690`（冲突：p1_pipeline 注册块、2 个顺序断言测试） |
| `feat/xianyu-slugs` | `4dfdf86` → merge `c98a7ae`（冲突：p1_pipeline 注册块、`p1_platform_companies.json`、2 个测试） |
| 整合改动 | `b9a8bed`（调度安全 / 清洗 / 飞书 collect 别名 / 单测 / 探针） |
| 部署件+收据 | 本收据所在提交（`deploy-artifacts/20260918g/` + 本文件） |

未 push、未合 main。

## 1. 合并说明

- **顺序**：`ali-tencent-gap`（FF）→ `foreign-companies`（--no-ff）→ `xianyu-slugs`（--no-ff）。
- **`p1_pipeline.py` 注册块**：三个分支都在银行块之后追加独立块；按任务要求"全部保留，
  顺序 平台北森/Moka → 银行 → 阿里/腾讯音乐 → Workday/SF → 飞书"，飞书块保留
  `setdefault`（不覆盖硬编码/已注册公司）。硬编码 50 的 `COMPANIES` 列表一字未动。
- **`p1_platform_companies.json`**：合并所有段（beisen 477 / moka 304 / feishu 78 /
  workday 9 / successfactors 3），`_README` 合并说明。
- **顺序类断言**：`tests/test_collector_next_integration.py` 改为按 REGISTRY 模块分块、
  断言"块连续且顺序正确"；`tests/test_p1_banks.py` 改为"银行块连续 + 相对顺序不变"，
  不再假设银行在末尾。
- **合并后集合**：924 家 = 50 硬编码 + beisen 477 + moka 301 + feishu 72 + 银行 5 +
  阿里 6 + 腾讯音乐 1 + Workday 9 + SF 3（moka/feishu 各有 3/6 家与硬编码同名，
  保留硬编码槽位不重复）。比任务预估的 920 略多，因为闲鱼表实际写入 477 北森 /
  301 生效 Moka / 72 生效飞书。

## 2. 调度安全设计与耗时估算

### 2.1 设计（全部在 `p1_pipeline.run()` 的分链/提交逻辑，不改适配器）

1. **scope 默认**：`company_scopes()` 对平台模块（beisen/moka/feishu/workday/successfactors/
   banks）默认返回 `campus,intern`；硬编码 50 与阿里/腾讯音乐返回三 scope。
   某平台公司要在配置对象里加 `"scopes": ["campus","intern","social"]` 才开 social。
2. **平台限流**：`platform_group()` 按上游主机分组（`zhiye.com` / `app.mokahr.com` /
   `jobs.feishu.cn` / `myworkdayjobs.com` / `successfactors` / `banks` / `alibaba` /
   `tencent_music`；硬编码各自 `company:<name>`）。`PlatformGate` 用信号量把同组并发
   钉在 `--platform-workers`（默认 2），并保证同组单元启动间隔 ≥`--platform-interval`
   （默认 1s）；跨平台仍受 `--workers`（精灵 4）限制。另注入
   `QIUZHAO_PLATFORM_REQUEST_INTERVAL`（取 max(1.0, platform-interval)，不降低调用方显式值）
   给 Workday/SF 这类支持的适配器；北森/Moka/飞书保留自身分页 pacing。
3. **分日轮转**：`companies_for_day()` 只对 `ROTATING_MODULES`（beisen/moka/feishu）
   按 `slug` 的 sha256 前 8 字节分桶，桶号 = `date.toordinal() % N`，每天跑一组；
   硬编码 50、银行、阿里/腾讯音乐、Workday/SF 恒在。`--platform-rotation N` 控制，
   仅在未传 `--companies` 时生效（显式公司集合永远全跑）。
4. **硬上限/重试**：`--max-run-seconds 18000` 与 `p1-retry-queue.json` 语义未改。
   `windows_collector.py` 无需新增参数（轮转/限流都有默认值），本包中原样使用
   `20260918b/windows_collector.py`，同步段一字未动。

### 2.2 耗时估算（按各分支收据实测请求数推算；结论：不轮转会 >3h）

实测口径：闲鱼批量实测（预算 15/租户）北森 ≈8 请求/租户/scope、Moka ≈11、飞书 ≈9；
生产关闭预算后 Moka 会取全量详情。按 campus+intern 两 scope、每条请求有效 ~0.5s、
同平台 2 路并发、全局 4 路估算：

| 平台 | 生效公司 | 每轮请求（估） | 2 路并发耗时（估） |
|---|---|---|---|
| 北森 zhiye.com | 477 | ~9,500（列表页+抽样详情） | ~0.7h |
| Moka app.mokahr.com | 301 | ~18,000（生产全量详情，平均 ~30 岗/租户×2 scope） | ~1.3h |
| 飞书 jobs.feishu.cn | 72 | ~1,000 + 144 次浏览器启动 | ~0.3–0.5h |
| **平台小计（850）** | | | **~2.0–2.5h**（考虑全局 4 路争用） |

再叠加**每天必跑**的硬编码 50（三 scope，现役日链本来就有）+ 银行 5 + 阿里 6 +
腾讯音乐 1 + Workday 9 + SF 3（≈1–2h），**整轮不轮转约 3–4.5h**，逼近甚至超过
`--max-run-seconds 18000`（5h），也超过 3h 阈值。因此实现轮转。

**轮转后**：N=2 时平台部分减半（~1–1.25h），整轮约 **2–2.5h**，为次日重试和
长尾大租户留出余量。该估算未把 WAF/网络波动计入，属保守下界。

## 3. 轮转推荐值

**推荐 `--platform-rotation 2`（已设为默认）**：850 家平台公司按 slug 哈希分成
435/415 两组（2026-09-18 实测），当天跑 415 或 435 家平台 + 74 家每天必跑 = 约
**489–509 单元链**（company 数，campus+intern 两 scope 在链内串行）。若次日观察发现
单轮仍 >3h 或频繁触发 18000s，再调 `3`（每组 ~283 家，平台部分再降三分之一，
新鲜度降为 3 天一轮）。`--platform-rotation 1` 关闭轮转、跑全量（用于人工全量核验）。

## 4. 公司名清洗统计

- 新增可重复函数 `qiuzhao/collector/p1_company_names.py`（`clean_company_name` /
  `strip_site_title` / `apply_cleanup` / `resolve_cleanup`，含 CLI：
  `python -m qiuzhao.collector.p1_company_names [--write]`）。
- 规则：干净名不动；脏名（含 招聘/门户/网申/官网/校招/校园、`|`/`-` 标语、英文
  campus recruitment、尾部编号、引号口号）优先取闲鱼表 `company_names` 中与"去后缀
  名"最长前缀匹配的名字；无表匹配则去后缀。同段内重名冲突回退到去后缀名，避免
  `NAME_TO_SLUG` 丢租户（科大国创云网 / 科大国创股份）。
- 统计：配置共 871 条（beisen/moka/feishu/workday/successfactors），**变更 60 条**
  （58 条取闲鱼表名，2 条冲突回退）。重复执行结果不变（幂等，二次运行 changed=0）。
- 对照文件：`pipeline-watch/company-name-cleanup.csv`（原名 → 清洗后 + 来源）。
  例：`海大官网招聘门户 → 海大集团`、`AIVA汽车校园招聘门户网 → AIVA汽车`、
  `招聘门户 → 回天新材`、`e签宝招聘官网-杭州天谷信息科技有限公司 → e签宝`。
  清洗后无同段重名、无新增与硬编码重名（安踏集团 等 9 家既有重叠保持不变）。

## 5. 离线验证（Mac，只读，未 `--apply`）

### 5.1 live 混合 `campus`（`--workers 4`）

命令（`/tmp/cn2-verify`，未写库；每租户预算 15、平台单元间隔 2s）：

```bash
QIUZHAO_PLATFORM_REQUEST_BUDGET=15 QIUZHAO_BANK_REQUEST_BUDGET=15 \
QIUZHAO_TME_REQUEST_BUDGET=15 QIUZHAO_PLATFORM_REQUEST_INTERVAL=2 \
python -m qiuzhao.collector.p1_pipeline --data-dir /tmp/cn2-verify/data \
  --run-dir /tmp/cn2-verify/run \
  --companies '中信建投,安徽康明斯,七色纺商业连锁有限公司,小天才,阿斯利康中国,保融科技,巴奴集团,交通银行,英伟达,腾讯音乐' \
  --scopes campus --workers 4 --platform-workers 2 --platform-interval 2 \
  --scope-timeout 180 --max-run-seconds 900
```

结果：**EXIT=2，总耗时 38s**；序号目录 `01`–`10` 齐全；10 个结果无 pending。
请求预算（used/limit）：中信建投 9、安徽康明斯 4、七色纺 4、小天才 15、阿斯利康中国 4、
保融科技 8、巴奴集团 3、交通银行 11、英伟达 15、腾讯音乐 3——**全部 ≤15**。
9 家 success（含飞书 `collect` 别名修复后真实跑通），英伟达因 15 预算上限记 partial。
链接：`/tmp/cn2-verify/run/status.json`。

**说明（硬约束冲突的处置）**：任务列出的 `商汤科技`（硬编码飞书路径）与 `大华股份`
（硬编码 Beisen 路径）适配器会**逐条抓详情**且不读任何预算/间隔 hook：实测大华单个列表页
就有 369 条（campus+social），无法满足"每租户 ≤15 请求、间隔 ≥2s"的硬约束。因此未对
这两家发外部请求，改用 5.2 的零网络桩验证其链路/序号/注册；建议后续给硬编码 Beisen/
飞书适配器补一个预算 hook（本次按"不改适配器"未做）。

### 5.2 零网络桩：完整混合 10 家（含商汤/大华）

`unittest.mock.patch(p.collect_process)` + `run(..., workers=4, platform_workers=2)`：
10 家全部到达、序号 `01`–`10`、10 个结果、无 pending；scope 分别
硬编码/阿里/腾讯音乐三 scope，平台/银行两 scope。写入 `/tmp/cn2-stub/`（无网络）。

### 5.3 零网络探针

`python pipeline-watch/collector-next2-probe.py`（纯 import，无请求）→ `PROBE OK`：
默认 924 家（50 硬编码 + 874）、无重复；块计数 beisen 477 / moka 301 / feishu 72 /
banks 5 / alibaba 6 / tencent_music 1 / workday 9 / successfactors 3；平台 scope
`['campus','intern']`、硬编码与阿里/腾讯音乐三 scope；默认轮转 2 组（435/415），
2026-09-18 选中 489 家（50 硬编码 + 24 每天跑 + 415 平台），硬编码与每天跑组恒在。

## 6. 部署步骤（同 `RECEIPT-collector-partial-keep.md` E3，加新文件校验与 Playwright 安装）

1. **备份**：精灵 `C:\mcp-suite-collector` 整目录 robocopy 到 `C:\mcp-suite-backup-<日期>\`。
   核对现役 3 个将被覆盖的文件 sha256 与 `20260918g/PROD-BACKUP-MANIFEST.txt` 一致：
   `p1_pipeline.py` = `dc046e32...`、`guopin.py` = `22e5f6ad...`、
   `deploy\windows_collector.py` = `14e17785...`（首 8 位）。不一致就停下来找总控。
2. **传输**：把 `20260918g/` 下 12 个文件传到精灵临时位置（scp 不可用则分片 base64，
   同 E2），精灵侧 `Get-FileHash` 与 `SHA256SUMS.txt` 逐字节核对后再覆盖。
3. **覆盖文件（12 个，一次性）**：`qiuzhao\collector\` 下
   `guopin.py`、`p1_pipeline.py`、`p1_platform_beisen.py`、`p1_platform_moka.py`、
   `p1_platform_workday.py`、`p1_platform_successfactors.py`、`p1_feishu_public.py`、
   `p1_banks_01.py`、`alibaba_headless.py`、`tencent_music.py`、
   `p1_platform_companies.json`，以及 `deploy\windows_collector.py`
   （**用本包的 20260918b 逐字版，不是分支 `deploy/windows_collector.py`**）。
   覆盖后对 12 个目标路径各做一次 sha256，与 `SHA256SUMS.txt` 比对留证。不需重启；
   计划任务次日 06:10 自然生效。
4. **Playwright Chromium（阿里 + 飞书 headless；由站长手动执行，本包未执行）**：

   ```bat
   C:\mcp-suite-collector\.venv\Scripts\python.exe -m playwright install chromium
   ```

   代码在找不到自带 Chromium 时回退系统 Chrome（`channel='chrome'`）。若精灵无 Chrome，
   必须先装 Chromium，否则阿里系与飞书公司会 blocked。
5. **首日观察**：见第 7 节。

## 7. 次日观察项

- `runs\<日期>\receipt.json`：`steps.p1` 为 0 或 2（不因个别平台 blocked 回滚）、
  `step_changes.p1.added/updated` 有数；`base-sync` 仍 `sync_exit==0`。
- `runs\<日期>\data\p1-status.json`：`companies` 数量 ≈ 489–509（轮转生效），
  50 硬编码 + 24 每天跑全在；`retry.priority/demoted` 正常。
- 各平台覆盖率：北森/Moka 大租户可能 `partial`（生产无预算时反而更完整）；
  飞书如全 blocked 先查 Playwright/Chrome。
- 耗时：`receipt.json` 的 p1 用时 < 18000s；若 >3h 或频繁超时，把
  `--platform-rotation` 调到 3。
- 公司名：抽查新入库记录的 `canonical_company` 是否为公司简称（不应再出现
  "招聘门户"等站点标题）。
- 重试队列：连续 3 天失败的单元会被降到最后；确认没有平台因限流被整批误判。

## 8. 回滚

- `guopin.py` / `p1_pipeline.py` / `deploy\windows_collector.py`：用第 1 步本地备份
  （或 `pipeline-watch/deploy-artifacts/20260918/` 同名文件）拷回。
- 9 个新增文件（`p1_platform_*.py`、`p1_feishu_public.py`、`p1_banks_01.py`、
  `alibaba_headless.py`、`tencent_music.py`、`p1_platform_companies.json`）：删除即可；
  旧 `p1_pipeline.py` 的平台 import 有 try/except，删掉后自动退回 50 家。
- 数据层无需回滚：本包不含改库逻辑，`--apply` 语义与重试队列未变。

## 9. 遗留与风险

1. **硬编码适配器无预算 hook**：大华/商汤这类路径会逐条抓详情，可能产生远超 15 的
   请求；本次未改适配器（遵守任务），建议后续统一加 `QIUZHAO_*_REQUEST_BUDGET`。
2. **耗时仍不确定**：Moka 生产全量详情是最大变量；轮转 N=2 是保守默认，必要时调到 3。
3. **`test_codes_kind.py::test_migration_is_safe_when_both_services_start_together` 为既存
   flaky**：多进程 sqlite 迁移偶发 `database is locked`。已在 `feat/banks-batch1` 基线复现
   （隔离跑 5 次 2 过 3 败，本分支 5 次 1 过 4 败；全量套件两者都可能出现第 4 条失败）。
   确定性失败集合与基线一致，仍是 3 条：`test_core::test_role_cohort_and_campaign_title_bases`、
   `test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、
   `test_schema::test_enum_check_fails_when_data_drifts`。
4. **飞书配置 78 行 / 生效 72 家**：6 家与硬编码重叠（小鹏/蔚来/影石/莉莉丝/商汤等），
   `setdefault` 让硬编码专用适配器继续生效；若要把它们切到配置化，需另定口径。
5. **公司名以闲鱼表为准**：个别表名与站点标题差异较大（如 tkgroup 东江北森→东江控股、
   yasc→长飞先进半导体），已按"优先闲鱼表"处理；如总控认为应以站点为准，可在
   `company-name-cleanup.csv` 上标注后重跑 `--write`。

## G. 站长最终口径版（20260918h）

**结论先行**：按站长 2026-09-18 18:40 最终口径改完——`--platform-rotation` 默认 **1**
（不轮转，924 家每天全跑）、平台公司默认 **三 scope（含 social）**、`windows_collector.py`
p1 步改为 `--scope-timeout 600 --workers 8 --platform-workers 3 --max-run-seconds 18000`
（以 `20260918b/windows_collector.py` 为底只改这一行，同步段一字未动）、新增次日公平排序
（`data/p1-last-attempt.json` + `plan_chains()`）。离线单测**确定性失败 3 条，与基线同一集合**
（另 1 条既存 flaky `test_codes_kind` 时有时无；改动后两次全量分别为 4 failed/448 passed 与
3 failed/449 passed），零网络探针 `PROBE OK`。Mac 零网络桩实测
每单元子进程 ≈**162 MB**；8 路 ≈1.5 GB、12 路 ≈2.1 GB。部署件
`pipeline-watch/deploy-artifacts/20260918h/` 就绪，`shasum -c` 全 OK。
**未部署、未 SSH、未碰阿里云、未调飞书、未发外部请求、未 push、未合并。**

### G.1 改动清单

| 文件 | 改动 |
|---|---|
| `qiuzhao/collector/p1_pipeline.py` | `PLATFORM_ROTATION_DEFAULT` 2→1；`PLATFORM_DEFAULT_SCOPES` →`campus,intern,social`；`--workers` 上限 6→64；新增 `last_attempt_path/load_last_attempt/save_last_attempt/stale_key`；`plan_chains(..., last_attempt=)` 公平排序；`run_unit()` 记录真实尝试时间 |
| `deploy/windows_collector.py` | p1 步参数只改一行：`--workers 4`→`--workers 8` 并新增 `--platform-workers 3` |
| `tests/test_p1_scheduling.py` | 调整 3 条因默认值失效的断言；新增 6 条：三 scope、配置收窄、rotation 默认 1、公平排序×2、两天模拟、run 记录 last-attempt |
| `tests/test_collector_next_integration.py` | 默认全量 + `--platform-rotation 2` 仍子集；windows args 断言改 `8`/`3` |
| `pipeline-watch/collector-next2-probe.py` | 断言改为新口径 + 公平排序 |
| `pipeline-watch/rss-measure-20260918h.py` / `.out` | 零网络 RSS 实测（可复现） |

未改任何适配器、未改同步段（`lark_sync_daemon` / `base-sync` 原样）、未改
`QIUZHAO_PLATFORM_REQUEST_INTERVAL` 逻辑。

### G.2 调度口径（不轮转 + 三 scope）

- `--platform-rotation` 默认 **1**：`companies_for_day(DEFAULT_COMPANIES, 1)` 原样返回全部
  **924 家**；参数保留，`--platform-rotation 2` 实测仍选中 489 家（50 硬编码 + 24 每天跑 +
  415 平台）。显式 `--companies` 永远全跑，不受轮转影响。
- 平台公司（北森/Moka/飞书/Workday/SuccessFactors/银行）默认 `campus,intern,social`；某公司
  仍可在 `p1_platform_companies.json` 的对象里用 `"scopes":["campus","intern"]` 收窄
  （字符串或数组均可）。
- 同平台并发 `--platform-workers 3`、同平台单元启动间隔 `--platform-interval` ≥1s、
  `QIUZHAO_PLATFORM_REQUEST_INTERVAL` 注入逻辑均保持。

### G.3 公平性兜底（5 小时硬上限）

- `run_unit()` 每次**真实**执行（`collect_process` 跑过、非 resume/skip）后，把
  `company/scope → epoch` 写入 `data/p1-last-attempt.json`；跳过/复用的单元刻意不更新，
  以保证「被截断」与「已完成」可区分。
- `plan_chains()` 公司排序键 = `(demoted, never_attempted, failed, stale, position)`：
  1. 连续 3 天失败整链仍降到最后（`demoted=1`，语义不变）；
  2. **有任一 scope 从未尝试**的公司排最前（`stale=0`）——正是当天被 `--max-run-seconds`
     截断的单元；
  3. 其余先排重试队列里的失败单元（`failed=0`），再按最早尝试时间升序（越旧越先）。
- 单测：`test_plan_chains_leads_with_never_attempted_then_stalest`（小米未尝试→最前）、
  `test_plan_chains_prioritizes_failed_units_next_day`（失败单元压过更晚尝试的成功单元）、
  `test_two_day_simulation_attempts_every_unit_once`（Day1 只跑首家公司，Day2 未尝试的两家
  排最前，两天并集覆盖全部单元）、`test_run_records_last_attempts_and_promotes_missing_unit`
  （run 级端到端）。
- 结论：即便某天 5h 上限截断，被截断的单元次日必然排最前，**每家公司至少隔日更新**；
  失败单元次日优先重试。

### G.4 耗时估算（workers=8 / platform-workers=3 / 3 scope / 不轮转）

口径：按各分支收据实测请求数（北森 477 家 ≈9,500 请求/2 scope、Moka 301 ≈18,000、
飞书 72 ≈1,000+144 次浏览器启动）×1.5（campus/intern→三 scope）、每条请求有效 ~0.5s、
每次 headless 启动 ~4s。同平台 3 路、全局 8 路，三个平台并列时 3+3+3=9 被全局 8 截住。

| 平台 | 生效公司 | 请求/轮（3 scope） | 单通道耗时 | 3 路并发 |
|---|---|---|---|---|
| 北森 zhiye.com | 477 | ~14,250 | ~7,125s | ~40 min |
| Moka app.mokahr.com | 301 | ~27,000 | ~13,500s | ~75 min |
| 飞书 jobs.feishu.cn | 72 | ~1,500 + 216 浏览器 | ~1,614s | ~9 min |

平台小计 **~1–1.5h**（Moka 为长尾）；再叠加每天必跑的 74 家（硬编码 50 + 银行 5 + 阿里 6 +
腾讯音乐 1 + Workday 9 + SF 3，三 scope）**~0.5–1h**（workers 4→8 约减半）；
整轮估算 **~1.5–3h**。生产 Moka 全量详情（无预算上限）与 `publish()` 串行写 `jobs.json`
是最大不确定项，保守上界 **~3–4h < 18000s**。

**若实测超过 5 小时**：G.3 兜底生效——当天未尝试的单元在 `p1-last-attempt.json` 里没有记录，
次日 `plan_chains()` 把它们排最前，因此**每家至少隔日更新**，不会出现长期饿死。

**`--workers` 提到 12 时**：请求时间理论上再降约 1/3（受同平台 3 路限制，实际收益递减），
整轮约 1–2h；代价见 G.5，内存约 2.1 GB、CPU 峰值 ≤75% 逻辑占用，精灵（16 GB / 12C16T / 日常
可用 5.8 GB）扛得住。不建议再往 12 以上加，瓶颈会变成同平台限流与 WAF。

### G.5 内存实测（Mac，零网络桩，不写库）

方法：`pipeline-watch/rss-measure-20260918h.py` 在临时目录建零网络桩适配器，用真实
`p1_pipeline --adapter` 子进程路径起单元，`ps -o rss=` 采样；结果存
`pipeline-watch/rss-measure-20260918h.out`。

| 项 | 实测 |
|---|---|
| 单单元峰值 RSS | **162.4 MB** |
| 两并发单元峰值 | 162.4 / 162.7 MB |
| 仅解释器 + import p1_pipeline | 162.3 MB |
| 父编排进程峰值（450 单元 / workers=12） | 166.0 MB |

结论：每单元子进程 ≈**160–165 MB**，几乎全部是 Python 解释器 + requests/bs4/normalize 栈，
与适配器无关；父进程开销可忽略。

- **8 路**：8×162.5 + 0.17 ≈ **1.47 GB**；**12 路**：≈ **2.12 GB**。精灵可用 5.8 GB →
  8 路余 ~4.3 GB、12 路余 ~3.7 GB。
- headless 单元（阿里 6 + 飞书 72，受 `--platform-workers 3` 限制最多 3 个并发）另起
  Chromium 子进程，按每路 +0.3–0.6 GB 粗估；12 路 + 3 headless 仍 < 4 GB。
- **CPU**：12 个单线程单元铺在 12 核 / 16 线程上，瞬时峰值 ≤75% 逻辑占用；单元以网络 I/O
  为主，CPU 不是瓶颈。
- **带宽**：平台 ~4.3 万请求/轮，按平均响应 50 KB（列表页为主，详情页更小）估 ≈2.1 GB/轮，
  3h 内均 ~1.6 Mbps、并发峰值个位数 Mbps；真正的约束是同平台 ≥1s 启动间隔与上游 WAF，
  不是链路带宽。50 KB/请求为估算假设，非实测。

### G.6 验证

- **单测**：基线 `pytest tests/` = 442 passed / 55 skipped，确定性失败 3 条：
  `test_core::test_role_cohort_and_campaign_title_bases`、
  `test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、
  `test_schema::test_enum_check_fails_when_data_drifts`；另 1 条既存 flaky
  `test_codes_kind::test_migration_is_safe_when_both_services_start_together` 时有时无
  （基线那次记为第 4 条失败）。改动后同样是这 3 条确定性失败，两次全量为
  **4 failed / 448 passed** 与 **3 failed / 449 passed**（+6 为新增测试），无新增失败。
- **零网络探针**：`python pipeline-watch/collector-next2-probe.py` → `PROBE OK`。关键值：
  `default_total=924`、`duplicates=0`、平台公司 `['campus','intern','social']`、
  `rotation_default=1`、`default_select_full=true`、`rotation2_total=489`、
  `fairness_order=['小米','拼多多','大疆']`、`failed_order=['拼多多','大疆']`。
- **部署件**：`shasum -c SHA256SUMS.txt` 全部 `OK`，且
  `p1_pipeline.py`/`windows_collector.py` 与源码 sha256 逐一相等。

### G.7 部署差异（20260918h）

- 12 文件与 20260918g 同名同集：`p1_pipeline.py`（`c48dbf94…`，本次新版）与
  `windows_collector.py`（`9eaf97cc…`，本次新版）更新，其余 10 个哈希与 g 逐字节相同。
- **Playwright**：总控实测精灵 `%LOCALAPPDATA%\ms-playwright` 当前不存在，部署时先检测
  （`Test-Path "$env:LOCALAPPDATA\ms-playwright"`），缺失则由站长执行
  `C:\mcp-suite-collector\.venv\Scripts\python.exe -m playwright install chromium`。
- **计划任务参数无需改**：p1 全部参数在 `deploy/windows_collector.py` 内，覆盖后次日 06:10
  自然生效，不需重启。
- 叠加顺序：从精灵现役 `20260918` 一步覆盖（b–g 均未部署）；回滚见
  `20260918h/PROD-BACKUP-MANIFEST.txt`。

## F. 部署记录（20260918h 上线，已执行）

**结论**：20260918h 累积部署件已上线成功。12 个目标路径覆盖后 sha256 与
`20260918h/SHA256SUMS.txt` 逐字节一致；`py_compile` 48 个 `.py` 全部通过；
`import deploy.windows_collector, qiuzhao.collector.p1_pipeline as P, qiuzhao.collector.guopin`
输出 `IMPORT_OK 924 924`；Playwright Chromium 安装并最小启动验证通过。未重启服务、
未改计划任务、未手动补跑、未动 `run.py`/`data\`/`runs\`/阿里云/计划任务；`.venv` 只新增
Playwright 浏览器（装到 `%LOCALAPPDATA%\ms-playwright`，不在 `.venv` 内）。
批准：Max 2026-09-18 18:40（原话“现在可以上线”）。

- 部署分支：`feat/collector-next-2`，`git log -1 --format=%h` = **`bcdfd09`**
  （2026-09-18 19:12:46 +0800，含 20260918h 部署件）。
- 执行时间：2026-09-18 20:10–20:17（CST，精灵本地时间）。
- 空闲判定（步骤 1）：`runs\20260918\receipt.json` `completed_at=2026-09-18T20:03:53`、
  无 `windows_collector.py`/`p1_pipeline`/`lark_sync` 进程、`data\lark-sync\status.json`
  = `success`/`complete`。等待窗口 19:16→20:06（当日 06:10 那次运行 + 其后 business 同步
  于 20:03 收尾），未终止任何进程。
- 备份：`C:\mcp-suite-backup-20260918-2010\`（`deploy\`、`qiuzhao\` 两子树，
  `robocopy /E /R:2 /W:5`，退出码均 = 1，≤7 成功）。备份内 4 个现役文件哈希与前提一致。
- staging：`C:\mcp-suite-deploy-20260918h\`（12 文件逐字节校验一致；另留
  `playwright-install.log` 安装日志）。scp 不可用，用分片 base64（每片 1300B）追加写入。

### F.1 覆盖前后哈希（全 64 位）

| 目标路径（相对 `C:\mcp-suite-collector`） | 覆盖前 | 覆盖后（= 清单） |
|---|---|---|
| `deploy\windows_collector.py` | `14e17785ccff51f94aea519bee1637582d974c6d65540ee6f379954b08c90c4a` | `9eaf97cc5d4e968c062aaa65468ab34c584534a4ced5523d75c7c26229ec8312` |
| `qiuzhao\collector\guopin.py` | `22e5f6ad0b66487ba7f6ccaee041da67c668d7ed98aeaa10408d7dc95a0abf89` | `add0d50c715e06eb968bb7671bc2e9787e81d9ad39be008e66731337f16b6c03` |
| `qiuzhao\collector\p1_pipeline.py` | `dc046e32f37d7482ac56222898d122edb52d93d8b48fed4f3c5c2c67770fdb90` | `c48dbf94c13f03394897a767f2fb918d1afcd06658ae93d32975d42cf98310a9` |
| `qiuzhao\collector\p1_feishu_public.py` | `08dd30e87893fb26ac653fa203c816ada07a5e9bfe201280163ceaa7f39350c8`（原本已存在） | `e9855205ad1cc9494855d1357ab93c68f6e6ead646e7441bd6032c7311a8ca4f` |
| `qiuzhao\collector\p1_banks_01.py` | ABSENT | `25e2399812f64ee1762b7686849bf7241c8e1353d7203347562f9794223ffb19` |
| `qiuzhao\collector\alibaba_headless.py` | `7a7feacaaed4bb091ba7cb94d39ca48824f3d205a5e0963585dc816b8cdf0e7b`（原本已存在，见 F.4） | `dab17686cf251f220950b8c8e13984d39dcbb07b8a3eeeea84bdea3ca3be7db2` |
| `qiuzhao\collector\tencent_music.py` | ABSENT | `7d19cbc34b45dfc5e31c3d9b7ed41dd51c638c5adb6c62bf6e0330904f3d3787` |
| `qiuzhao\collector\p1_platform_beisen.py` | ABSENT | `3faeb5686aa7bf05a7b6754b35a607c50a9666e8247dd5b46d430307b9eb33a5` |
| `qiuzhao\collector\p1_platform_moka.py` | ABSENT | `569e0865d96ba7f91a4803330975ac76f9f35277b9f1bf312092c598c636a777` |
| `qiuzhao\collector\p1_platform_workday.py` | ABSENT | `d95e11b29f30368a1f4657d22fdb1c10d88495bd1ccac03f8a15c613caeb706b` |
| `qiuzhao\collector\p1_platform_successfactors.py` | ABSENT | `658c81c07bd4ebda62735662dfac54722dccc830517072e3a40d9329701f1216` |
| `qiuzhao\collector\p1_platform_companies.json` | ABSENT | `ee0f288cf6213da356f9f0dcaf03e54374472ab3519b2a1a4f91e8b9ee86349b` |

- `qiuzhao\collector\run.py` 未覆盖，覆盖后仍为 `5e94f91b770ef02bfad887e10bb6fab3405d8b184a81b98df9d14fe28c266b28`。
- 覆盖后 12 目标 `TARGET_ALL_MATCH=True`（目标 = staging = 清单）。

### F.2 py_compile 与 import（步骤 5）

- `py_count=48`（`deploy\` + `qiuzhao\` 下全部 `.py`，排除 `__pycache__`/`.venv`），
  `py_compile_batches_failed=0`（正式 venv，`-X utf8`）。
- `IMPORT_OK 924 924`，`import_exit=0`（cwd=`C:\mcp-suite-collector`）。

### F.3 Playwright Chromium（步骤 3）

- 安装前：`import playwright`/`from playwright.sync_api import sync_playwright` 均 OK，
  但 `%LOCALAPPDATA%\ms-playwright` **不存在**（默认 Chromium 启动失败）；系统 Chrome 存在
  （`C:\Program Files\Google\Chrome\Application\chrome.exe`）。
- 执行 `C:\mcp-suite-collector\.venv\Scripts\python.exe -m playwright install chromium`，退出 0，
  装到 `C:\Users\-LZH-\AppData\Local\ms-playwright`：`chromium-1187`、
  `chromium_headless_shell-1187`、`ffmpeg-1011`、`winldd-1007`（仅 chromium，无其他浏览器）。
- 最小启动验证（headless，不访问外网）：`chromium-launch-ok 140.0.7339.16`，`launch_exit=0`。
- 阿里系/飞书 headless 依赖就绪，首日不会因缺浏览器 blocked。

### F.4 与任务前提不一致处（已按“还原而非删除”处理）

- 任务/`PROD-BACKUP-MANIFEST.txt` 声明 9 个新增文件在精灵上应 ABSENT；实测
  `alibaba_headless.py`（7900 B，mtime `2026-09-13T15:08:36`）与
  `p1_feishu_public.py`（17074 B，mtime `2026-09-13T15:08:36`）**原本已存在**，同为
  2026-09-13 铺底内容（非本次部署产生）。二者均已进备份。
- 因此回滚口径修正为：3 个被覆盖的现役文件（`guopin.py`/`p1_pipeline.py`/
  `deploy\windows_collector.py`）+ 未动的 `run.py` 从备份拷回；`p1_feishu_public.py`、
  `alibaba_headless.py` 从备份**还原**（不删除）；其余 7 个新增文件删除。
- `windows_collector.py` 与 20260918 基线逐行 diff：仅第 162 行 p1 步参数一处变化
  （新增 `--scope-timeout 600 --workers 8 --platform-workers 3`，保留 `--max-run-seconds 18000`），
  同步段未变，与任务描述一致。

### F.5 回滚

- **未触发**（步骤 5 全部校验通过，无需回滚）。
- 若日后需回滚：`C:\mcp-suite-backup-20260918-2010\` 见 F.4 口径；回滚后校验 4 个现役文件
  哈希应回到 F.1“覆盖前”列的值。

### F.6 次日观察项（2026-09-19 06:10 首次实测，供总控核对）

- `runs\20260919\receipt.json`：`steps` 出现 `basic`/`p1` 的 0 或 2；`step_changes.p1`
  条数；p1 起止时间（不轮转、三 scope、8 路并发，预期 3–5 小时；若触顶 5 小时
  `--max-run-seconds 18000`，看 `status.pending` 与次日公平排序是否生效）。
- `runs\20260919\data\source_state.json`：`guopin.discovered`（预期约 14）、
  `fallback_used=false`。
- p1 status：平台公司尝试数（应为全部 874，或受 5 小时上限截断的数量）、各平台
  blocked 比例、银行/阿里/外企的 `coverage.status`。
- `data\p1-retry-queue.json` 是否生成；飞书同步 `changed` 量级（对比本次 9-18 的
  92722 → 修复后应显著下降）。
- 本次未手动补跑，首次实测即次日 06:10 计划任务。
