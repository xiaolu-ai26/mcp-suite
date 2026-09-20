# 20260920d 增量部署件(tupu360 60 家启用 + 美团少采修复 + 每日采集缺口报告)

生成:2026-09-20,分支 `feat/gap-report`
(worktree `/Users/maxzhl/Projects/mcp-suite-gap`;起点 `feat/collector-next-6` f0694da7
= `feat/collector-next-5` f32cc9b3(精灵现役 20260920a)+ Moka 续采 + tupu360 分页修复 +
全适配器分页审计)。

状态:**未部署**。必须由站长明确说「上线」后才可覆盖精灵正式目录。

## 0. 这个包是什么,以及它和 20260920c 的关系

**20260920d 取代 20260920c,不要两个一起部署。** 20260920c 从未部署;d = c 的全部 13 个文件
+ 本分支新增/修改的 3 个文件,合计 **16 个运行时文件 = 15 个覆盖 + 1 个新增**。

| 来源 | 文件数 | 说明 |
|---|---|---|
| `feat/collector-next-6`(20260920c 的内容) | 13 | Moka 详情缓存续采、tupu360 分页硬截断修复、6 处「分页谎报」缺陷修复。其中 `p1_pipeline.py` 与 `p1_platform_companies.json` 在 d 里是**再改过的版本** |
| `feat/gap-report`(本分支) | 3 | 新增 `collection_gap.py`;修改 `p1_meituan_public.py`、`deploy/windows_collector.py` |

叠加顺序:**`20260920a`(精灵现役)→ `20260920d`**。`20260919g/h/i` 与 `20260920c` 均已作废。

## 1. 这个包改了什么(三件事)

### 1.1 tupu360:站长 2026-09-20 决定启用 60 家

- 站长原话:**「接回来的60家都开」**。tupu360(图谱天下)的 `robots.txt` 是**平台级**
  `User-agent: * / Disallow: /` —— 站长已知情并决定采集,该决定已逐行写进配置的
  `enabled_reason` 字段,并在 tupu360 段 `_README` 里留痕。
- `p1_platform_companies.json` 的 tupu360 段 68 行:**60 家 careersite 租户 `enabled:true`**,
  **8 家保持 `enabled:false`** 并写明原因 ——
  7 家微信专属(wxtemp)租户(`nestle`/`taitaile`/`autoliv`/`louisvuitton`/`jntl`/`google`/
  `boschhuayu-steering`,匿名侧只答扫码页或「该网站已停用」)+ `johnsonelectric`
  (careersite 租户在所有公开渠道均 0 个职位)。这 8 家启用只会产生必然为空的单元。
- **公司总数:1069 → 1124(+55)**。60 家里有 5 家的注册槽已被更早的适配器占用
  (`setdefault` 不顶替):ABB→Phenom、康明斯→ORC、强生→Workday、斯堪尼亚→Moka、
  药明康德→`p1_sources_41_50`;其余 55 家是净增。
- **容量提醒(重要)**:2026-09-20 早上那次 p1 从 06:41 跑到 11:43,撞上了
  `--max-run-seconds 18000` 的上限(958/约 3300 个单元完成,`run_finished=false`)。
  tupu360 再增加 180 个单元(60 家 × 3 scope,适配器按各租户 channel 采)会进一步加剧。
  **建议站长在部署本包后评估 `--max-run-seconds` 与 `--platform-rotation`**;
  否则 tupu360 的单元可能连续多日排不进当日窗口(会体现在缺口报告的「无 expected_total」
  或单元总数下降上)。

### 1.2 美团少采:根因不是分页上限,是瞬时 SSL 断连打断了整个 scope

- **根因(用 2026-09-20 真实 coverage 实证,不是读代码猜)**:`p1_meituan_public.py` 的
  `_post_json` 对**任何**传输异常直接抛错,翻页循环 `except` 后**整体退出** ——
  social 停在第 16 页、intern 第 7 页、campus 第 2 页,`errors` 里是
  `Network failure: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] ...>`。
  `pagination_exhausted=false` 是**诚实的**(确实没翻完)。页间 `sleep(0.08)` 也远低于本项目的
  1 秒礼貌下限。**不存在页数上限,也没有 `pagination_exhausted` 谎报。**
