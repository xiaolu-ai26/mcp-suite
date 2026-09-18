# RECEIPT — collector-next-4：外企四条线 + 公司名规范化合并 + 累积部署件 20260919g（不部署）

**结论先行**：`feat/foreign-ats-a`（Eightfold 5 家 + Phenom 8 家）、`feat/foreign-ats-b`
（Avature 4 家 + ORC 9 家 + iCIMS robots 闸门 0 家 + 4 家"0 条"修复）、`feat/foreign-ats-c`
（tupu360 适配器）、`feat/foreign-discovery`（外企全集 1278 家 + 净增 82 家 + CSV 接收器）与
`feat/company-normalize`（公司名三层字段规范化 + 别名表）已依次合并到 `feat/collector-next-4`，
`p1_pipeline.py` 的每个注册块**全部保留**（append-only，后加入的块不删除/不改写任何既有行）。
同名公司冲突逐个实测处置：**惠普 / 应用材料 → Eightfold，飞利浦 → Phenom**（对手 workday 行
`enabled:false` 留档），**强生 → 既有 workday 租户**（tupu360 全段留档），**毕马威 → 现役
`kpmg/76195`**（第二个 moka 租户 `kpmg/74356` 留档）。**tupu360 全段 14 行默认 `enabled:false`**
（平台 robots.txt 全站 `Disallow: /`），iCIMS 段 0 家 + robots 闸门不变。默认集合
**948 → 1056 家**（`REGISTRY == DEFAULT_COMPANIES`、0 重名），21 个模块。`pytest tests/`
失败清单相对 `feat/collector-next-3` 基线**不新增**（3 条既有失败 + 偶发 `test_codes_kind`）。零网络探针 `pipeline-watch/collector-next4-probe.py` **PROBE OK**。累积部署件
`pipeline-watch/deploy-artifacts/20260919g/`（26 个运行时文件 + `SHA256SUMS.txt` +
`PROD-BACKUP-MANIFEST.txt` + `DEPLOY-NOTES.md`）`shasum -c` **26/26 OK** 且与分支源码逐字节一致；
在「next-3 树 + g 覆盖」的模拟精灵目录里 import 闭包自洽（`IMPORT_OK 1056 1056`）。
**未部署、未 SSH、未碰阿里云、未调飞书、未读取/打印令牌、未登录、未发外部请求、未 push、
未合并 main、未终止任何进程。**

工作区：`/Volumes/臭垃圾桶/生财MCP/_worktrees/collector-next-4`（分支 `feat/collector-next-4`）。
Python：`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python`。外接盘 `._*`（AppleDouble）已加进
`.gitignore` 并确认未入库。

## 0. 分支与提交

| 项 | 值 |
|---|---|
| 起点 | `feat/collector-next-3` = `2b123c2`（精灵现役 20260918k，948 家） |
| merge 1 | `df7f33d` ← `feat/foreign-ats-a` `1f9118b`（自动合并，无冲突） |
| merge 2 | `c3c0d97` ← `feat/foreign-ats-b` `48f535c`（3 个文件冲突，已解） |
| merge 3 | `f840c81` ← `feat/foreign-ats-c` `64724de`（3 个文件冲突，已解） |
| merge 4 | `bcc6195` ← `feat/foreign-discovery` `3010f71`（2 个文件冲突，已解） |
| merge 5 | `9b0e701` ← `feat/company-normalize` `8990dba`（自动合并，无冲突） |
| 整合改动 + 探针 | `15b648d`（同名冲突处置、`enabled:false` 契约、单测） |
| 本收据 + 部署件 | 本收据所在提交 |

未 push、未合并 main、未部署。

## 1. 合并与冲突处理

