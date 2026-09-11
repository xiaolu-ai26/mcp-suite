# 美团 (Meituan) 校招源探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910  
**采集时间**: 2026-09-10  
**采集方式**: 浏览器渲染访问 (mac_computer_use_tool bu 平面)

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://zhaopin.meituan.com/web/campus
- **attribution_evidence_excerpt**: 招聘站域名 zhaopin.meituan.com 为 meituan.com 子域名；页脚 "@2026 美团版权所有 京ICP备10211739号"；招聘意见反馈 zhaopin@meituan.com；静态资源 s3plus.meituan.net
- **homepage_url**: https://www.meituan.com/
- **official_entry_url**: https://zhaopin.meituan.com/web/campus
- **job_list_url**: https://zhaopin.meituan.com/web/campus (全部) / https://zhaopin.meituan.com/web/position?hiringType=4_1 (应届校招)
- **detail_url_pattern**: https://zhaopin.meituan.com/web/position/detail?jobUnionId={numeric_id}&highlightType=campus

## 2. 读取方式

- **access_mode**: public_api (SPA + 公开REST API)
- **authentication_required_for_read**: false
- **authentication_required_for_apply**: true (立即申请需登录)
- **source_kind**: 企业自建
- **platform_family**: 美团自建招聘系统 (React/Vue SPA)
- **platform_version_hint**: hiringType=4_1 (应届校招类型标识)

### 已发现 API 端点

| 方法 | 端点 | 用途 |
|------|------|------|
| POST | /api/official/job/getJobList | 岗位列表/搜索 |
| POST | /api/category/allData | 分类筛选数据 |
| GET | /api/official/job/search/enum?enumType=CAMPUS_HIRING | 校招类型枚举 |
| GET | /api/official/job/search/enum?enumType=NEW_BEIDOU_HIRING | 北斗计划枚举 |
| GET | /api/official/job/search/enum?enumType=JF | 职位类别枚举 |
| GET | /api/official/job/search/enum?enumType=BG | 部门枚举 |
| POST | /api/official/city/search | 城市搜索 |
| POST | /api/official/user/current/get | 用户信息 |

## 3. 分页信息

- **pagination_type**: page_number
- **expected_total**: 604 (全部校招职位) / 189 (应届校招筛选后)
- **observed_unique_total**: 10 (首页可见)
- **completeness**: partial (仅采集首页样例，应届校招共19页)

## 4. 招聘范围

- **scope_country_region**: 中国内地 + 香港 + 海外(沙特/巴西/阿联酋等)
- **scope_recruitment_type**: 混合 (应届校招 + 转正实习 + 日常实习)
- **scope_campaign**: 2027届秋招 (应届校招含北斗计划、LongCat大模型人才校招)
- **届别要求**: 应届生 (具体届别要求需查看岗位详情)
- **地域分布**: 北京、上海、深圳、成都、香港、广州、武汉、杭州、西安、重庆、南京、厦门；海外沙特、巴西、阿联酋、科威特、卡塔尔、巴林、阿曼
- **招聘项目**: 应届校招(北斗计划、LongCat大模型人才校招、食杂零售管培生计划)、转正实习、日常实习
- **部门**: 核心本地商业(美团平台/酒店旅行/基础研发平台)、人力资源平台、Keeta、软硬件服务(无人车业务部)等

## 5. 真实岗位样例

### 应届校招岗位

| # | 岗位标题 | 性质 | 工作地点 | 更新日期 |
|---|---------|------|---------|---------|
| 1 | HR服务与流程优化岗（AI+HR服务方向） | 应届 | 北京 | 2026/09/01 |
| 2 | 人力资源数字化与AI产品经理 | 应届 | 北京 | 2026/09/01 |
| 3 | 【北斗】世界模型算法工程师 | 应届 | 北京/深圳 | 2026/08/31 |
| 4 | 【北斗】具身智能运控算法研究员 | 应届 | 北京/深圳 | 2026/08/31 |
| 5 | 大模型数据算法工程师 | 应届 | 北京 | 2026/08/27 |
| 6 | 飞行器设计工程师 | 应届 | 深圳 | 2026/08/18 |
| 7 | 战略与投资分析师 | 应届 | 北京/上海/深圳 | 2026/08/17 |

### 日常实习岗位

| # | 岗位标题 | 性质 | 工作地点 | 部门 | 详情URL |
|---|---------|------|---------|------|---------|
| 1 | 招聘HR实习生（AI方向） | 日常实习 | 北京 | 人力资源平台 | https://zhaopin.meituan.com/web/position/detail?jobUnionId=4306214875&highlightType=campus |
| 2 | Agent开发实习生（AI 产品方向） | 日常实习 | 成都 | 核心本地商业-美团平台 | (列表页可见) |
| 3 | Keeta Ads 商业产品实习生 | 日常实习 | 北京 | Keeta | (列表页可见) |

**实习岗详情摘要 (Agent开发实习生)**:
- 职责: AI Agent核心系统开发(Prompt工程、Chain、Harness、Skills模块)、功能模块实现、性能调优、技术调研
- 要求: 熟悉Java/Python等；计算机基础扎实；熟悉SQL；对大模型应用/Agent/Prompt工程有兴趣
- 优先: 大模型应用开发经验、Agentic系统经验(Claude Code/DeepAgent/LangGraph)、技能模块加载经验

## 6. 任务状态

- **integration_stage**: samples_confirmed
- **run_health**: ok
- **blocker_reason**: 无

## 7. 调查过程记录

1. 访问 https://campus.meituan.com/ → 重定向到 https://zhaopin.meituan.com/web/campus
2. 校招首页显示全部校招职位604个，含应届校招、转正实习、日常实习
3. 首页默认显示日常实习岗位，通过JS点击"应届校招"筛选 → URL变为 /web/position?hiringType=4_1
4. 应届校招筛选后显示189个职位，19页
5. 通过 network_requests 发现核心API: POST /api/official/job/getJobList
6. 点击实习岗位确认详情URL模式: /web/position/detail?jobUnionId={id}&highlightType=campus
7. 确认页脚版权声明和域名归属作为官方归属证据

## 8. 适配器开发建议

- 优先使用 API: POST /api/official/job/getJobList，需分析请求体参数(page, pageSize, hiringType, category, city等)
- hiringType=4_1 可筛选应届校招，其他类型可通过 /search/enum 接口获取
- 详情页URL可直接通过jobUnionId构造，highlightType=campus为校招标识
- 应届校招189条(19页)，全部校招604条，可分类型采集