- **修法**(`p1_meituan_public.py`):
  1. 瞬时传输错误(URLError/SSLError/连接重置/截断 JSON)**重试 4 次、指数退避 1/2/4/8 秒**;
     4xx(除 408/429)是真实应答,**不重试**。重试次数记入 `coverage.retries`。
  2. 页间间隔 **≥1 秒**(`REQUEST_INTERVAL_FLOOR`),`QIUZHAO_PLATFORM_REQUEST_INTERVAL`
     只能调慢不能调快。
  3. `pageSize` 20 → **100**(2026-09-20 实测服务端尊重该值:social 从 126 页降到 26 页,
     请求数减少 4/5)。
  4. **诚实性加固**:站点自报 `totalPage` 小于自报 `totalCount` 时,继续翻页补齐(有界
     `PAGE_OVERRUN_LIMIT=20`,并把 `pages_beyond_reported_total` 留成证据);空页提前出现且
     未采齐时记 `list exhausted ...` 错误并保持 `partial`。
- **修复前后(2026-09-20 真实只读验证,不 `--apply`、不写库、间隔 ≥1s)**:

  | scope | 修复前(今早线上) | 修复后(本包实测) | 站点自报 | 结果 |
  |---|---|---|---|---|
  | social | 320 | **2502** | 2502 | `complete=true`,26 页,51.4s,0 重试 |
  | intern | 140 | **401** | 401 | `complete=true`,5 页,7.6s,0 重试 |
  | campus | 40 | **188** | 189 | `partial`(服务端**自身**返回重复 `jobUnionId`,唯一 188 < 189) |
  | 合计 | 500 | **3091** | 3092 | 缺口 2588 → **1** |

  campus 的 1 条缺口是站点侧重复行,不是漏采;错误里如实记
  `duplicate source_record_id=... at page=2`,**没有伪装成 complete**。

### 1.3 每日「采集缺口报告」(本任务核心)

- 新增 `qiuzhao/collector/collection_gap.py`;`p1_pipeline.run()` 结束前调用它,
  产出 `runs\<日期>\collection-gap.json` 与 `collection-gap.md`。
- `deploy\windows_collector.py` 把摘要写进 `receipt.json` 的**新字段 `collection_gap`**
  (总缺口 `total_gap`、声称完整却少采的单元数 `units_complete_but_short`、
  `top3_companies`、`units_without_expected_total` 等)。报告缺失或损坏**不会**影响整轮退出码。
- **兜底(针对 2026-09-20 真实故障)**:那天 p1 撞上 `--max-run-seconds 18000`,被本链的
  18100 秒 step 超时杀掉,**没走到写报告那一步**。所以 `deploy\windows_collector.py` 在
  `runs\<日期>\collection-gap.json` 不存在时,会从最新的
  `runs\<日期>\data\p1-runs\*\status.json` **现场重建**报告并写盘,再把摘要放进 receipt ——
  否则「每日缺口」恰好在最该看的那天消失。重建失败才降级为
  `{'available': false, 'reason': ...}`。
- 报告内容:每单元 `company/scope/status/complete/expected_total/collected_jobs/gap`;
  汇总(吻合数、**「声称 complete 却少采」单独高亮**、partial 缺口 TOP 20、无 `expected_total`
  单元数与清单);与前一日的 `collection-gap.json` 对比(新缺口 / 缺口变大 / 收窄 / 消除)。
- 阈值告警:声称完整却少采 > 0,或单公司缺口 > 200 → 写
  `runs\<日期>\collection-gap-alert.jsonl`,并在 `qiuzhao.notify` 存在时推送。
  **注意**:`qiuzhao.notify` 属于 `feat/cc-bot-notifier`(部署件 `20260920b`),**不在本包内**;
  本包在没有它时降级只写告警文件(报告里会写 `merge feat/cc-bot-notifier to enable push`)。
  站长若要飞书推送,需另部署 20260920b。

## 2. 文件清单(16 个运行时文件)

