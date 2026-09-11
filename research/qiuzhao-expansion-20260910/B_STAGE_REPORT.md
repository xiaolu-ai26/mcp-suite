# B阶段适配器实现报告 — 秋招MCP扩源项目

**任务编号**: QIUZHAO-EXPANSION-20260910
**阶段**: B（适配器实现）
**执行日期**: 2026-09-10
**执行人**: B阶段适配器实现执行者

---

## 1. 已实现适配器

| # | 企业 | Slug | 适配器文件 | 状态 |
|---|------|------|-----------|------|
| 1 | 腾讯 | tencent | `qiuzhao/collector/tencent.py` | ✅ 可运行，完整采集 |
| 2 | 字节跳动 | bytedance | `qiuzhao/collector/bytedance.py` | ✅ 可运行，API可达但校招岗位为0（见第4节） |

**实现数量**: 2 / 2（B阶段要求的两个适配器均已实现并实际运行）

---

## 2. 各适配器采集结果

### 2.1 腾讯 (tencent)

| 指标 | 值 |
|------|-----|
| API端点 | `POST https://join.qq.com/api/v1/position/searchPosition` |
| 分页方式 | `pageIndex` / `pageSize`（camelCase，非A阶段记录的`page_number`） |
| 每页数量 | 100 |
| 预期岗位总数 | 814（API返回`count`字段） |
| 实际采集岗位数 | **814** |
| 唯一source_id数 | 814 |
| 总页数 | 9 |
| 扫描页数 | 9 |
| 采集完整性 | ✅ 完整（collected == expected） |
| 错误数 | 0 |
| 运行时长 | ~11秒（9次请求，delay=1s） |

**首/中/末页样例核对**:

| 位置 | ID | 岗位名称 | 城市 | 详情URL |
|------|-----|---------|------|---------|
| 首页(第1页) | tencent-1282707398326592512 | AI全栈工程师 | 深圳、北京、上海、广州、成都、杭州 | https://join.qq.com/post_detail.html?postid=1282707398326592512 |
| 中页(第5页) | tencent-1282064456142398464 | 微信小微主动推荐 - 主动智能与持续学习 Agent 研究 | 广州 | https://join.qq.com/post_detail.html?postid=1282064456142398464 |
| 末页(第9页) | tencent--6 | 项目实习生-职能 | 深圳、北京、上海、广州、成都 | https://join.qq.com/post_detail.html?postid=-6 |

**字段映射**:
- `postId` → `source_record_id` / `id`（前缀 `tencent-`）
- `positionTitle` → `job_title`
- `workCities`（空格分隔）→ `cities`（列表，"深圳总部"规范化为"深圳"）
- `positionFamily`（数字）→ `job_category`（映射为技术研发/产品/设计等）
- `bgs`（事业群缩写）→ `recruiting_unit_raw` / `hiring_department_raw`
- `projectName` / `recruitLabelName` → `cohort_raw` / `campaign_cohort_raw`

**已知限制**:
- API同时返回校招和实习岗位，无明确的校招过滤参数
- 列表API不含完整岗位描述，需详情页二次抓取
- 未披露截止日期
- 末页存在`postId=-6`的异常记录（实习生岗位），已保留原始数据

### 2.2 字节跳动 (bytedance)

| 指标 | 值 |
|------|-----|
| API端点 | `POST https://jobs.bytedance.com/api/v1/search/job/posts` |
| 分页方式 | `offset` / `limit` |
| 每页数量 | 100 |
| API返回总数 | 10000（**API硬上限**，实际总数可能超过） |
| 实际采集岗位数 | **10000** |
| 唯一source_id数 | 10000 |
| 扫描页数 | 100 |
| 采集完整性 | ✅ 达到API上限（offset 0→9900） |
| 校招岗位数 | **0**（在10000条样本中） |
| 社招岗位数 | 10000（100%） |
| 错误数 | 0 |
| 运行时长 | ~5分钟（100次请求，delay=1s） |

**首/中/末页样例核对**:

| 位置 | ID | 岗位名称 | 城市 | 详情URL |
|------|-----|---------|------|---------|
| 首页(offset=0) | bytedance-7683050653016951045 | 游戏创意广告编导（AI短剧方向）- OAK Studio | 北京、广州 | https://jobs.bytedance.com/campus/position/7683050653016951045/detail |
| 中页(offset=5000) | bytedance-7638474435041970437 | 商业产品经理（AI变现方向）-中国广告产品 | 北京 | https://jobs.bytedance.com/campus/position/7638474435041970437/detail |
| 末页(offset=9900) | bytedance-7621834588668938501 | APaaS实施业务顾问-信息系统 | — | https://jobs.bytedance.com/campus/position/7621834588668938501/detail |

