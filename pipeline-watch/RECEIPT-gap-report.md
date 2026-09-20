# RECEIPT — tupu360 60 家启用 + 美团少采修复 + 每日采集缺口报告

分支 `feat/gap-report`(worktree `/Users/maxzhl/Projects/mcp-suite-gap`,起点 `feat/collector-next-6` f0694da7)
执行:DeepSeek(执行会话),2026-09-20。
**未部署、未覆盖精灵正式目录、未碰阿里云、未写飞书生产 Base、未读取/打印任何令牌、未登录、未 push、未合并 main、未终止任何进程。**

---

## 0. 结论

1. **tupu360 60 家已全部 `enabled:true`**(站长 2026-09-20 原话「接回来的60家都开」),
   8 家匿名侧拿不到的保持 `false` 并写明原因。默认公司集合 **1069 → 1124(+55)**。
2. **美团少采的根因不是分页上限,是一次瞬时 SSL 断连把整个 scope 打断**:`_post_json` 对任何传输
   异常直接抛错、翻页循环整体退出,social 停在第 16 页、intern 第 7 页、campus 第 2 页;
   页间 `sleep(0.08)` 也远低于 1 秒礼貌下限。修法是**重试 + ≥1 秒节流 + pageSize 100**
   (外加 totalPage/totalCount 不一致时的有界补页)。**真实只读验证:320 → 2502(social)、
   140 → 401(intern)、40 → 188(campus),缺口 2588 → 1**(剩下那 1 条是服务端自己返回的重复行)。
3. **每日采集缺口报告已建成并接入 p1 收尾**:`runs\<日期>\collection-gap.{json,md}`,
   含「声称 complete 却少采」单独高亮、partial 缺口 TOP20、与前一日对比;关键数字进
   `receipt.json` 的新字段 `collection_gap`;超阈值写告警文件(飞书通道需合并 `20260920b`)。
   **用今早真实数据跑出的数字与总控 09:40 实测逐条吻合**(958 单元 / 2 个声称完整却少采 /
   18 个 partial / 2631 条 partial 缺口 / 美团 2588)。
4. **附带发现(不在本任务范围,但必须上报)**:今早那轮 p1 从 06:41 跑到 11:43,
   **撞上 `--max-run-seconds 18000` 上限**,被 `windows_collector` 的 18100 秒 step 超时杀掉,
   因此 `runs\20260920\receipt.json` 里**根本没有 `p1` 这一项**,`p1-status.json` 被
   `reset_p1` 删除(只有 `p1-runs\*\status.json` 留下来)。**若不加处理,每日缺口报告恰好在
   最该看的那天不会生成** —— 已在 Windows 链里加了「从 p1 run status 现场重建报告」的兜底。

---

## 1. tupu360:60 家启用

### 1.1 站长决定(原文留痕)

> **「接回来的60家都开」** —— 站长,2026-09-20。

平台级事实:tupu360(图谱天下)的 `robots.txt` 是
`User-agent: * / Disallow: /`(全站禁止)。**站长已知情并决定采集**,该决定逐行写进配置:

- 每一条启用的行都有 `enabled_reason`:
  `站长 2026-09-20 明确决定启用（原话“接回来的60家都开”）；平台级 robots.txt 为 \`User-agent: * / Disallow: /\`，站长已知情并决定采集。`
- tupu360 段 `_README` 重写:写明 `ROBOTS` 事实、站长决定原文与日期、60 家来源
  (2026-09-19 全站实测 180 单元 / 5523 条真实岗位)、8 家为何仍关、如何单行启停、
  以及 5 家同名「槽位由更早适配器持有」。

### 1.2 启用清单(60 家)与总数

68 行 = **60 家 careersite 租户(全部启用)** + **8 家保持关闭**。

