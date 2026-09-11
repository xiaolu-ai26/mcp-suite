# 项目基线核对报告 — QIUZHAO-EXPANSION-20260910 A阶段

> 生成时间：2026-09-10 北京时间
> 基于实际源码读取，非任务书推测。
> 项目路径：/Users/maxzhl/Projects/mcp-suite/

---

## 1. 实际代码结构与模块职责

```
mcp-suite/
├── core/
│   ├── server.py          # ASGI入口：Streamable HTTP MCP + 兑换页/指南/健康检查/用量
│   ├── store.py           # 鉴权与额度：SQLite存储、兑换码生成、API key、每日限额
│   ├── admin.py           # 本地批量兑换码生成（仅输出路径和数量，不输出凭证）
│   └── static/            # 兑换页HTML/CSS/JS（index.html, guide.html, site.css, app.js）
├── qiuzhao/
│   ├── tools.py           # Jobs类：岗位数据加载、搜索、截止查询、详情、公开字段过滤
│   ├── collector/
│   │   ├── run.py         # 每日采集主流程：6个适配器调度、合并、去重、状态更新、摘要
│   │   ├── ccb.py         # 建行总部校招适配器（旧TLS兼容，公开API，不登录）
│   │   ├── guopin.py      # 国聘6个企业专场适配器（公开API白名单，按公司选择器分段）
│   │   └── verify_samples.py  # 跨来源样本独立复核（邮政详情、国家能源原页、建行、国聘2组）
│   └── data/
│       ├── jobs.json          # 岗位快照（9191条，只读）
│       ├── source_coverage.json  # 来源覆盖统计与其他优先级源审计
│       ├── source_state.json     # 各采集源运行状态
│       ├── summary.json          # 汇总统计
│       ├── alerts.json           # 采集报警
│       ├── excluded_records.json # 邮政排除记录
│       ├── guopin_excluded_records.json  # 国聘排除记录
│       └── evidence/             # 采集证据文件（按run_id分目录）
├── tests/
│   ├── test_core.py       # 6项单元测试（兑换原子性、并发限额、权限过期、午夜重置、字段保真、届别优先）
│   └── e2e_local.py       # 本地HTTP/MCP端到端测试（需启动本地服务）
├── deploy/
│   ├── collector-daily.sh     # 每日采集包装脚本（flock锁、失败保留旧快照、写cron-status）
│   ├── mcp-suite-qiuzhao.cron  # cron配置（北京时间06:10）
│   ├── mcp-suite.service      # systemd服务配置
│   ├── mcp-suite-qiuzhao.conf # Nginx配置
│   ├── deploy.sh              # 部署脚本
│   └── final-online/          # 线上最终快照与验收收据（只读参考）
├── requirements.txt           # fastmcp==2.14.7, uvicorn==0.52.4, httpx==0.28.1, beautifulsoup4
├── README.md                  # 项目说明
└── private/                   # 权限drwx------，含兑换码库存和access.sqlite3（禁止读取）
```

### 模块职责详述

| 模块 | 职责 | 关键类/函数 |
|---|---|---|
| `core/server.py` | MCP HTTP服务入口，3个工具注册，Bearer鉴权中间件，兑换/用量/健康检查路由，安全头注入 | `FastMCP`, `MeterTools`, `Guard`, `jobs_search/deadlines/detail` |
| `core/store.py` | SQLite鉴权存储，兑换码生成与兑换，API key创建，每日限额原子扣减，用量日志 | `Store`, `AccessError`, `PLANS`, `digest()` |
| `core/admin.py` | CLI批量生成兑换码，独占文件创建防覆盖 | `main()` |
| `qiuzhao/tools.py` | 岗位数据加载与查询，公开字段过滤（排除evidence_path），过期自动标记，届别匹配优先级 | `Jobs`, `load()`, `search()`, `deadlines()`, `detail()`, `public()` |
| `qiuzhao/collector/run.py` | 采集主流程，6适配器调度，合并去重，下架标记，摘要/状态/报警输出 | `Collector`, `base_job()`, `postal()`, `chnenergy()`, `telecom()`, `boc()`, `run()` |
| `qiuzhao/collector/ccb.py` | 建行总部校招公开API采集，旧TLS兼容（OP_LEGACY_SERVER_CONNECT），证书校验保持开启 | `PublicClient`, `collect_ccb()`, `campaign_fields()` |
| `qiuzhao/collector/guopin.py` | 国聘6个企业专场公开API采集，白名单路径限制，公司选择器分段分页 | `collect_guopin()`, `campaign_pages()`, `public_api()` |
| `qiuzhao/collector/verify_samples.py` | 独立复核：邮政详情API、国家能源原页、建行公开API、国聘2组单页列表 | `verify()` |