**字段映射**:
- `id` → `source_record_id` / `id`（前缀 `bytedance-`）
- `title` → `job_title`
- `job_category.name` → `job_category`
- `city_list` / `city_info.name` → `cities`
- `description` + `requirement` → `description_raw`（截断至5000字符）
- `publish_time`（毫秒时间戳）→ `published_at`
- `recruit_type.parent.name` → `recruitment_type_parent_raw`（用于区分校招/社招）
- `job_post_info.address_list` → `address_list`

---

## 3. 关键发现与阻塞

### 3.1 腾讯API分页参数修正（A阶段信息偏差）

A阶段记录腾讯API使用`page_number`分页，但实际探测发现：
- **正确参数名为`pageIndex`**（camelCase），`page_number`被API忽略，导致所有页返回相同的前20条
- **正确参数名为`pageSize`**（camelCase），`page_size`同样被忽略
- `pageSize=100`可用，814岗仅需9页（A阶段记录的90页是基于page_size=10的估算）
- 此修正已在适配器中实现并验证

### 3.2 字节跳动校招岗位缺失（严重发现）

**使用`portal_type=2`（A阶段记录的校招门户参数）调用API，在10000条返回结果中，0条为校招岗位，100%为社招（`recruit_type.parent.name = "社招"`）。**

已排查的参数组合：
- `portal_type=2` → 100%社招
- `portal_type=3` → 100%社招
- `portal_type=1,4,5` → API返回空响应
- `recruitment_id_list=["1"]` → API返回空响应
- 尝试`/api/v1/search/recruitment/list`端点 → 404

**可能原因**:
1. 字节跳动2027届校招尚未正式启动（当前为2026年9月，部分企业校招在9月中下旬启动）
2. 校招岗位使用独立的API端点或`recruitment_id`过滤，需通过浏览器DevTools捕获校招页面实际请求
3. A阶段记录的7581岗可能是在不同时间点探测的结果

**影响**: 字节适配器代码可运行、API可达、分页正常，但当前无法采集到校招岗位。采集到的10000条均为社招岗位，不适合直接纳入秋招岗位库。

**后续行动**: C阶段需用浏览器访问`https://jobs.bytedance.com/campus/position`，通过DevTools捕获实际的校招API请求参数（特别是`recruitment_id_list`的正确值）。

---

## 4. 基线回归测试结果

```
$ .venv/bin/python -m pytest tests/test_core.py -q
......                                                                   [100%]
6 passed in 0.22s
```

| 测试项 | 结果 |
|--------|------|
| test_atomic_redemption | ✅ PASS |
| test_atomic_daily_limit | ✅ PASS |
| test_expiry_product_and_invalid | ✅ PASS |
| test_midnight_resets_and_handshake_free | ✅ PASS |
| test_jobs_preserve_facts_and_deadline_order | ✅ PASS |
| test_role_cohort_overrides_campaign_title | ✅ PASS |

**结论**: 6/6通过。新适配器（tencent.py、bytedance.py）为独立新增文件，未修改任何现有代码，不影响核心功能。

---

## 5. 适配器规格清单

已完成 **14份** 适配器规格文档（A阶段列出16家候选，减去已实现的2家=14家；任务要求12份，超额完成2份），位于 `manifests/adapter_specs/`：

### 第一优先级（公开REST API）— 4份
| Slug | 企业 | 预期岗位 | 主要难点 |
|------|------|---------|---------|
| alibaba | 阿里巴巴 | 477 | CSRF token机制 |
| jd | 京东 | 126 | 微信端API兼容性 |
| meituan | 美团 | 604(应届189) | jobType过滤校招 |
| netease | 网易 | 10(互联网项目) | projectId多项目遍历 |

### 第二优先级（Moka/北森系统）— 6份
| Slug | 企业 | 预期岗位 | 系统 | 主要难点 |
|------|------|---------|------|---------|
| hengrui | 恒瑞医药 | 444 | Moka | campusId提取、版本差异 |
| pharmaron | 康龙化成 | 584 | Moka | 域名确认、多基地城市 |
| catl | 宁德时代 | 601 | MokaHR | MokaHR与Moka版本差异 |
| bosch | 博世 | 180 | MokaHR | 双语内容、域名确认 |
| mindray | 迈瑞医疗 | 20+ | 北森 | 北森版本多样性、token |
| sinobiological | 义翘神州 | 24 | 北森传统版 | 无JSON API，需HTML解析 |

