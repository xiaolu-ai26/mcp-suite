# 秋招 MCP：已上线来源每日自动更新 adapter 封装 — 实现报告

日期：2026-09-10
范围：为 qiuzhao/collector 新增互联网/科技公司公开来源 adapter，接入现有 `run.py` 调度；**仅输出 staging 快照与代码，不发布生产，不改 cron/锁/鉴权**。

## 1. 交付物

新增/修改文件（均在 `qiuzhao/collector/`）：

| 文件 | 层 | 说明 |
|---|---|---|
| `meituan.py` | API | 美团校招（POST getJobList） |
| `netease.py` | API | 网易主站(projectId=103) + 互娱(projectId=102) |
| `midea.py` | API | 美的校招（自动解析 projectRuleId） |
| `mindray.py` | API | 迈瑞医疗公开岗位板 |
| `base_headless.py` | 基类 | Playwright headless Chromium 通用封装 |
| `alibaba_headless.py` | headless | 阿里校招（headless 取 XSRF token） |
| `run.py` | 修改 | 注册上述 + 已有 tencent/bytedance，扩展 `--source` 与 complete 清理前缀 |

复用已有：`tencent.py`、`bytedance.py`（本次接入调度，未改其行为）。

## 2. 实测结果（本地 staging，单次全量）

| source | 传输 | expected | actual | complete | 备注 |
|---|---|---|---|---|---|
| tencent | 公开 JSON | 815 | 815 | ✅ | pageIndex/pageSize camelCase |
| bytedance | 公开 JSON | 10000* | 10000 | ✅ | *API 上限，实际可能更多 |
| meituan | 公开 JSON | 189 | 187 | ⚠️ | 2 条被标题过滤/近似去重 |
| netease | 公开 JSON | 130 | 130 | ✅ | 主站77 + 互娱53 |
| midea | 公开 JSON | 146 | 146 | ✅ | 自动定位「2027届美的星」projectRuleId |
| mindray | 公开 JSON | 264 | 264 | ✅ | 公开板含社招，按关键词标 campus_guess |
| alibaba | headless+XSRF | 0 | 0 | ✅ | 当前在招 0（历史快照 477），机制已跑通 |

staging 输出：
- `research/qiuzhao-v3-launch-20260910/staging_adapters/{company}/manifest.json`（run_id/source_id/页数/expected vs actual/anomalies）
- `research/qiuzhao-v3-launch-20260910/staging_adapters/{company}/jobs.json`（该源独立快照）

## 3. 关键技术发现（踩坑记录）

1. **美团分页**：裸 `pageNo` 被忽略（恒返回同一页 ~20 条）。真实请求需把分页包在 `page` 对象内：
   `{"page":{"pageNo":1,"pageSize":20}, ...}`。修正后 totalCount=189 校招、分页连续。
2. **网易分页**：`pageIndex` 服务端被忽略；用 `pageSize=100` 一次取回全部（主站77/互娱53）。
3. **迈瑞分页**：`PageIndex` 从 **0** 开始（不是1）。修正后 100+100+64=264。
4. **美的**：`projectRuleId` 不是「2027届美的星」字符串，而是 UUID；adapter 先 GET 项目列表自动解析在校且 `employementCategory=1` 的校招项目。
5. **阿里**：SPA，JSON 接口 `/position/search?_csrf=<token>`，token 等于首屏 cookie `XSRF-TOKEN`；headless 加载页面后由浏览器上下文带 cookie 发请求。当前校招在招 0 个（与历史 477 无关，属正常空窗口）。
6. **字节**：当前纯 POST `/api/v1/search/job/posts` 仍可用（code=0），故保留已有非 headless 实现；headless 路径作为兜底备选。

## 4. 接入 run.py 的方式

- 沿用现有「逐源 try/except + 失败保留旧快照」模式：单源异常只写 `states[name].failed`，不影响其它源与旧 jobs。
- 新源加入 `complete` 清理前缀表：complete=true 时，旧快照中该前缀且本次缺失的记录标 `status=removed`。
- `--source` choices 扩展为 6 旧 + 7 新；`--source all` 全量。
- **未改动**：06:10 cron 入口、`collector-daily.sh`、flock 锁、`/var/lib/mcp-suite` 路径。
- 每源独立超时（底层 urlopen 35s，headless 45s）；headless 依赖为可选导入，未装 playwright 时该源标 failed 而非整体崩溃。

## 5. 三层策略落点

- **第一层 API**：tencent / jd / meituan / netease(主站+互娱) / midea / mindray。其中 **京东** `campus.jd.com/api/wx/position/page` 当前对匿名 POST 返回 500/400/415（需微信端上下文），未接入，标记为待 headless/manual。
- **第二层 headless**：`base_headless.py` + `alibaba_headless.py`（已跑通）。
- **第三层 manual**：恒瑞 Moka 等需登录源，**未接入**，待有凭证后在 registry 标 manual。

## 6. 硬性约束遵守

- ✅ 未写生产 jobs.json；所有输出落在 `research/.../staging_adapters/` 与 staging_run。
- ✅ 未动 access.sqlite3 / 套餐 / 额度 / 鉴权 / 其它站点。
- ✅ 未改 cron 入口与 flock。
- ✅ 未绕过登录/验证码（阿里仅用公开页面首屏下发的公开 token）。
- ✅ 采集低频：每源 page 间隔 ≥0.6s（生产默认 1.25s）。
- ✅ 现有 6 国企源导入与 `--source boc` 实跑验证未破坏。

## 7. 上线前待办（本次不做）

1. 京东：用 headless 复现微信端请求头/body，或改走公开校园站。
2. 美团 187/189：核对 2 条差异是标题过滤还是接口截断（manifest 已记录 diff=-2）。
3. 部署服务器需 `uv pip install playwright && playwright install chromium`，否则 alibaba 源自动 failed 跳过。
4. 48 小时无成功复核标 stale 的逻辑，待发布步骤统一合并时实现（本次仅 staging）。
