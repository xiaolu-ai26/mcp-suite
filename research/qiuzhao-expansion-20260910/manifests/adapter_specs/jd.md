# 京东 (jd) 适配器规格

## 基本信息
- **Slug**: jd
- **公司全称**: 北京京东世纪贸易有限公司
- **校招官网**: https://campus.jd.com
- **A阶段预期岗位数**: 126
- **实现优先级**: P1（第一优先级，公开REST API）

## API端点
- **列表接口**: `POST https://campus.jd.com/api/wx/position/page`
- **详情页**: `https://campus.jd.com/web/jobDetails?jobId={id}`

## 请求格式
```json
{
  "pageNo": 1,
  "pageSize": 10,
  "keyword": "",
  "jobType": 1,
  "cityCode": ""
}
```
- Content-Type: `application/json`
- 可能需要 Referer: `https://campus.jd.com/`

## 分页机制
- 页码分页：`pageNo` 从1开始
- 每页数量：`pageSize`（建议10-20）
- 响应包含 `totalCount` 或 `total` 字段

## 响应字段映射
| 响应字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `jobId` | `source_record_id`, `id` (前缀 jd-) | 岗位ID |
| `jobName` / `positionName` | `job_title` | 岗位名称 |
| `departmentName` | `recruiting_unit_raw` | 招聘部门 |
| `cityName` / `workLocation` | `cities` | 工作城市 |
| `jobCategory` | `job_category` | 岗位类别 |
| `education` | `education_raw` | 学历要求 |
| `majorRequirement` | `major_requirements_raw` | 专业要求 |
| `jobDescription` | `description_raw` | 岗位职责 |
| `jobRequirement` | `requirement_raw` | 任职要求 |
| `publishDate` | `published_at` | 发布日期 |

## 技术难点和阻塞
1. **微信端API**: 接口路径含 `/wx/`，可能原为微信小程序设计，需确认 PC 端是否可直接调用
2. **字段结构**: 京东 API 响应可能有嵌套层级（`data.list`），需首次调用确认
3. **岗位数较少**: 仅126岗，可能部分岗位已关闭，需处理状态字段

## 实现建议
- 直接 POST 调用，无需 CSRF
- delay >= 1.5s
- 完整采集约需 13 页（pageSize=10），预计 30 秒

## 验收标准
- 采集岗位数 >= 100
- 首/中/末页各至少1条岗位可核对
