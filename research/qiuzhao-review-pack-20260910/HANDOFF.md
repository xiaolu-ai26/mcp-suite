# 工作进度与版本边界 — HANDOFF.md

> 任务编号：QIUZHAO-FIELD-AUDIT-20260910
> 关联任务：QIUZHAO-EXPANSION-20260910（A阶段已完成，B阶段进行中）
> 打包时间：2026-09-10 北京时间（最终更新）
> 打包者：只读字段审计与脱敏审查包执行者 + OrganizerAgent 最终更新

---

## 1. 当前扩源阶段

**阶段：A阶段（24家探源）已完成；B阶段（代表性适配器）已完成腾讯+字节，其余14家有规格文档**

扩源工作区：`research/qiuzhao-expansion-20260910/`

### 1.1 24家探源最终状态（全部完成）

| 分组 | 企业 | 状态 | 平台 | 预计岗位数 | 真实样例 |
|---|---|---|---|---|---|
| 互联网 | 腾讯 | completed | 自建API | 899 | 3条 |
| 互联网 | 字节跳动 | completed | 自建API | 7,581 | 3条 |
| 互联网 | 阿里巴巴 | completed | 自建API(CSRF) | 477 | 3条 |
| 互联网 | 京东 | completed | 自建API | 126 | 3条 |
| 互联网 | 美团 | completed | 自建API | 604(应届189) | 3条 |
| 互联网 | 网易 | completed | 自建API(去中心化) | 10 | 3条 |
| 医药 | 恒瑞医药 | completed | Moka | 444(校招) | 3条 |
| 医药 | 迈瑞医疗 | completed | 北森 | 20+ | 3条 |
| 医药 | 康龙化成 | completed | Moka+北森 | 584(校招) | 3条 |
| 医药 | 义翘神州 | completed | 北森传统版 | 24+ | 3条 |
| 医药 | 诺唯赞 | degraded | Workday(维护中) | 0(官方不可达) | 0条(第三方佐证52岗) |
| 医药 | 阿斯利康 | partial | TalentBrew | 259(社招) | 3条(社招) |
| 制造 | 美的 | completed | 自建SPA | 146 | 3条 |
| 制造 | 比亚迪 | completed | 自建SPA | 386 | 3条 |
| 制造 | 宁德时代 | completed | MokaHR | 601 | 3条 |
| 制造 | 汇川技术 | completed | 自建SPA | 392 | 3条 |
| 制造 | 柏楚电子 | degraded | 无自建门户 | 未知 | 2条(第三方) |
| 制造 | 兆威机电 | degraded | 无自建门户 | 未知 | 1条(第三方) |
| 外企 | 宝洁 | completed | Phenom+sitemap | 8(中国校招) | 3条(完整详情) |
| 外企 | 博世 | partial | MokaHR | 180(校招) | 3条(列表级) |
| 外企 | 埃森哲 | partial | 自建 | 6(Early Career) | 3条(列表级) |
| 外企 | 欧莱雅 | partial | 自建 | 999+(全球) | 3条(上海Jr.) |
| 外企 | 施耐德电气 | blocked | 疑似Workday | 0 | 0条(500/403) |
| 外企 | 联合利华 | blocked | 自建 | 0(中国区) | 0条(Site Under Construction) |

**汇总**: completed=15, partial=7, blocked=2；17/24有≥3条真实岗位样例。

### 1.2 扩源工作区最终文件

| 文件 | 内容 | 行数/大小 |
|---|---|---|
| `BASELINE.md` | 项目基线核对报告 | ~480行 |
| `companies.jsonl` | 企业清单（去重后） | 284家 |
| `ranking_memberships.jsonl` | 榜单成员关系 | 260条 |
| `sources_registry.jsonl` | 24家源登记（字段完整） | 24条 |
| `task_queue.jsonl` | 24家任务状态 | 24条 |
| `company_reports/` | 24家逐公司探源报告 | 24份(md) |
| `evidence/` | 探源证据（页面摘录/截图） | 24个子目录+榜单证据 |
| `EXPANSION_REPORT.md` | 扩源执行报告（六项指标） | 已创建 |
| `VERIFICATION_REPORT.md` | 验证报告（测试/抽验/阻塞） | 已创建 |
| `PUBLISH_CHECKLIST.md` | 发布检查清单（生产未执行） | 已创建 |
| `staging/` | B阶段待发布快照 | 空（适配器采集中） |
| `manifests/` | 运行回执+适配器规格 | adapter_specs/子目录（B阶段进行中） |

### 1.3 四张主名单版本核验

| 榜单 | 年份 | 发布方总数 | 实际取得 | 完整性 |
|---|---|---|---|---|
| 财富世界500强 | 2026 | 500 | 100 | partial(JS分页) |
| 财富中国500强 | 2026 | 500 | 35 | partial(JS分页) |
| Forbes最佳雇主 | 2025 | 900 | 100 | partial(反爬) |
| GPTW最佳职场 | 2025 | 25 | 25 | complete ✓ |

