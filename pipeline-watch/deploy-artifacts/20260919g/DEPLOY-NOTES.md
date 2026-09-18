# 20260919g 累积部署件(叠加在 20260918k 之上;不部署,等站长说"上线")

分支 `feat/collector-next-4`(起点 `feat/collector-next-3` = 20260918k),26 个运行时文件 +
`SHA256SUMS.txt` + `PROD-BACKUP-MANIFEST.txt` + 本说明。**不含测试与夹具**。

## 1. 相对 20260918k 的增量

| 类别 | 文件 | 目标路径(精灵) |
|---|---|---|
| **覆盖(9)** | `p1_pipeline.py`、`p1_platform_companies.json`、`p1_feishu_public.py`、`p1_platform_beisen.py`、`p1_platform_moka.py`、`p1_platform_successfactors.py`、`p1_platform_workday.py`、`p1_foreign_01.py`、`p1_platform_51job.py` | `qiuzhao\collector\*` |
| **新增(6)** | `p1_platform_eightfold.py`、`p1_platform_phenom.py`、`p1_platform_avature.py`、`p1_platform_icims.py`、`p1_platform_orc.py`、`p1_platform_tupu360.py` | `qiuzhao\collector\*` |
| **新增(2)** | `company_names.py` → `qiuzhao\company_names.py`;`company_aliases.json` → `qiuzhao\data\company_aliases.json` | 公司名规范化依赖 |
| **覆盖(1,不在 k 清单)** | `normalize.py` → `qiuzhao\normalize.py`(normalize 阶段接入公司名三层规范化) | 见 §5 CAVEAT |
| **无需覆盖(8,与 k 逐字节一致)** | `windows_collector.py`(**与 k 逐字节一致**,sha256 `9eaf97cc…`)、`guopin.py`、`alibaba_headless.py`、`p1_banks_01.py`、`tencent_music.py`、`bytedance.py`、`p1_bytedance_public.py`、`p1_midea_public.py` | 随包只为自洽校验,内容与 k/现役完全相同 |

`deploy\windows_collector.py` 本次**未改一行**(p1 步参数仍是 `--scope-timeout 600 --workers 8
--platform-workers 3 --max-run-seconds 18000`、末尾仍是 `lark_sync_daemon`),与 20260918k 的
`9eaf97cc5d4e968c062aaa65468ab34c584534a4ced5523d75c7c26229ec8312` 逐字节一致。

## 2. 内容摘要

- **默认公司集合 948 → 1056**,`REGISTRY == DEFAULT_COMPANIES`,`duplicates 0`。
- 新增外企平台适配器 6 个:Eightfold(5 家)、Phenom(8 家)、Avature(4 家)、ORC(9 家)、
  iCIMS(**0 家**,robots 闸门)、tupu360(**0 家**,全段留档)。全部进 `PLATFORM_MODULES` 与
  `PLATFORM_HOST_GROUPS`(`eightfold` / `phenom` / `avature` / `icims` / `oraclecloud` /
  `tupu360.com`),受 `--platform-workers 3` 与同平台启动间隔 ≥1s 约束,默认三 scope。
- 外企发现两条线写入配置:`moka +13`、`dayee +4`、`job51 +8`、`beisen +1`、`workday +56`、
  `successfactors +1`(净增 82 个公司名,其中 4 个与批 A/B 同名去重)。
- **同名冲突处置**:惠普/应用材料 → Eightfold,Eightfold 实测 16/131 条 vs workday 1/3 条;
  飞利浦 → Phenom(159 vs workday 8);三行 workday 留档 `enabled:false`。强生继续走既有
  workday 租户 `jj/wd5/JJ`(tupu360 全段留档)。毕马威第二个 moka 租户 `kpmg/74356` 留档,
  显式锁定现役 `kpmg/76195`。三行都在配置里保留租户 id 与切换说明。
- **tupu360 全段 14 行 `enabled:false`**:平台 robots.txt 是全站 `Disallow: /`,6 家实测可读的
  careersite 租户(IQVIA 艾昆纬/礼来/舍弗勒/宝马/茵梦达 + 强生)一并留档,等站长拍板。
  **强生的工作日 workday 行是下一轮要核对的重点:本轮没有对 workday 租户做新的实测,若首日
  `强生/campus+intern+social` 三 scope 全是 0 条,说明它是"猜测租户",需要在收据/待办里升级。**
- **iCIMS 段保持 0 家**:适配器带 robots 闸门(命中 `Disallow: /` 只发 1 个 robots 请求就返回
  `blocked`),首日不会因为该段产生任何采集请求。
- **`enabled:false` 契约**:12 个配置驱动适配器(beisen/moka/feishu/workday/successfactors/
  dayee/51job/eightfold/phenom/avature/icims/orc/tupu360)统一在加载时跳过留档行 —— 留档行
  不进 `REGISTRY`、不进默认集合、不采集;对没有 `enabled:false` 的既有行完全惰性。

## 3. Playwright / Chromium 依赖