| # | 文件 | 目标路径(精灵) | 动作 | 20260920d sha256(前 8 位) | 前提 sha256(前 8 位) |
|---|---|---|---|---|---|
| 1 | `p1_pipeline.py` | `qiuzhao\collector\` | 覆盖 | `751e227a` | `093b237e` |
| 2 | `p1_platform_companies.json` | `qiuzhao\collector\` | 覆盖 | `3b2dedf9` | `cd4c403b` |
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
| 13 | `p1_netease_public.py` | `qiuzhao\collector\` | 覆盖 | `2e71ffd6` | `e0b4534e`(**实测**) |
| 14 | `p1_meituan_public.py` | `qiuzhao\collector\` | 覆盖 | `422562c9` | `27dbb5b4`(**实测**) |
| 15 | `windows_collector.py` | `deploy\` | 覆盖 | `d9d75bd0` | `9eaf97cc`(**实测**) |
| 16 | `collection_gap.py` | `qiuzhao\collector\` | **新增** | `34351a1c` | **ABSENT**(`Test-Path=False` 实测) |

`PROD-BACKUP-MANIFEST.txt` 另有 13 个 VERIFY ONLY 文件(7 个 20260920a 状态 + 6 个 20260918k 状态),
前提哈希全部按精灵**实测**核对过,**零漂移**。20260920c 遗留的 `p1_netease_public.py`
CAVEAT 已被实测关闭(实际值 = 预期的 `e0b4534e…`)。

## 3. 部署步骤(执行者用)

1. **空闲判定**:确认无采集在跑、`runs\<今天>` 不存在、计划任务 `State=Ready`、
   `data\lark-sync\status.json` 正常。
2. **前提核对**:按 `PROD-BACKUP-MANIFEST.txt` 的表格逐条 `Get-FileHash`,与「前提 sha256」列
   比较。任一不符 → 停下记录漂移,不要盲目覆盖。
3. **备份**:`robocopy` 备份 `C:\mcp-suite-collector\qiuzhao` 与 `...\deploy`
   (退出码 ≤7 为成功;不要备份整个 collector 目录,`recovery\` 约 3.4 GB)。
4. **传输**:16 个文件分片 base64 传入暂存目录(每片 ≤1300 字符),逐文件 `Get-FileHash` 与
   `SHA256SUMS.txt` 核对,**16/16 通过才继续**。
5. **覆盖**:15 个覆盖 + 新建 `qiuzhao\collector\collection_gap.py`;不删任何文件。
6. **覆盖后校验**(正式 venv,cwd=`C:\mcp-suite-collector`):
   - `py_compile` 全部 0 失败;
   - `IMPORT_OK 1124 1124`(tupu360 启用后 **1124**,不再是 1069);
   - `LOCK True`(P0 热修 `_publish_thread_lock` 仍在);
   - `from qiuzhao.collector import collection_gap` 可导入;
   - `REGISTRY['IQVIA 艾昆纬'] == 'qiuzhao.collector.p1_platform_tupu360'`;
   - tupu360 段 60 enabled / 8 disabled;
   - `REGISTRY['美团'] == 'qiuzhao.collector.p1_meituan_public'`。
7. **不重启服务、不改计划任务、不手工补跑 p1**;等下一个 06:10 周期。

## 4. 上线后第一次观察(2026-09-21 06:10)

- `runs\20260921\collection-gap.json` 与 `.md` **存在**;`receipt.json` 里有 `collection_gap` 字段。
- 美团三个 scope 应从「320/140/40」变成 `2502/401/188` 量级;缺口报告里美团不再占 TOP1。
- 若 tupu360 的单元没进当日窗口(见 §1.1 容量提醒),报告里的单元总数会明显小于 1124×N,
  这是**容量**问题不是采集失败 —— 按缺口报告的「无 expected_total / 单元总数」判断。
- 报告里若出现「声称 complete 却少采」,那是最高优先级:说明某适配器在自报总数与实存数
  不一致时仍标了 complete。

## 5. 回滚

15 个文件从备份还原,`qiuzhao\collector\collection_gap.py` **删除**(原本不存在)。
还原后核对 `p1_pipeline.py` 回到 `093b237e…`(Windows 并发发布锁不能丢)。
