# 阿里巴巴 (alibaba) 适配器规格

## 基本信息
- **Slug**: alibaba
- **公司全称**: 阿里巴巴集团控股有限公司
- **校招官网**: https://campus.alibaba.com
- **A阶段预期岗位数**: 477
- **实现优先级**: P1（第一优先级，公开REST API）

## API端点
- **列表接口**: `POST https://campus-talent.alibaba.com/position/search`
- **详情页**: `https://campus.alibaba.com/positionDetail.htm?postId={id}`

## 请求格式
```json
{
  "pageNo": 1,
  "pageSize": 10,
  "keyword": "",
  "recruitType": "CAMPUS",
  "deptCodes": [],
  "cityCodes": []
}
```
- Content-Type: `application/json`
- 需要 CSRF token：首次 GET 校招首页获取 cookie 中的 `_csrf_token`，后续请求 header 携带 `X-CSRF-TOKEN`

## 分页机制
- 页码分页：`pageNo` 从1开始
- 每页数量：`pageSize`（建议10-50）
- 响应包含 `total` 字段，需遍历至 `pageNo * pageSize >= total`

## 响应字段映射
| 响应字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `postId` | `source_record_id`, `id` (前缀 alibaba-) | 岗位唯一ID |
| `name` / `positionName` | `job_title` | 岗位名称 |
| `deptName` | `recruiting_unit_raw`, `hiring_department_raw` | 部门/事业群 |
| `cityName` / `workCity` | `cities` | 工作城市（可能为列表） |
| `categoryName` | `job_category` | 岗位类别 |
| `education` | `education_raw` | 学历要求 |
| `major` | `major_requirements_raw` | 专业要求 |
| `description` | `description_raw` | 岗位描述 |
| `requirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |
| `recruitType` | `cohort_raw` | 招聘类型（校招/实习） |

## 技术难点和阻塞
1. **CSRF Token**: 必须先访问首页获取 cookie 和 CSRF token，否则 API 返回 403
2. **请求频率**: 阿里接口有较严格的限流，建议 delay >= 2s
3. **字段命名**: 阿里 API 字段命名可能随版本变化，需首次调用后确认
4. **岗位详情**: 列表接口可能不含完整描述，需二次调用详情接口

## 实现建议
- 先用 `requests.Session` 保持 cookie
- GET `https://campus-talent.alibaba.com/` 获取 CSRF token
- POST 列表接口时携带 `X-CSRF-TOKEN` header
- 完整采集约需 48 页（pageSize=10），预计 2-3 分钟

## 验收标准
- 采集岗位数 >= 400（与预期 477 偏差 <= 15%）
- 首/中/末页各至少1条岗位可核对
- 详情 URL 可正常访问
