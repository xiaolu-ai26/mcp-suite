# 迈瑞医疗 (Mindray) - 探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**company_slug**: mindray
**采集时间**: 2026-09-10
**执行状态**: 成功

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://career.mindray.com/campus
- **attribution_evidence_excerpt**: 页面显示"mindray"品牌标识、"生命科技，因你亲近"标语、"2027届全球校园招聘"标题；官网 https://www.mindray.com/cn/ 服务热线4007005652，邮箱800online@mindray.com
- **辅助证据**: 职位列表页JS资源来自北森CDN (acdn.bstatics.com)，含 `@beisen/analysis-pms`、`ux-recruitment-portal-2022`，确认北森系统

## 2. 招聘入口

| 字段 | 值 |
|---|---|
| homepage_url | https://www.mindray.com/cn/ |
| official_entry_url | https://career.mindray.com/campus |
| job_list_url | https://career.mindray.com/campus/jobs |
| detail_url_pattern | 北森SPA路由 (待确认具体路径，/campus/jobs/{jobId}返回解析错误) |
| 备用域名 | https://mindray.zhiye.com (北森传统域名，/campus显示维护中) |
| 备用域名2 | https://mindray.italent.cn (北森) |

## 3. 读取方式

| 字段 | 值 |
|---|---|
| access_mode | requires_rendering (北森SPA，职位数据通过JS动态加载，但web.fetch可渲染获取) |
| authentication_required_for_read | false (职位列表可公开浏览) |
| authentication_required_for_apply | true (投递需注册登录北森账号) |
| source_kind | 北森 |
| platform_family | 北森(Beisen) |
| platform_version_hint | ux-recruitment-portal-2022 (北森新版招聘门户) |

## 4. 分页信息

| 字段 | 值 |
|---|---|
| pagination_type | 前端分页/筛选 (北森标准，支持按职位族、地点筛选) |
| expected_total | 未知 (页面未显示总数，首屏加载20个研发族职位) |
| observed_unique_total | 20 (首屏可见，PHD01-10 + RD01-10) |
| completeness | 部分验证 - 仅获取研发族首屏20个职位，营销/供应链/技术支持/职能族需进一步翻页或筛选 |

## 5. 招聘范围

| 字段 | 值 |
|---|---|
| scope_country_region | 中国全国 (深圳、武汉、北京、西安、杭州、南京、成都 + 30+城市) |
| scope_recruitment_type | 校园招聘 (2027届全球校园招聘) |
| scope_campaign | 2027届全球校园招聘 (2026-09-04正式启动) |
| 届别要求 | 2027届全球应届毕业生: 国内本硕2026.8-2027.7毕业; 国内博士/海外本硕博2026.1-2027.7毕业 |
| 职能分布 | 研发、营销、供应链、技术支持、职能 (五大类) |

## 6. 真实岗位样例

### 岗位1: PHD01 系统控制算法研究工程师（博士）
- **岗位编号**: J18899
- **招聘单位**: 迈瑞医疗
- **工作地点**: 广东省·深圳市
- **性质判断**: 校招博士研发岗 (页面标注"校园招聘"，职位编码PHD01，标题含"博士")
- **届别要求**: 2027届博士毕业生
- **职位族**: 研发族
- **详情URL**: 北森SPA (待确认)
- **采集时间**: 2026-09-10

### 岗位2: RD06 软件开发工程师
- **岗位编号**: J18980
- **招聘单位**: 迈瑞医疗
- **工作地点**: 广东省·深圳市, 湖北省·武汉市, 北京市, 陕西省·西安市, 浙江省·杭州市
- **性质判断**: 校招研发岗 (页面标注"校园招聘"，职位编码RD06)
- **届别要求**: 2027届毕业生 (硕士/本科)
- **职位族**: 研发族
- **详情URL**: 北森SPA (待确认)
- **采集时间**: 2026-09-10

### 岗位3: RD07 机械开发工程师
- **岗位编号**: J18981
- **招聘单位**: 迈瑞医疗
- **工作地点**: 广东省·深圳市, 湖北省·武汉市, 江苏省·南京市
- **性质判断**: 校招研发岗 (页面标注"校园招聘")
- **届别要求**: 2027届毕业生
- **职位族**: 研发族
- **详情URL**: 北森SPA (待确认)
- **采集时间**: 2026-09-10

### 岗位4 (补充): PHD07 试剂研发工程师（博士）
- **岗位编号**: J18905
- **工作地点**: 广东省·深圳市, 湖北省·武汉市, 北京市
- **性质**: 校招博士研发岗

### 岗位5 (补充): PHD10 学术专员（超声影像产品）（博士）
- **岗位编号**: J18922
- **工作地点**: 深圳、武汉、西安、北京、成都 (5城)
- **性质**: 校招博士岗

## 7. 任务状态

| 字段 | 值 |
|---|---|
| integration_stage | A阶段-探源完成 |
| run_health | healthy |
| blocker_reason | null (职位详情URL模式待B阶段确认) |

## 备注

- 此前403问题已解决: 使用浏览器UA的web.fetch可正常访问career.mindray.com
- 旧域名 mindray.zhiye.com/campus 显示"系统升级维护中"(8月8日恢复，已过期)，实际招聘已迁移至 career.mindray.com
- 北森系统，首屏仅加载研发族20个职位，其他职位族(营销/供应链/技术支持/职能)需通过页面筛选获取
- 招聘流程: 简历投递 → 综合测评 → 专业面试(线上) → 综合面试(线下) → 语言测评(如需) → Offer发放
- 校招福利: 定制化培养(一对一导师)、免息购房贷款、预借安家费、报销入职交通费、免费过渡酒店
