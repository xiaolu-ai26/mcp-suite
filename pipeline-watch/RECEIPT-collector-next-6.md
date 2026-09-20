# RECEIPT: collector-next-6 —— 接回两个漏掉的分支 + 全适配器「分页谎报」审计

分支 `feat/collector-next-6`(worktree `/Users/maxzhl/Projects/mcp-suite-merge6`,起点 `feat/collector-next-5` f32cc9b3 = 精灵现役 20260920a)
提交:`c2b60fb3`(Moka 续采)· `b067b977`(tupu360 配置 + 分页修复)· `f97d0a64`(分页审计修复)· 本收据提交
**未部署**:未 SSH 精灵、未碰阿里云、未写库、未写飞书、未 push、未合并 main。

---

## 0. 一句话结论

两个漏掉的分支已按「只取该取的」接回:**Moka 的详情缓存复用 + 预算只算真实网络请求**整段并入(含其 32 行单测),
**tupu360 全站**只取**分页修复 + 单测夹具 + 60 家配置(全部 `enabled:false`)**,xlsx(4.5 MB)/csv(18 MB)与
`20260919g` 部署件副本留在 `feat/tupu360-fullsite` 原处。全适配器分页审计找到并修掉 **6 处「被截断/异常却仍声称已翻完」**
的真缺陷 + 5 处同类边界,每条都有回归单测;**默认公司集合保持 1069 家不变**,`pytest tests/` 失败清单与
`feat/collector-next-5` 基线逐条一致(3 条既有失败,新增失败 0,新增通过 17 条),零网络探针 `PROBE OK`。
部署件 `pipeline-watch/deploy-artifacts/20260920c/` 13 个运行时文件(全部覆盖),`shasum -c` 13/13 OK 且与分支源码逐字节一致。

---

## 1. 两个合并

### 1.1 `95a88ad3`(feat/platform-adapters 的后续提交)—— Moka 续采,整段并入

`git cherry-pick 95a88ad3`,唯一冲突是 `tests/test_p1_platform_moka.py` 的**尾部追加冲突**
(collector-next-5 之后又加了雀巢/安永等配置断言),解法是两边都留。并入内容:

| 文件 | 变化 | 说明 |
|---|---|---|
| `qiuzhao/collector/p1_platform_moka.py` | +29/−1 | 新增 `_cached_detail(output_dir, ident)`:复用上一轮已落盘的 `detail-<id>.json`,**不花预算**;`_detail()` 先查本地缓存,并在共享详情缓存命中时**退还** `budget['used'] -= 1` → 「预算 = 真实网络请求数」 |
| `tests/test_p1_platform_moka.py` | +32 | `test_second_bounded_pass_resumes_from_saved_details`:第一轮 4 次预算拿 1 条详情并 `request_budget_exhausted=True`;第二轮从落盘详情续采,**一次都不重取**(`calls == ['moka-campus-1', 'moka-paused-1']`),`used == 4` |
| `pipeline-watch/platform-adapters-backfill.py` | +71 | 该分支的多轮有界续采运行器(可复现) |
| `pipeline-watch/RECEIPT-platform-adapters.md` | +84/−33 | 该分支收据更新(10 家全部 success/complete:18 轮、326 请求、单轮 ≤20) |

**行为一致性验证**:合并后 `p1_platform_moka.py` 与 `feat/platform-adapters` 的差异**只剩 collector-next-5 时期
已有的行**(`DEFAULT_REQUEST_BUDGET = None`、`enabled:false` 跳过、docstring),即 95a88ad3 的补丁**逐字**落在了
collector-next-5 的版本上;`tests/test_p1_platform_moka.py` 9 条全绿。
生产默认仍**无预算上限**(`DEFAULT_REQUEST_BUDGET = None`),20 次/租户只是离线验证的礼貌限制 —— 这一点在
95a88ad3 的 docstring 里已写明。

### 1.2 `c0d552f2`(feat/tupu360-fullsite)—— 只取该取的