| 文件 | 冲突分支 | 处理 |
|---|---|---|
| `qiuzhao/collector/p1_pipeline.py` | b、c | 三处冲突（注册块 / `PLATFORM_MODULES` / `PLATFORM_HOST_GROUPS` / `_load_scope_opt_ins` 段名）**两侧全保留**；最终注册顺序 = 既有块 → **Eightfold → Phenom**（批 A）→ **Avature → iCIMS → ORC**（批 3）→ **tupu360（`setdefault`）**（批 C）。`_load_scope_opt_ins()` 段名补成 13 段（含 `eightfold/phenom/orc/tupu360` 等） |
| `qiuzhao/collector/p1_platform_companies.json` | a、b、c、d | 逐段、同段内逐 key 取并集。四条的改动**全是纯新增行**（无删除、无改值），唯一同 key 冲突是 `workday.coke/wd1/coca-cola-careers`：b 写字符串 `"可口可乐"`、discovery 写对象 `{name, search_text: China, max_list_pages: 8}`；保留 discovery 的显式对象形式（默认值本就是 `search_text=China`、默认页上限 20，对实测 12 条无影响），`json` 解析后 0 重复 key |
| `tests/test_collector_next_integration.py` | a、b、c、d | 块顺序/覆盖/规模断言逐处取并集，最终按整合后的真实值收敛到 1056 |
| `.gitignore` | e | 自动合并（`qiuzhao/data/*` + `!qiuzhao/data/company_aliases.json`），另加 `._*` 规则 |
| 其余 | — | `qiuzhao/company_names.py`、`qiuzhao/data/company_aliases.json`、`qiuzhao/normalize.py`、各适配器与夹具单测均自动合并 |

合并后逐名比对：**既有 948 家模块归属 0 处变化、0 家丢失**（见 §3 的模块表与探针
`per_module`）。注册块全部 append-only：a/b 用 `REGISTRY.update`（同名行已在配置里留档，
实际不顶替），c 用 `REGISTRY.setdefault`，feishu 保持既有 `setdefault`。

## 2. 同名公司处置表（逐个实测）

| 公司 | 冲突行 | 实测（收据出处） | 处置 |
|---|---|---|---|
| **惠普** | `eightfold: apply.hp.com` ↔ `workday: hp/wd5/ExternalCareerSite` | Eightfold **16 条**（campus 0 / intern 1 / social 15，`RECEIPT-foreign-ats-a.md`）；workday **1 条**（social，`RECEIPT-foreign-discovery.md` §2R.2 第 57 行） | **Eightfold 生效**；workday 行 `enabled:false` + 切换说明留档 |
| **应用材料** | `eightfold: careers.appliedmaterials.com` ↔ `workday: amat/wd1/External` | Eightfold **131 条**（3/3/125）；workday **3 条**（campus） | **Eightfold 生效**；workday 行留档 |
| **飞利浦** | `phenom: PHILUS` ↔ `workday: philips/wd3/jobs-and-careers` | Phenom **159 条**（0/14/145）；workday **8 条**（social） | **Phenom 生效**；workday 行留档 |
| **强生** | `workday: jj/wd5/JJ`（现役）↔ `tupu360: jnj`（18 条校招 + 4 实习 + 322 社招） | tupu360 段按站长口径**全段留档**（robots 全站 Disallow）；workday 行是 20260918f 带入的租户，**本轮没有做新的实测** | **workday 继续生效**（tupu360 留档）。⚠️ **红字提示**：若首日 `强生` 三 scope 全 0 条，说明 workday 行是"猜测租户、实测 0 条"，需要在待办里升级为"强生暂无可采来源"，并把 tupu360 的启用决策提给站长 |
| **毕马威** | `moka: kpmg/74356` ↔ `moka: kpmg/76195`（同段重名） | 现役 `NAME_TO_SLUG` 解析到 `kpmg/76195`（`kpmg/74356` 是第二批新增的惰性行，next-3 收据 §9.1 已记录） | **`kpmg/76195` 显式生效**；`kpmg/74356` 改对象 + `enabled:false` 留档（并给 moka 加载器加 `enabled` 支持，不再靠 dict 顺序） |
| 高露洁 / 高露洁棕榄 | `beisen: colgate` ↔ `moka: colpal/28788` | 两个**不同官方名**（任务书点名核对） | 不构成重名冲突，各段各留一条、互不覆盖（守护单测断言两条都在、各归各段） |
| 欧莱雅 | 任务书举例"北森与 Avature" | **实测不成立**：base（next-3）与合并后的配置里 `欧莱雅`/`loreal` 只出现在 `avature: careers.loreal.com/en_US/jobs`，北森段没有欧莱雅行（b 收据的说法是"大易 iframe 壳页 → 改由 Avature 接入"，北森段从未有过这一行） | 无冲突；欧莱雅由 Avature 生效（2 条 social） |
| 艾昆纬 / IQVIA 艾昆纬 | `workday: REDACTED`（8 条）↔ `tupu360: iqvia`（12/5/12 条） | tupu360 全段留档 | 归一化后两个名字都收敛为自身（`IQVIA 艾昆纬` 是配置品牌名），**不需要合并**；tupu360 留档，workday 行生效 |
| 可口可乐 | `workday` 同 key，b 与 discovery 都写 | b 实测 12 条（`searchText=China`） | 同 key 取 discovery 的对象形式（语义等价），首日按 1 行采集 |
| 德州仪器 / 洲际 / 百胜等 | ORC 段 `_note` 已写明 | 德州仪器 ORC 95 条但会顶掉 Moka `ti/142216` 槽位 → **不注册**；摩根系等按适配器交付时结论 | 保持适配器里的既有决定，不改 |

