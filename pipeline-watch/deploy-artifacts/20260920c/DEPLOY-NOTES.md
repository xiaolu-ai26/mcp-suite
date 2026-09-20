# 20260920c 增量部署件(Moka 续采 + tupu360 分页修复/配置 + 分页谎报审计)

生成:2026-09-20,分支 `feat/collector-next-6`
(worktree `/Users/maxzhl/Projects/mcp-suite-merge6`;起点 `feat/collector-next-5` f32cc9b3 = 精灵现役 20260920a,
依次并入 `feat/platform-adapters` 95a88ad3、`feat/tupu360-fullsite` c0d552f2 的代码与配置,再做全适配器分页审计)。

状态:**未部署**。必须由站长明确说「上线」后才可覆盖精灵正式目录。

## 0. 这个包是什么

在**精灵现役 20260920a 之上**的**增量**包:13 个运行时文件,**全部是覆盖**,不新增、不删除任何文件。
`deploy\windows_collector.py`、`run.py`、`p1_platform_beisen.py`、`p1_platform_51job.py`、
`p1_platform_icims.py`、`p1_feishu_public.py`、`normalize.py`、`company_names.py`、
`company_aliases.json` 以及 k 的 7 个文件**本次一行未改**,不进包(见 `PROD-BACKUP-MANIFEST.txt` 的两段 VERIFY ONLY)。

## 1. 前提(精灵当前真实状态)

- 精灵现役 = **20260920a**(2026-09-20 01:32 上线;执行者 + 总控独立核验 18/18 逐字节一致、
  `IMPORT_OK 1069 1069`、`LOCK True`)。
- `PROD-BACKUP-MANIFEST.txt` 里的前提哈希 = 20260920a 清单(用
  `git show feat/collector-next-5:pipeline-watch/deploy-artifacts/20260920a/SHA256SUMS.txt`
  逐条核对,未照抄)。
- 唯一例外:`qiuzhao\collector\p1_netease_public.py` **从未进过任何部署件**,精灵上的实际哈希
  没有记录 → 必须先 `Get-FileHash` 记录真实值再覆盖(清单里有 CAVEAT)。

## 2. 文件清单(13 个运行时文件,全部覆盖)

