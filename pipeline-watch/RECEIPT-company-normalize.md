# 收据：公司名字段规范化（normalize 阶段）+ 精灵临时目录全库干跑

- 分支：`feat/company-normalize`（worktree `/Volumes/臭垃圾桶/生财MCP/_worktrees/company-normalize`，基线 `feat/collector-next-3` 2b123c2）
- 状态：**代码 + 单测 + 干跑完成；未部署、未覆盖精灵正式目录、未碰阿里云、未调飞书、未 push、未合并 main**
- 部署件：`pipeline-watch/deploy-artifacts/20260919e/`（3 个运行时文件 + SHA256SUMS + PROD-BACKUP-MANIFEST + DEPLOY-NOTES）
- 干跑目录（精灵）：`C:\mcp-suite-normalize-test\`（新建，正式目录 `C:\mcp-suite-collector` 全程只读）

---

## 1. 先结论

1. 库里三个公司名字段全空的 **25291 行（27.04%）** 在 normalize 后降到 **0**；
   `canonical_company` 从 26437 空（28.27%）降到 0，`company`/`company_name`/`recruiting_unit_raw` 同样归零。
2. 展示名去重数 **4016 → 3947**：211 组「同一家公司的不同写法」被合并成同一个名字，
   涉及 11629 行；前 100 家公司的岗位数除这些改名外**逐条不变**。
3. 「同岗位跨来源、公司名不一致」的分组从 **948 降到 796**（-152）。
   剩下 796 组是**集团 vs 子公司两层**的结构性问题（兵器系 158、中国移动系 40、中国联通系 15、
   招商局系 2、其他 581），不是拼写差异，需要「子公司→集团」的归属表才能继续收敛 —— 见第 7 节。
4. 幂等已验证：第二次 normalize `filled_total 0`、`would_change_existing 0`，文件字节不变。
5. 记录条数与 id 集合完全不变（前后 id 集合 sha256 相同），没有合并、没有删除。
6. `would_change_existing` 全仓**没有任何代码消费**（只有 `qiuzhao/normalize.py` 自己算并打印；
   `deploy/windows_collector.py` 只看 normalize 步骤的退出码），本次 9 条不构成拦截。
7. 干跑时抓到一个真 bug（平台配置并入品牌集合时存成裸字符串，取 `[0]` 退化成首字符，
   出现 `国信证券 → 国`），已修 + 加回归测试；第 6 节的数字是修复后重跑的。

---

## 2. 现状量化（精灵只读，2026-09-19 01:0x 快照）

快照 `C:\mcp-suite-collector\data\jobs.json`，343,047,764 字节，
sha256 `1da0252e84d0cab6b9bb85fb5e3456e31c56ffb1a194c443e583440714eac60e`，**93519 条**。

| 字段 | 空值数 | 空值率 |
|---|---|---|
| `canonical_company` | 26437 | 28.27% |
| `company` | 57777 | 61.78% |
| `company_name` | 56281 | 60.18% |
| 三字段全空 | 25291 | **27.04%** |
| `recruitment_unit` | 0 | 0% |
| `recruiting_unit_raw` | 7130 | 7.62% |

- **三字段互相矛盾的行 = 0**：`company` 与 `company_name` 同时非空时 31688/31688 完全一致，
  `canonical_company` 是它们的子集。所谓「取值冲突」不在同一行内，而在**同一岗位的不同来源行之间**（第 7 节）。
- 全空行的分布极集中：国聘各专场/国聘网 13709 行、字节跳动 4171、中国邮政 2648、腾讯 907、阿里巴巴 477、
  国家能源 422、中科创星系 125 …… 全空行**全部**有 `recruitment_unit`（0 空），其中 19166 行另有 `recruiting_unit_raw`。
- `recruitment_unit` 形态：去重 4916 个。长度 ≤4 的简称 63862 行、含「有限公司/股份」18154 行、
  含集团/控股/总部 2673 行、含分支/部门词 1373 行。
- **线上 MCP 现在的兜底**：`qiuzhao/v4_fields.py:707`
  `"company": _text(r.get("canonical_company") or r.get("recruitment_unit") or r.get("company"))`。
  所以腾讯行现在返回 `腾讯科技（深圳）有限公司`、邮政行返回 `中国邮政集团有限公司` —— 是真值，但不是品牌名。
  切到规范化后同一个表达式直接返回 `腾讯` / `中国邮政`，**服务器一行代码不用改**。
- 另一个口径坑：腾讯行的 `recruiting_unit_raw` 是部门码（`TEG 264 / IEG 156 / CSIG 132 / WXG 118 / CDG 53 …`），
  所以**证据顺序必须 `recruitment_unit` 在 `recruiting_unit_raw` 之前**，否则品牌会变成 `TEG`。

---

## 3. 设计与实现

### 3.1 字段口径

| 字段 | 口径 | 写入策略 |
|---|---|---|
| `canonical_company` | 品牌/集团层规范名 | 每次重算，写 |
| `company` | 对外展示名 = canonical | 每次重算，写 |
| `company_name` | 同上（历史同义字段） | 每次重算，写 |
| `recruitment_unit` | 用人单位层 | **只补空**，已有非空值绝不覆盖 |
| `recruiting_unit_raw` | 来源原始串 | **只补空** |

`recruitment_unit` 为什么不动：全库 0 空值；把它改写成 raw 的用人单位层会改动 19166 行，
并影响 `normalize.py` 的 `industry` 查表（`unit_to_industry` 等按 `recruitment_unit` 命中）。
这是「另一件事」，本任务列成待决策项。

### 3.2 判定顺序（`qiuzhao/company_names.py`）

证据取第一个非空字段：`canonical_company → company → company_name → recruitment_unit → recruiting_unit_raw`，
然后按下表逐条试，**第 5 步是默认结局**：

| 步 | 规则 | 例子 |
|---|---|---|
| 1 | `aliases` 精确命中（忽略空白/全半角括号/大小写） | 腾讯科技（深圳）有限公司 → 腾讯 |
| 2 | `prefixes` 前缀命中，且余串以法人/机构后缀收尾 | 中国移动通信集团北京有限公司 → 中国移动 |
| 3 | 文本本身就是已知品牌 | 阿里巴巴 → 阿里巴巴 |
| 4 | 逐层剥法人后缀（有限公司/股份有限公司/集团/(中国)…）后命中品牌 | 中国航天科工集团有限公司 → 中国航天科工集团 |
| 4b | 再摘一个行业词，**只有当剩下的正好是已知品牌** | 小米科技有限公司 → 小米 |
| 5 | 以上都不中 → **保留原名，不猜** | 三亚海洋实验室 / 塞浦路斯阿里斯托开发有限公司北京代表处 |

已知品牌集合 = 别名表的 `brands`（60）+ 表里所有 canonical 目标 + `p1_platform_companies.json`
里各租户的规范公司名（893，运行时读取，取不到就跳过）。canonical 目标自动入集合 ⇒ 幂等。

### 3.3 别名表 `qiuzhao/data/company_aliases.json`

`aliases` 19 条 / `prefixes` 3 条 / `brands` 60 条，**每条带 `basis`**，
前缀标注 `[数据]`（现役库里能直接看到的一致写法）、`[任务]`（派单点名样例）、`[通用简称]`（常识）。
覆盖了派单点名的全部样例：腾讯、滴滴（北京小桔科技有限公司）、大疆/大疆创新、
网易互娱、石晶光电、招商局/仁和人寿。

**网易互娱的处理写明了**：`网易互娱 → 网易`（并入），依据是 53 行 `recruitment_unit=网易互娱`
（source `网易互娱校招官网`）与 2996 行 `recruitment_unit=网易` 是同一集团的两个校招入口，
互娱是事业群不是独立法人；`网易互联网 → 网易` 同理。**要拆分只需删掉这两行。**
网易有道（`网易有道信息技术（北京）有限公司`）**不并入**，保持独立。

### 3.4 为什么不把公司字段放进 `NORMALIZED_FIELDS`

`qiuzhao/collector/run.py:253` 会把 `NORMALIZED_FIELDS` 的上一轮取值带进刷新行。
公司名一旦那样继承，改别名表就会留下改不动的旧名。所以另立 `COMPANY_FIELDS`，
`REPORTED_FIELDS = NORMALIZED_FIELDS + COMPANY_FIELDS`（20 个）只用于统计与自检，
每天由 normalize 从采集器的新鲜输出重新推导。有单测锁这条
（`test_company_fields_are_reported_but_not_inherited_by_collector_merge`）。

---

## 4. 单测

`tests/test_company_names.py`（新增，42 条），覆盖：别名、前缀、保守后缀规则、
**不确定保留原名**、空表时默认保留、展示名三字段不变量、用人单位层只补不覆盖、
`normalize_records` 幂等、`canonical_of` 幂等、**统计口径**、别名表自检（每条有 basis、
canonical 稳定、条目形状）、`normalize_file` 条数与 id 不变。

统计口径那条按派单要求写死：
```python
before = {腾讯: 3, 字节跳动: 2, 阿里巴巴: 1}          # 按 recruitment_unit/canonical 计
normalize_records(records)
after  = {腾讯: 3, 字节跳动: 2, 阿里巴巴: 1}          # 按 canonical_company 计
assert after == before
```
样本里故意放了干扰项 `塞浦路斯阿里斯托开发有限公司北京代表处`（名字含「阿里」子串），
断言它**不会**被算进阿里巴巴 —— 真实库里就有这一行。

全量回归（主仓 venv，`PYTHONPATH=<worktree>`）：

| 版本 | 结果 |
|---|---|
| 基线 `2b123c2`（干净 worktree `/tmp/baseline-next3`） | **3 failed, 498 passed, 55 skipped** |
| 本分支 | **3 failed, 540 passed, 55 skipped** |

（540 = 498 + 新增 42 条；多次全量跑的差异只在 flaky 那条，见下。）

失败清单逐条相同：`test_core::test_role_cohort_and_campaign_title_bases`、
`test_p1_pipeline::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint`、
`test_schema::test_enum_check_fails_when_data_drifts` —— 与交接文档记录的三条既有失败一致，**未新增**。

多次全量跑的结果：`3 failed/538 passed`（提交前）、`4 failed/539 passed`（提交后第一次）、
`3 failed/540 passed`（最终确认）。三条硬失败的名单每次都完全相同。

另外交接文档点名的 flaky 用例 `test_codes_kind.py::test_migration_is_safe_when_both_services_start_together`
在这台机器上负载高时会随机会红。单独跑 6 次：本分支 3 次失败 / 基线 `2b123c2` **也** 3 次失败
（两边同源，与本改动无关）。全量跑出现过一次 `4 failed/539 passed`（就是它多红了一条，同时多一条通过），
其余为 `3 failed`。

---

## 5. 全库干跑（精灵临时目录，未碰正式目录）

流程：`C:\mcp-suite-collector\qiuzhao` 复制到 `C:\mcp-suite-normalize-test\code\qiuzhao`（54 文件）
→ 覆盖 3 个改动文件（分片 base64 逐字节 sha256 校验，3/3 `sha_ok True`）
→ 现役 `jobs.json` 复制到 `C:\mcp-suite-normalize-test\jobs.json`（只读复制，sha256 相同）
→ 跑真实 `qiuzhao.normalize.normalize_file`，两遍。

同时跑了一个**对照组**：`C:\mcp-suite-normalize-test\control\` 用**现役未改的代码** +
同一份库快照跑一遍，用来把「本次改动造成的差异」和「normalize 本来就有的差异」分开。

### 5.1 三个字段空值率 前 → 后

| 字段 | 前 | 后 |
|---|---|---|
| `canonical_company` | 26437（28.27%） | **0** |
| `company` | 57777（61.78%） | **0** |
| `company_name` | 56281（60.18%） | **0** |
| 三字段全空 | 25291（27.04%） | **0** |
| `recruiting_unit_raw` | 7130（7.62%） | **0** |
| `recruitment_unit` | 0 | 0 |

### 5.2 公司去重数 前 → 后

| 口径 | 前 | 后 |
|---|---|---|
| 展示名（`canonical_company or recruitment_unit or company`，= 线上 MCP 口径） | 4016 | **3947** |
| `canonical_company` | 50 | 3947 |
| `company` | 415 | 3947 |
| `company_name` | 34 | 3947 |
| `recruitment_unit` | 4916 | 4916（不动） |
| `recruiting_unit_raw` | 4798 | 5348（补齐 7130 行带出的新取值） |

### 5.3 前 100 家公司岗位数 前 → 后

`pipeline-watch/deploy-artifacts/20260919e/` 同级产物见外接盘
`_research/company-normalize/dryrun-top100-before-after.csv`（115 行）。
只有改名涉及的公司有变化，其余逐个数字不变。例：

| 公司 | 前 | 后 |
|---|---|---|
| 字节跳动 | 4173 | 4173 |
| 小米 | 3545 | 3545 |
| 中国邮政集团有限公司 → 中国邮政 | 2648 | 2652 |
| 中国联合网络通信集团有限公司 → 中国联通 | 2584 | 2700 |
| 中国移动通信集团有限公司 → 中国移动 | 1797 | 1878 |
| 腾讯科技（深圳）有限公司 → 腾讯 | 907 | 907 |
| 网易（含网易互娱 53） | 3031 | 3084 |
| 科大讯飞 | 893 | 904 |
| 大疆（含大疆创新 15） | 660 | 675 |

### 5.4 被改名的公司清单（CSV）

`_research/company-normalize/dryrun-renamed-companies.csv`：**211 对**
（列：改名后 / 改名后岗位数 / 改名前的展示名 / 合并前的岗位数 / 样例来源 / 样例招聘单位），
涉及 **11629 行**。行级样例 3000 条在 `dryrun-renamed-rows-sample.csv`。
前 9 大：中国邮政 2648、中国联通 2584、中国移动 1797、中国航天科工集团 1241、
腾讯 907、中国能源建设 649、国家能源集团 422、中国兵器工业集团 406、中国兵器装备集团 167。

### 5.5 耗时与内存

| 项 | 第一遍 | 第二遍（幂等验证） | 对照组（现役代码） |
|---|---|---|---|
| 耗时 | 31.37 s | 30.87 s | 30.12 s |
| 进程峰值工作集 | **2234.8 MB** | 2111.5 MB | （未测） |
| `filled_total` | 147931 | **0** | 297 |
| `would_change_existing` | **9** | **0** | 0 |
| 产物字节 | 327,333,989 | 327,333,989（字节不变） | 322,249,691 |

精灵 16GB 内存，峰值 2.2GB；`windows_collector.py` 给 normalize 的超时是 **1800 s**，余量充足。

### 5.6 记录条数与 id 集合

- 条数：**93519 → 93519**。
- id 集合 sha256：`d2c19eeebb1245f43e3e261f1a0c08afcc36d7a38f9bdc5ae58d22fc9f074880`
  **前后完全相同**；两个产物的 id 顺序也相同（`SAME_ORDER_IDS True`）。
- 297 行本来就没有 id（前后一致，未受影响）。

### 5.7 `would_change_existing` 不拦截

- 全仓只有 `qiuzhao/normalize.py` 计算并打印这个字段，没有任何代码消费它。
- `deploy/windows_collector.py` 对 normalize 步骤只看**退出码**（`state['steps']['normalize'] != 0` 才回滚），
  退出码不受这个计数影响。`qiuzhao/collector/run.py` 同理。
- 本次 9 条明细（**全部是预期的改名**，用对照组逐位置比对得出）：

| 行号 | id | 字段 | 前 | 后 |
|---|---|---|---|---|
| 16665-16667 | `mokahr_c3ff8…` 等 3 条 | company | 兆易创新科技集团股份有限公司 | 兆易创新 |
| 17981-17983 | `zhiye_iflytek_…` 等 3 条 | company | 科大讯飞股份有限公司 | 科大讯飞 |
| 17999 | `zhiye_keyence_390836746` | company | 基恩士（中国）有限公司 | 基恩士 |
| 20362 | `guopin-215467196850112072` | company | 中国联合网络通信有限公司湖北省分公司 | 中国联通 |
| 20363 | `guopin-215300458401498642` | company | 中国联合网络通信有限公司新疆维吾尔自治区分公司 | 中国联通 |

（其余 20 万+ 行的 `company`/`company_name` 改动都是从**空**变成有值，不计入该字段。）

---

## 6. 干跑抓到并修掉的 bug

`_load_platform_names()` 最初返回 `{匹配键: 名字字符串}`，而其它表返回 `{键: (规范名, 依据)}`。
调用方统一 `entry[0]` 取规范名，于是平台配置来的品牌名**退化成了首字符**：
干跑第一轮出现 `国信证券 → 国`、`中金公司 → 中`、`基恩士（中国）有限公司 → 基`、
`兆易创新科技集团股份有限公司 → 兆` 共 18 行（`would_change_existing 18`）。
已改成统一返回 tuple，并加两条回归测试
（`test_every_brand_entry_is_a_full_name_not_a_bare_string`、
`test_platform_config_names_are_usable_as_canonical`）；
修后重跑 `would_change_existing 9`，就是 5.7 那 9 条预期改名。
**这个 bug 只会在干跑里暴露，单测覆盖不到 —— 是这次先干跑再上线的主要收获。**

---

## 7. 疑似同岗跨来源重复（本任务只统计，不合并）

口径：键 = 归一化 `job_title`(前 60 字) + 归一化(`recruiting_unit_raw` 或 `recruitment_unit`)。
**记录合并/删除一律没做。**

| 指标 | 前 | 后 |
|---|---|---|
| 分组总数 | 77786 | 77786 |
| 同键多行分组 | 7210 | 7210 |
| 落在重复分组里的行 | 22943 | 22943 |
| **组内公司名不一致的分组** | **948** | **796** |

剩下的 796 组按主题分桶（完整清单 `_research/company-normalize/dryrun-conflict-buckets.txt`，
样例 60 组在 `dryrun-compare.json` 的 `after.dup.samples`）：

| 桶 | 组数 | 典型对子 |
|---|---|---|
| 其他（以建筑/能源/航天/汽车系国企为主） | 581 | 中国能源建设 ‖ 中国能源建设集团甘肃省电力设计院有限公司；百度 ‖ 百度在线网络技术（北京）有限公司 |
| 兵器系 | 158 | 中国兵器工业集团 ‖ 安徽方圆机电股份有限公司 |
| 中国移动系 | 40 | 中国移动 ‖ 中移物联网有限公司 / 咪咕文化科技有限公司 / 卓望公司 |
| 中国联通系 | 15 | 中国联通 ‖ 中国联通国际有限公司 |
| 招商局系 | 2 | 招商局集团 ‖ 招商局仁和人寿保险股份有限公司 |

**这 796 组的性质**：国聘「企业校招专场」行的 `recruitment_unit` 是**办场集团**，
`recruiting_unit_raw` 才是实际用人单位；另一个来源（国聘行动 / 国聘网校园招聘）没有专场信息，
只能拿实际用人单位当公司名。两边是**集团层 vs 用人单位层**，不是拼写差异。
要继续收敛需要一张「子公司/分公司 → 集团」归属表，属于另一件事。

反例说明为什么不能靠规则硬收：`启明星辰信息技术集团股份有限公司` 出现在
`国聘官方企业校招专场：中国移动通信集团有限公司` 里，与另一来源的 `启明星辰…` 成了对子。
把「专场集团」无条件套到行上会造出错误归属，所以本任务不做。

---

## 8. 待决策（需要站长/Max 拍板）

1. **要不要继续收敛那 796 组**（集团 vs 子公司）？需要归属表；本体量远大于别名表，且要逐条有依据。
2. **`recruitment_unit` 要不要升级成用人单位层**（用 `recruiting_unit_raw` 覆盖）？会改动 19166 行，
   并影响 `industry` 查表，建议单独一轮 + 干跑。
3. **服务器侧是否同步这 3 个文件**（`/opt/mcp-suite/`）。不同步也能正常展示规范名（见 DEPLOY-NOTES）；
   同步属于服务器写操作，要站长明确确认。
4. **网易互娱/网易互联网并入网易**是否认可；不认可删两行即可。
5. 别名表要不要继续扩：目前 19 条精确 + 3 条前缀，覆盖的是高频与点名样例；
   库内还有 3117 个含法人后缀的 `recruitment_unit` 取值按「保留原名」处理。

---

## 9. 产物清单

| 产物 | 位置 |
|---|---|
| 代码 | 分支 `feat/company-normalize`：`qiuzhao/company_names.py`（新增）、`qiuzhao/data/company_aliases.json`（新增）、`qiuzhao/normalize.py`（改）、`tests/test_company_names.py`（新增）、`.gitignore`（放开别名表入库） |
| 部署件 | `pipeline-watch/deploy-artifacts/20260919e/`（3 运行时文件 + `SHA256SUMS.txt` + `PROD-BACKUP-MANIFEST.txt` + `DEPLOY-NOTES.md`） |
| 干跑原始报告 | 精灵 `C:\mcp-suite-normalize-test\report\`；本机副本 `_research/company-normalize/dryrun-*.{json,csv,txt}` |
| 干跑脚本 | `_research/company-normalize/s1..s4_*.py`（只读统计）、本机 `/tmp/dry_*.py`（干跑链） |

干跑临时目录占用（精灵 `C:\mcp-suite-normalize-test\`，盘上余量 61GB）：实测 **657,708,321 字节 ≈ 0.61GB**
（跑完的 `jobs.json` 327MB + 对照组 322MB + `code/` 与 `control/code/` 各 ~2.4MB + `report/` ~5MB），
留着供站长复核；不需要时整个目录删掉即可（正式目录不受影响）。

收尾只读复核（2026-09-19 01:2x，精灵）：正式目录 `qiuzhao/normalize.py` 仍是
`a53adaf33c891b5d8d8dd5b7531c0799b57666d5a62e987dc92ac22b9eb51b31`（部署前基线，未被本任务改写）、
`qiuzhao/company_names.py` 与 `qiuzhao/data/` 不存在、`data/jobs.json` 仍是 343,047,764 字节 —— **正式目录零写入**。

**未做的事**：未部署、未覆盖精灵正式目录、未写 `C:\mcp-suite-collector`（全程只读）、
未碰阿里云、未调飞书任何接口、未读取/打印任何令牌、未登录、未绕过验证码/签名、未 push、未合并 main、
未终止任何进程、未使用 `git stash`。