`enabled:false` 契约在 **12 个配置驱动适配器**（beisen / moka / feishu / workday /
successfactors / dayee（`p1_foreign_01`）/ job51 / eightfold / phenom / avature / icims / orc，
tupu360 原本就有）里统一：加载时跳过留档行 → 不进 `REGISTRY`、不进默认集合、不采集。
对既有行完全惰性（默认集合只减掉 5 个 tupu360 名称）。守护单测
`test_every_config_driven_adapter_honours_the_enabled_false_park` 覆盖全部 13 段。

## 3. 调度归类、模块家数与默认集合

**默认集合 1056 家** = 20260918k 的 948 + 批 A 13 + 批 3 17 + tupu360 5 + 外企发现 82 − 4 个
同名去重 − 5 个 tupu360 留档名称 = 1056。`len(DEFAULT_COMPANIES) == len(set(...)) ==
len(REGISTRY) == 1056`，`duplicates 0`。

| 连续块（DEFAULT 顺序） | 家数 | 归类 |
|---|---|---|
| 硬编码 `COMPANIES` | 50 | 每天必跑（p1_sources_*） |
| `p1_platform_beisen` | 479 | 平台模块（zhiye.com） |
| `p1_platform_moka` | 326（模块共 329，3 家在硬编码槽内被 adopt） | 平台模块（app.mokahr.com） |
| `p1_banks_01` | 5 | 平台模块（banks） |
| `alibaba_headless` | 6 | headless 专用 |
| `tencent_music` | 1 | 专用 |
| `p1_platform_workday` | 65 | 平台模块（myworkdayjobs.com） |
| `p1_platform_successfactors` | 4 | 平台模块（successfactors） |
| `p1_feishu_public` | 72 | 平台模块（jobs.feishu.cn，setdefault） |
| `p1_bytedance_public` / `p1_midea_public` | 1 / 1 | 每天必跑专用适配器（独立 gate 组） |
| `p1_foreign_01`（大易） | 11 | 平台模块（hotjob.cn） |
| `p1_platform_51job` | 9 | 平台模块（51job.com） |
| **`p1_platform_eightfold`** | **5** | 平台模块（eightfold） |
| **`p1_platform_phenom`** | **8** | 平台模块（phenom） |
| **`p1_platform_avature`** | **4** | 平台模块（avature） |
| **`p1_platform_orc`** | **9** | 平台模块（oraclecloud） |
| `p1_platform_icims` | **0** | 平台模块（icims，robots 闸门，表里无行） |
| `p1_platform_tupu360` | **0** | 平台模块（tupu360.com，整段留档） |

