# 收据：阿里 5 家子公司 + 腾讯音乐（专用适配器）——分支/单测/只读实测

**分支**：`feat/ali-tencent-gap`（基于 `feat/banks-batch1` `fc18bd8`）
**worktree**：`/Volumes/臭垃圾桶/生财MCP/_worktrees/ali-tencent`
**性质**：只读采集适配器开发 + 离线单测 + 只读实测。**未部署、未 SSH、未碰阿里云服务器、未调飞书、未登录、未 push/合并、未写线上库、未终止任何进程。**

---

## 0. 结论

1. **阿里 477 条的根因已定位并修复**：旧 `alibaba_headless.py` 指向 `talent.alibaba.com/campus/position-list` 且硬编码 `categoryType='freshman'` + `corpCode=''`；该入口现已改版，2026-09-18 实测返回 `totalCount=0`。当前官方集团批次在 `campus-talent.alibaba.com`（`batchId=100000760001`，477 条）。
2. **阿里系 5 家子公司全部接入**，且都能拿到**当前 27 届**岗位：集团平台 `searchCondition/list` 的 `customDept` 业务集团过滤器按叶子部门码（`customDeptCode`）筛选，实测 淘天 71 / 阿里云 128 / 高德 12 / 淘宝闪购(饿了么) 16；菜鸟不在集团 `customDept` 列表内，走其独立站点 `talent.cainiao.com`（当前官方公开 0 个岗位，已核实为空）。
3. **腾讯音乐新专用适配器跑通**：`join.tencentmusic.com` 公开 JSON 接口，campus（应届生 33 + 技术大咖 4）=37 条，均通过 `validate_result` 且 `complete=true`。
4. **单测**：新增 17 个离线夹具测试全绿；`pytest tests/` 失败清单与 `feat/banks-batch1` 基线**完全一致**（同样 3 个既存失败，405 passed / 55 skipped）。
5. **7 个实体 `campus` 只读实测全部 `status=success, complete=true`**，预算远低于每实体 40 次上限。

---

## 1. 各实体入口与参数（2026-09-18 只读实测）

| 实体（company 注册名） | 官方入口 | 请求体关键参数 | 官方 totalCount | 说明 |
|---|---|---|---|---|
| 阿里巴巴 | `campus-talent.alibaba.com/campus/position/` | `channel=campus_group_official_site`、`batchId=100000760001`、`customDeptCode=''`、`pageSize=50`、`categoryType=freshman` | 477 | 集团 2027 届应届生批次 |
| 淘天 | 同上集团平台 | 同上 + `customDeptCode`=淘天集团叶子码（18 个，运行时从 `searchCondition/list` 解析） | 71 | 自建站 `talent.taotian.com` 当前仅挂 26 届批次（34 条），故以集团平台当前批次为准 |
| 阿里云 | 同上集团平台 | 同上 + `customDeptCode`=阿里云叶子码（10 个） | 128 | 自建站 `careers.aliyun.com` 当前 `listBatch` 为空、列表 0 条（26 届已关）；集团平台有当前 27 届 |
| 高德 | 同上集团平台 | 同上 + `customDeptCode`=高德地图叶子码（7 个） | 12 | 自建站 `talent.amap.com` 当前为 26 届批次（45 条） |
| 饿了么 | 同上集团平台 | 同上 + `customDeptCode`=淘宝闪购叶子码（6 个） | 16 | 品牌已更名「淘宝闪购」，官方站点 `talent.ele.me`；自建站当前 0 条 |
| 菜鸟 | `talent.cainiao.com/campus/recruitment-position` | `batchId=4000000250`（菜鸟生计划/校招）、`4000000249`（实习生计划）；独立站点不走集团 `customDept` | 0 | `listBatch` 该域返回 404，官方页面以 `batchCode` 映射 batchId；当前 岗位数 0 |
| 腾讯音乐 | `join.tencentmusic.com` | `POST /api/uc-job/list` `{page,ss=100,type}`；campus=`type 10 应届生 + 40 技术大咖`，intern=`20 实习生 + 30 日常实习生` | 37 | 纯公开 HTTP，无需浏览器；不存在截止日字段 |

阿里系鉴权/批次/部门参数含义：
- `XSRF-TOKEN`：SPA 页面 JS 首次加载写入的 cookie；`/position/search` 需带 `?_csrf=<token>`，非浏览器指纹直连会被 WAF 403，故**继续走 headless**。
- `batchId`：官方批次（`searchCondition/listBatch` 的 `graduate` / `internship` / `topTalentPlan`）。
- `customDeptCode`：`searchCondition/list` 的 `customDept` 业务集团**叶子部门码**逗号串；直接传父码（如 60001）返回 0，必须展开叶子码。
- `corpCode` / `categoryType`：实测对结果无过滤作用（`corpCode` 任意值均返回全量；`categoryType` 由 `batchId` 决定），适配器保留可配置但不再依赖。

---

## 2. 只读实测表（`campus`，输出 `_worktrees/ali-tencent-out/run/`）