| # | 文件 | 目标路径(精灵) | 动作 | 20260920c sha256(前 8 位) | 前提 sha256(前 8 位) |
|---|---|---|---|---|---|
| 1 | `p1_pipeline.py` | `qiuzhao\collector\` | 覆盖 | `2892beb8` | `093b237e` |
| 2 | `p1_platform_companies.json` | `qiuzhao\collector\` | 覆盖 | `d1f7a42b` | `cd4c403b` |
| 3 | `p1_platform_moka.py` | `qiuzhao\collector\` | 覆盖 | `5fd758ce` | `778a956d` |
| 4 | `p1_platform_successfactors.py` | `qiuzhao\collector\` | 覆盖 | `2f69a6e6` | `cdeaaa26` |
| 5 | `p1_platform_workday.py` | `qiuzhao\collector\` | 覆盖 | `0943caf8` | `b576b94c` |
| 6 | `p1_foreign_01.py` | `qiuzhao\collector\` | 覆盖 | `98b348af` | `29c62e62` |
| 7 | `p1_platform_eightfold.py` | `qiuzhao\collector\` | 覆盖 | `ca543048` | `10e87b96` |
| 8 | `p1_platform_phenom.py` | `qiuzhao\collector\` | 覆盖 | `533e721a` | `f40eb834` |
| 9 | `p1_platform_avature.py` | `qiuzhao\collector\` | 覆盖 | `f2ebdd6f` | `378e4f9f` |
| 10 | `p1_platform_orc.py` | `qiuzhao\collector\` | 覆盖 | `d15d3a8b` | `bd3528bc` |
| 11 | `p1_platform_tupu360.py` | `qiuzhao\collector\` | 覆盖 | `0130b3bb` | `51a10990` |
| 12 | `alibaba_headless.py` | `qiuzhao\collector\` | 覆盖 | `1b8eb2f7` | `dab17686` |
| 13 | `p1_netease_public.py` | `qiuzhao\collector\` | 覆盖 | `2e71ffd6` | 见 CAVEAT |

## 3. 内容摘要

- **默认公司集合保持 1069 家不变**(`REGISTRY == DEFAULT_COMPANIES`,重名 0,模块 21 个)。
  tupu360 段从 14 行扩到 **68 行**(60 家 careersite 真实岗位租户 + 8 行原文调查记录),
  **全部 `enabled:false`** —— 平台 robots.txt 是 `User-agent: * / Disallow: /`,是否启用等站长决定。
  因此 tupu360 在 REGISTRY 里仍然是 **0 家**,每日链完全不受影响。
- **Moka 详情缓存复用 + 多轮有界续采**(95a88ad3):`_cached_detail()` 复用上一轮已落盘的
  `detail-<id>.json` 且**不花预算**,共享详情缓存命中时**退还**预算 → 「预算 = 真实网络请求数」,
  重复的有界轮次是续采而不是重花;生产默认仍无上限(`DEFAULT_REQUEST_BUDGET = None`)。
- **tupu360 分页硬截断修复**(c0d552f2):`PAGE_CAP = 120` 只作安全阀,翻页目标改为站点自报
  页数(`共N页` / `ceil(共N个职位 / page size)`);真触顶时记 `page_cap_hit` 且**不置**
  `pagination_exhausted`。原缺陷把 40 页上限当目标,把康龙化成社招的 828 条截成 600。
- **分页谎报审计修复**(本分支,6 处真缺陷 + 5 处同类边界):
  `p1_platform_successfactors.py`(unify 回退继承 classic 的已翻完证明)、
  `p1_platform_avature.py`(空页/重复页直接当翻完,legend 仍报 36 条)、
  `p1_netease_public.py`(缺 total 字段被当成 0 个在招并丢掉已读行)、
  `alibaba_headless.py`(缺 totalCount 被当成目标 0,第一页就断)、
  `workday/orc/phenom/eightfold/p1_foreign_01`(站点自报 total=0 且有行时被当末尾)、
  `p1_pipeline.py`(`validate_result` 新增闸门:记了 `page_cap_hit` 的结果永不能通过 complete 校验)。
  完整审计表见 `pipeline-watch/RECEIPT-collector-next-6.md`。
- **没有任何采集行为的扩大**:审计修复只让「截断/异常」不再被报成「已翻完」,不会新增或减少
  已确认的岗位;受影响的 scope 会从 `complete` 降为 `partial`(数据仍按 partial-keep 保留)。

## 4. 部署后验证(与以往一致)

1. 暂存区 `Get-FileHash -Algorithm SHA256` 对 `SHA256SUMS.txt` 13/13 一致。
2. `py_compile` 13 个文件 exit 0;`IMPORT_OK 1069 1069`;`LOCK True`(p1_pipeline 的
   `_publish_thread_lock` 必须在位,本包 `p1_pipeline.py` = 20260920a 版 + 审计闸门)。
3. 覆盖后逐文件哈希 13/13 与清单一致。
4. 零网络探针:`python pipeline-watch\collector-next6-probe.py` → `PROBE OK`。
5. `deploy\windows_collector.py` 未改:p1 步仍是 `--scope-timeout 600 --workers 8
   --platform-workers 3 --max-run-seconds 18000`、末尾仍是 `lark_sync_daemon`。
6. 次日 06:10 观察:tupu360 仍为 0 家、p1 起止时间、`receipt.json` 的 steps。

## 5. 回滚

从 `C:\mcp-suite-backup-<YYYYMMDD-HHmm>\` 还原 13 个文件(全部是还原,没有新增文件要删)。
还原后确认 `p1_pipeline.py` = `093b237e…`(20260919k/20260920a 的 Windows 发布锁必须活过回滚)。