- 6 个新适配器全部在 `PLATFORM_MODULES` 与 `PLATFORM_HOST_GROUPS`（探针断言
  `platform_modules_without_group == []`），受 `--platform-workers 3` 与同平台启动间隔 ≥1s 约束，
  **默认三 scope**（`company_scopes()` 对 6 家的代表公司都返回 `campus/intern/social`），
  且都不在 `ROTATING_MODULES`。
- iCIMS 段 0 家：适配器照交，`collect()` 先取 `/robots.txt`，命中 `Disallow: /` 只发 1 个请求就
  `blocked`；tupu360 段 14 行全部 `enabled:false` + `blocked_reason`，`merged_registry() == {}`。

## 4. 公司名规范化自洽检查

- 对**合并后全部 1019 条配置公司名**（13 段，含 18 条留档行）跑了一遍
  `qiuzhao.company_names.canonical_of()`：**会被改名的清单为空**（0 条）。
  原因：`company_names` 的已知品牌集合 = 别名表 brands + 全部分段 canonical 目标 +
  **`p1_platform_companies.json` 里的全部公司名**（`table_info()` = aliases 19 / prefixes 3 /
  brands 1080 / platform_names 1020），配置名天然是规范化不动点；且没有任何配置名命中别名/前缀规则。
- 规范化后的**活跃**公司名无跨段重名，也不与硬编码 50 名冲突（除既有的 9 个"硬编码槽被
  moka/feishu 声明"的已文档化重叠：三七互娱/金山办公/鹰角网络 → moka，影石Insta360/
  莉莉丝游戏/小鹏汽车/蔚来汽车/叠纸游戏/商汤科技 → feishu `setdefault` 保留硬编码槽）。
- 守护单测覆盖 6 个新增段：`CONFIG_SECTION_MODULES` 增加
  `eightfold/phenom/avature/icims/orc/tupu360`；`test_registry_names_are_unique_and_config_
  sections_never_hijack_a_module` 断言"REGISTRY 唯一 + 配置段不得跨段重名生效"（留档行用
  `enabled:false` 跳过，不计入 declared）。
- 顺手记：`IQVIA 艾昆纬`（tupu360）在规范化下仍是自身，与 workday 的 `艾昆纬` 是**两个不同
  展示名**；tupu360 留档所以不冲突，若将来启用 tupu360，需要站长在"合并成一个公司名"与
  "保留两个名字"之间拍板。

## 5. 耗时估算（8 路 workers + 平台限 3 路，用各分支收据实测数）

| 线 | 实测请求（收据出处） | 折合请求/轮 |
|---|---|---|
| 批 A Eightfold 5 + Phenom 8 | 39 单元 / **524 次**（验证节流 2s、25 次/单元预算，`RECEIPT-foreign-ats-a.md`） | 生产无预算，按"岗位数 + 列表页数"外推 **≈1,660 次** |
| 批 B Avature 4 + ORC 9 + 4 家修复 + 欧莱雅 | ORC 列表 `limit=200` + 详情按 40/批；Avature 西门子 36 页 + 215 详情、EA 26、贝恩/欧莱雅 2；耐克 124 条 | **≈400 次** |
| 外企发现 82 家（moka+10 / dayee+5 / job51+8 / beisen+1 / workday+58） | SOP 实测 **269 run / 872 请求**（`RECEIPT-foreign-discovery.md` §2R.7）；workday 行都带 `max_list_pages 8–24` 上限；moka 按 next-2 口径 ≈90 次/家 | **≈1,800–2,200 次** |
| tupu360（14 行）+ iCIMS（0 行） | 全段留档 | **0** |
| **新增合计** | | **≈3,900–4,300 次/轮** |

基线（948 家，`RECEIPT-collector-next-2.md` §G.4）：北森 ≈14,250 次、Moka ≈27,000 次、
飞书 ≈1,500 次 + 216 次浏览器启动；平台小计 ≈1–1.5h，每天必跑 74 家 ≈0.5–1h，
**整轮 1.5–3h、保守上界 3–4h**。新增边际：约 4,000 次 × ~0.5s/次 ≈ 33 分钟串行，
按同平台 3 路 / 全局 8 路摊薄后约 **+10–30 分钟**（Moka +10 家 ≈ +3 分钟，workday +58 家
≈ +3–5 分钟，Eightfold/Phenom 两组各 3 路 ≈ +5–8 分钟）。