---

## 2. 现有采集适配器清单

共 **6个采集适配器**，覆盖 **11个集团/机构体系**：

### 2.1 直采官方渠道（5个）

| 适配器 | 企业/渠道 | 采集方式 | 岗位数 | 状态 |
|---|---|---|---|---|
| `postal` | 中国邮政集团有限公司 | 官网公告 + 智联授权2027校招专场API（`fe.zhaopin.com/grace/api/dsc/search-job-list`），分页100/页 | 2,648 | success, complete |
| `chnenergy` | 国家能源投资集团有限责任公司 | 官网校园招聘列表HTML（`zhaopin.chnenergy.com.cn/recTypeSerch`）+ 各岗位详情页HTML解析 | 422 | success, complete |
| `telecom` | 中国电信集团有限公司 | 官网校园招聘页（`job.chinatelecom.com.cn/wt/TELE/web/index/campus`）+ 历史已导入岗位URL复核 | 10 | success, **incomplete**（仅最新页+历史） |
| `boc` | 中国银行股份有限公司 | 官网2027校招公告HTML（`boc.cn/aboutboc/bi4/...`），解析总行直属机构明确岗位 | 14 | success, complete（仅明确命名岗位） |
| `ccb` | 中国建设银行股份有限公司 | 官方招聘公开API（`job1.ccb.com/tran/WCCMainPlatV5`，TXCODE=NHR106公告/NHR104列表），旧TLS兼容 | 39 | success, complete（总部2027计划） |

### 2.2 国聘企业专场（6个，统一适配器 `guopin`）

| domain | 企业 | 采集方式 | 岗位数 | 排除数 |
|---|---|---|---|---|
| `zgyd` | 中国移动通信集团有限公司 | 国聘公开API（`gp-api.iguopin.com/api/jobs/v1/list`），公司选择器分段 | 1,610 | 0 |
| `ceec` | 中国能源建设股份有限公司 | 同上 | 634 | 16（社招/性质冲突） |
| `cgnpc` | 中国广核集团有限公司 | 同上 | 8 | 0 |
| `cam2027` | 中国机械科学研究总院集团有限公司 | 同上 | 72 | 0 |
| `casicjob` | 中国航天科工集团有限公司 | 同上 | 1,165 | 14（社招） |
| `zglt` | 中国联合网络通信集团有限公司 | 同上 | 2,569 | 0 |

国聘合计：**6,058条**（排除30条非校招/冲突记录）

### 2.3 其他优先级源审计（已尝试但受阻）

`source_coverage.json` 中记录了13个已审计但未接入的源：

| 企业 | 状态 | 原因 |
|---|---|---|
| 中国中车 | blocked | 403 Forbidden |
| 国家电网 | blocked | 412 Precondition Failed |
| 南方电网 | blocked | 初始200后403 |
| 华能 | blocked | 初始200后403 |
| 大唐 | adapter_missing | 200动态站点，无已验证适配器 |
| 华电 | blocked | TLS unexpected EOF |
| 国家电投 | blocked | 503 |
| 中核 | blocked | 412 |
| 中石油 | blocked | 412 |
| 中石化 | blocked | TLS证书校验失败（未禁用校验） |
| 中海油 | blocked | TLS unexpected EOF |
| 工商银行 | adapter_missing | 200站点，旧TLS兼容，适配器未完成 |

---

## 3. 现有岗位快照统计

> 数据来源：`qiuzhao/data/jobs.json` + `summary.json` + `source_coverage.json`
> 快照合并时间：2026-09-10T10:21:10+08:00

### 3.1 总体统计

