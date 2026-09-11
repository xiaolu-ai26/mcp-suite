# 联合利华(Unilever)中国区校招源报告

**任务编号**: QIUZHAO-EXPANSION-20260910
**公司**: 联合利华 (Unilever)
**company_slug**: unilever
**采集时间**: 2026-09-10
**状态**: ❌ 阻塞 - 中国区校招职位无法通过URL筛选获取

---

## 1. 官方归属证据

| 字段 | 内容 |
|------|------|
| attribution_evidence_url | https://careers.unilever.com/ |
| attribution_evidence_excerpt | 页面标题"A bright, new future"，摘录"Every day, 3.4 billion people around the world enjoy our products - from groundbreaking brands like Hellmann's, Domestos, Dove and Rexona..."，含GBS/Customer Development/R&D/Supply Chain/Marketing/Finance/HR等职能分类 |
| 中国官网 | https://www.unilever.com.cn/ |
| 中国招聘页 | https://www.unilever.com.cn/careers/ → "Site Under Construction" |

## 2. 招聘入口

| 字段 | 内容 |
|------|------|
| homepage_url | https://www.unilever.com.cn/ |
| official_entry_url | https://careers.unilever.com/ |
| job_list_url | https://careers.unilever.com/en/search-jobs |
| detail_url_pattern | 未确认 (职位列表页链接未暴露具体URL) |

## 3. 读取方式

| 字段 | 内容 |
|------|------|
| access_mode | web.fetch (search-jobs页可渲染全球职位列表) |
| authentication_required_for_read | 否 |
| authentication_required_for_apply | 是 |
| source_kind | 官方全球招聘官网 |
| platform_family | 联合利华自建招聘平台 |
| platform_version_hint | 全球255职位，37页 |

## 4. 分页信息

| 字段 | 内容 |
|------|------|
| pagination_type | 页码分页 (Page 1/37, Go/Prev/Next) |
| expected_total | 255 (全球) |
| observed_unique_total | 255 (全球)，中国区0 (无法筛选) |
| completeness | 全球职位列表可访问，中国区无法通过URL筛选 |

## 5. 招聘范围

| 字段 | 内容 |
|------|------|
| scope_country_region | 全球 (中国区招聘页建设中) |
| scope_recruitment_type | 全球社招为主，中国区UFLP校招已启动 |
| scope_campaign | **UFLP 2027管理培训生招聘已启动** (确认来源: 交大就业 2026-09-06) |
| 地域分布 | 全球职位分布: 菲律宾、加拿大、巴西、墨西哥、美国等；中国区职位未在全球列表前7页出现 |
| 届别要求 | UFLP面向应届毕业生(具体时间窗口未获取) |

## 6. 真实岗位样例

**0条中国区校招真实岗位样例**

### blocker_reason
1. **中国区招聘页建设中**: https://www.unilever.com.cn/careers/ 返回"Site Under Construction. Please check back at a later date."
2. **全球招聘页URL参数过滤不生效**:
   - ?location=China → 仍显示255个全球职位
   - ?keyword=graduate&location=China → 仍显示255个全球职位
   - ?keyword=trainee&location=Shanghai → 仍显示255个全球职位
   - 筛选功能为纯前端JS交互，无法通过URL参数触发
3. **UFLP 2027校招已确认启动**，但官方申请入口未在全球招聘页找到，可能通过微信公众号或专门校招网站
4. 全球职位列表前7页均为菲律宾(Cavite)、加拿大(Toronto)、巴西(Rio de Janeiro)、墨西哥(Toluca)、美国(Jefferson City/Hoboken)等地区职位，未发现明确标注为China/Shanghai的校招/管培岗位
5. 按硬性约束，不伪造结果，登记阻塞原因

### 全球职位样例(非中国区，仅作平台功能佐证)
1. Rigids Area Engineer - Cavite, Central Luzon (菲律宾)
2. Senior Key Account Manager - Costco & Dollar/Value - Toronto, Ontario (加拿大)
3. Senior Supply Chain Financial Analyst - Foods - Hoboken, NJ (美国)

## 7. 任务状态

| 字段 | 内容 |
|------|------|
| integration_stage | A阶段-探源阻塞 |
| run_health | blocked |
| blocker_reason | 中国区招聘页"Site Under Construction"；全球招聘页URL参数过滤不生效(纯前端JS)，无法筛选中国区职位；UFLP 2027校招已确认启动但申请入口未在官网找到。建议后续通过浏览器交互筛选全球职位，或关注联合利华中国官方微信公众号获取校招入口。 |