| # | tenant | 公司 | 2026-09-19 公开页实测 | 备注 |
|---|---|---|---|---|
| 1 | `Viatris` | 晖致医药有限公司 | campus 13 / intern 15 / social 244 | |
| 2 | `accentureats` | 埃森哲 | campus 10 / intern 12 / social 87 | |
| 3 | `aexpec` | 连通（杭州）技术服务有限公司 | social 6 | |
| 4 | `andritz` | 安德里茨（中国）有限公司 | campus 1 / intern 6 / social 46 | |
| 5 | `astrazeneca` | 阿斯利康 | intern 1 / social 267 | |
| 6 | `bd` | 碧迪医疗器械(上海)有限公司 | social 11 | |
| 7 | `bmw` | 宝马 | social 2 pages | |
| 8 | `bmw-brilliance` | 华晨宝马汽车有限公司 | campus 4 / intern 5 / social 19 | |
| 9 | `carrier` | 开利空调 | social 25 | |
| 10 | `chinadatagroup` | 华道数据处理有限公司 | social 38 | |
| 11 | `cn.abb` | ABB | social 2 | **槽位在 Phenom** |
| 12 | `cummins` | 康明斯 | campus 27 / intern 5 / social 35 | **槽位在 ORC** |
| 13 | `danfoss` | 丹佛斯(上海)自动控制有限公司 | campus 2 | |
| 14 | `dowstone.cn` | 道氏 | campus 24 / social 6 | |
| 15 | `estee` | 雅诗兰黛（上海）商贸有限公司 | social 26 | |
| 16 | `evergrande` | 恒大集团有限公司 | campus 6 | |
| 17 | `fosunholiday` | 地中海度假集团 | social 2 | |
| 18 | `fuyao` | 福耀玻璃 | campus 121 / intern 4 / social 228 | |
| 19 | `grgtest` | 广电计量检测集团股份有限公司 | social 89 | |
| 20 | `hbglobal` | 华宝集团 | campus 1 | |
| 21 | `healthineers` | 西门子医疗 Siemens Healthineers | campus 17 / intern 1 / social 218 | |
| 22 | `hella` | Hella | social 8 | |
| 23 | `heraeus` | 贺利氏 | campus 2 / social 23 | |
| 24 | `hfcFoods` | 东莞徐记食品有限公司 | social 7 | |
| 25 | `hitachi-helc.com` | 日立电梯（中国）有限公司 | campus 1 / social 5 | |
| 26 | `ibmcampus` | IBM 校招 | campus 12 / intern 6 | |
| 27 | `ict.ac` | 中国科学院计算技术研究所 | social 111 | |
| 28 | `innomotics` | 茵梦达 | campus 3 / intern 5 / social 36 | |
| 29 | `intel` | Intel | campus 15 / intern 3 / social 7 | |
| 30 | `intelcampus` | 英特尔（校招） | campus 1 / intern 1 / social 16 | |
| 31 | `ioe.ac.cn` | 中国科学院光电技术研究所 | campus 48 / social 7 | |
| 32 | `iqvia` | IQVIA 艾昆纬 | campus 12 / intern 5 / social 12 | |
| 33 | `iscas` | 中科院软件所 | campus 89 / social 1 | |
| 34 | `jiuniudianshang` | 九牛电商 | social 1 | |
| 35 | `jnj` | 强生 | campus 18 / intern 4 / social 322 | **槽位在 Workday** |
| 36 | `joomet` | 荞麦咨询 | campus 2 / intern 1 | |
| 37 | `lilly` | 礼来 | campus 17 | |
| 38 | `lvmh` | LVMH | campus 13 / intern 12 / social 104 | |
| 39 | `pfizer` | 辉瑞 | social 279 | |
| 40 | `pfizercampus` | 辉瑞校招系统 | intern 13 | |
| 41 | `pharmaron-bj` | 康龙化成（北京）新药技术股份有限公司 | campus 144 / intern 41 / social 828 | 分页深度样板 |
| 42 | `sanofi` | 赛诺菲（中国）投资有限公司上海分公司 | intern 20 / social 126 | |
| 43 | `scania` | 斯堪尼亚 | social 36 | **槽位在 Moka** |
| 44 | `schaeffler` | 舍弗勒 | intern 2 (+2) / social 70 | |
| 45 | `siemens` | 西门子中国 | campus 42 / intern 6 / social 167 | |
| 46 | `siemens-energy` | 西门子能源 | campus 1 / social 98 | |
| 47 | `simedarbyats.industrial` | 森达美信昌机器工程有限公司 | campus 2 / social 62 | |
| 48 | `simemotors` | 森那美汽车 | intern 2 / social 51 | |
| 49 | `skhynix` | SK 海力士大连 | campus 8 / intern 2 / social 56 | |
| 50 | `swireproperties` | 太古地产（中国）投资有限公司 | social 9 | |
| 51 | `tjyh2003` | 英华实验学校 | campus 2 / social 20 | |
| 52 | `toyota` | 丰田汽车（中国）投资有限公司 | social 11 | |
| 53 | `tptest` | 中力迅科技 | social 1 | |
| 54 | `tsingyun` | 清云智通（北京）科技有限公司 | campus 8 / social 37 | |
| 55 | `tuv` | 莱茵技术（上海）有限公司 | social 1 | |
| 56 | `wanji` | 万集科技 | campus 56 / social 15 | |
| 57 | `weinview` | 威纶通 | campus 8 / social 33 | |
| 58 | `wuxiapptec` | 药明康德 | campus 198 / intern 27 / social 397 | **槽位在 `p1_sources_41_50`** |
| 59 | `xmhxgroup.com` | 厦门恒兴集团有限公司 | social 63 | |
| 60 | `yumchina` | 百胜中国 | social 1 | |