### 第三优先级（自建SPA/Phenom）— 4份
| Slug | 企业 | 预期岗位 | 技术架构 | 主要难点 |
|------|------|---------|---------|---------|
| midea | 美的 | 146 | Vue SPA | 需浏览器捕获XHR API |
| byd | 比亚迪 | 386 | Vue SPA | 需浏览器捕获XHR API |
| inovance | 汇川技术 | 392 | Vue SPA | 需浏览器捕获XHR API |
| pg | 宝洁 | 8 | Phenom平台 | sitemap+JSON-LD解析 |

---

## 6. 未实现项和阻塞原因

| 项 | 状态 | 原因 |
|----|------|------|
| 字节跳动校招岗位采集 | ⚠️ 部分完成 | 适配器可运行，但API当前返回0条校招岗位（100%社招）。需C阶段用浏览器捕获校招专用API参数 |
| 其余14家适配器实现 | ⏸️ 仅规格 | B阶段范围仅要求实现腾讯和字节，其余仅输出规格文档 |
| 腾讯岗位详情描述 | ⚠️ 未采集 | 列表API不含完整描述，需详情页二次抓取（B阶段未要求） |
| 字节API 10000上限以上岗位 | ⚠️ 未采集 | API硬上限10000，超出部分需按城市/类别分片请求 |
| 阿里巴巴CSRF token | ⏸️ 未实现 | 仅规格阶段，C阶段实现 |

---

## 7. 生产部署前必须完成的事项

### 7.1 代码层面
1. **字节校招参数确认**: 必须通过浏览器DevTools捕获字节校招页面的实际API请求，找到正确的`recruitment_id_list`或其他校招过滤参数，否则字节适配器无法采集到校招岗位
2. **腾讯实习岗位过滤**: 需添加`recruitLabelName`或`projectName`过滤逻辑，排除实习生岗位（当前814条中包含实习岗）
3. **详情页描述采集**: 腾讯和字节的列表API均不含完整岗位描述，需评估是否增加详情页二次请求
4. **集成到run.py**: 当前适配器为独立运行，需在C阶段评估是否集成到主调度器（需修改run.py，B阶段约束禁止）

### 7.2 数据层面
5. **数据schema兼容验证**: 新适配器输出的字段需与`qiuzhao/data/jobs.json`的现有schema完全兼容，特别是`cohort_raw`、`deadline`、`status`等字段的填充逻辑
6. **去重策略**: 腾讯`postId=-6`等异常ID需处理，避免与其他来源ID冲突
7. **字节社招数据处理**: 当前采集的10000条社招岗位不应纳入秋招岗位库，需在校招参数确认后重新采集

### 7.3 运维层面
8. **限流策略验证**: 生产环境需确认各API的安全请求频率，当前delay=1s为测试值
9. **错误重试机制**: 当前适配器遇到API错误即停止，生产环境需增加指数退避重试
10. **监控告警**: 需将新适配器接入现有的`alerts.json`和`source_state.json`监控体系

---

## 8. 文件清单

### 新增代码文件
- `qiuzhao/collector/tencent.py` — 腾讯适配器（9.7KB）
- `qiuzhao/collector/bytedance.py` — 字节跳动适配器（12.7KB）

### 采集输出
- `staging/tencent_jobs.json` — 814条腾讯岗位
- `staging/bytedance_jobs.json` — 10000条字节岗位（社招）
- `staging/tencent_pending/` — 腾讯采集完整输出（含evidence）
- `staging/bytedance_pending/` — 字节采集完整输出（含evidence）

### 运行回执
- `manifests/tencent_run.json` — 腾讯运行manifest
- `manifests/bytedance_run.json` — 字节运行manifest

### 适配器规格
- `manifests/adapter_specs/` — 14份规格文档（alibaba, jd, meituan, netease, hengrui, pharmaron, catl, bosch, mindray, sinobiological, midea, byd, inovance, pg）

### 本报告
- `B_STAGE_REPORT.md` — 本文件

---

## 9. 约束遵守情况

| 约束 | 遵守情况 |
|------|---------|
| 禁止读取private/目录 | ✅ 未触碰 |
| 禁止修改生产（不部署、不替换服务器数据、不变更定时任务、不覆盖access.sqlite3、不改jobs.json） | ✅ 未触碰 |
| 不修改现有代码文件（run.py、ccb.py、guopin.py、tools.py、store.py、server.py） | ✅ 仅新增tencent.py和bytedance.py |
| 新适配器代码放在qiuzhao/collector/下的新文件中 | ✅ 已遵守 |
| 不绕过验证码、登录、付费墙、403/429 | ✅ 所有API均为公开匿名访问 |
| 不伪造执行结果、测试输出、命令回执 | ✅ 所有数据均为实际运行结果 |
| 保持三个现有工具兼容 | ✅ 基线测试6/6通过，未修改现有代码 |

---

**报告完成时间**: 2026-09-10 12:05 CST