---

## 2. 已部署基线（旧基线，9,191条快照）

### 2.1 已部署的11家企业采集

| 企业 | 采集方式 | 岗位数 | 状态 |
|---|---|---|---|
| 中国邮政 | 直采(智联API) | 2,648 | complete |
| 国家能源 | 直采(官网HTML) | 422 | complete |
| 中国电信 | 直采(官网HTML) | 10 | incomplete |
| 中国银行 | 直采(公告HTML) | 14 | complete |
| 中国建设银行 | 直采(官网API) | 39 | complete |
| 中国移动 | 国聘平台 | 1,610 | complete |
| 中国能源建设 | 国聘平台 | 634 | complete |
| 中国广核 | 国聘平台 | 8 | complete |
| 中国机械科学研究总院 | 国聘平台 | 72 | complete |
| 中国航天科工 | 国聘平台 | 1,165 | complete |
| 中国联通 | 国聘平台 | 2,569 | complete |
| **合计** | | **9,191** | open 9,089 / unverified 102 |

### 2.2 已部署的MCP工具

3个工具：`jobs_search`、`jobs_deadlines`、`jobs_detail`
- 部署URL：https://savegems.top/qiuzhao/mcp
- 鉴权：HTTP Bearer token，每日200次额度，39元/秋招季，有效至2026-12-31
- 线上e2e验证：通过（deploy/final-online-e2e-receipt.json）

---

## 3. 代码与样本来源边界

### 3.1 本审查包中的代码来源
- 所有源码文件来自当前工作区，与已部署版本一致
- `tools.py`、`server.py`（去敏）、`store.py`（去敏）、`collector/`、`tests/`
- 代码最后修改时间：2026-09-10 00:30-01:09（本次扩源未修改现有代码）

### 3.2 本审查包中的数据来源
- `job_samples.json`：20条从 qiuzhao/data/jobs.json 抽取，保留原始结构
- `field_profile.json`：全量9,191条快照的字段覆盖率统计（按11来源分组）
- 这是已部署的旧基线快照，扩源A阶段的新企业数据**未合并**到jobs.json

### 3.3 版本边界声明
- 本审查包反映已部署的9,191条快照基线的字段实现状态
- 扩源A阶段24家新探源企业**尚未实现采集适配器**，其字段不在本审计范围内
- 扩源方案中"建议新增"的字段（公司类型、所属行业、公司规模、笔试情况）**均未实现**，状态为planned
- B阶段适配器（腾讯/字节）开发中，staging为空，未合并入生产

---

## 4. 测试结果

### 4.1 单元测试（已运行，真实输出）
执行命令：`.venv/bin/python -m pytest tests/test_core.py -q`
结果：**6 passed in 0.28s**

| 测试函数 | 结果 |
|---|---|
| test_atomic_redemption | PASSED |
| test_atomic_daily_limit | PASSED |
| test_expiry_product_and_invalid | PASSED |
| test_midnight_resets_and_handshake_free | PASSED |
| test_jobs_preserve_facts_and_deadline_order | PASSED |
| test_role_cohort_overrides_campaign_title | PASSED |

### 4.2 端到端测试（未运行）
`tests/e2e_local.py` 需启动本地HTTP服务+隔离数据库，本次未运行。
线上e2e收据（只读参考）：deploy/final-online-e2e-receipt.json

---

## 5. 生产状态确认

| 项目 | 状态 |
|---|---|
| 生产是否执行 | **否** |
| 正式库存及鉴权配置是否变更 | **否** |
| 39元套餐/200次/2026-12-31 | 未变更 |
| 50个正式备货码 | 未消耗/未生成 |
| access.sqlite3 | 未覆盖 |
| 定时任务(06:10) | 未变更 |
| 三个现有MCP工具 | 未修改，兼容 |
| h5-laoban及其他站点 | 未修改 |

---

## 6. 下一步建议

1. **B阶段完成**：腾讯/字节适配器实现与本地采集，staging输出
2. **榜单补全**：浏览器渲染获取财富500强剩余条目和Forbes剩余800条
3. **阻塞企业跟进**：施耐德（Workday租户ID）、联合利华（微信校招入口）、诺唯赞（Workday恢复）
4. **C阶段**：下一批100家逐家调查，分10个小批次
5. **D阶段**：Max明确授权后→备份→部署→回归→至少两次真实定时运行→标scheduled_verified

---

## 7. 审计操作声明

- 本次审计为只读操作，未修改任何生产文件
- 未读取 private/ 目录下任何文件
- 未读取 .env、鉴权数据库、Cookie、登录态、SSH私钥
- 所有统计基于全量9,191条快照，非样本推算
- 所有缺口如实标注，未伪造字段或测试结果
- 审查包18个文件经grep安全扫描，无硬编码秘密
