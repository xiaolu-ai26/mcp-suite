# 20260920a 唯一部署件(g + h + i + P0 热修;取代 20260919g/h/i)

生成:2026-09-20,分支 `feat/collector-next-5`
(worktree `/Users/maxzhl/Projects/mcp-suite-next5`;起点 `feat/collector-next-4` 82af4f72,
依次并入 `feat/multi-entrance` b6a81d83、`feat/normalize-adjust` 579c222d、`fix/p1-winlock` a2fb3bf4)。

状态:**未部署**。必须由站长明确说"上线"后才可覆盖精灵正式目录;建议先核对 9-20 06:10 首轮实测
(20260919k 热修后的第一次真实运行)。

## 0. 这个包是什么

**本包取代 `20260919g`、`20260919h`、`20260919i` 三个包,那三个包作废,不要再单独部署。**
原因:三个包各自从 `feat/collector-next-4` 分叉、各自带一份 `p1_pipeline.py`,而且都**不含**
20260919k 的 Windows 发布锁热修;直接按原顺序叠放会把热修覆盖掉,9-21 早上 p1 会再次整段回滚。
本包把三条线合成一棵树,并且 `p1_pipeline.py` = `feat/collector-next-4` 的版本 + **逐字节相同**的热修补丁。

## 1. 前提(精灵当前真实状态)

- 精灵现役 = **20260918k**(2026-09-18 20:27:41 上线,17 个文件已核)+ **20260919k P0 热修**
  (2026-09-20 00:40 上线,只覆盖 `qiuzhao\collector\p1_pipeline.py`:`ff96be4d…` → `13a5ec53…`)。
- `20260919g/h/i` **都没有部署过**,它们的新增文件在精灵上**不存在**(ABSENT)。
- 逐文件部署前哈希与 drift 处理见 `PROD-BACKUP-MANIFEST.txt`;任何不一致就停。

## 2. 文件清单(18 个运行时文件 = 10 覆盖 + 8 新增)

