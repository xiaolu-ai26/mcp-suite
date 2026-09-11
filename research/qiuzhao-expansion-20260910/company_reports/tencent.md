# 腾讯 (Tencent) 校招源探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910  
**采集时间**: 2026-09-10  
**采集方式**: 浏览器渲染访问 (mac_computer_use_tool bu 平面) + web.fetch

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://www.tencent.com/zh-cn/
- **attribution_evidence_excerpt**: 腾讯官网页脚包含"加入我们"链接；招聘站域名 join.qq.com 为腾讯自有域名；CDN 资源域名为 cdn.multilingualres.hr.tencent.com (hr.tencent.com 子域名)；页脚版权声明 "Copyright © 1998 - 2026 Tencent. All Rights Reserved."
- **homepage_url**: https://www.tencent.com/
- **official_entry_url**: https://join.qq.com/
- **job_list_url**: https://join.qq.com/post.html
- **detail_url_pattern**: https://join.qq.com/post_detail.html?postid={numeric_id}

## 2. 读取方式

- **access_mode**: public_api (SPA 渲染 + 公开 REST API)
- **authentication_required_for_read**: false
- **authentication_required_for_apply**: true (投递简历需登录)
- **source_kind**: 企业自建
- **platform_family**: Tencent HR 自建系统 (前端 Vue.js，Element UI 组件)
- **platform_version_hint**: V2Post (JS 文件名含 V2Post_zh-cn.js)

### 已发现 API 端点

| 方法 | 端点 | 用途 |
|------|------|------|
| POST | /api/v1/position/searchPosition | 岗位列表搜索/分页 |
| GET | /api/v1/position/getPositionWorkCities | 工作城市列表 |
| GET | /api/v1/position/getPositionFamily | 岗位类别 |
| GET | /api/v1/position/getRecruitCity | 招聘城市 |
| GET | /api/v1/position/getProjectMapping | 项目映射 |
| GET | /api/v1/dictionary/?types=RecruitType,BusinessGroup,RecruitProjectPostList | 字典数据 |

## 3. 分页信息

- **pagination_type**: page_number
- **expected_total**: 899 (页面显示"共899个岗位")
- **observed_unique_total**: 10 (首页可见，共90页)
- **completeness**: partial (仅采集首页样例，全量需遍历90页API)

## 4. 招聘范围

- **scope_country_region**: 中国内地为主 (深圳总部、北京、上海、广州、成都、杭州、合肥等)
- **scope_recruitment_type**: 混合 (校招应届 + 实习 + 人才专项)
- **scope_campaign**: 2027届秋招 (2027校园招聘)
- **届别要求**: 应届毕业生 (2027届)；实习生含应届实习和日常实习
- **地域分布**: 深圳总部、北京、上海、广州、成都、杭州、合肥等
- **事业群**: CDG(企业发展)、CSIG(云与智慧产业)、IEG(互动娱乐)、PCG(平台与内容)、TEG(技术工程)、WXG(微信)

## 5. 真实岗位样例

| # | 岗位标题 | 类别 | 性质 | 工作地点 | 详情URL | postid |
|---|---------|------|------|---------|---------|--------|
| 1 | AI全栈工程师 | 技术 | 应届毕业生 | 深圳总部/北京/上海/广州/成都/杭州 | https://join.qq.com/post_detail.html?postid=1282707398326592512 | 1282707398326592512 |
| 2 | Agent开发工程师 | 技术 | 应届毕业生 | 深圳总部/北京/上海/广州/成都 | https://join.qq.com/post_detail.html?postid=1282707395466077184 | 1282707395466077184 |
| 3 | AI应用工程师 | 技术 | 应届毕业生 | 深圳总部/北京/上海/广州/成都 | https://join.qq.com/post_detail.html?postid=1282707395466077185 | 1282707395466077185 |

**岗位1详情摘要 (AI全栈工程师)**:
- 岗位描述: 负责产品业务系统全栈开发，构建基于大模型的全链路应用系统(AI能力接入、Agent架构、RAG系统、业务知识库)
- 岗位要求: 熟练掌握主流前后端技术栈；熟练使用AI编程工具；了解大模型原理与推理部署，熟悉RAG/Agent原理；具备系统设计能力
- 面试城市: 远程面试
- 招聘部门: CDG/CSIG/IEG/PCG/TEG/WXG

## 6. 任务状态

- **integration_stage**: samples_confirmed
- **run_health**: ok
- **blocker_reason**: 无

## 7. 调查过程记录

1. 访问 https://join.qq.com/ → 确认腾讯校招首页，导航含"岗位投递"
2. 点击"岗位投递" → 进入 https://join.qq.com/post.html，显示共899个岗位
3. 页面为 Vue.js SPA，DOM 快照不直接渲染岗位卡片，通过 get_page_text() 获取岗位列表文本
4. 通过 bu.find() 定位岗位卡片元素引用，点击进入详情页，确认 URL 模式为 post_detail.html?postid=xxx
5. 通过 bu.network_requests() 发现公开 API 端点，核心为 POST /api/v1/position/searchPosition
6. 访问 https://www.tencent.com/ 确认页脚"加入我们"链接作为归属证据
7. 采集3条真实岗位详情

## 8. 适配器开发建议

- 优先使用 API: POST /api/v1/position/searchPosition，需分析请求体参数 (page, pageSize, recruitType, projectId 等)
- 详情页可通过 postid 直接访问，无需渲染
- 全量采集需遍历 90 页，注意请求频率控制