**保持 `enabled:false` 的 8 家(附原因,都是为了不凑数开一个必然失败的)**
7 家微信专属(wxtemp)租户:`nestle` 雀巢、`taitaile` 太太乐、`autoliv` 奥托立夫、
`louisvuitton` 路易威登、`jntl` 科赴、`google` Google 谷歌、`boschhuayu-steering` 博世华域转向
—— 匿名侧 `<slug>.tupu360.com` 只答扫码页「该网站已停用」,careersite 侧无公开路由,适配器不登录;
`johnsonelectric` 德昌电机 —— 官方 careersite 租户在所有公开渠道(CAMPUS/INTERNSHIP/SOCIAL/校园大使)
均 **0 个职位**,公布的入口是微信租户。

### 1.3 注册结果(实测)

| 指标 | 值 |
|---|---|
| tupu360 段行数 | 68(60 启用 + 8 关闭) |
| `tupu360.COMPANIES` | **60** |
| `tupu360.merged_registry()` | 60 个名字 |
| `DEFAULT_COMPANIES` | **1124**(原 1069) |
| `REGISTRY` | 1124(键集合与 DEFAULT 相同、无重复) |
| 注册模块数 | 22(原 21;tupu360 模块此前 0 家,现在 55 家) |
| tupu360 真正接管的公司 | **55**(60 − 5 家槽位被更早适配器持有) |

5 家同名冲突按既有 `setdefault` 约定**不顶替**:ABB→Phenom、康明斯→ORC、强生→Workday、
斯堪尼亚→Moka、药明康德→`p1_sources_41_50`。**这 5 家的 tupu 行虽然 enabled,但日常采集仍走原适配器**
——这是既有约定,不是本分支引入的。

### 1.4 容量提醒(重要,需要站长决定)

今早 p1 从 **06:41:51 跑到 11:43:31**,撞上 `--max-run-seconds 18000`(5 小时)上限,
958 个单元完成、`run_finished=false`。tupu360 启用后单元数 **+180**(60 家 × 3 scope),
在同一个 18000 秒窗口里**大概率采不完**,表现会是「部分单元当轮没轮到」(缺口报告里体现为
单元总数偏低 / 无 `expected_total` 的单元变多)。