| 取 | 内容 |
|---|---|
| ✅ | `qiuzhao/collector/p1_platform_tupu360.py` +42/−7:分页硬截断修复(`PAGE_CAP = 120` 仅安全阀、按站点自报页数翻页、触顶记 `page_cap_hit` 且不置 `pagination_exhausted`;`_fetch_direct_api` 补 `page_cap_hit`) |
| ✅ | `tests/test_p1_platform_tupu360.py` +153/−8(含 3 条 56 页真实夹具分页深度单测)与 `tests/fixtures/tupu360/pharmaron-bj-*.html` 3 个夹具(共 3096 行) |
| ✅ | `qiuzhao/collector/p1_platform_companies.json` tupu360 段 14 → 68 行(+325/−1),**但全部 `enabled:false`**(改造见 §3) |
| ✅ | `pipeline-watch/RECEIPT-tupu360-fullsite.md`(交接说明书:robots.txt 原文、站长决定、180 单元/5523 条实测)、`pipeline-watch/tupu360-fullsite-run.py`(运行器)、`pipeline-watch/tupu360-fullsite/inputs/*.json` 4 个小文件(共 ~100 KB 的发现输入) |
| ❌ **不取** | `tupu360-全站岗位-20260919.xlsx`(4.5 MB)、`tupu360-全站岗位-20260919.csv`(18 MB)、`deploy-artifacts/20260919g/` 整份副本(已被 20260920c 取代)。它们仍在分支 `feat/tupu360-fullsite` 原处:`pipeline-watch/tupu360-fullsite/tupu360-全站岗位-20260919.{xlsx,csv}`、`pipeline-watch/deploy-artifacts/20260919g/` |

`tests/test_collector_next_integration.py` 的冲突取 collector-next-5 一侧(家数注释按「tupu360 全关」更新),
`EXPECTED_DEFAULT_COMPANIES` 保持 **1069**(该分支的 1005 是「60 家全开」的世界,与本分支口径不同)。

---

## 2. 全适配器「分页谎报」审计表(核心)

审计口径三条:**①安全上限只能当安全阀,绝不能当目标页数;②触顶必须显式标记,绝不在截断时报 `pagination_exhausted`;
③异常/字段缺失不得被当成「空结果」或「已翻完」。**
`p1_pipeline.validate_result` 的事实约束:`complete` 需要 `status=success` + `detail_complete` + `errors` 为空 +
证据文件齐备 + (`expected_total == 收录数`,或 `expected_total is None` 时 `pagination_exhausted is True`
且 `unique_source_ids == 收录数` 且有 `last_page_evidence`)。