| 指标 | 值 |
|---|---|
| 总岗位数 | **9,191** |
| open | 9,089 |
| unverified | 102 |
| expired | 0（当前快照中无） |
| removed | 0（当前快照中无） |
| 集团/机构体系数 | 11 |
| 招聘单位名称标签数 | 567（非法律主体核验） |
| 去重source_url数 | 9,140 |
| 最新复核时间 | **2026-09-10T10:32:38+08:00**（中国联通） |
| 最早复核时间 | 2026-09-10T00:58:02+08:00（建行） |

### 3.2 各来源条数与状态分布

| 来源 | 岗位数 | open | unverified | 最新复核时间 |
|---|---:|---:|---:|---|
| 中国邮政 | 2,648 | 2,648 | 0 | 06:11:26 |
| 中国联通 | 2,569 | 2,569 | 0 | 10:32:38 |
| 中国移动 | 1,610 | 1,610 | 0 | 10:27:43(coverage)/01:08:48(state) |
| 中国航天科工 | 1,165 | 1,114 | 51 | 10:29:15(coverage)/01:09:38(state) |
| 中国能源建设 | 634 | 593 | 41 | 10:28:13(coverage)/01:09:04(state) |
| 国家能源 | 422 | 422 | 0 | 06:46:07 |
| 中国机械科学研究总院 | 72 | 72 | 0 | 10:28:25(coverage)/01:09:11(state) |
| 中国建设银行 | 39 | 39 | 0 | 10:25:09(coverage)/00:58:02(state) |
| 中国银行 | 14 | 14 | 0 | 06:46:41 |
| 中国电信 | 10 | 0 | 10 | 06:46:39 |
| 中国广核 | 8 | 8 | 0 | 10:28:19(coverage)/01:09:07(state) |
| **合计** | **9,191** | **9,089** | **102** | — |

### 3.3 届别分布

| 指标 | 数量 |
|---|---|
| 明确提及2027届 | 4,981 |
| 明确2026届且无2027 | 89（按2027查询不命中） |
| 未披露届别 | 4,105 |

---

## 4. 现有MCP工具Schema

三个工具均通过 `@mcp.tool()` 注册，受 `MeterTools` 中间件鉴权和额度扣减。

### 4.1 jobs_search

**参数：**

| 参数 | 类型 | 约束 | 说明 |
|---|---|---|---|
| city | str \| None | max_length=100 | 城市，如北京；未披露城市不会猜测 |
| major | str \| None | max_length=100 | 专业关键词 |
| cohort | str \| None | max_length=100 | 公告中明确写出的届别，如2027 |
| keyword | str \| None | max_length=200 | 单位/签约主体/岗位关键词 |
| limit | int | 1≤limit≤100, 默认50 | 每页条数 |
| offset | int | ≥0, 默认0 | 翻页偏移 |

**返回字段（envelope）：**
- `data_as_of` / `数据截至时间`：全库最新复核时间
- `source_urls`：去重的原公告URL列表
- `jobs`：岗位列表（公开字段，见数据schema）
- `total`：匹配总数
- `offset`：当前偏移
- `next_offset`：下一页偏移或null
- `suggestion`：无结果时的放宽建议

**匹配逻辑：** city匹配cities数组；major匹配major_requirements_raw和major_tags；cohort优先匹配cohort_raw，回退campaign_cohort_raw；keyword匹配recruitment_unit/contracting_entity/recruiting_unit_raw/parent_unit_raw/hiring_department_raw/job_title/job_category/description_raw。所有条件AND。按published_at倒序。

### 4.2 jobs_deadlines

**参数：**

| 参数 | 类型 | 约束 | 说明 |
|---|---|---|---|
| days | int | 1≤days≤366, 默认7 | 未来N天（含今天） |
| limit | int | 1≤limit≤100, 默认100 | 每页条数 |
| offset | int | ≥0, 默认0 | 翻页偏移 |

**返回字段：** 同envelope + `total`, `days`, `order="deadline_desc"`, `next_offset`, `suggestion`

**筛选逻辑：** 仅纳入deadline_type="explicit"且status不在{removed, expired, unverified}的记录；deadline在[today, today+days]范围内；按deadline倒序。

### 4.3 jobs_detail

**参数：**

| 参数 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | str | min_length=1, max_length=200 | jobs_search返回的岗位id |

**返回字段：** 同envelope + `found`(bool), `suggestion`

**逻辑：** 精确匹配id，返回全部业务字段（排除evidence_path等内部路径）。

---

## 5. 现有测试清单与运行方式