| 适配器 | 主路径 | 是否需要浏览器 |
|---|---|---|
| Eightfold | 普通 `requests` 打页面自身的 `/api/pcsx/search` + `position_details` | **否**(Playwright 仅在 401/403/429 时兜底,实测 39/39 次走直连) |
| Phenom | 普通 `requests` 打 `/widgets` 的 `refineSearch` / `jobDetail` | **否**(同上) |
| Avature / ORC / iCIMS / tupu360 | 纯 HTTP | 否 |
| 大易 / 51job / 字节 / 美的 / 北森 / Moka / Workday / SF / 银行 / 腾讯音乐 | 纯 HTTP | 否 |
| 阿里系(`alibaba_headless.py`)、飞书(`p1_feishu_public.py`) | headless | **是**(沿用现役依赖) |

精灵 `%LOCALAPPDATA%\ms-playwright\chromium-1187` 在 20260918k 部署时已实测在位
(`LAUNCH_OK`,140.0.7339.16),本次**不需要重装**;Eightfold/Phenom 即使 Playwright 不可用,
只要上游不返回 401/403/429 也能正常采集。若首日这两段出现 `blocked` 且 `mode=headless`,
按"浏览器缺失"排查;若 `mode=direct` 仍失败,按上游改版/WAF 排查。

## 4. 部署步骤(沿用 `TASK-collector-next-3-deploy.md` 流程,文件清单按 g 更新)

1. **等空闲**:`runs\<今天>\receipt.json` 有 `completed_at`;无 `windows_collector.py` /
   `p1_pipeline` / `lark_sync` 的 python 进程;`data\lark-sync\status.json` 不是 `running`。
   正在跑就每 5 分钟看一次,最多等 3 小时;超时不部署。
2. **前置哈希核对**:按 `PROD-BACKUP-MANIFEST.txt` 的**唯一前提**(精灵现役 = 20260918k)逐文件
   核对 26 个目标路径的部署前 sha256;9 个覆盖文件必须等于 k 值、8 个新增文件必须 ABSENT、
   `qiuzhao\normalize.py` 按 CAVEAT 先记录真实哈希。任何不一致就停(drift)。
3. **备份**:`robocopy C:\mcp-suite-collector\deploy C:\mcp-suite-backup-<YYYYMMDD-HHmm>\deploy /E /R:2 /W:5`
   与 `...\qiuzhao ...\qiuzhao /E /R:2 /W:5`(退出码 ≤7 成功;**不要**全目录 robocopy)。
4. **Playwright**:按 §3,先 `Test-Path` 确认 `chromium-1187` 在位,缺才
   `python -m playwright install chromium`;失败不阻塞部署,但要标注"阿里系/飞书首日 blocked"。
5. **传输并校验**:26 个文件传到 `C:\mcp-suite-deploy-20260919g\`,逐字节与 `SHA256SUMS.txt`
   一致后才允许下一步。
6. **覆盖 18 个目标路径**(10 覆盖 = 9 个 k 文件 + `qiuzhao\normalize.py`;8 新增 = 6 个新适配器 + `company_names.py` + `company_aliases.json`),`windows_collector.py` 等 8 个无需覆盖的
   文件可比对哈希后跳过。覆盖后再各算一次 sha256;`py_compile` 全部 `.py`;用正式 venv
   (cwd=`C:\mcp-suite-collector`)跑
   `python -c "import deploy.windows_collector, qiuzhao.collector.p1_pipeline as P; print(len(P.DEFAULT_COMPANIES), len(P.REGISTRY))"`
   → 预期 **`1056 1056`**;再抽查 REGISTRY:
   `惠普/应用材料 → p1_platform_eightfold`、`飞利浦 → p1_platform_phenom`、
   `强生 → p1_platform_workday`、`毕马威 → p1_platform_moka`、`微软 → p1_platform_eightfold`。
   不重启任何服务、不改计划任务。
7. **import 闭包校验**(`py_compile` 覆盖不到):逐个 import
   `qiuzhao.company_names`、`qiuzhao.normalize`、6 个新适配器、
   `qiuzhao.collector.{p1_platform_beisen,p1_platform_moka,p1_platform_workday,p1_platform_successfactors,p1_feishu_public,p1_foreign_01,p1_platform_51job}`,
   并断言 `qiuzhao.company_names.canonical_of('腾讯')==('腾讯','brand')`、tupu360/iCIMS 注册 0 家。
8. **不手动补跑**:以次日 06:10 的正常运行为首次实测。
9. **收尾**:把部署记录(时间、备份路径、覆盖前后哈希、import 输出、Playwright 结果)追加到
   `pipeline-watch/RECEIPT-collector-next-4.md` 的部署记录节;在 worktree 分支上 commit,不 push。
10. **回滚**:按 `PROD-BACKUP-MANIFEST.txt` 恢复 10 个覆盖文件(9 个 k 文件 + `normalize.py`),删除 8 个新增
    文件,回滚后逐字节校验 = 前提值并写明触发原因。

## 5. 已知注意事项

- `qiuzhao\normalize.py` 不在 20260918k 清单里(见 manifest 的 CAVEAT),部署前必须记录真实哈希;
  它读 `qiuzhao\normalize_tables.json`(未改、已在精灵)与 `qiuzhao\data\company_aliases.json`(本包新增)。
- `qiuzhao\data\` 目录若不存在需先建(本包只带 `company_aliases.json` 一个文件)。
- 服务器侧(`/opt/mcp-suite/`)不改也能返回规范名:`v4_fields` 的 `canonical_company or …` 已能取到;
  若要同步 `qiuzhao/company_names.py` 与别名表,须站长单独确认。
- 本包不含 `run.py`(未改)与任何测试/夹具。