建议(部署本包时一并决定):**提高 `--max-run-seconds`(daytime 窗口允许的话)或启用
`--platform-rotation` 把平台公司分天轮转**。本分支不改调度,只如实上报。

---

## 2. 美团少采:根因与修复

### 2.1 根因(用今早真实 coverage 实证,不是读代码猜)

今早 `runs\20260920\data\p1-runs\20260920T064151\status.json` 里美团三个单元:

| scope | status | expected_total | collected_jobs | pages_scanned | pagination_exhausted | errors(首条) |
|---|---|---|---|---|---|---|
| social | partial | 2500 | 320 | 16 | **false** | `Network failure: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] …>` |
| intern | partial | 399 | 140 | 7 | **false** | 同上 |
| campus | partial | 189 | 40 | 2 | **false** | 同上 |

结论:
- **不是分页上限**:适配器用 `for page_no in range(1, 1000000)`,没有 cap。
- **不是预算**:美团适配器没有 budget 概念。
- **不是「把安全阀当目标」**:没有安全阀。
- **没有 `pagination_exhausted` 谎报**:三处都诚实写了 `false`。
- **真因**:`_post_json()` 对任何传输异常直接 `raise`,`collect()` 的 `except Exception` 记一条
  error 后**整体退出** —— 一次瞬时 SSL EOF 就把整个 scope 截断在第 N 页;而页间 `sleep(0.08)`
  远低于本项目 1 秒的礼貌下限,把被限流/掐断的概率放大。
- **接口本身很宽**:2026-09-20 实测 `pageSize=100` **被服务端尊重**(返回 100 行、`totalPage`
  按 100 重算),social 2501 条只需 26 页而不是 126 页。

### 2.2 修法(`qiuzhao/collector/p1_meituan_public.py`)

| # | 改动 | 说明 |
|---|---|---|
| 1 | **传输重试** | 瞬时错误(URLError / ssl.SSLError / 连接重置 / 截断 JSON)重试 **4 次**,退避 1/2/4/8 秒;4xx(除 408/429)是真实应答**不重试**,5xx 重试。次数记入 `coverage.retries` |
| 2 | **页间节流 ≥1 秒** | `REQUEST_INTERVAL_FLOOR = 1.0`;`QIUZHAO_PLATFORM_REQUEST_INTERVAL` 只能调慢不能调快 |
| 3 | **pageSize 20 → 100** | 实测服务端尊重;请求数降到 1/5 |
| 4 | **补页守卫** | 站点自报 `totalPage` 小于自报 `totalCount` 时,继续翻页补齐(有界 `PAGE_OVERRUN_LIMIT=20`),并把 `pages_beyond_reported_total` 留成证据 |
| 5 | **空页诚实化** | 空页提前出现且未采齐 → 记 `list exhausted at page N with X of totalCount=Y`,保持 `partial` |
| 6 | 证据字段 | `coverage` 新增 `page_size` / `request_interval` / `retries` / `pages_beyond_reported_total` |

`complete` 的判定条件**没有放松**:仍要求 `unique_source_ids == expected_total` 且
`pagination_exhausted is True` 且**无任何 error**。

### 2.3 真实只读验证(不 `--apply`、不写库、间隔 ≥1 秒)

用分支代码直接调 `collect()`(不经 p1_pipeline、不写库),输出到本机临时目录:

| scope | 修复前 | 修复后 | 站点自报 | pages | 耗时 | 重试 | 结果 |
|---|---|---|---|---|---|---|---|
| social | 320 | **2502** | 2502 | 26 | 51.4s | 0 | `complete=true` |
| intern | 140 | **401** | 401 | 5 | 7.6s | 0 | `complete=true` |
| campus | 40 | **188** | 189 | 3 | 6.0s | 0 | `partial`,缺口 1 |
| **合计** | **500** | **3091** | 3092 | 34 | 65s | 0 | 缺口 **2588 → 1** |