### 5.1 单元测试 — `tests/test_core.py`（6项）

| 测试函数 | 验证内容 |
|---|---|
| `test_atomic_redemption` | 12线程并发兑换同一码仅1次成功；数据库不含明文凭证 |
| `test_atomic_daily_limit` | 220次并发扣额仅200次成功，429拒绝；usage_log精确200条 |
| `test_expiry_product_and_invalid` | 跨产品权限拒绝、无效key拒绝、过期key拒绝 |
| `test_midnight_resets_and_handshake_free` | 午夜跨日额度重置；authorize/握手不扣次 |
| `test_jobs_preserve_facts_and_deadline_order` | 截止日期倒序、届别搜索、空结果建议、过期自动标记、missing返回空 |
| `test_role_cohort_overrides_campaign_title` | 岗位明确2026届不被专场2027标题覆盖；cohort_filter_scope正确标注 |

**运行方式：**
```sh
.venv/bin/python -m pytest -q
```

### 5.2 端到端测试 — `tests/e2e_local.py`

**前置条件：** 使用隔离的 `private/test-access.sqlite3` 启动本地 `127.0.0.1:8768` 服务。

**验证内容：**
- 新码HTTP兑换200、重复码400
- 无key访问MCP 401
- 工具列表=3个且列工具不扣额（200→200）
- 三工具各调用1次，额度200→197
- jobs_search total≥300、jobs_deadlines有结果、detail有found和source_urls
- 过期key访问MCP 403且含"过期"
- 生成Claude Code测试用隔离key和配置

**运行方式：**
```sh
# 先启动本地服务（隔离数据库）
MCP_DB_PATH=private/test-access.sqlite3 MCP_JOBS_PATH=qiuzhao/data/jobs.json \
  .venv/bin/uvicorn core.server:app --host 127.0.0.1 --port 8768
# 另一个终端
.venv/bin/python -m tests.e2e_local
```

### 5.3 样本复核 — `qiuzhao/collector/verify_samples.py`

独立重新读取官方源对照已存记录：邮政详情API 1条、国家能源原页 1条、建行公开API 1条、国聘cam2027和cgnpc各1条。输出 `sample_verification.json`。

```sh
.venv/bin/python -m qiuzhao.collector.verify_samples --output-dir qiuzhao/data
```

---

## 6. 每日任务机制

### 6.1 Cron配置 — `deploy/mcp-suite-qiuzhao.cron`

```
# 主机时区已验证为 Asia/Shanghai (CST)
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
10 6 * * * mcp-suite /opt/mcp-suite/deploy/collector-daily.sh
```

- **时间：** 北京时间每天 06:10
- **执行用户：** mcp-suite
- **脚本：** /opt/mcp-suite/deploy/collector-daily.sh

### 6.2 包装脚本 — `deploy/collector-daily.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /opt/mcp-suite
export PYTHONUNBUFFERED=1
exec 9>/var/lib/mcp-suite/collector.lock
if ! flock -n 9; then exit 0; fi   # 非阻塞锁，已有运行则退出
if python -m qiuzhao.collector.run --output-dir /var/lib/mcp-suite >> collector-cron.log 2>&1; then
  # 成功：写cron-status.json success
else
  # 失败：写cron-status.json failure（含exit_code），保留旧快照，退出码传播
  exit "$rc"