| # | 文件 / 函数 | 判定 | 证据(片段 + 触发条件) | 已修 |
|---|---|---|---|---|
| 1 | `p1_platform_successfactors.py` `collect()` unify 回退 | **有缺陷** | classic 分支第一页空且 `raw_rows==0` 时 `list_complete = True`(:495),随后进 unify 回退;unify 循环 `while page_number < max_pages`(:529,`max_list_pages` 默认 20)。**触发**:unify 端点 (>20 页 / 预算耗尽) 提前 break 时 `list_complete` 仍是 classic 那份 True → `pagination_exhausted=True`,而 `expected_total = len(selected)-filtered` 自洽 → 可判 `complete` | ✅ 进 unify 时 `list_complete = False`(:527),截断记 `page_cap_hit` + `last_page_evidence='unify pages=N of at most M;total=…;truncated=true'`(:556-566)。单测 `test_unify_fallback_capped_scan_never_claims_exhaustion` / 对照 `…_that_reads_the_site_total_is_still_complete` |
| 2 | `p1_platform_avature.py` `collect()` 列表循环 | **有缺陷** | `if not page_cards or not new_cards: list_complete = True`(原 :618)。**触发**:站点 legend 已报 `1-10 of 36`,第 2 页返回降级空壳(或分页重复第 1 页)时,直接判「已翻完」并截断在 10 条 | ✅ 用站点自报 legend 做交叉校验:已见数 < legend 总数时记 `page_cap_hit` + `list_truncated` + `last_page_evidence=…;legend_total=36;truncated=true`,**不置** `list_complete`(:618-643);`search_total` 不再被后续空页覆盖成 None。3 条单测 |
| 3 | `p1_netease_public.py` `fetch_campus_api_project` / `fetch_leihuo_project` | **有缺陷** | `if not total:`(原 :425、:546)同时匹配 `total == 0` **和** `total is None`。**触发**:接口返回了行但没有 `total`/`count_number` 字段时,走 `notes.append('currently has 0 open positions')` + `exhausted=True` + `return []` → **把刚读到的行全部丢掉并声称「确认无在招」** | ✅ 改成只认 `total == 0`;`total is None` 保留全部已读行、记 note/error、`exhausted` 保持 False(:425-435、:552-562)。3 条单测(含 `test_confirmed_zero_still_completes` 保护真 0) |
| 4 | `alibaba_headless.py` `_collect_entity()` 批次分页 | **有缺陷** | `total = int(content.get('totalCount') or 0)`(原 :545)把**缺失字段**压成目标 `0`,随后 `page * PAGE_SIZE >= batch_total` 在第一页就成立。**触发**:`totalCount` 缺失或为 0 且有行 → 第 1 页后 break,`pagination_exhausted` 仍为 True(初值) | ✅ 缺失即 `None`(不再当终止条件,`batch_total and …`);新增 `totals_reported`,全部批次都没报总数时 `expected_total = None` → 永不可能 `complete`(:516、:551-557、:584-588)。1 条单测断言仍请求 page 2 |
| 5 | `p1_platform_workday.py` `collect()` | **同类边界(加固)** | `if total is not None and offset >= int(total or 0)`(原 :400):站点自报 `total=0` 却有行时,第一页即判 `list_complete=True` | ✅ 改为「只有正数 total 才能终止」(:404)。单测见 #6 |
| 6 | `p1_platform_orc.py` `collect()` | **同类边界(加固)** | `coverage['site_total_china'] is not None and offset >= …`(原 :428)同型 | ✅ `if coverage.get('site_total_china') and offset >= int(...)`(:430) |
| 7 | `p1_platform_phenom.py` `collect()` | **同类边界(加固)** | `if total is not None and offset >= int(total)`(原 :624)同型;`fresh == 0`(重复页)本身已正确拒绝翻完 | ✅ `if total and offset >= int(total)`(:626)。单测 `test_zero_total_hits_next_to_real_rows_never_ends_the_scan` |
| 8 | `p1_platform_eightfold.py` `collect()` | **同类边界(加固)** | `if total is not None and start >= int(total)`(原 :606)同型 | ✅ `if total and start >= int(total)`(:608) |
| 9 | `p1_foreign_01.py`(大易) `collect()` | **同类边界(加固)** | `if isinstance(total_page, int) and page >= total_page`(原 :303):`totalPage=0` 且有行时第一页即判 `list_complete=True` | ✅ 加 `total_page > 0`(:305)。单测 `test_zero_total_page_next_to_real_rows_never_ends_the_scan` |
| 10 | `p1_pipeline.py` `validate_result()` | **有缺陷(纵深防御缺口)** | 原实现只看 `pagination_exhausted` 真值,不认「适配器自述触顶」。**触发**:任何适配器同时写 `page_cap_hit=True` 与 `complete=True` 时会被放行(把 `expected_total` 设成截断后的条数即可绕开 `expected_total` 一致性检查) | ✅ 新增闸门:`if complete and coverage.get('page_cap_hit'): raise ValueError('a scan that hit its page safety cap cannot claim complete coverage')`(:562-565),`collect_process` 把它变成 `blocked('adapter contract rejected: …')`(不删旧数据)。单测 `test_page_cap_hit_can_never_validate_as_complete` |
| 11 | `p1_platform_tupu360.py` `_fetch_next_pages` / `_fetch_direct_api` / `collect` | **无缺陷(本次随包接入的修复)** | 原 `page_cap=40` 当目标页数把 828 条截成 600;修复后 `PAGE_CAP=120` 仅安全阀、目标 = `max(共N页, ceil(共N个职位/page_size))`、触顶 `page_cap_hit=True` 且 `pagination_exhausted=False` + 记 error(:637-680、:942-950) | 已随 `c0d552f2` 并入(3 条深度单测) |
| 12 | `p1_meituan_public.py` `collect()` | **无缺陷** | `for page_no in range(1, 1000000)` 是事实上无上限(:201),三条置 True 的路径都在站点自报 `totalPage` / `seen==totalCount` 之后(:340、:345、:359);兜底 `page_no >= expected_total`(:363)只 break **不置** exhausted;异常走 `errors`(:376)且 `complete` 要求 `not errors`(:385-393) | — |
| 13 | `p1_sources_01_10.py`(PDD/小米/京东/vivo·BYD/HONOR/华为/快手/小红书/OPPO/Moka 旧路径) | **无缺陷** | 所有 `for page in range(1,10001)` 循环后都有 `for…else: raise` 或 `if len(seen)!=total: raise/append error`(如 :210、:283、:355、:447、:506、:574、:611),触顶必然变成错误;`collect_moka_sites` 的 `terminal` 由「空页 + `len(listed)==total`」共同证明(:196-210),`pagination_exhausted=True` 只在全程无异常时执行(:238) | — |
| 14 | `p1_sources_11_20.py`(米哈游/蚂蚁/安克/滴滴/联想/海康/携程/…) | **无缺陷** | 每个分页循环都以 `else:raise ValueError('<x> pagination limit reached')` 收尾(:79、:135、:166、:415、:516、:534、:578),触顶即报错;`_lenovo` 另有 `if len(visited)>1000: raise`(:459) | — |
| 15 | `p1_sources_31_40.py`(北森/汇川/理想/TP-LINK/蔚来/…) | **无缺陷** | 每个循环后 `if len(seen)!=total: raise ValueError('<x> incomplete list')`(:46、:97、:144、:252、:311);TP-LINK 实习分支的无分页 `internshipdata` 有原文依据 | — |
| 16 | `p1_sources_41_50.py`(小米/京东) | **无缺陷** | 分页后 `if len(seen)!=total: raise`(:41、:81、:110、:134);小米还额外把「海外源未接入」写成 error,使其永远 `partial` | — |
| 17 | `p1_banks_01.py`(中信/招商/交行) | **无缺陷** | 三个 `while page <= 200` 的三种出口:空页置 True、`len(jobs) >= expected` 置 True、**触顶不置**(保持 False → partial)。中信的 `pageCount` 用落盘夹具证伪了「页数 vs 条数」歧义:`citic_campus_page1.json` 15 行 / `page2` 5 行,两页 `pageCount` 恒为 20、`tableData.totalCount` 分别是 15/5 → `pageCount` 是**记录总数 20**,不是页数 | — |
| 18 | `p1_bytedance_public.py` `collect()` | **无缺陷(正面样板)** | `API_CAP=10000` 显式当上限:起始即 `cap_limited = count >= API_CAP`(:265),`offset >= API_CAP` 只 break(:318),`complete` 硬要求 `not cap_limited and pagination_exhausted`(:328-334),并把 `api_cap_limited`/`api_cap_note` 写进 coverage | — |
| 19 | `p1_platform_51job.py` `collect()` | **无缺陷(单页源,假设已记录)** | 微站是**单张公告页**,夹具 `51job_pepsico.html` 里 0 个分页标记(无「下一页/Next/page=」);`pagination_exhausted=True` 与 `expected_total=len(seen)` 是同一事实的两种写法。**残留假设**:若该微站将来改成多页,本适配器不会发现 | — |
| 20 | `p1_platform_beisen.py` `collect()` | **无缺陷(残留:无分页上限)** | `while True`(:262)没有页数上限,只靠「空页 + `len(seen)==total`」+ 重复 GUID 报错终止;空页置 True(:267)。不会谎报,但站点若永不返回空页且不断给新行会无限翻页(**现状风险,未改**:北森在册 481 家,改终止条件风险大于收益) | — |
| 21 | `p1_platform_moka.py` `collect()` | **无缺陷(残留:同 #20)** | `while True` 同上;空页且 `total` 已知时要求 `len(listed)==total` 才 `terminal=True`(:293-300),否则 `list_complete=False` + `raise`(:315-317) | — |
| 22 | `p1_platform_icims.py` `collect()` | **无缺陷(证据不足以判缺陷,残留风险已记)** | 与 #2 同型的 `if not page_cards or not new_cards: list_complete = True`(:449),但没有 legend/总数可交叉校验,且**该平台 0 家在册、robots 全站 `Disallow: /`、不在每日链上**;录到的夹具只有一页,**无任何证据**显示真实终止态不是「空页」。为不引入无依据的行为变更,本轮不改,风险写在这里 | — |
| 23 | `p1_platform_workday.py`/`orc`/`avature`/`successfactors`/`eightfold`/`phenom` 的 `max_list_pages`/`max_page_loads` 安全阀 | **无缺陷** | 触顶一律 `list_complete`/`listing_exhausted` 保持 False(如 workday :377、orc :406、avature :594、icims :440),即 `pagination_exhausted=False` → `partial` | — |

**汇总**:真缺陷 6 处(#1、#2、#3、#4、#10 + 记在 #5-#9 的同类边界 5 处,合计 11 处改动),已在 `f97d0a64` 修完并各带回归单测;
判定无缺陷 12 处(其中 3 处记了残留风险:#19 单页假设、#20/#21 无页数上限、#22 无法判定的同型模式)。

---

## 3. tupu360 60 家「全关」的理由与启用方法

- **为什么全关**:tupu360(图谱天下)的 `robots.txt` 是**平台级** `User-agent: * / Disallow: /`。
  本项目对 robots 明禁的来源(猎聘/BOSS/智联校园/iCIMS 的 8 家租户)一律不采集,所以 20260919g
  虽然实测读到 60 家 / 180 单元 / 5523 条真实岗位,本条分支**只接入配置与代码,不接入启用状态**。
  是否启用由站长决定(前一次同样口径见 `feat/foreign-ats-c` 的收据)。
- **配置形态**:`p1_platform_companies.json` 的 `tupu360` 段 **68 行** = 60 家 careersite 租户
  (`note` 含实测条数,如康龙化成 social 828 条)+ 8 行「匿名侧拿不到」的调查记录(6 家微信专属 + 德昌电机 + 太太乐);
  **68 行全部 `enabled:false`** 且每行都有 `blocked_reason`;
  `_README` 写明 robots 决定、60 家来源、以及「启用只需把该行 `enabled` 改成 `true`」。
- **要启用某一家,只需要改一个字段**:把该行(或整段)`"enabled": false` 改成 `true`。
  适配器在 import 时读这个文件(`_read_platform()`),`p1_pipeline` 通过 `merged_registry()` 合并该段,
  下一个 06:10 周期就会把它纳入采集;**不需要改代码、不需要改调度、不需要重新生成部署件**。
  例:把 `"pharmaron-bj": { "enabled": false, … }` 改成 `true` 后,康龙化成(北京)新药技术股份有限公司
  即进入 REGISTRY(单测 `test_fullsite_tenants_are_public_careersite_hosts_and_stay_parked` 末尾就演示了这一步:
  `entry_override('pharmaron-bj')` → `merged_registry() == {'康龙化成（北京）新药技术股份有限公司': tupu360}`)。
- 同名的 3 家按既有约定用 `setdefault` 不顶替:**强生**留 Workday、**斯堪尼亚**留 Moka、**药明康德**留 `p1_sources_41_50` 硬编码槽位。
- 全站数据留在原分支:`pipeline-watch/tupu360-fullsite/tupu360-全站岗位-20260919.xlsx`(5 sheet)、同名 `.csv`(18 MB)、
  `pipeline-watch/RECEIPT-tupu360-fullsite.md`(robots.txt 原文 + 站长 2026-09-19 决定),均在 `feat/tupu360-fullsite` 上。

---

## 4. 验证

### 4.1 单测(基线对比)

| 树 | 结果 | 失败清单 |
|---|---|---|
| `feat/collector-next-5` f32cc9b3(基线) | **3 failed / 656 passed / 55 skipped** | `test_core::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema::test_enum_check_fails_when_data_drifts` |
| `feat/collector-next-6`(本分支) | **3 failed / 673 passed / 55 skipped** | 与基线**逐条相同**;新增通过 = +17(全是本次新增的回归单测) |

`test_codes_kind`(既有偶发)本轮两边都通过。命令:
`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python -m pytest tests/ -q`(merge6 与 mcp-suite-next5 各跑一次)。

新增单测恰好 17 条 = 随合并进来的 5 条(`test_p1_platform_moka.py` +1 = 95a88ad3 的续采回归;
`test_p1_platform_tupu360.py` +4 = c0d552f2 的 3 条 56 页分页深度单测 + 本分支「60 家全关」断言 1 条)
+ 本次审计修复的 12 条(`test_p1_platform_successfactors.py` +2、`test_p1_platform_avature.py` +3、
`test_p1_netease_public.py` +3、`test_p1_alibaba_tencent.py` +1、`test_p1_platform_phenom.py` +1、
`test_p1_foreign_01.py` +1、`test_p1_pipeline.py` +1)。逐文件 `def test_` 计数差 = 17,与 673−656 相符。

### 4.2 零网络探针

`/Users/maxzhl/Projects/mcp-suite/.venv/bin/python pipeline-watch/collector-next6-probe.py` → **`PROBE OK`**
(不发任何请求,只读源码/配置与 import `p1_pipeline`)。断言:默认 1069 / 无重名 / REGISTRY==DEFAULT / 21 个模块 /
tupu360 68 行(60 careersite、0 启用、无缺 `blocked_reason`、REGISTRY 0 家)/ iCIMS 0 家 /
Moka 续采标记、tupu360 分页标记、5 个审计修复标记、5 处正数 total 守卫、11 个「已判无缺陷」适配器仍在位 /
`PLATFORM_ROTATION_DEFAULT == 1`(不轮转)。

### 4.3 默认公司集合

`DEFAULT_COMPANIES = 1069`、`REGISTRY = 1069`、模块 21 个 —— 与精灵现役 20260920a **完全一致**
(tupu360 全关不进 REGISTRY;Moka 的续采不改变在册公司)。本次三个提交**没有一家公司增删**:
`git diff --numstat f32cc9b3 HEAD -- qiuzhao/collector/p1_platform_companies.json` = +325/−1,唯一删除行是 `_README` 的重写。

### 4.4 未发外部请求

审计全程靠读代码 + 已有夹具(`tests/fixtures/**`,均为历史录制);新增单测用 `FakeSession`/`FakeAliTransport`/`patch.object`
把请求缝全部替换,**没有一次真实网络调用**;`feat/tupu360-fullsite` 的 5772 次请求是 2026-09-19 那次运行留下的,
本分支**没有重跑**。

---

## 5. 部署件 `pipeline-watch/deploy-artifacts/20260920c/`

- 13 个运行时文件,**全部是覆盖**(相对精灵现役 20260920a),不新增、不删除;`shasum -a 256 -c SHA256SUMS.txt` **13/13 OK**,
  且与 `qiuzhao/collector/` 源码**逐字节一致**(13/13 diff 为空)。
- `PROD-BACKUP-MANIFEST.txt`:前提哈希**逐条**取自 `git show feat/collector-next-5:pipeline-watch/deploy-artifacts/20260920a/SHA256SUMS.txt`
  (未照抄),`alibaba_headless.py` 取 20260918k 的值(它在 20260920a 里是 VERIFY ONLY);
  两段 VERIFY ONLY 共 14 个文件必须保持不动;**唯一 CAVEAT**:`p1_netease_public.py` 从未进过任何部署件,
  精灵上的真实哈希无记录 → 必须先 `Get-FileHash` 记录再覆盖。
- `DEPLOY-NOTES.md`:13 文件清单 + 前提/内容摘要 + 部署后验证步骤 + 回滚说明(`p1_pipeline.py` 必须能回到 `093b237e…`,
  20260919k 的 Windows 发布锁要活过回滚)。
- 本次**没有**改 `deploy/windows_collector.py`、`run.py`、`p1_platform_beisen.py`、`p1_platform_51job.py`、
  `p1_platform_icims.py`、`p1_feishu_public.py`、`normalize.py`、`company_names.py`、`company_aliases.json`。

---

## 6. 遗留 / 待站长决定

1. **tupu360 是否启用**(robots 平台级 `Disallow: /`):启用方法见 §3;60 家的实测条数写在各自 `note` 里。
2. **强生由 tupu360 还是 Workday 采**:本轮维持 Workday(同名 `setdefault` 不顶替);tupu360 侧那条有 322 条社招实数。
3. **`p1_platform_beisen.py` / `p1_platform_moka.py` 的列表循环没有页数上限**(§2 #20/#21):
   不会谎报,但站点异常时可能长时间翻页;北森在册 481 家,加硬上限属于行为变更,留给下一次单独评估。
4. **`p1_platform_icims.py` 的同型模式**(§2 #22):该平台 0 家、robots 全禁、不在链上,且无夹具能证伪「空页=终止」,
   本轮只记录风险;若将来要接入任何 iCIMS 租户,先用真实页面确认终止态再决定。
5. **`p1_platform_51job.py` 的单页假设**(§2 #19):微站若改成多页,当前实现不会发现。
6. 部署件 20260920c **未部署**;是否上线等站长明确指示。