**结论：典型 2–3.5h，保守上界 ≈4.5h < 18000s（5h）**，本轮不预期触发硬上限，因此
**不需要**为了赶工改调度参数。若真实首日超过 5h：`--max-run-seconds 18000` 会截断当天剩余
单元，`plan_chains()` 的公平兜底（next-2 §G.3，4 条单测）把"有 scope 从未尝试"的公司
**次日排最前**，因此**每家至少隔日更新**，不会饿死；判定看 `data/p1-last-attempt.json`
与 p1 status 的 `pending`。

**建议（不自行改调度参数）**：① 首日实测前不动任何参数，只看 `runs\20260919\receipt.json`
的 p1 起止与截断情况；② 若确认超 4.5h，候选杠杆是 `--workers 12`（next-2 实测内存
≈2.1GB、精灵 16GB 可承受，受同平台 3 路限制收益递减）或现成的 `--platform-rotation 2`
（轮转开关，默认关），两者都要站长拍板；③ tupu360 留档（−5 家）与 iCIMS 0 家已经是最省的
处置，不建议为了数字再动。

## 6. 单测

命令：`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest tests/ -q -rf -p no:randomly`

| 分支 | 结果 | 失败清单 |
|---|---|---|
| `feat/collector-next-3`（`2b123c2`，基线，`/private/tmp/baseline-next3`） | 4 failed, 497 passed, 55 skipped | ① `test_core.py::test_role_cohort_and_campaign_title_bases` ② `test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint` ③ `test_schema.py::test_enum_check_fails_when_data_drifts` ④ 偶发 `test_codes_kind.py::test_migration_is_safe_when_both_services_start_together` |
| `feat/collector-next-4`（合并后） | 4 failed, 639 passed, 55 skipped | 与基线**逐条相同**，无新增；偶发 `test_codes_kind` 本次也触发 |
| `feat/collector-next-4`（收据定稿前复跑） | **3 failed, 640 passed, 55 skipped** | flaky 未触发，剩下就是基线的 3 条既有失败 |

新增/更新测试（本分支）：`test_default_set_is_h_baseline_plus_i_j_a_c_and_discovery_additions`
（1056 + 同名归属）、`test_icims_and_tupu360_register_no_company`、
`test_parked_rows_are_inert_in_the_owning_adapter`（workday 三行出注册表、毕马威锁 76195）、
`test_every_config_driven_adapter_honours_the_enabled_false_park`（13 段统一契约）；
tupu360 单测改成"全段留档 + 显式启用才可采"（32 条全绿，fixture 自动启用并修掉
teardown 污染下一测试的隐患）。分支自带的 Eightfold/Phenom/Avature/ORC/iCIMS/发现/规范化
单测全部保留通过（639 = 497 + 142）。

## 7. 零网络探针

`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python pipeline-watch/collector-next4-probe.py`
（只 import、不发任何请求，exit 0）：

```json
{"hardcoded": 50, "k_baseline": 948, "default_total": 1056, "added_since_k": 108,
 "duplicates": 0, "module_count": 21,
 "same_name_owners": {"惠普": "...p1_platform_eightfold", "应用材料": "...p1_platform_eightfold",
                      "飞利浦": "...p1_platform_phenom", "强生": "...p1_platform_workday",
                      "毕马威": "...p1_platform_moka"},
 "tupu360_rows": 14, "tupu360_registers": 0, "tupu360_all_parked": true, "icims_registers": 0,
 "new_modules": {"...eightfold": {"in_platform_modules": true, "host_group": "eightfold", "registered": 5},
                 "...phenom": {"...": "phenom", "registered": 8},
                 "...avature": {"...": "avature", "registered": 4},
                 "...icims": {"...": "icims", "registered": 0},
                 "...orc": {"...": "oraclecloud", "registered": 9},
                 "...tupu360": {"...": "tupu360.com", "registered": 0}},
 "platform_modules_without_group": [], "rotation_default": 1, "default_select_full": true,
 "probe_day_total": 1056, "config_rows": 1019,
 "names_normalization_would_rewrite": [],
 "normalization_table": {"aliases": 19, "prefixes": 3, "brands": 1080, "platform_names": 1020}}
PROBE OK
```

