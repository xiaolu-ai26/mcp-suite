# 秋招MCP v3 条件4：新合格库真实验收报告

**日期**：2026-09-10（北京时间）
**任务**：用修复后的合格数据（9,199条）启动本地隔离MCP服务，完成真实MCP验收与Agent接通
**执行方式**：真实启动 uvicorn 服务 + 真实 MCP Streamable HTTP 协议调用 + 真实扣额；**未使用旧 9,191 库的任何测试结果代替**
**结论**：**条件4 通过 ✅**

---

## 一、隔离环境配置

| 项 | 值 |
|---|---|
| 隔离工作目录 | `/tmp/qz_v3_iso/` |
| 岗位数据（MCP_JOBS_PATH） | `/tmp/qz_v3_iso/jobs.json`（由 `conditional_release/qualified_jobs.json` 复制） |
| 测试数据库（MCP_DB_PATH） | `/tmp/qz_v3_iso/access.sqlite3`（全新建库，非生产库） |
| 监听 | `127.0.0.1:8771`（8769 已被占用，改用 8771） |
| MCP_PUBLIC_BASE_URL | `http://127.0.0.1:8771` |
| MCP_PRODUCT | `qiuzhao` |
| 启动命令 | `MCP_JOBS_PATH=... MCP_DB_PATH=... MCP_PUBLIC_BASE_URL=... uvicorn core.server:app --port 8771` |
| 生产库 | `private/access.sqlite3` **全程未触碰**（见第六节） |

**测试码安全**：测试码明文仅存于 `/tmp/qz_v3_iso/.code`（权限 0600），本报告只记录其 SHA-256：
- 测试码 SHA-256：`8a094cbd5c45733631575508c076153f4fb8809b0571f214611add1c170eb709`
- 兑换后 API key SHA-256：`a91adcb678aa87fdaa9cc65cd78ba11480779843591742ac99297c011f91bd2a`

**服务状态**：验收完成后已 `kill` 全部 uvicorn 进程，`lsof -i :8771` 确认端口已释放。

---

## 二、新库就位确认（/health）

```
GET http://127.0.0.1:8771/health
→ {"status":"ok","jobs":9199,"data_as_of":"2026-09-10T14:53:37+08:00"}
```

- **jobs = 9199**，不是旧库的 9191 ✅
- 与合格子集构成一致：postal 2648 + guopin 6058 + chnenergy 422 + ccb 39 + boc 14 + midea 10 + pg 8 = **9,199**

---

## 三、四项新筛选真实查询回执

数据全部来自隔离库（直接调用 `qiuzhao.tools.Jobs.search`，与 MCP 同一代码路径；不伪造）。

| # | 筛选 | 请求参数 | 返回 total | 验证 |
|---|---|---|---|---|
| 1 | **company** | `company="中国邮政"` | **2648** | 全部 `recruitment_unit=中国邮政集团有限公司`，源=邮政2027校招 ✅ |
| 2 | **recruitment_type** | `recruitment_type="校园招聘"` | **5016** | 命中 `recruitment_type_raw="校园招聘"` 的国聘记录 ✅ |
| 3 | **industry** | `industry="金融"` | **0** | 如预期返回空（数据集无企业行业字段，不伪造），并给出放宽建议 ✅ |
| 4 | **region** | `region="北京"` | **1132** | 命中 `cities` 含"北京"（含"北京-海淀区"等） ✅ |
| 5 | region 旁证 | `region="上海"` | 176 | cities 包含匹配正常 ✅ |

**company 样本**：
- `postal-CC360925120J40908096113` | 中国邮政集团有限公司 | 古交市分公司-金融柜员岗 | 太原
- `postal-CC360925120J40908096013` | 中国邮政集团有限公司 | 清徐县分公司-金融柜员岗 | 太原

**recruitment_type 样本**：
- `guopin-217492741108532502` | 中国移动 | AI算法工程师（产线/博后站） | 北京-海淀区

**industry 验证不伪造**：返回 0 条 + `suggestion="可放宽专业或届别条件、换城市，或仅按关键词搜索。未披露条件不会被推断。"` —— 确认未用 `job_category`（岗位职能）冒充企业行业。

---

## 四、jobs_detail 三条以上不同源

| 源 | id | found | 字段数 | 关键返回 |
|---|---|---|---|---|
| **postal（邮政）** | `postal-CC360925120J40906453313` | true | 31 | 中国邮政集团 / 金融财务类 / 北京 / deadline 2026-10-31 / open / source_url+application_url 齐全 |
| **guopin（国聘）** | `guopin-216572682861282064` | true | 36 | 中国移动 / 数智化部-大数据开发工程师 / 北京-东城区 / deadline 2026-10-17 / open |
| **midea（美的）** | `midea-001` | true | 30 | 美的集团股份有限公司 / 电机控制软件工程师 / 佛山市 / open |
| **pg（宝洁）** | `pg-CNC003184` | true | 30 | Procter & Gamble (宝洁) / R&D Scientist / 北京 / open |

详情均返回完整业务字段（含 source_url / application_url / deadline / status / cities），且内部 `evidence_path` 未暴露（public() 已剔除）。

---

## 五、旧功能回归