fi
```

**关键机制：**
- **flock非阻塞锁：** `/var/lib/mcp-suite/collector.lock`，若上一次未完成则直接退出（exit 0），避免重叠
- **失败保留：** 采集器内部每个适配器独立try/except，失败的源写alert但不中断其他源；旧快照通过merged字典保留，仅成功的源更新
- **下架标记：** 对complete=True的源，旧记录中不在新列表的标记为removed（国聘按专场complete分组判断）
- **日志：** `collector-cron.log`（stdout/stderr追加）
- **状态文件：** `cron-status.json`（成功/失败+完成时间）、`alerts.json`（源级报警）、`source_state.json`（各源状态）、`summary.json`（汇总）

### 6.3 systemd服务

`deploy/mcp-suite.service` 管理MCP HTTP服务（非采集任务）。采集由cron触发。

---

## 7. 数据Schema（jobs.json每条记录的字段）

> 全库共出现 **47个字段**，不同来源字段集略有差异。基础字段由 `base_job()` 提供，各适配器按需扩展。

### 7.1 基础字段（所有记录必有，来自base_job）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | str | 唯一岗位ID，前缀标识来源（postal-/chn-/telecom-/boc-/ccb-/guopin-） |
| recruitment_unit | str | 集团/机构体系名称（11个值之一） |
| contracting_entity | str | 签约法律主体，未披露时为空字符串（从不推断） |
| job_title | str | 岗位名称 |
| job_category | str | 岗位类别 |
| cities | list[str] | 工作城市列表 |
| major_requirements_raw | str | 专业要求原文 |
| major_tags | list | 专业标签（通常为空） |
| education_raw | str | 学历要求原文 |
| cohort_raw | str | 届别原文（岗位级明确写出的） |
| deadline | str \| None | 截止日期（YYYY-MM-DD），未披露为None |
| deadline_type | str | explicit/undisclosed/until_filled |
| status | str | open/unverified/expired/removed |
| application_url | str | 投递URL |
| source_url | str | 原公告/岗位URL |
| published_at | str \| None | 发布日期 |
| reviewed_at | str | 复核时间（ISO8601+08:00） |
| source_name | str | 来源名称 |
| evidence_path | str | 内部证据文件路径（**不暴露给MCP响应**） |
| description_raw | str | 岗位描述原文 |

### 7.2 扩展字段（部分来源有）

| 字段 | 出现来源 | 说明 |
|---|---|---|
| recruiting_unit_raw | 全部 | 招聘单位原文（发布方标签，非法律主体） |
| parent_unit_raw | chn/ccb | 上级单位 |
| hiring_department_raw | postal/chn/ccb/guopin | 招聘部门 |
| campaign_cohort_raw | boc/ccb/guopin | 专场标题届别（回退匹配用） |
| campaign_url | postal/boc/ccb/guopin | 专场URL |
| announcement_url | postal/boc/ccb | 公告URL |
| announcement_evidence_path | postal/boc/ccb | 公告证据路径（内部） |
| deadline_scope | postal/chn/boc/ccb/guopin | 截止日期来源范围 |
| cohort_scope | postal/ccb | 届别来源范围 |
| education_scope | ccb | 学历来源范围 |
| published_at_scope | postal/ccb/guopin | 发布日期来源范围 |
| job_title_scope | ccb | 岗位名来源范围 |
| requirements_scope | telecom/ccb | 要求来源范围 |
| job_listing_url | ccb | 岗位列表URL |
| source_record_id | postal/ccb/guopin | 源系统原始记录ID |
| source_group_key | guopin | 国聘专场domain |
| source_status_raw | guopin | 源状态原始值 |
| source_is_apply_raw | guopin | 源是否可投递原始值 |
| nature_raw | guopin | 招聘性质原文（校招/社招） |
| recruitment_type_raw | guopin | 招聘类型原文 |
| record_kind | boc/ccb/guopin | 记录类型标识 |
| status_note | telecom | 状态说明 |
| directory_evidence_path | guopin | 国聘目录广告证据路径（内部） |

### 7.3 MCP响应过滤

`Jobs.public()` 方法在返回前：
1. 移除所有以 `evidence_path` 结尾的字段（内部路径不暴露）
2. 添加 `cohort_filter_scope` 字段（role_record/campaign_title_only/undisclosed）
3. 若deadline已过且status≠removed，自动标记为expired

---

## 8. 套餐与鉴权配置

> 仅记录存在性与配置参数，不读取任何密钥/兑换码值。

### 8.1 套餐配置 — `core/store.py` PLANS

```python
PLANS = {
    "qiuzhao-2026": {
        "product": "qiuzhao",
        "price_cny": 39,
        "expires_at": "2027-01-01T00:00:00+08:00",  # 实际失效时间
        "daily_limit": 200
    }
}
```

| 配置项 | 值 |
|---|---|
| 产品名 | qiuzhao |
| 套餐ID | qiuzhao-2026 |
| 价格 | 39元人民币 |
| 有效期至 | 2026-12-31当天结束（实际2027-01-01 00:00:00+08:00失效） |
| 每日调用限额 | 200次（北京时间00:00重置） |
| 兑换码格式 | QZ- + 32位十六进制大写（总长35字符） |
| API key格式 | qz_ + token_urlsafe(32) |

### 8.2 鉴权机制

- **协议：** HTTP Bearer Token（Authorization: Bearer <api_key>）
- **存储：** SQLite（WAL模式），仅存兑换码和key的SHA-256摘要，不存明文
- **表结构：** api_keys, entitlements, redemption_codes, daily_usage, usage_log
- **额度扣减：** `BEGIN IMMEDIATE` 事务 + `UPDATE ... WHERE used<daily_limit` 原子条件更新，并发安全
- **扣次范围：** 仅进入工具执行的调用计1次（包括空结果）；握手、列工具、/usage、/health、/redeem不扣次
- **用量日志：** 仅记匿名key_id、产品、工具名、时间，不记查询参数或简历

### 8.3 库存与数据库

- **首发库存：** `private/qiuzhao-2026-stock-50.txt`（50个兑换码，权限0600，**禁止读取**）
- **本地初始数据库：** `private/access.sqlite3`（权限0600，**禁止读取/覆盖**）
- **生产数据库：** 服务器 `/var/lib/mcp-suite/access.sqlite3`（**禁止覆盖**）
- **测试数据库：** `private/test-access.sqlite3`（隔离测试用）
- **库存状态：** 50/50备货码与远端数据库对应且全部未兑换；活跃测试key为0

### 8.4 安全控制

- 兑换页Origin校验（仅允许savegems.top和本地base_url）
- 请求体大小限制1024字节
- CSP安全头：default-src 'self'，禁止frame-ancestors
- API key长度上限200字符
- 数据库文件权限0600，父目录0700

---

## 9. 能力确认

| 能力 | 状态 | 说明 |
|---|---|---|
| 文件读写 | ✓ | 可读写项目目录下文件；private/目录权限drwx------不可读 |
| 代码执行 | ✓ | Python 3.14.7（.venv）、Node v22.23.2 可用；pytest可运行 |
| 浏览器能力 | 需实测 | 见下方浏览器实测记录 |
| 网络访问 | ✓ | general_search、web.fetch可访问公开网页 |
| 生产环境访问 | ✗（禁止） | 不部署、不替换服务器数据、不变更定时任务、不覆盖access.sqlite3 |

### 浏览器实测

**结果：✓ 浏览器能力可用。**

- `mac_computer_use_tool`：本会话返回"Subagent暂不支持操作电脑相关操作"，不可用
- `computer_use_tool`（bu平面）：**可用**。`seed_browser_use` 模块正常加载，`bu.snapshot()` 成功返回当前浏览器页面DOM树（实测时浏览器打开着字节跳动校招职位页 `jobs.bytedance.com`，viewport 675x811，可正常读取页面元素、链接、文本）
- 可用方法包括：`navigate`, `snapshot`, `click`, `fill_input`, `get_page_text`, `screenshot`, `scroll`, `wait_for_load`, `js`, `new_tab`, `switch_tab` 等
- 结论：后续B阶段如需浏览器渲染获取Forbes完整榜单或动态页面岗位数据，可使用 `computer_use_tool` 的 bu 平面

---

## 10. 扩展约束与兼容性要求

### 10.1 三个现有工具必须保持兼容

新增数据源后，`jobs_search`、`jobs_deadlines`、`jobs_detail` 的参数和返回envelope结构不得变更。新记录必须遵循现有数据schema，至少包含base_job的全部字段。

### 10.2 采集器扩展点

`qiuzhao/collector/run.py` 的 `run()` 方法中，适配器列表为：
```python
[('postal', self.postal), ('chnenergy', ...), ('telecom', self.telecom),
 ('boc', self.boc), ('ccb', lambda: collect_ccb(self)), ('guopin', lambda: collect_guopin(self))]
```

新增适配器需：
1. 实现返回 `list[dict]`（符合base_job schema）的函数
2. 在 `collector.states[name]` 写入状态（含status/checked_at/collected_jobs/complete）
3. 失败时raise Exception，由run()统一捕获写alert
4. complete=True时，run()会自动将旧记录中不在新列表的标记为removed
5. 遵循 `--source` 参数的choices列表

### 10.3 硬性约束回顾

- 禁止读取private/目录
- 禁止修改生产环境
- 不绕过验证码/登录/付费墙/反爬
- 不伪造执行结果
- 保持三工具兼容
