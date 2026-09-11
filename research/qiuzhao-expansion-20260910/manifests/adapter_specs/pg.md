# 宝洁 (pg) 适配器规格

## 基本信息
- **Slug**: pg
- **公司全称**: 宝洁（中国）有限公司
- **校招官网**: Phenom 平台托管
- **A阶段预期岗位数**: 8（中国校招）
- **实现优先级**: P3（第三优先级，Phenom平台+sitemap）

## 技术架构
- 平台：Phenom（国际化招聘平台）
- 数据来源：Sitemap + 岗位详情页
- Phenom 平台通常有公开 API，但需确认端点

## 数据采集方式
### 方式一：Sitemap 索引
- Sitemap URL: `https://{company}.phenom.com/sitemap.xml` 或类似
- 从 sitemap 中提取所有岗位详情页 URL
- 逐一抓取详情页解析字段

### 方式二：Phenom API（需探测）
```
GET https://{company}.phenom.com/api/jobs?location=China
POST https://{company}.phenom.com/api/search/jobs
```

## 详情页解析
Phenom 平台详情页通常包含结构化数据（JSON-LD）：
```html
<script type="application/ld+json">
{
  "@type": "JobPosting",
  "title": "...",
  "description": "...",
  "jobLocation": {...},
  "datePosted": "...",
  "hiringOrganization": {...}
}
```
可直接解析 JSON-LD 获取结构化字段。

## 字段映射
| 来源 | 目标字段 | 说明 |
|---------|---------|------|
| JSON-LD `title` | `job_title` | 岗位名称 |
| JSON-LD `jobLocation.address.addressLocality` | `cities` | 工作城市 |
| JSON-LD `description` | `description_raw` | 岗位描述（HTML） |
| JSON-LD `datePosted` | `published_at` | 发布时间 |
| JSON-LD `hiringOrganization.name` | `recruiting_unit_raw` | 招聘组织 |
| URL 中的 ID | `source_record_id`, `id` (前缀 pg-) | 岗位ID |
| 详情页文本 | `education_raw`, `major_requirements_raw` | 从描述中提取 |

## 技术难点和阻塞
1. **岗位数极少**: 仅8个中国校招岗，验证样本有限
2. **Phenom 平台**: 国际平台，可能有地区限制或 CDN 防护
3. **英文内容**: 岗位描述可能为英文，需保留原文
4. **Sitemap 可用性**: 需确认 sitemap 是否包含校招岗位

## 实现建议
1. 先确认宝洁中国校招的 Phenom 域名
2. 检查 sitemap.xml 是否可用
3. 优先使用 JSON-LD 解析（结构化、稳定）
4. 若 API 可用，优先使用 API
5. delay >= 2s（国际平台可能限流）
6. 完整采集预计 30 秒内

## 验收标准
- 采集岗位数 >= 6
- 至少1条岗位可核对
- JSON-LD 解析逻辑正确
- 英文内容正确保留