- 请求数 34 次(每 scope 3/5/26,均 ≤300),间隔 ≥1 秒。
- campus 的 1 条缺口**是服务端自己返回了重复 `jobUnionId`**(`duplicate source_record_id=4697317646 at page=2`),
  唯一 id 188 < 自报 189。**没有伪装成 complete**,如实保持 `partial` 并记录原因。
- 修复后 `美团` 的缺口从 2588 条降到 1 条,缺口报告里不再占 TOP1。

---

## 3. 每日「采集缺口报告」(本任务核心)

### 3.1 产物

| 文件 | 说明 |
|---|---|
| `qiuzhao/collector/collection_gap.py`(**新增**) | 报告的全部逻辑,纯函数 + 一个 `publish()` 落盘入口 |
| `qiuzhao/collector/p1_pipeline.py`(改) | `run()` 结束前调用 `collection_gap.publish(status, default_run_root(data_dir, run_dir))`,结果写进 `status['collection_gap']` |
| `deploy/windows_collector.py`(改) | 新函数 `collection_gap_summary(run, stage)`;把摘要写进 `receipt.json` 的 **`collection_gap`** 字段;报告缺失时从 `p1-runs\*\status.json` **现场重建** |
| `runs\<日期>\collection-gap.json` | 机器可读:958 个单元全量 + 汇总 + 对比 |
| `runs\<日期>\collection-gap.md` | 人类可读:摘要 / **声称 complete 却少采(高亮)** / partial 缺口 TOP20 / 公司维度 / 与前一天对比 / 无总数的单元清单 / 附全部单元 |
| `runs\<日期>\collection-gap-alert.jsonl` | 超阈值告警落盘 |

### 3.2 报告口径

- 每个单元:`company / scope / status / complete / expected_total / collected_jobs / gap`
  (+ `pages_scanned` / `pagination_exhausted` / `retries` / `error_count` / `error_preview` / `published`)。
- `gap = max(0, expected_total − collected_jobs)`;`expected_total` 为 `None` 时 `gap=None`,
  单元进「站点不报总数」清单,**既不算吻合也不算缺口**。
- 汇总:单元总数、可比对数、吻合数、有缺口单元数、**声称 complete 却少采(单列一类)**、
  partial 缺口数、无总数单元数、总缺口、公司维度 TOP、TOP3 缺口公司。
- 对比前一日同名报告:新出现缺口 / 缺口变大 / 收窄 / 已消除。

### 3.3 告警阈值

| 条件 | 级别 |
|---|---|
| 声称 complete 却少采 **> 0** | critical |
| 单公司缺口 **> 200** | warning |

触发后**总是**写 `collection-gap-alert.jsonl`;若 `qiuzhao.notify` 可导入则同时调用
`notify(event, fields=...)` 推送。**本分支没有 `qiuzhao/notify.py`(它在 `feat/cc-bot-notifier` / 部署件 `20260920b`)**,
所以当前降级只写告警文件,报告里如实记录
`{'channel': 'file', 'sent': False, 'reason': 'qiuzhao.notify is not on this branch (merge feat/cc-bot-notifier to enable push)'}`。
**合并 20260920b 后无需改任何代码即自动走飞书。**

### 3.4 用今早真实数据跑出的样例(证据在 `pipeline-watch/gap-report-evidence/`)

输入(只读取自精灵):当日 `runs\20260920\data\p1-runs\20260920T064151\status.json`(958 单元),
前一日 `runs\20260918\data\p1-status.json`(118 单元,作对比基线)。

| 指标 | 本报告 | 总控 2026-09-20 09:40 实测 | |
|---|---|---|---|
| 已完成单元 | 958 | 958 | ✅ |
| 站点自报总数可比对 | 834 | — | |
| 完全吻合 | 814 | — | |
| 站点不报总数 | 124 | 124 | ✅ |
| **声称 complete 却少采** | **2 个 / 5 条**(商汤科技 intern 66/70、social 86/87) | 2 个 / 5 条 | ✅ |
| 老实标 partial 且少采 | 18 个单元 | 18 个 | ✅ |
| partial 缺口合计 | 2631 | 2631 | ✅ |
| 其中美团 | 2588(social 2180 / intern 259 / campus 149) | 2588 | ✅ |
| 总缺口 | 2636(= 2631 + 5) | — | |
| TOP3 缺口公司 | 美团 2588、米哈游 14、金山办公 7 | 美团一家占 2588 | ✅ |

