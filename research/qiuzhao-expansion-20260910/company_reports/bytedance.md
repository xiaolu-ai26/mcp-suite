# 字节跳动 (ByteDance) 校招源探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910  
**采集时间**: 2026-09-10  
**采集方式**: 浏览器渲染访问 (mac_computer_use_tool bu 平面)

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://www.bytedance.com/
- **attribution_evidence_excerpt**: 字节跳动官网页脚含"加入我们"、"招聘官网"链接；招聘站域名 jobs.bytedance.com 为 bytedance.com 子域名；静态资源域 lf3-static.bytednsdoc.com；API 系统标识 people-suite
- **homepage_url**: https://www.bytedance.com/
- **official_entry_url**: https://jobs.bytedance.com/campus
- **job_list_url**: https://jobs.bytedance.com/campus/position
- **detail_url_pattern**: https://jobs.bytedance.com/campus/position/{numeric_id}/detail

## 2. 读取方式

- **access_mode**: public_api (SPA 渲染 + 公开 REST API)
- **authentication_required_for_read**: false
- **authentication_required_for_apply**: true (投递需登录)
- **source_kind**: 企业自建
- **platform_family**: ByteDance People Suite (字节跳动自建人力招聘系统)
- **platform_version_hint**: portal_type=3 (校招门户标识)

### 已发现 API 端点

| 方法 | 端点 | 用途 |
|------|------|------|
| POST | /api/v1/search/job/posts | 岗位搜索/列表 (offset分页) |
| GET | /api/v1/config/job/filters/3 | 筛选器配置 |
| GET | /api/v1/user/mobile/login_status | 登录状态检查 |
| GET | /api/v1/website/agent/config | AI助手配置 |
| GET | /api/v1/ip/location | IP定位 |

**search/job/posts 参数**: keyword, limit(默认10), offset, job_category_id_list, tag_id_list, location_code_list, subject_id_list, recruitment_id_list, portal_type=3(校招), job_function_id

## 3. 分页信息

- **pagination_type**: offset
- **expected_total**: 7581 (页面显示"开启新的工作（7581）")
- **observed_unique_total**: 10 (首页可见，limit=10)
- **completeness**: partial (仅采集首页样例，全量需遍历 offset 0~7580)

## 4. 招聘范围

- **scope_country_region**: 全球 (中国内地为主，含香港、新加坡、首尔、东京、悉尼、洛杉矶、纽约、西雅图、伦敦、巴黎等)
- **scope_recruitment_type**: 混合 (正式校招 + 实习)
- **scope_campaign**: 2027届秋招 (2027届校园招聘)
- **届别要求**: 2027届获得本科及以上学历 (正式岗)；实习含日常实习(全体在校生)和ByteIntern(2027届毕业生)
- **地域分布**: 北京、上海、深圳、杭州、广州、成都、西安、香港、新加坡、首尔、东京、悉尼、洛杉矶、纽约、西雅图、圣何塞、伦敦、巴黎、都柏林等
- **招聘项目**: 2027届校园招聘、2027届前沿技术领域人才校招、2027届Seed大模型人才校招、前沿技术领域人才实习招聘、Seed大模型人才实习招聘、日常实习、ByteIntern

## 5. 真实岗位样例

| # | 岗位标题 | 类别 | 性质 | 届别/项目 | 工作地点 | 职位ID | 详情URL |
|---|---------|------|------|----------|---------|--------|---------|
| 1 | 大数据AI工程师 - 数据BP | 研发-大数据 | 正式 | 2027届校园招聘 | 北京/杭州/上海/深圳 | A177077 | https://jobs.bytedance.com/campus/position/7682636037198694709/detail |
| 2 | AI产品经理（用户/社交方向）- TikTok | 产品 | 正式 | 2027届校园招聘 | 北京 | A242469A | (列表页可见) |
| 3 | 广告架构工程师 - 中国交易与广告 | 研发-后端 | 正式 | 2027届校园招聘 | 北京/上海/杭州等4城 | A155751 | (列表页可见) |
| 4 | 城市营销实习生 - 抖音生活服务 | 运营 | 实习 | 日常实习 | 北京 | A139998 | https://jobs.bytedance.com/campus/position/7683130603059005749/detail |

**岗位1详情摘要 (大数据AI工程师 - 数据BP)**:
- 团队: 负责字节跳动泛抖音、国际化、创新与中台等业务的数据BP
- 职责: 海量数据全链路建设、数据解决方案、SQL/ETL开发、LLM提升数据开发效率、AI应用数据基建
- 要求: 2027届本科及以上，计算机/数学/大数据相关专业；扎实计算机基础；熟练至少一门主流编程语言；有分布式系统/数据挖掘论文或开源项目加分

## 6. 任务状态

- **integration_stage**: samples_confirmed
- **run_health**: ok
- **blocker_reason**: 无

## 7. 调查过程记录

1. 访问 https://jobs.bytedance.com/campus → 确认字节跳动校招首页
2. 关闭AI助手弹窗，点击"职位"→ 进入 /campus/position，显示7581个岗位
3. 页面直接内联展示岗位完整描述（团队介绍、职责、要求），无需点击详情即可读取
4. 通过 bu.network_requests() 发现核心API: POST /api/v1/search/job/posts，offset分页
5. 验证岗位详情页URL模式: /campus/position/{id}/detail
6. 访问 https://www.bytedance.com/ 确认页脚"加入我们"、"招聘官网"链接
7. 采集4条真实岗位（含完整详情）

## 8. 适配器开发建议

- 优先使用 API: POST /api/v1/search/job/posts，portal_type=3 限定校招，offset从0开始每次+10
- 列表API已返回完整岗位描述（团队介绍、职责、要求），无需额外请求详情页
- 岗位ID有两种: 内部numeric_id(URL中) 和 职位ID(如A177077，页面展示)
- 全量7581条，约759页API请求，注意频率控制
