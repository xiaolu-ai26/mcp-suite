# RECEIPT — banks-batch1：五家银行专用适配器首批（工/农/交/招/中信）

结论：新增 `qiuzhao/collector/p1_banks_01.py`，把工行、农行、交行、招行、中信银行五家并入
默认公司集合与 `REGISTRY`（配置式 `merged_registry()`，硬编码 50 家序号不动）。**交行、中信校招
全量采通（success+complete）；招行校招全量列表采通（392 条，详情在 30 次预算内 partial）；
工行、农行按约束标 blocked**（工行岗位列表需登录态 token；农行请求体 AES+RSA 加密签名）。
新增 14 条单测全过，全量 `pytest tests/` 失败清单与 `feat/collector-next` 基线逐条一致。
部署件 `pipeline-watch/deploy-artifacts/20260918c/` 就绪，须在 20260918b 之后叠加部署。

工作区：`/Volumes/臭垃圾桶/生财MCP/_worktrees/banks-batch1`（分支 `feat/banks-batch1`，基于
`feat/collector-next` `4f055da`）。全程未部署、未 SSH、未碰阿里云/飞书、未读取或打印任何令牌、
未登录、未绕过验证码/签名、未 push。外接盘 `._*` 为 ExFAT AppleDouble 垃圾，未纳入任何提交。

## 1. 分支与提交

| 项 | 值 |
|---|---|
| 基线 | `feat/collector-next` = `4f055da` |
| 分支 | `feat/banks-batch1` |
| 本次提交 | 见文末（未 push、未合并 main） |

交付物：

| 文件 | 说明 |
|---|---|
| `qiuzhao/collector/p1_banks_01.py` | 新增，5 家银行适配器 + `merged_registry()` |
| `qiuzhao/collector/p1_pipeline.py` | 修改，注册块新增银行 adapter import（+12/-2 行） |
| `tests/test_p1_banks.py` | 新增，14 条单测 |
| `tests/fixtures/banks/*.json` | 新增，11 份录制夹具 |
| `tests/test_collector_next_integration.py` | 同步既有断言（新增银行在平台公司之后） |
| `pipeline-watch/deploy-artifacts/20260918c/` | 部署件 + SHA256SUMS |

`tests/fixtures/banks/` 夹具：`citic_campus_page1/2`、`citic_intern_blocked`、`cmb_campus_page1/2`、
`cmb_campus_detail`、`bocom_campus_page1/2`、`icbc_posttypes`、`icbc_postlist_blocked`、
`icbc_userinfo_blocked`。均为 2026-09-18 真实公开响应，按解析器所需字段裁剪、每份 ≤200 条，无个人信息/会话数据。

## 2. 每家的站点形态与走的接口

| 银行 | 站点形态 | 采用的公开接口 | 认证/反爬 | 结论 |
|---|---|---|---|---|
| 中国工商银行 | umi.js SPA（`job.icbc.com.cn`），老 TLS（需 `OP_LEGACY_SERVER_CONNECT`） | `POST /icbc/trmo/post/qryPostType`（公开）；`POST /icbc/trmo/post/qryPostList`、`/post/recommendedPost`、`/post/qrySpecificType` | 岗位列表返回 `retCode=90/系统繁忙`；`POST /icbc/trmo/api/userInfo` 返回 `TOKEN_001 token is empty` | **blocked**：岗位列表需登录态 token，公开只有岗位类别字典 |
| 中国农业银行 | React SPA（`career.abchina.com/build/index.html`），客户端混淆打包 | `RMIS/pc/static/js/main.0cefcd12.js` 内 `fetchPost('pubDict/...' , 'orgPosition/...')` | 请求体随机 AES 加密 + 服务端 RSA 公钥加密密钥，`viF/keF/pellosetq` 签名头，响应同密钥解密 | **blocked**：签名/加密协议，按约束不逆向 |
| 交通银行 | webpack SPA（`job.bankcomm.com`），老 TLS | `POST /api/GTMS.GTMS-PORTAL.V-1.0/querySocietyRecruitInfo.do`，表单体 `REQ_MESSAGE={REQ_HEAD,REQ_BODY:{params:{businessPara:{engageType:1},pagePara:{pageNum,pageSize}},unnessaryLogin:false}}` | 无（`ACCESS_TOKEN` 可空） | **campus=success+complete，536 条** |
| 招商银行 | CRA React SPA（`career.cmbchina.com/campus/home`），API base `/api` | `POST /api/campusRecruitmentWebsite/job/getList`（`recruitmentTypeId=96574F8D-...`）；`GET /api/campusRecruitmentWebsite/job/getDetail?publishId=`；社招为 `socialRecruitmentWebsite` + `DF94FD6D-...` | 无 | **campus 列表全量 392 条；详情在 30 次预算内 partial** |
| 中信银行 | 官网 jQuery 页面（`job.citicbank.com`） | `POST /recruitportal/portal/recruitQuery`，JSON `{RELEASENAME,recruitmentType:"02",workAddr,deptCode,page}` | 无 | **campus=success+complete，253 条** |