告警(实际落盘 2 条):

```json
{"event":"collection_gap.complete_but_short","severity":"critical","count":2,"gap":5,
 "units":["商汤科技/intern 66/70","商汤科技/social 86/87"]}
{"event":"collection_gap.company_gap","severity":"warning","company":"美团","gap":2588,
 "threshold":200,"scopes":["social:2180","intern:259","campus:149"]}
```

与前一日对比(9-18 → 9-20):新缺口 12、变大 3、收窄 2、消除 4。

### 3.5 兜底:报告不能在最该看的那天消失

见 §0.4。`collection_gap_summary()` 在 `runs\<日期>\collection-gap.json` 不存在时,
从最新的 `runs\<日期>\data\p1-runs\*\status.json` 现场重建报告并写盘,再取摘要;
重建也失败才返回 `{'available': false, 'reason': ...}`。**这条路永不抛异常、永不影响退出码**,
单测覆盖 4 种情形(报告在 / 只有 status / 都没有 / 报告损坏)。

---

## 4. 单测与验证

| 树 | `pytest tests/` | 失败清单 |
|---|---|---|
| `feat/collector-next-6` f0694da7(基线) | 3 failed / 673 passed / 55 skipped | `test_core::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema::test_enum_check_fails_when_data_drifts` |
| `feat/gap-report`(本分支) | **3 failed / 710 passed / 55 skipped** | 与基线**逐条相同,新增失败 0** |

新增通过 **+37**:缺口报告 26(`tests/test_collection_gap.py`,含 4 条 Windows 链兜底)、
美团分页/重试 9、p1 集成 2。既有 tupu360 与集成测试按「60 家启用」更新(3 条改写,不是删除断言)。

新覆盖的关键点:
- 缺口计算(含 `expected_total=None`、over-collection 不为负、error_preview 截断);
- 「声称 complete 却少采」单独成类并触发 critical;
- 单公司缺口阈值(200 边界:200 不报、201 报);
- 与前一天对比(新/变大/收窄/消除、首次出现标记、无前日报告);
- 报告落盘(JSON+MD、原子写、无 `.tmp` 残留)、按 `runs\<日期>` 目录定日期(不看 UTC 起点);
- 告警落盘 / 注入假 notify / notify 抛异常不影响报告;
- 958 单元真实形态端到端复现(与总控数字一致);
- 美团:瞬时 SSL EOF 后重试成功、重试耗尽保持 partial、404 不重试 / 503 重试、
  退避序列 `[1,2,4,8]`、页间 ≥1 秒、环境变量只能调慢、totalPage 短于 totalCount 时补页、
  空页提前出现记错误、补页有界;
- tupu360:60 启用 / 8 关闭、每行决定留痕、注册 55 家净增、5 家槽位不顶替。

另有零网络探针 `pipeline-watch/gap-report-probe.py` → **PROBE OK**(不发任何网络请求;
同时说明:旧的 `collector-next6-probe.py` 断言「68 行全关 / 1069 家」,那些断言**按设计已被
站长 2026-09-20 的决定取代**,不要再拿它当当前真理)。

---

## 5. 部署件 `pipeline-watch/deploy-artifacts/20260920d/`

- **16 个运行时文件 = 15 覆盖 + 1 新增**(`collection_gap.py`)。`SHA256SUMS.txt` **16/16 OK**,
  且每个文件与分支源码**逐字节一致**(`cmp` 全过)。
