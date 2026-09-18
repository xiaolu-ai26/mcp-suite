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
