# 京东 (JD) 校招源探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910  
**采集时间**: 2026-09-10  
**采集方式**: 浏览器渲染访问 (mac_computer_use_tool bu 平面)

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://campus.jd.com/
- **attribution_evidence_excerpt**: 招聘站域名 campus.jd.com 为 jd.com 子域名；页脚版权 "Copyright © 2004-2025 京东JD.com 版权所有"；京东集团官网 https://www.jdcorporate.com/
- **homepage_url**: https://www.jd.com/
- **official_entry_url**: https://campus.jd.com/
- **job_list_url**: https://campus.jd.com/#/jobs
- **detail_url_pattern**: https://campus.jd.com/#/details?id={numeric_id}

## 2. 读取方式

- **access_mode**: public_api (Hash路由SPA + 公开API)
- **authentication_required_for_read**: false
- **authentication_required_for_apply**: true (投递简历跳转登录页 passport.jd.com)
- **source_kind**: 企业自建
- **platform_family**: 京东自建招聘系统 (Vue.js SPA, hash路由)
- **platform_version_hint**: /api/wx/ (微信端API路径风格)

### 已发现 API 端点

| 方法 | 端点 | 用途 |
|------|------|------|
| POST | /api/wx/position/page?type=present | 岗位列表/分页 |
| POST | /api/wx/position/dict?type=present | 字典数据(类别/地点) |
| GET | /api/wx/position/getProjectList | 招聘项目列表 |
| GET | /api/wx/position/isLogin | 登录状态 |
| GET | /api/wx/resume/checkResumeAndDelivery | 简历投递检查 |

## 3. 分页信息

- **pagination_type**: page_number (顶部有1/2/3/4标签，API支持分页)
- **expected_total**: 126 (页面显示"职位推荐 126个"，可能为特定筛选条件下的数量)
- **observed_unique_total**: 4 (首页可见职位卡片)
- **completeness**: partial (仅采集首页样例，全量需通过API遍历)

**注意**: 页面顶部的1/2/3/4可能为职位分类标签而非分页。实际分页需通过API参数确认。

## 4. 招聘范围

- **scope_country_region**: 全国为主 (含日本、英国伦敦、中国香港)
- **scope_recruitment_type**: 混合 (应届校招 + 实习 + 顶尖人才专项)
- **scope_campaign**: 2027届秋招 (2027校园招聘)
- **届别要求**: 2026年10月1日至2027年9月30日期间毕业，统招大专及以上学历
- **地域分布**: 全国各省市(88+城市)，含海外(日本、英国伦敦)
- **招聘项目**: 
  - 应届生: JDS-新星计划(8.3-11.30)、TET-管理培训生(7.1-11.30)、新锐之星(8.17-11.30)
  - 实习生: JD YOUNG-实习生计划(全年)、新锐之星实习生
  - TGT专项: 顶尖青年技术天才计划(全年)、顶尖青年技术实习生
- **业务集团**: 京东零售、京东科技、探索研究院、京东物流、京东健康、京东工业、京东产发、国际事业群、CHO/CCO/CFO体系

## 5. 真实岗位样例

| # | 岗位标题 | 类别 | 性质 | 届别要求 | 工作地点 | 所属业务 | 详情URL |
|---|---------|------|------|---------|---------|---------|---------|
| 1 | 销售拓展 | 一线销售/销售类 | 应届 | 2026.10.1-2027.9.30毕业 | 上海/北京/西安/重庆等88城 | 京东物流/京东健康/京东零售 | https://campus.jd.com/#/details?id=9329 |
| 2 | 营业部/集配站站长 | 物流储备类 | 应届 | (新星计划) | 长春/南宁/柳州等269城 | 京东物流 | (列表页可见) |
| 3 | 仓/场地经理 | 物流储备类 | 应届 | (新星计划) | 上海/广州/南宁等60城 | 京东物流 | (列表页可见) |
| 4 | 市场营销 | 市场类 | 应届 | (新星计划) | (列表页可见) | (列表页可见) | (列表页可见) |

**岗位1详情摘要 (销售拓展)**:
- 工作内容: 销售拓展、客户拜访维护、跨部门协调、全供应链服务、商业营运数据分析
- 任职资格: 2026.10.1-2027.9.30毕业，统招大专及以上；擅长沟通谈判；数据敏感度；事业心进取心

## 6. 任务状态

- **integration_stage**: samples_confirmed
- **run_health**: ok
- **blocker_reason**: 无

## 7. 调查过程记录

1. 访问 https://campus.jd.com/ → 确认京东校招首页，"2027校园招聘火热进行中"
2. 首页展示5个人才项目: JD YOUNG实习生、新星计划、TET管培生、顶尖青年技术天才、新锐之星
3. 点击"招聘职位"→ 进入 /#/jobs，显示职位推荐126个
4. 页面为hash路由SPA，筛选条件丰富(项目/类别/地点/业务)
5. 通过 network_requests 发现核心API: POST /api/wx/position/page?type=present
6. 点击岗位"销售拓展"→ 进入 /#/details?id=9329，完整获取岗位描述和届别要求
7. 确认页脚版权声明作为归属证据

## 8. 适配器开发建议

- 优先使用 API: POST /api/wx/position/page?type=present，需分析请求体参数(pageNum, pageSize, projectType, category等)
- 详情页为hash路由 /#/details?id={id}，API可能有对应详情接口
- 岗位地点覆盖极广(88-269城市)，数据中地点为字符串列表
- 全量126条，数量较少，可一次性采集