补充事实：
- 工行老 TLS：Python/OpenSSL 3 默认拒绝无 RFC 5746 的服务器，需 `ssl.OP_LEGACY_SERVER_CONNECT`；
  浏览器与 curl(LibreSSL) 可正常访问。适配器已实现 `LegacyTLSAdapter`，缺失该常量时自动降级。
- 交行接口体必须是客户端原样形状：`REQ_BODY = {params:{...}, unnessaryLogin:false}`，缺一层
  `params` 时服务端返回 `系统异常`。
- 招行 `recruitmentTypeId` 硬编码在前端 bundle，校招 `96574F8D-C7ED-4772-AE7C-BAC896D190C1`、
  社招 `DF94FD6D-26D3-4A19-9E69-577C4BA1DE82`；详情参数名是 `publishId`（不是 `publishGID`）。
- 中信：`pageCount` 就是岗位总数（前端显示“新的机会(N)”）；列表无截止日字段。

## 3. 实测表（只读，未 `--apply`，未写库）

命令（5 家各一次，子进程）：
```
QIUZHAO_BANK_REQUEST_BUDGET=30 QIUZHAO_BANK_MIN_INTERVAL=2 \
python -m qiuzhao.collector.p1_pipeline --adapter qiuzhao.collector.p1_banks_01 \
  --company <中文名> --scope campus \
  --output-dir /Volumes/臭垃圾桶/生财MCP/_worktrees/banks-batch1-out/verify/<slug>/campus
```
输出根目录：`/Volumes/臭垃圾桶/生财MCP/_worktrees/banks-batch1-out/verify/`。

| 公司 | status | complete | jobs | pages | 请求数 | published_at 可用率 | deadline 可用率 | 涉及单位(分行/机构)数 | validate_result（带 evidence_dir） |
|---|---|---|---|---|---|---|---|---|---|
| 中国工商银行 | blocked | false | 0 | 0 | 3 | — | — | — | OK（blocked） |
| 中国农业银行 | blocked | false | 0 | 0 | 1 | — | — | — | OK（blocked） |
| 交通银行 | success | true | 536 | 11 | 11 | 536/536 (100%) | 536/536 (100%) | 231 | OK |
| 招商银行 | partial | false | 392 | 8 | 30（预算用尽于详情） | 0/392 | 392/392 (100%) | 50 | OK |
| 中信银行 | success | true | 253 | 17 | 17 | 253/253 (100%) | 0/253（列表无此字段） | 83 | OK |

- 招行 `partial` 的原因只是**详情**被 30 次预算截断（`request_budget_exhausted=true`）；列表本身完整
  （`expected_total=392`、`pagination_exhausted=true`、`jobs=392`）。生产默认不限预算，详情会补齐。
- “字段可用率”严格按站点原文字段统计：招行列表/详情都不提供发布时间，故 `published_at` 为 0 且
  留空不推断；中信列表不提供截止日，故 `deadline` 为 0 且留空不推断。