同时断言：块顺序末尾为 `eightfold → phenom → avature → orc`（iCIMS/tupu360 注册 0 家所以无块）、
每个平台模块都有 host 组、6 个新模块都不轮转、同名归属与留档行正确、
配置公司名规范化 0 改名、默认不轮转时全选 1056 家。

## 8. 累积部署件 `pipeline-watch/deploy-artifacts/20260919g/`

26 个运行时文件（**不含**测试与夹具）+ `SHA256SUMS.txt` + `PROD-BACKUP-MANIFEST.txt` +
`DEPLOY-NOTES.md`：

| 类别 | 文件 |
|---|---|
| 覆盖（9，内容与 k 不同） | `p1_pipeline.py`、`p1_platform_companies.json`、`p1_feishu_public.py`、`p1_platform_beisen.py`、`p1_platform_moka.py`、`p1_platform_successfactors.py`、`p1_platform_workday.py`、`p1_foreign_01.py`、`p1_platform_51job.py` |
| 新增（8） | `p1_platform_eightfold.py`、`p1_platform_phenom.py`、`p1_platform_avature.py`、`p1_platform_icims.py`、`p1_platform_orc.py`、`p1_platform_tupu360.py`、`company_names.py`（→`qiuzhao\company_names.py`）、`company_aliases.json`（→`qiuzhao\data\`） |
| 覆盖（1，不在 k 清单） | `normalize.py`（→`qiuzhao\`，normalize 阶段接入三层规范化，见 CAVEAT） |
| 无需覆盖（8，与 k 逐字节一致） | `windows_collector.py`（`9eaf97cc…`，与 k **完全相同**，本次未改一行）、`guopin.py`、`alibaba_headless.py`、`p1_banks_01.py`、`tencent_music.py`、`bytedance.py`、`p1_bytedance_public.py`、`p1_midea_public.py` |

校验（本地实测）：`shasum -a 256 -c SHA256SUMS.txt` → **26/26 OK**；26 个文件与分支源码
（`qiuzhao/collector/*`、`deploy/windows_collector.py`、`qiuzhao/company_names.py`、
`qiuzhao/normalize.py`、`qiuzhao/data/company_aliases.json`）逐个 `cmp` → **全部一致**；
`py_compile` 24 个 `.py` 全部通过、`p1_platform_companies.json` 可解析；
**模拟精灵的 import 闭包校验**：用 `git archive feat/collector-next-3 qiuzhao deploy` 铺出
"现役树"+ g 覆盖到目标路径，然后 import 24 个模块 →
`IMPORT_OK 1056 1056`、`CLOSURE_OK 24`、`TUPU_ICIMS_REGISTERED {} {}`、`WORKDAY_PARKED []`、
`KPMG kpmg/76195 329`、`REGISTRY_SPOT {惠普/应用材料→eightfold, 飞利浦→phenom, 强生→workday,
毕马威→moka, 微软→eightfold}`、`CANON ('腾讯','brand')`。

`PROD-BACKUP-MANIFEST.txt` 以 **20260918k 为前提**（k 部署时 17/17 校验通过、之后无 drift 记录），
逐文件列出部署前应有 sha256：9 个覆盖文件 = k 的 SHA256SUMS 值、8 个新增文件 = `ABSENT`、
`qiuzhao\normalize.py` = **VERIFY**（不在 k 清单里，给候选值
`a53adaf3…`（`850af325` 版），要求部署时先用 `Get-FileHash` 记录真值再覆盖）。
`DEPLOY-NOTES.md` 含 **Playwright 依赖说明**：Eightfold/Phenom 主路径是纯 `requests`
（站点自身公开 JSON 接口），Playwright 只在 401/403/429 时兜底，39/39 次实测全走直连；
精灵 `chromium-1187` 在 k 部署时已验证在位，本次不需要重装。

## 9. 部署步骤（沿用 `TASK-collector-next-3-deploy.md` 流程，清单按 g 更新）

1. **等空闲**：`runs\<今天>\receipt.json` 有 `completed_at`；无 `windows_collector.py` /
   `p1_pipeline` / `lark_sync` 的 python 进程；`data\lark-sync\status.json` 不是 `running`。
   正在跑每 5 分钟看一次、最多等 3 小时，超时不部署。
2. **前置哈希核对**：按 `PROD-BACKUP-MANIFEST.txt` 的唯一前提逐文件核对 26 个目标路径；
   9 个覆盖文件必须等于 k 值、8 个新增必须 ABSENT、`normalize.py` 按 CAVEAT 记录真值。
   任何不一致就停（drift）。
3. **备份**：`robocopy C:\mcp-suite-collector\deploy C:\mcp-suite-backup-<YYYYMMDD-HHmm>\deploy /E /R:2 /W:5`
   + 同样备份 `qiuzhao`（退出码 ≤7 成功；**不要**全目录 robocopy）。
4. **Playwright**：`Test-Path "$env:LOCALAPPDATA\ms-playwright"` 确认 `chromium-1187`，缺才装；
   失败不阻塞，但要标注"阿里系/飞书首日 blocked"。
5. **传输并校验**：26 个文件传到 `C:\mcp-suite-deploy-20260919g\`，逐字节对 `SHA256SUMS.txt`。
6. **覆盖 18 个目标路径**（10 覆盖 = 9 个 k 文件 + `normalize.py`；8 新增 = 6 个适配器 +
   `company_names.py` + `qiuzhao\data\company_aliases.json`；
   8 个无需覆盖的文件比对哈希后跳过），覆盖后复算 sha256、`py_compile` 全部 `.py`、
   正式 venv（cwd=`C:\mcp-suite-collector`）跑
   `python -c "import deploy.windows_collector, qiuzhao.collector.p1_pipeline as P; print(len(P.DEFAULT_COMPANIES), len(P.REGISTRY))"`
   → 预期 **`1056 1056`**；抽查 REGISTRY 同 §8。
7. **import 闭包**：逐个 import `qiuzhao.company_names`、`qiuzhao.normalize`、6 个新适配器与 9 个
   覆盖模块，断言 `canonical_of('腾讯')==('腾讯','brand')`、tupu360/iCIMS 注册 0 家。
8. **不手动补跑**：以次日 06:10 的正常运行为首次实测。
9. **收尾**：部署记录（时间、备份路径、覆盖前后哈希、import 输出、Playwright 结果）追加到
   本收据"部署记录"节；在 worktree 分支上 commit，不 push。
10. **回滚**：按 manifest 恢复 10 个覆盖文件（9 个 k 文件 + `normalize.py`）、删除 8 个新增文件
    （`company_aliases.json`、`company_names.py`、6 个新适配器），回滚后逐字节校验 = 前提值。

## 10. 次日观察项（相对 k 的新增部分）

- **集合规模**：p1 status 公司数应为 **1056**；看到 948/1061 说明覆盖不完整或配置段丢失。
- **同名归属**：`惠普`/`应用材料` 应走 eightfold、`飞利浦` 走 phenom、`强生` 走 workday、
  `毕马威` 走 moka `kpmg/76195`；若 `强生` 三 scope 全 0 条 → 按 §2 的红字升级。
- **tupu360 / iCIMS 零请求**：首日这两段不应产生任何采集请求（留档 + robots 闸门）；
  若出现 `p1_platform_tupu360` 单元，说明覆盖了旧的 JSON。
- **新平台首日**：`eightfold`/`phenom`/`avature`/`oraclecloud` 四个 gate 组的
  `coverage.status` 与 `mode`（`direct` vs `headless`）；出现 401/403/429 才可能触发
  Playwright 兜底；`avature` 的翻页参数按门户自带的 offset 走，注意 `pagination_exhausted`。
- **发现批的 58 家 workday**：`max_list_pages 8–24` 上限下的 `partial` 属预期；重点看
  `social` 出条数与 `coverage.complete`。
- **公司名规范化**：`normalize` 步骤耗时应仍为 ~30s 级（k 时代全库干跑 31.37s / 峰值 2.2GB）；
  `canonical_company/company/company_name` 三字段空值率应从 27% 降到 ~0；
  `data\` 出现异常增长或 normalize 退出码非 0 要立刻看 `recursive` 段。
- 其余沿用 k 的观察项：`guopin.discovered`（约 14）、`fallback_used=false`、
  `data\p1-retry-queue.json`、各平台 blocked 比例、p1 起止时间与 `status.pending`、
  飞书同步 `changed` 量级。

## 11. 回滚

- 触发条件：§9 第 2/5/6/7 步任一校验失败，或首日实测出现整段回滚（p1 `step_changes` 异常）。
- 口径：恢复 10 个覆盖文件 + 删除 8 个新增文件（含 `company_aliases.json`）；
  `normalize.py` 是**还原**不是删除；回滚依据在仓库内（manifest + 备份目录）。
- 回滚**同样要站长同意**（沿用交接文档第 1 节铁律）。

## 12. 遗留

1. **强生**：workday `jj/wd5/JJ` 从未在本轮实测过；tupu360 有 18+4+322 条实测数据但按
   robots 全段留档。首日若 workday 三 scope 全 0，需要在待办里升级并请站长在
   "启用 tupu360(robots 例外)"与"强生暂无可采来源"之间拍板。
2. **tupu360 整段待站长决策**：6 家 careersite 租户（IQVIA 艾昆纬/礼来/舍弗勒/宝马/茵梦达/强生）
   都有实测数据与入口 URL，改 `enabled:true` 即可启用；平台 robots.txt 是全站 Disallow。
3. **`enabled:false` 契约只在 12 个配置驱动适配器 + tupu360 生效**：`beisen/moka/feishu/
   workday/successfactors/dayee/job51/eightfold/phenom/avature/icims/orc/tupu360` 已统一，
   将来新加适配器要照 tupu360 的 docstring 加同样的跳过逻辑（守护单测会抓）。
4. **`normalize.py` 的精灵现役哈希未知**（不在 k 清单）：部署前必须记录真值（manifest CAVEAT）。
5. **`qiuzhao\data\` 目录**：精灵上若不存在需先建目录再放 `company_aliases.json`。
6. **服务器侧未改**：`/opt/mcp-suite/` 的 `v4_fields` 靠 `canonical_company or …` 已能返回规范名；
   若要同步 `company_names.py`/别名表到服务器，须站长单独确认。
7. **公司名规范化的两个业务口径**仍待 Max 定：796 组"集团 vs 子公司"两层不一致需要归属表；
   `recruitment_unit` 是否升级为用人单位层（沿用 company-normalize 收据 §9）。
8. **毕马威第二个租户**已从"靠 dict 顺序"改成显式留档；若 `kpmg/76195` 停更，把两行的
   `enabled` 对调即可。
9. **iCIMS 8 家 robots 全站 Disallow**：没有可采租户，本期 0 家是预期，不是失败。
10. **本任务未部署**：1056 家的真实耗时、5h 上限是否触发、新平台首日产出，都要等上线后
    次日 06:10 才能确认。

## 13. 边界

本收据只证明：合并完成、冲突处置有据、默认集合 1056、单测无新增失败、探针通过、部署件哈希
自洽且可导入。**不等于**业务效果已验证（新平台首日产出、耗时、飞书同步量级都要等实测）。
硬约束遵守：未部署、未 SSH、未碰阿里云、未调飞书、未读取/打印令牌、未登录、**未发任何外部
请求**（探针与单测全部本地）、未 push、未合并 main、**未终止任何进程**、未使用 `git stash`。
