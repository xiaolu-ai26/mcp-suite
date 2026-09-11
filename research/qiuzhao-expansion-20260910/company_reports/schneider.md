# 施耐德电气(Schneider Electric)中国区校招源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**公司**: 施耐德电气 (Schneider Electric)
**company_slug**: schneider
**采集时间**: 2026-09-10
**状态**: ❌ 阻塞 - 无法获取真实岗位样例

---

## 1. 官方归属证据

| 字段 | 内容 |
|------|------|
| attribution_evidence_url | https://www.se.com/cn/en/careers/overview.jsp |
| attribution_evidence_excerpt | 页面含"为什么选择施耐德电气？"、"专业人才"、"销售及服务"、"数字化与工程"、"学生和青年专业人才"分类，以及按"分类"和"地点"的职位筛选器 |
| 中国官网 | https://www.se.com/cn/ |

## 2. 招聘入口

| 字段 | 内容 |
|------|------|
| homepage_url | https://www.se.com/cn/ |
| official_entry_url | https://www.se.com/cn/en/careers/overview.jsp |
| job_list_url | 未确认 (overview.jsp页面含职位筛选器但具体职位列表为JS渲染) |
| detail_url_pattern | 未确认 (疑似Workday: https://schneiderelectric.wdX.myworkdayjobs.com/...) |

## 3. 读取方式

| 字段 | 内容 |
|------|------|
| access_mode | web.fetch (overview.jsp可访问，但职位列表未渲染) |
| authentication_required_for_read | 未知 (职位列表可能公开) |
| authentication_required_for_apply | 是 |
| source_kind | 官方招聘官网 |
| platform_family | 疑似Workday (外企常用，但租户ID未确认) |
| platform_version_hint | 尝试wd5/wd1均返回500 |

## 4. 分页信息

| 字段 | 内容 |
|------|------|
| pagination_type | 未知 |
| expected_total | 未知 |
| observed_unique_total | 0 |
| completeness | 无数据 |

## 5. 招聘范围

| 字段 | 内容 |
|------|------|
| scope_country_region | 中国 (页面有"学生和青年专业人才"分类) |
| scope_recruitment_type | 未知 (含校招分类但无具体职位) |
| scope_campaign | 未知 |
| 地域分布 | 未知 |
| 届别要求 | 未知 |

## 6. 真实岗位样例

**0条真实岗位样例**

### blocker_reason
1. **Workday API端点返回HTTP 500**:
   - https://schneiderelectric.wd5.myworkdayjobs.com/SchneiderElectric → 500
   - https://schneiderelectric.wd1.myworkdayjobs.com/Careers → 500
2. **se.com招聘页返回403**:
   - https://www.se.com/cn/en/careers/ → HTTP 403 (禁止自动化访问)
   - https://www.se.com/cn/zh/careers/ → link dead
3. **overview.jsp可访问但职位列表为JS动态加载**: web.fetch无法提取具体职位数据
4. 未找到施耐德电气中国区2027校园招聘的专门入口或可访问的职位列表
5. 按硬性约束，不绕过403/反爬限制，登记阻塞原因

## 7. 任务状态

| 字段 | 内容 |
|------|------|
| integration_stage | A阶段-探源阻塞 |
| run_health | blocked |
| blocker_reason | Workday端点返回500，se.com/careers返回403，overview.jsp职位列表JS渲染无法提取；未获取到任何真实岗位样例。建议后续通过浏览器交互或官方微信公众号获取校招职位。 |