| # | 工具/参数 | 请求 | 结果 | 验证 |
|---|---|---|---|---|
| 1 | jobs_search 无新参数 | `limit=1` | **total=9199** | 不传新参数时与全库一致，旧调用兼容 ✅ |
| 2 | cohort | `cohort="2027"` | 8672 | 命中 role_record / campaign_title_only 两种 scope ✅ |
| 3 | city | `city="北京"` | 1132 | cities 包含匹配 ✅ |
| 4 | keyword | `keyword="银行"` | 93 | 命中岗位名/单位含"银行"，样本为邮政金融柜员岗 ✅ |
| 5 | jobs_deadlines | `days=30, limit=5` | 1126 | 按 deadline 倒序（order=deadline_desc），样本 2026-10-10 中国移动 ✅ |
| 6 | jobs_deadlines | `days=1` | 0 | 今日窗口无明确截止，正常空结果 ✅ |

无新参数时 total=9199，证明新增的四个可选参数为"空值不过滤"，不改变旧调用语义。

---

## 六、Agent 真实接通证据（MCP Streamable HTTP）

未使用第三方客户端 UI，改用与 e2e 同栈的 `fastmcp.Client` + `StreamableHttpTransport` 直连 `/mcp` 端点，完成协议层全流程：initialize → tools/list → call tool → 扣额回执。

**1) 无 key 访问 `/mcp`**：HTTP **401**（鉴权拦截正常）。

**2) 兑换测试码**：`POST /redeem` → HTTP **200**
```
product=qiuzhao, daily_limit=200, remaining_today=200,
expires_at=2027-01-01, mcp_url=http://127.0.0.1:8771/mcp
```
（明文 code / api_key 未写入本报告，仅留 hash）

**3) tools/list 返回 3 个工具**：
```
jobs_deadlines, jobs_detail, jobs_search
```

**4) jobs_search 入参 schema 含 4 个新参数**（properties 全量）：
```
city, cohort, company, industry, keyword, limit, major, offset, recruitment_type, region
```
新参数描述均已下发：
- `company`：企业/单位名称关键词，如中国邮政；在recruitment_unit等企业主体字段中做包含匹配
- `recruitment_type`：招聘类型，如校园招聘；未披露类型不推断
- `industry`：企业主体行业筛选…当前数据集无企业行业字段，此筛选暂返回空结果
- `region`：地域/城市关键词，如北京；在岗位城市字段中做包含匹配

**5) 真实调用 `jobs_search(limit=1)`**：
```
total=9199, n_jobs_returned=1
first_job: guopin-217492741108532502 | 中国移动通信集团有限公司 |
           AI算法工程师（产线/博后站） | 北京-海淀区 | 国聘... |
           source_url=https://www.iguopin.com/job/detail?id=217492741108532502
```
返回的是隔离库真实岗位，data_as_of=2026-09-10T14:53:37+08:00。

**6) 扣额回执（/usage）**：

| 时点 | remaining_today |
|---|---|
| 兑换后、任何工具调用前 | **200** |
| initialize + tools/list 后（list 不计费） | **200** |
| 一次 jobs_search 后 | **199** |

扣额 **200 → 199**，恰好 +1 次计费，与单次 `jobs_search` 对应；`usage_log` 表确认仅 `jobs_search` 1 条记录。

---

## 七、新库验证（9,199 + 美的/宝洁可查）

| 检查 | 结果 |
|---|---|
| 隔离服务 /health | **9199**（非 9191）✅ |
| `company="美的"` | **10 条**（midea-001…midea-010）✅ 新增源，旧库无 |
| `company="宝洁"` | **8 条**（pg-CNC003172/3222/3221/3215/3210…）✅ 新增源，旧库无 |
| `keyword="美的"` | 11 条 ✅ |
| 生产 `qiuzhao/data/jobs.json` 有效记录 | **仍为 9191**（未被替换）✅ |
| 生产 `private/access.sqlite3` | mtime 未变；本测试码 hash 在生产库中 **0 条** ✅ |
| 隔离库 usage_log | 仅 `jobs_search` ×1（与扣额一致）✅ |

净变化核对：旧 9,191 → 新 9,199 = +8（美的 10 + 宝洁 8 − 电信 10），与条件3合格子集一致。

---

## 八、硬性约束自查

- [x] 未碰生产 `private/access.sqlite3`（mtime 不变、测试码 hash 不在生产库、生产 api_keys/redemption_codes 行数未变）
- [x] 未修改生产服务器（仅本地 127.0.0.1:8771 隔离进程）
- [x] 测试码明文未写入报告，仅记 SHA-256
- [x] 未伪造查询结果（全部来自隔离库真实调用，回执落盘 `/tmp/qz_v3_iso/receipts_direct.json` 与 `receipts_agent.json`）
- [x] 服务用完已停，端口 8771 已释放

---

## 九、最终结论

**条件4 通过。**

合格子集 9,199 条已通过本地隔离 MCP 服务完成真实验收：
- 四项新筛选行为正确（company 2648 / recruitment_type 5016 / industry 0 不伪造 / region 1132）；
- jobs_detail 跨 postal/guopin/midea/pg 四源字段完整；
- 旧功能（cohort/city/deadlines/keyword/无参兼容）全部回归通过；
- Agent 真实 MCP 协议接通成功：3 工具、4 新参数 schema 下发、`jobs_search(limit=1)` 返回真实岗位、扣额 200→199；
- 新库确认为 9,199 条且新增源美的（10）、宝洁（8）可查，旧 9,191 库与生产库均未被触碰。