- **本包取代 `20260920c`**(c 从未部署):d 含 c 的全部 13 个文件 + 本分支 3 个改动。
  **叠加顺序:`20260920a`(精灵现役)→ `20260920d`。** `20260919g/h/i` 与 `20260920c` 均已作废。
- `PROD-BACKUP-MANIFEST.txt`:前提哈希**逐条在精灵上只读实测**——
  - 20260920a 的 13 行(含 `p1_pipeline.py` = `093b237e…`)全部吻合,**零漂移**;
  - `p1_netease_public.py` 实测 = `e0b4534e…`(**关闭了 20260920c 遗留的 CAVEAT**);
  - 两个从未进过任何部署件的文件按实测记录前提:`p1_meituan_public.py` = `27dbb5b4…`、
    `deploy\windows_collector.py` = `9eaf97cc…`(后者与 c 的 VERIFY ONLY 值一致);
  - `collection_gap.py` = **ABSENT**(`Test-Path=False` 实测);
  - 另有 13 个 VERIFY ONLY 文件(7 个 20260920a + 6 个 20260918k)全部实测吻合。
- `DEPLOY-NOTES.md`:叠加顺序、16 文件清单、前提/内容哈希、部署步骤、覆盖后校验
  (**`IMPORT_OK 1124 1124`**、`LOCK True`、`collection_gap` 可导入、
  `REGISTRY['IQVIA 艾昆纬']` 指向 tupu360)、回滚方式、上线后第一次观察项、容量提醒。

---

## 6. 遗留与建议

1. **tupu360 的日常容量**:60 家 × 3 scope = +180 单元,与今早刚撞到的 18000 秒上限冲突。
   需要站长决定提高 `--max-run-seconds` 或启用 `--platform-rotation`(本分支不改调度)。
2. **告警飞书通道未在本分支**:需合并 `feat/cc-bot-notifier`(部署件 `20260920b`)才有推送;
   本包单独上线时告警只落文件。合并后零代码改动自动生效。
3. **今早 receipt 缺 `p1` 步的真因未 100% 定位**:事实是 p1 撞 18000 秒上限、被 18100 秒
   step 超时打断、`p1-status.json` 被 `reset_p1` 删除、`receipt.json` 里既无 `p1` 也无
   `normalize`,并带 `TypeError: 'NoneType' object is not subscriptable`。超时路径
   (`step()` 返回 124)本该在 receipt 里留下 `step_changes.p1={'exit':124,...}`,
   **实际没有**,说明异常发生在更早的位置。**本分支没有复现、没有修改这条链路**
   (只加了只读的 `collection_gap_summary`),建议单独立项排查 `windows_collector` 的
   step 记录路径 —— 这个 bug 的意义是:**即使 p1 采到 958 个单元,整轮仍可能被判失败并回滚**。
4. **campus 的 1 条缺口是服务端重复行**:如果要让 `complete` 语义区分「服务端重复」与「我方漏采」,
   可以让 `validate_result` 认 `duplicate_source_ids` 证据 —— 本次**故意没做**,保持
   「自报数与唯一数不等就不算 complete」的严格口径,避免为好看而放松诚实性。
5. **米哈游/金山办公/恒瑞医药等 17 个单元的小缺口(个位数)**:多数是详情页取不到
   (`Incomplete Moka detail` / 详情超时),属另一个课题(详情重试),本次未动。

---

## 7. 硬约束遵守声明

未部署;未覆盖精灵正式目录;未碰阿里云;**未写飞书生产 Base**;未读取或打印任何令牌;
未登录任何站点;未 push;未合并 main;**未终止任何进程**。
任何对精灵的 SSH **全部只读**:`Get-ChildItem` / `Get-Content` / `Get-FileHash` / `Test-Path`,
以及把瘦身脚本经 stdin 交给正式 venv 执行后只读 stdout(未在精灵落任何文件)。
对美团 API 的 34 次请求是任务要求的真实只读采集验证(未 `--apply`、未写库),
间隔 ≥1 秒、单 scope 请求数 ≤300。
