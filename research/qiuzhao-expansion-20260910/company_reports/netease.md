# 网易 (NetEase) 校招源探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910  
**采集时间**: 2026-09-10  
**采集方式**: 浏览器渲染访问 (mac_computer_use_tool bu 平面) + web.fetch API验证

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://campus.163.com/
- **attribution_evidence_excerpt**: 招聘站域名 campus.163.com 为 163.com 子域名；页脚 "© 1997-2026 网易公司版权所有 | 浙ICP备17006647号-2"；各业务集团校招均使用163.com子域名(leihuo.163.com, campus.game.163.com)
- **homepage_url**: https://www.163.com/
- **official_entry_url**: https://campus.163.com/app/index
- **job_list_url**: https://campus.163.com/app/job/position?id=103 (网易互联网2027届校招)
- **detail_url_pattern**: https://campus.163.com/app/detail/index?id={numeric_id}

## 2. 读取方式

- **access_mode**: public_api (SPA + 公开REST API)
- **authentication_required_for_read**: false
- **authentication_required_for_apply**: true (投递简历需登录)
- **source_kind**: 企业自建
- **platform_family**: 网易自建招聘系统 (campuspc API)
- **platform_version_hint**: projectId=103 (网易互联网2027届校招项目ID)

### 已发现 API 端点

| 方法 | 端点 | 用途 |
|------|------|------|
| GET | /api/campuspc/position/getJobList?pageSize=10&currentPage=1&projectId=103 | 岗位列表 |
| GET | /api/campuspc/project/navigation/list | 所有校招项目导航 |
| GET | /api/campuspc/project/banner?projectId=103 | 项目Banner |

### 网易校招项目分布(去中心化架构)

| 项目 | URL | projectId |
|------|-----|-----------|
| 网易互联网2027届校园招聘 | https://campus.163.com/app/job/position?id=103 | 103 |
| 网易互娱2027届校园招聘 | https://campus.game.163.com/app/job/position?id=102 | 102 |
| 网易游戏雷火2027届校园招聘 | https://leihuo.163.com/campus/#/full | 独立站 |
| 星火计划2027届人力资源培训生 | https://campus.163.com/app/talents/stars | - |
| 蛋仔派对AI实习生专项 | https://campus.game.163.com/app/job/position?id=75 | 75 |
| 日常实习生 | https://hr.163.com/job-list.html?workType=1 | 独立站 |

## 3. 分页信息

- **pagination_type**: page_number (currentPage参数, pageSize=10)
- **expected_total**: 10 (网易互联网项目id=103，页面显示"到底啦~")
- **observed_unique_total**: 10
- **completeness**: complete (网易互联网项目仅10个岗位，已全部采集)
- **注意**: 网易整体校招岗位分散在多个业务集团独立站点，互联网项目仅10个，互娱和雷火有更多岗位

## 4. 招聘范围

- **scope_country_region**: 中国内地 (北京、杭州为主)
- **scope_recruitment_type**: 混合 (应届校招 + 实习)
- **scope_campaign**: 2027届秋招 (网易互联网2027届校园招聘)
- **届别要求**: 本科及以上学历 (具体见岗位详情)
- **地域分布**: 北京、杭州 (互联网项目)；杭州 (雷火)；多城市 (互娱)
- **招聘项目**: 网易互联网2027届校招、网易互娱2027届校招、网易雷火2027届校招、星火计划HR培训生、蛋仔派对AI实习、日常实习

## 5. 真实岗位样例

### 网易互联网2027届校招 (projectId=103，全部10个岗位)

| # | 岗位标题 | 类别 | 工作地点 | 详情URL |
|---|---------|------|---------|---------|
| 1 | 市场管理培训生-网易有道 | 市场 | 北京 | (列表页可见) |
| 2 | 全栈开发工程师-网易有道 | 技术 | 北京 | (列表页可见) |
| 3 | 语音交互算法工程师-网易有道 | 人工智能 | 杭州、北京 | (列表页可见) |
| 4 | AI Agent 应用开发工程师-网易有道 | 技术 | 北京 | https://campus.163.com/app/detail/index?id=4858 |
| 5 | AI全栈工程师（数据方向）-网易有道 | 技术 | 北京 | (列表页可见) |
| 6 | 算法应用工程师-网易有道 | 技术 | 北京 | (列表页可见) |
| 7 | AI infra工程师（C++）-网易有道 | 技术 | 杭州、北京 | (列表页可见) |
| 8 | 大模型算法工程师-网易有道 | 人工智能 | 杭州、北京 | (列表页可见) |
| 9 | 计算机视觉/多模态大模型算法工程师-网易有道 | 人工智能 | 杭州、北京 | (列表页可见) |
| 10 | 内容极客专项-市场营销 | 市场 | 杭州 | (列表页可见) |

**岗位4详情摘要 (AI Agent 应用开发工程师-网易有道)**:
- 项目: 网易互联网2027届校园招聘
- 地点: 北京 | 类别: 技术 | 发布: 2026-08-27
- 职责: Agent产品大前端交互与应用开发；任务编排、工具调用、RAG/知识库等Agent技术应用
- 要求: 本科及以上，计算机/软件工程相关；熟悉Java/Python/JS/Swift/Kotlin；熟悉Web/iOS/Android/Windows/macOS至少一种；了解Prompt/RAG/Tool Calling
- 加分: Agent/RAG/MCP/Skill/跨端/全栈项目经验
- 面试: 远程面试

### 网易雷火2027届校招(补充样例)
- 虚拟世界架构师（游戏战斗策划）| 游戏策划 | 杭州 | 2027届应届毕业生
- 游戏研发工程师（客户端方向）| 技术 | 杭州 | 2027届应届毕业生
- 场景原画设计师 | 艺术/设计 | 杭州 | 2027届应届毕业生
- 网申截止: 10月15日，分页7页

## 6. 任务状态

- **integration_stage**: samples_confirmed
- **run_health**: ok
- **blocker_reason**: 无 (网易互联网项目仅10个岗位已全部采集；互娱/雷火为独立站点需单独适配)

## 7. 调查过程记录

1. 访问 https://campus.163.com/ → 重定向到 /app/index，首页为视觉落地页
2. 点击"立即投递"→ 进入 /app/recruit/entry，显示按业务集团分流的项目列表
3. 通过 web.fetch 调用导航API /api/campuspc/project/navigation/list，获取所有6个校招项目的精确URL
4. 访问网易互联网2027届校招 /app/job/position?id=103，显示10个岗位(全部为网易有道)，页面底部"到底啦~"
5. 通过 network_requests 发现岗位列表API: GET /api/campuspc/position/getJobList?pageSize=10&currentPage=1&projectId=103
6. 点击岗位"AI Agent 应用开发工程师"→ 进入 /app/detail/index?id=4858，完整获取岗位描述和要求
7. 同时访问雷火校招站 leihuo.163.com/campus，确认其独立岗位列表(7页，杭州，游戏类岗位)
8. 确认页脚版权声明和多域名归属作为官方归属证据

## 8. 适配器开发建议

- 网易互联网项目: API简单，GET /api/campuspc/position/getJobList，projectId=103，仅10条可一次性采集
- 网易整体校招为去中心化架构，需分别适配:
  - 互联网/星火计划: campus.163.com (同一API体系，不同projectId)
  - 互娱: campus.game.163.com (类似API体系，projectId=102/75)
  - 雷火: leihuo.163.com (独立SPA，需单独分析)
  - 日常实习: hr.163.com (独立站点)
- 详情页URL: /app/detail/index?id={id}，可直接构造
- timeStamp参数为当前时间戳，无鉴权
