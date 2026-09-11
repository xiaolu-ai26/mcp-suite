# 秋招 MCP v3 · A线#4 岗位MVP接入报告

- 执行时间：2026-09-10（UTC+8）
- 输入：现有生产快照 `qiuzhao/data/jobs.json`（9191 条，11 个集团体系）
- 输出快照：`job_mvp/staging_merged/jobs.json`（**10043 条**，未覆盖生产）
- 硬约束遵守：未改 `server.py` / `store.py`；未碰 `private/`、50码、`access.sqlite3`；未绕过登录/验证码/付费墙；旧工具调用语义兼容。

---

## 1. 各企业接入数量与核查通过率

| 企业 | 源 | 列表总数 | 接入 | 通过率 | 说明 |
|---|---|---|---|---|---|
| **腾讯** | join.qq.com 公开 API（searchPosition，9页全量） | 814 | **814** | 100% | 与现有9191条按 source_url+title+company 交叉去重，0 重复 |
| **宝洁 P&G** | pgcareers.com（Phenom）8 个内地校招岗详情页 JSON-LD | 8 | **8** | 100% | 8/8 详情页 HTTP 200，含 title/多地点/毕业窗口/职责 |
| **美的** | careers.midea.com 校招页（SPA，10条/页，共146） | 146 | **10** | 6.8% | 第1页富文本（含职责）核查接入；其余页交互分页未完成，见阻塞 |
| **迈瑞医疗** | career.mindray.com/campus（北森，共58） | 58 | **20** | 34.5% | 研发族首屏 PHD01-10/RD01-10 接入；其余4族需类目筛选 |
| 恒瑞医药 | app.mokahr.com（Moka，共444） | 444 | 0 | 0% | **blocker**：列表 API 返回 `{"code":1,"msg":"Need Login"}`，不绕过登录 |
| 字节跳动 | jobs.bytedance.com/campus | ~7581 | 0 | 0% | **blocker**：校招 API 需 `_signature` 反爬 token，见 §2 |

**合并口径**：现有 9191 + 腾讯 814 + 宝洁 8 + 美的 10 + 迈瑞 20 = **10043**。

### 腾讯内部核查细分
- 校招/实习区分（按 projectName + 标题关键词）：**校招 382**（青云计划-应届 276 + 应届毕业生 106）、**实习 432**（青云计划实习 268 + 应届实习 94 + 日常实习 65 + 项目实习 5）。该 feed 为校招门户，无社招混入。
- 港澳台单列：13 条含「中国香港」，标 `region=overseas`，不混入内地可投计数。
- 字段核查（抽查 ≥20，实际逐条）：job_title、cities、source_record_id 来自官方 API（`status=0`，count 一致）；detail URL `post_detail.html?postid=xxx` 抽查 5 条均 HTTP 200（标题「岗位详情 | 腾讯校招」）；deadline 列表 API 不返回，统一 `deadline_type=undisclosed`，不臆造。
- 未通过 0 条，逐条日志见 `tencent_review_log.jsonl`（814 行）。

---

## 2. 阻塞原因（blocker）

### 字节跳动 —— `_signature` 反爬 token
- 正确参数已定位（浏览器 DevTools 捕获真实 XHR）：
  - 端点：`POST https://jobs.bytedance.com/api/v1/search/job/posts`
  - **参数走 URL query string（非 JSON body）**：`recruitment_id_list=201`（应届）、`portal_type=3`、`portal_entrance=1`
  - 旧 `bytedance.py` 用 `portal_type=2` + JSON body → 返回 10000 条社招（即此前「0校招」根因）。
- **阻塞**：真实请求必带客户端 JS 生成的 `_signature=...`；裸请求（urllib/curl 无签名）返回 **HTTP 400 EOF**。该签名由反爬 SDK 生成，不属于登录，但需浏览器运行时执行签名算法。
- 处置：按「403/429≠0岗位」与不绕过原则，登记 blocker，未循环抓社招自称成功。下一步建议在渲染浏览器内由页面 fetch 携带签名采集，或离线还原签名算法。

### 恒瑞医药（Moka）—— Need Login
- 站点 ID：`app.mokahr.com/campus-recruitment/hengrui/145997`（页面可公开浏览）。
- 职位列表 API `https://app.mokahr.com/api/applications/jobs?site_id=145997` 返回 `{"code":1,"msg":"Need Login"}`（401）。
- 处置：不绕过登录，登记 blocker；改选迈瑞（北森，公开渲染）完成医药线最低覆盖。

### 美的 —— 交互分页未全量
- 列表 146 条、10 条/页、页码 1–15；首屏 10 条含完整职责已接入。
- 详情/列表走 `apiprod.midea.com/stp/sc-msct/resource/all/app/...`，裸请求 404（网关 `/app/{path}` 路由 + 渲染时签名/会话），浏览器内翻页点击在自动化中不稳定。
- 处置：接入已验证的 10 条，剩余 136 条标 partial。

---

## 3. MCP 工具 schema 扩展说明
详见 `tools_diff.md`。`jobs_search` 新增 4 个**可选**参数：
- `company`（公司关键词）、`recruitment_type`（校招/实习/社招）、`industry`（行业/职能）、`region`（mainland/overseas）
- 全部默认 `None`，不传时行为与旧版完全一致；空值不筛选、不猜测。
- `pytest tests/test_core.py` → **10 passed**（含原核心用例）。

---

## 4. 三个真实场景验证（`scenario_tests/`）

| 场景 | 查询 | 结果 | 文件 |
|---|---|---|---|
| a. 按背景检索 | `major=计算机, cohort=2027, city=深圳` | **43 条** | `scenario_a_background.json` |
| a2. 新筛选实测 | `city=深圳, recruitment_type=校招, company=腾讯` | **259 条** | `scenario_a2_newfilters.json` |
| b. 三岗对照 | 腾讯 / 宝洁 / 迈瑞 各取 1 岗 | **3 岗**并列对比 | `scenario_b_compare3.json` |
| c. 截止与准备顺序 | `jobs_deadlines(days=7)` | **4 条**未来7天截止（均为中国能建，最近 09-13/09-14/09-15） | `scenario_c_deadlines7d.json` |
| c2. 宽窗佐证 | `jobs_deadlines(days=30)` | 1126 条 | `scenario_c_deadlines30d.json` |

---

## 5. 交付物清单
- `job_mvp/staging_merged/jobs.json` —— 合并待发布快照（10043 条，未覆盖生产）
- `job_mvp/tencent_review_log.jsonl` —— 腾讯逐条核查日志（814 行）
- `job_mvp/scenario_tests/` —— 三个场景查询与返回（5 个 JSON）
- `job_mvp/tools_diff.md` —— tools.py 修改说明
- `job_mvp/JOB_MVP_REPORT.md` —— 本报告
- 中间件：`process_tencent.py`、`collect_pg.py`、`build_midea_mindray.py`、`run_scenarios.py`
- 各企业 staging：`pg_staging.json`、`midea_staging.json`、`mindray_staging.json`

## 6. 诚实标注（partial / blocker）
- 美的 10/146、迈瑞 20/58：**partial**（已渲染部分富文本接入，未枚举完整源）。
- 字节 0/7581、恒瑞 0/444：**blocker**（反爬签名 / 需登录），未用社招/假数据凑数。
- 腾讯 deadline 全部 `undisclosed`（列表 API 不返回），未臆造截止日；届别以岗位原文/项目标签为准。