| 实体 | status | complete | 条数 | 官方 total | 页数 | 请求/预算 | 届别可用率 | 发布时间可用率 | 截止日可用率 | 毕业窗口可用率 |
|---|---|---|---|---|---|---|---|---|---|---|
| 阿里巴巴 | success | true | 477 | 477 | 10 | 12/40 | 100% | 0% | 0% | 100% |
| 淘天 | success | true | 71 | 71 | 2 | 5/40 | 100% | 0% | 0% | 100% |
| 阿里云 | success | true | 128 | 128 | 3 | 6/40 | 100% | 0% | 0% | 100% |
| 高德 | success | true | 12 | 12 | 1 | 4/40 | 100% | 0% | 0% | 100% |
| 饿了么 | success | true | 16 | 16 | 1 | 4/40 | 100% | 0% | 0% | 100% |
| 菜鸟 | success | true | 0 | 0 | 1 | 2/40 | n/a | n/a | n/a | n/a |
| 腾讯音乐 | success | true | 37 | 37 | 3 | 3/40 | 100% | 100% | 0% | 0% |

- 全部结果均通过 `p1_pipeline.validate_result`（阿里系 `complete` 要求 `expected_total == 返回条数`、无错误、证据文件齐全）。
- 字段可用率来自实测 `jobs`：阿里系 `publishTime` 官方字段全为 `None`，故 `published_at` 一律留空；平台无截止日字段，`deadline` 一律留空；届别取官方批次名（`campaign_cohort_raw`，如「阿里巴巴2027届应届生」）；毕业窗口取官方 `graduationTime`（2026-11-01 ~ 2027-10-31）。腾讯音乐 `published_at` 取官方 `date` 字段（样例 `2024-08-05`，原文照录，不推断），届别取官方 `job_type_descr`（应届生/技术大咖）。
- 证据：`run/summary.json`、`run/<slug>/campus/result.json` + `ali-<company>-batch*-page*.json` / `tme-type*-page*.json`。

---

## 3. 交付物

### 代码
| 文件 | 改动 |
|---|---|
| `qiuzhao/collector/alibaba_headless.py` | 重写为多实体 p1 适配器（`ENTITIES` 配置：站点入口 / `batch_discovery` / `dept_label` / 回退 batchId；headless 带 Chromium→系统 Chrome 回退；≥2s 节流；每实体 40 次预算） |
| `qiuzhao/collector/tencent_music.py` | 新增：腾讯音乐专用适配器（公开 HTTP、类型码→scope 映射、预算/节流、`validate_result` 契约） |
| `qiuzhao/collector/p1_pipeline.py` | **仅**在既有 REGISTRY 注册块（平台/银行）之后追加独立注册块；`DEFAULT_COMPANIES` 自动纳入 7 家 |
| `tests/test_p1_alibaba_tencent.py` | 新增 17 个离线单测（解析/分页/空字段不推断/预算/无 headless/注册），夹具在 `tests/fixtures/ali_tencent/`（真实响应脱敏裁剪，2026-09-18 录制，无网络） |
| `tests/test_collector_next_integration.py`、`tests/test_p1_banks.py` | 各改 1 处顺序断言：银行块仍连续，允许其后追加本批次注册块（保持基线失败清单不变） |

### 部署件
`pipeline-watch/deploy-artifacts/20260918e/`：`alibaba_headless.py`、`tencent_music.py`、`p1_pipeline.py`、`SHA256SUMS.txt`、`DEPLOY-NOTES.md`。

- 叠加顺序：在 `20260918c`（银行批次 1）之后；`p1_pipeline.py` 为 append-only，若其它并行批次已部署需保留其注册块。
- 精灵若缺自带 Chromium，安装命令（**本次未执行**）：
  `C:\mcp-suite-collector\.venv\Scripts\python.exe -m playwright install chromium`
  代码在无自带 Chromium 时回退系统 Chrome（`channel='chrome'`）。

### 测试
- 基线（`feat/banks-batch1`）：`3 failed, 388 passed, 55 skipped`（`test_core::test_role_cohort_and_campaign_title_bases`、`test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、`test_schema::test_enum_check_fails_when_data_drifts`）。
- 本次：`3 failed, 405 passed, 55 skipped` —— **失败清单不新增**，新增 17 测全绿。

---

## 4. 遗留与边界

1. **阿里云 / 饿了么 / 菜鸟 自有校招站当前无岗位**：阿里云 `careers.aliyun.com`、饿了么 `talent.ele.me` 的当前列表为 0（站点仍挂 26 届）；菜鸟 `talent.cainiao.com` 四个 batchCode（`cainiaoStar`/`internship`/`freshman`/`talentPlan`）当前均为 0 条。适配器按官方 totalCount 返回 `complete=true` 的空快照（仅索引到官方入口与批次，不伪造岗位）；待其 27 届开放后无需改代码即可自动取到。
2. **菜鸟不在集团 `customDept` 列表内**，必须走独立站点；其 batchCode→batchId 映射来自官方页面真实请求（`freshman=4000000250`、`internship=4000000249`、`cainiaoStar=123123213`、`talentPlan=4000000245`），若官方改版需重录。
3. **social 范围未接入**：阿里系校园平台不提供社招；腾讯音乐社招不在 `/api/uc-job/list`。两者 `social` 均返回 `blocked` 并写明原因，不消耗网络请求。
4. **同一岗位跨实体重复**：淘天/阿里云/高德/饿了么的岗位同时属于「阿里巴巴」集团 477 条，属于产品口径上的「该公司在招」，不是去重丢失；如需集团与子公司互斥，需另定口径。
5. **`published_at` 阿里系全空**是官方事实（`publishTime=None`），未用 `modifyTime` 顶替；腾讯音乐发布时间可能偏旧（原文照录）。
6. **未验证项**：本次仅本地只读实测，未在精灵执行；未做日链端到端（需部署后由站长执行）。