| # | 文件 | 目标路径(精灵) | 动作 | 20260920a sha256(前 8 位) |
|---|---|---|---|---|
| 1 | `p1_pipeline.py` | `qiuzhao\collector\` | 覆盖 | `093b237e` |
| 2 | `p1_platform_companies.json` | `qiuzhao\collector\` | 覆盖 | `cd4c403b` |
| 3 | `p1_feishu_public.py` | `qiuzhao\collector\` | 覆盖 | `03f732d8` |
| 4 | `p1_platform_beisen.py` | `qiuzhao\collector\` | 覆盖 | `6885efb1` |
| 5 | `p1_platform_moka.py` | `qiuzhao\collector\` | 覆盖 | `778a956d` |
| 6 | `p1_platform_successfactors.py` | `qiuzhao\collector\` | 覆盖 | `cdeaaa26` |
| 7 | `p1_platform_workday.py` | `qiuzhao\collector\` | 覆盖 | `b576b94c` |
| 8 | `p1_foreign_01.py` | `qiuzhao\collector\` | 覆盖 | `29c62e62` |
| 9 | `p1_platform_51job.py` | `qiuzhao\collector\` | 覆盖 | `968193b3` |
| 10 | `normalize.py` | `qiuzhao\` | 覆盖(不在 k 清单,先 VERIFY) | `52fb48f7` |
| 11 | `p1_platform_eightfold.py` | `qiuzhao\collector\` | 新增 | `10e87b96` |
| 12 | `p1_platform_phenom.py` | `qiuzhao\collector\` | 新增 | `f40eb834` |
| 13 | `p1_platform_avature.py` | `qiuzhao\collector\` | 新增 | `378e4f9f` |
| 14 | `p1_platform_icims.py` | `qiuzhao\collector\` | 新增 | `132d6a04` |
| 15 | `p1_platform_orc.py` | `qiuzhao\collector\` | 新增 | `bd3528bc` |
| 16 | `p1_platform_tupu360.py` | `qiuzhao\collector\` | 新增 | `51a10990` |
| 17 | `company_names.py` | `qiuzhao\` | 新增 | `ee094356` |
| 18 | `company_aliases.json` | `qiuzhao\data\` | 新增(目录不存在先建) | `ae311e93` |

另有 **8 个 k 文件必须保持不变、不进本包**(SHA256SUMS 里没有,`PROD-BACKUP-MANIFEST.txt`
的 VERIFY ONLY 段列了期望哈希):`guopin.py`、`alibaba_headless.py`、`p1_banks_01.py`、
`tencent_music.py`、`bytedance.py`、`p1_bytedance_public.py`、`p1_midea_public.py`、
`deploy\windows_collector.py`。**`deploy\windows_collector.py` 本次一行未改**(p1 步仍是
`--scope-timeout 600 --workers 8 --platform-workers 3 --max-run-seconds 18000`、末尾仍是
`lark_sync_daemon`),`run.py` 也不在包里。

## 3. 内容摘要

- **默认公司集合 948 → 1069**(g 的 1056 + h 的 13),`REGISTRY == DEFAULT_COMPANIES`、
  重名 0、模块 21 个。模块分布:北森 481 / Moka 333 / 飞书 72 / Workday 69 / 大易 11 /
  51job 9 / ORC 9 / Phenom 8 / SF 7 / Eightfold 5 / Avature 4 / tupu360 0 / iCIMS 0 +
  大厂 sources 47 / 阿里 6 / 银行 5 / 腾讯音乐 1 / 字节 1 / 美的 1。
- **P0 热修保留(本包最重要的点)**:`p1_pipeline.py` 含模块级 `_publish_thread_lock`
  (文件锁保留、`finally` 显式 `LOCK_UN`),`run_unit()` 把单个 `publish()` 异常收敛为
  该单元失败(`publish_error`、`published=False`、进 retry-queue),不再冒泡终止整段。
  证据:合并后的 `p1_pipeline.py` 与 `fix/p1-winlock` 的同一文件**逐字节一致**,
  且 `git diff 82af4f72 HEAD -- p1_pipeline.py` 与 `git diff 82af4f72 fix/p1-winlock -- p1_pipeline.py`
  完全相同(即"collector-next-4 的文件 + 热修补丁",没有别的改动)。`fix/p1-winlock` 的
  6 条锁相关单测在本包全过。
- **h 的多入口合并行保住**:`moka["nestlezgc/91899"]` 雀巢 3 租户(91899/91898/124026)、
  `moka["ey/166374"]` 安永 2 租户(166374/102474);另新增 Moka 博西家电/北京环球度假区/
  昂际航电、北森 上汽大众/光束汽车、Workday 杜邦/友邦/丹纳赫/通用磨坊、SF 阿克苏诺贝尔/
  汇丰/阿迪达斯,共 13 家。
- **公司名规范化以 i 的收窄版为准**:只补空,不做品牌并入/集团合并;`company_names.py` 与
  `company_aliases.json` 与 `20260919i` 逐字节一致。已实测:网易互娱、网易互联网、
  中国移动通信、中国联合网络通信、中国邮政都**保持原名**(`keep`/`brand`),
  同一实体归一保留(如 `腾讯科技（深圳）有限公司` → `腾讯`),1019 条配置公司名 0 条会被改名。
- 同名冲突处置沿用 g:惠普/应用材料 → Eightfold,飞利浦 → Phenom,强生 → Workday
  (`jj/wd5/JJ`,h 已实测非空 campus 1/intern 10/social 195),毕马威 → 现役 Moka `kpmg/76195`。
- tupu360 全段 14 行仍 `enabled:false`(robots 全站 Disallow),iCIMS 段 0 家,两段首日
  都不产生采集请求。
- **单测**:`pytest tests/` = **3 failed / 656 passed / 55 skipped**,失败清单与
  `feat/collector-next-4` 基线(3 failed / 640 passed / 55 skipped)**逐条相同、未新增**;
  零网络探针 `pipeline-watch/collector-next5-probe.py` = PROBE OK。

## 4. Playwright / Chromium

Eightfold / Phenom 主路径是纯 `requests`(Playwright 只在 401/403/429 时兜底),Avature /
ORC / iCIMS / tupu360 纯 HTTP,都**不需要**新装浏览器;阿里系与飞书沿用现役
`%LOCALAPPDATA%\ms-playwright\chromium-1187`(20260918k 部署时已实测在位)。
本次不需要重装;若这两段首日 `blocked` 且 `mode=headless`,再按"浏览器缺失"排查。

## 5. 部署步骤(沿用 `TASK-collector-next-4-deploy.md` 流程,文件清单按本包)

1. **等空闲**:当天 `runs\<日期>\receipt.json` 有 `completed_at`;无 `windows_collector.py` /
   `p1_pipeline` / `lark_sync` 的 python 进程;`data\lark-sync\status.json` 不是 `running`。
   正在跑就每 5 分钟看一次,最多等 4 小时;超时不部署。
2. **前置哈希核对**:按 `PROD-BACKUP-MANIFEST.txt` 的**唯一前提**(20260918k + 20260919k 热修)
   逐文件核对 18 个目标路径的部署前 sha256:10 个覆盖文件必须等于表内值(注意
   `p1_pipeline.py` 前提是 **`13a5ec53…`**,不是 k 的 `ff96be4d…`),8 个新增文件必须 ABSENT,
   `qiuzhao\normalize.py` 先记录真实哈希(VERIFY)。任何不一致就停(drift)。
   顺手核 VERIFY ONLY 的 8 个文件仍等于 k 值。
3. **备份**:`robocopy C:\mcp-suite-collector\deploy C:\mcp-suite-backup-<YYYYMMDD-HHmm>\deploy /E /R:2 /W:5`
   与 `...\qiuzhao ...\qiuzhao /E /R:2 /W:5`(退出码 ≤7 成功;**不要**全目录 robocopy);
   核对备份里 `p1_pipeline.py` = `13a5ec53…`。
4. **Playwright**:按 §4,先 `Test-Path` 确认 `chromium-1187` 在位,缺才
   `python -m playwright install chromium`。
5. **传输并校验**:18 个文件传到 `C:\mcp-suite-deploy-20260920a\`,逐字节与 `SHA256SUMS.txt`
   一致(18/18 OK)后才允许下一步。scp 不可用,用分片 base64(每片 ≤1300 字符)并逐字节校验。
6. **覆盖 18 个目标路径**;覆盖后各再算一次 sha256 复核。然后正式 venv
   (`.venv\Scripts\python.exe`,cwd=`C:\mcp-suite-collector`)跑 `py_compile` 全部 `.py`,
   再跑 import 闭包:
   `python -c "import deploy.windows_collector, qiuzhao.collector.guopin, qiuzhao.normalize; from qiuzhao.collector import p1_pipeline as P; print('IMPORT_OK', len(P.DEFAULT_COMPANIES), len(P.REGISTRY))"`
   → 预期 **`IMPORT_OK 1069 1069`**;并断言 `THREAD_LOCK_PRESENT`(`'_publish_thread_lock' in
   open(r'qiuzhao\collector\p1_pipeline.py',encoding='utf-8').read()` → True)、
   `qiuzhao.company_names.canonical_of('网易互娱')==('网易互娱','keep')`、
   `canonical_of('腾讯科技（深圳）有限公司')==('腾讯','alias')`、tupu360/iCIMS 注册 0 家。
   逐个 import 6 个新适配器,确认无悬空 import。不重启服务、不改计划任务。
7. **不手动补跑**;次日 06:10 首次实测。
8. **收尾**:部署记录追加到 `pipeline-watch/RECEIPT-collector-next-5.md`,在本分支 commit(不 push、不合并);

## 6. 回滚

按 `PROD-BACKUP-MANIFEST.txt`:从第 3 步备份恢复 10 个覆盖文件,删除 8 个新增文件
(`company_names.py`、`company_aliases.json`、6 个新适配器),`normalize.py` 是恢复不是删除。
回滚后逐字节校验:`p1_pipeline.py` 必须回到 **`13a5ec53…`**(热修不能丢,否则 9-21 早上
p1 会再次整段回滚),其余回到 k 值;写明触发原因。

## 7. 次日观察项

`runs\<日期>\receipt.json` 的 `steps`/`step_changes`(p1 应为 exit 2 或 0,**不再是
`rolled_back`**)与 p1 起止时间(估 2–3.5h,上界 4.5h);`p1.log` 0 次 `Errno 36` /
`Resource deadlock`;`data\p1-retry-queue.json` 与 `p1-last-attempt.json` 应生成;
新平台各家 `coverage.status`(惠普/微软/高通/宝洁/玛氏/罗氏/ABB/西门子/霍尼韦尔/摩根大通、
以及 h 新接的雀巢/汇丰/阿迪达斯/安永等);**强生三 scope 若全 0 要升级**;normalize 后
三个公司名字段空值应为 0、记录数与 id 集合不变;库总量;飞书同步耗时。

## 8. 硬约束(部署时)

只覆盖清单内路径;不碰 `.venv`、`data\`、`runs\`;不碰阿里云;不改计划任务;不手动跑飞书同步;
不读取/打印任何令牌;不删除精灵上任何目录;不 push、不合并 main;不终止任何进程。