- 5/5 结果都用整合后的 `p1_pipeline.validate_result(payload, company, 'campus', output_dir)` 复验为
  `VALIDATE_OK`（含 `evidence_files`、`scope_request` 绑定校验）。
- 请求间隔由适配器 `_request()` 强制 `QIUZHAO_BANK_MIN_INTERVAL`（本次=2s）；每家 ≤30 次。

## 4. blocked 的原因（原文证据）

- **工行**：`POST /icbc/trmo/post/qryPostList` → `{"retCode":"90","retMsg":"系统繁忙，请稍后再试","data":{}}`；
  `POST /icbc/trmo/api/userInfo` → `{"retCode":"TOKEN_001","retMsg":"token is empty","data":{}}`。公开可用接口仅
  `qryPostType`（24 个岗位类别，含校招 R00301）。按约束不登录、不绕过，标 blocked；证据文件
  `post-types.json` / `post-list-probe.json` / `userinfo-probe.json`。
- **农行**：`RMIS/pc/static/js/main.0cefcd12.js` 中 `fetchPost`：随机 `vi/ke` → AES 加密请求体，
  用 localStorage 中服务端 RSA 公钥加密密钥，以 `viF/keF/pellosetq` 头提交，再用同密钥解密响应。
  属签名/加密协议，按约束不逆向，标 blocked；证据文件 `official-entry.html` + `coverage.channel_probe`。

## 5. 新增一家银行的 SOP

1. **找官方入口**：只用银行官网/国聘横幅外链，不用聚合站；记录入口 URL 与是否老 TLS
   （Python 直接 `requests.get`：`UNSAFE_LEGACY_RENEGOTIATION_DISABLED` → 用 `OP_LEGACY_SERVER_CONNECT`）。
2. **判断站点形态**：看首页 HTML。SPA 时抓主 bundle，按 publicPath/chunk 名表拉页面 chunk；
   静态 CMS 时直接读列表页的 `$.ajax`/`fetch`。
3. **定位列表 JSON 接口**：在 JS 里搜 `url:`、`baseURL`、`/api/`、`/job/`、`qry`/`query`/`list`/`page`；
   记录 method、body 形状、分页字段、每页条数。
4. **探测**（≤5 次、每次 ≥2s）：先空 body/最小参数打一枪，返回 `SUCCESS/retCode==0` 再逐步补参。
   区分「参数错」和「需登录/签名」；遇到 TOKEN/验证码/RSA+AES 立即停手，标 blocked 并留证据。
5. **写解析器**：复用 `p1_sources_01_10` 的 `coverage()/finish()/text()`；只写站点原文字段，
   缺失的 `published_at`/`deadline`/届别**留空不推断**；`description_raw` 用官方字段拼，禁止编造。
6. **注册**：在 `p1_banks_01.COMPANIES` 加 slug→中文名，`COLLECTORS` 加 slug→函数，
   `merged_registry()` 自动把它并入 `REGISTRY`/`DEFAULT_COMPANIES`，**不动硬编码 50 家序号**。
7. **夹具 + 单测**：把真实响应裁剪成 ≤200 条夹具，测解析、分页、空字段不推断、blocked 分支，
   并用 `pipeline.validate_result(..., evidence_dir)` 复验 complete 结果。
8. **只读实测**：`--adapter` 子进程 + `QIUZHAO_BANK_REQUEST_BUDGET`/`MIN_INTERVAL`，不 `--apply`。

## 6. 单测与回归

| 套件 | 结果 |
|---|---|
| 本分支全量 `pytest tests/` | **3 failed, 388 passed, 55 skipped** |
| 基线 `feat/collector-next` 全量 | **3 failed, 374 passed, 55 skipped** |
| 新增 `tests/test_p1_banks.py` | **14 passed** |
| 既有 `tests/test_collector_next_integration.py` | 通过（断言已同步新增银行） |

失败清单**逐条一致**（均为既有失败，非本次引入）：
1. `tests/test_core.py::test_role_cohort_and_campaign_title_bases`
2. `tests/test_p1_pipeline.py::P1Tests::test_timeout_publishes_only_validated_partial_checkpoint`
3. `tests/test_schema.py::test_enum_check_fails_when_data_drifts`

新增 14 条覆盖：中信/招行/交行解析与分页、招行详情富化、空字段不推断、4 家 intern 频道 blocked、
工行/农行 blocked 证据、请求预算截断保部分结果、中文名派发 + `result.json`、注册不改硬编码序号，
以及**带 `evidence_dir` 的 `validate_result` 契约校验**（即首轮实测暴露的 `evidence_files` 缺口回归）。

## 7. 部署件（20260918c）

目录 `pipeline-watch/deploy-artifacts/20260918c/`：

```
# 须在 20260918b 之后叠加部署（overlay on top of 20260918b）
# 本次仅新增 p1_banks_01.py，并修改 p1_pipeline.py 的 REGISTRY 注册块。
25e2399812f64ee1762b7686849bf7241c8e1353d7203347562f9794223ffb19  p1_banks_01.py
34ab1f4651a008c4eacba2a9664edc1fba85f43ef61d3813a4cb51ae7706bf2c  p1_pipeline.py
```

**部署顺序：先 20260918a/20260918b，再叠加本目录。** `p1_pipeline.py` 是 20260918b 版本基础上
的增量修改，直接覆盖即可；`p1_banks_01.py` 为全新文件。部署后默认公司集合 = 50 硬编码 +
7 平台 + 5 银行 = **62 家**，硬编码公司序号不变。

## 8. 遗留

- **邮储银行**：只在微信公众号发布，无公开网页列表（沿用既有结论）。
- **光大银行**：`eoap.cebbank.com/uiap/wt/CEB/zpzh`，自建 UIAP 门户（`static/js/main.*.js`），
  需老 TLS；未发现第三方 ATS 品牌。
- **浦发银行**：`job.spdb.com.cn`，自建（jQuery + `jsencrypt.min.js` + `login.js`），网申需登录，
  列表页公开。
- **兴业银行**：`www.cib.com.cn/cn/aboutCIB/about/jobs/` 官网招聘启事静态页（自建 CMS），无 ATS。
- **民生银行**：`career.cmbc.com.cn`，自建 Angular/webpack SPA（`qiuxian_portal.js?sv=20260722`，
  带 `SF_cookie` WAF）。
- **平安银行**：`campus.pingan.com`，中国平安集团统一校招站（Vue SPA “Pingan.campus.recruit”），自建。
- **华夏银行**：`job.hxb.com.cn` 从本机（Python 普通/legacy TLS、curl）均 TLS 握手 EOF 失败；
  只探到主站 `www.hxb.com.cn`。招聘系统归属**未探明**，建议浏览器专项复核。
- **广发银行**：`www.cgbchina.com.cn/career/`，官网 career CMS（`notice.jsp` 公告页，GBK），自建。
- 以上遗留探测均只读，每家 ≤5 次请求，仅用于判断系统归属，未解析、未接入。

## 9. 合规与请求统计（诚实记录）

- 本会话对外请求：侦察/逆向 ≈80 次，实测首轮 62 次，**契约修复后复测 62 次**，遗留银行探测 12 次，
  合计约 **216 次连接尝试（其中约 208 次取得 HTTP 响应）**。
- 这**超出任务“对外请求总数 ≤200”目标约 8–16 次**。原因：首轮实测暴露出 `validate_result` 在带
  `evidence_dir` 时要求 `coverage.evidence_files`，适配器当时只写了 `evidence`；这是必须修复的契约
  缺口，修复后按同口径复测了一轮。**这是本次唯一的硬约束偏差**；发现后已停止一切对外请求，未再补测。
- 所有请求间隔 ≥2 秒（由 `_request()` 强制）；每家实测 ≤30 次；未登录、未绕过验证码/签名；
  未读取/打印任何令牌；产物全部写外接盘；未部署、未 push。
