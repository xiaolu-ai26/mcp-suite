# 恒瑞医药 (hengrui) 适配器规格

## 基本信息
- **Slug**: hengrui
- **公司全称**: 江苏恒瑞医药股份有限公司
- **校招官网**: Moka系统托管
- **A阶段预期岗位数**: 444（校招）
- **实现优先级**: P2（第二优先级，Moka系统）

## API端点
Moka系统标准端点（需首次探测确认域名）：
- **列表接口**: `POST https://{company}.mokahr.com/api/bifrost/job/list`
- **详情页**: `https://{company}.mokahr.com/campus/position/{id}`

Moka 系统常见 API 模式：
```
POST /api/bifrost/job/list
Content-Type: application/json
{
  "campusId": "{campus_id}",
  "pageIndex": 1,
  "pageSize": 10,
  "keyword": "",
  "jobCategoryIds": [],
  "cityCodes": []
}
```

## 请求格式
- 需要先访问校招首页获取 `campusId`（嵌入在页面 JS 或 meta 标签中）
- 部分 Moka 站点需要 `x-csrf-token` header
- Referer 必须为对应校招页面

## 分页机制
- 页码分页：`pageIndex` 从1开始（部分版本为 `pageNo`）
- 每页数量：`pageSize`（建议10-20）
- 响应包含 `total` / `totalCount` 字段

## 响应字段映射（Moka通用结构）
| 响应字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `jobId` | `source_record_id`, `id` (前缀 hengrui-) | 岗位ID |
| `jobName` / `title` | `job_title` | 岗位名称 |
| `departmentName` | `recruiting_unit_raw` | 部门 |
| `cityName` / `workCity` | `cities` | 工作城市 |
| `jobCategoryName` | `job_category` | 岗位类别 |
| `educationName` | `education_raw` | 学历要求 |
| `majorRequirement` | `major_requirements_raw` | 专业要求 |
| `jobDescription` | `description_raw` | 岗位职责 |
| `jobRequirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |

## 技术难点和阻塞
1. **campusId 发现**: 需从首页 HTML/JS 中提取当前校招项目 ID
2. **Moka 版本差异**: 不同企业的 Moka 系统版本可能不同，API 路径和字段名有差异
3. **反爬机制**: Moka 系统可能有请求频率限制和 User-Agent 检测
4. **域名确认**: 恒瑞医药的 Moka 域名需首次访问确认（可能是 hengrui.mokahr.com 或自定义域名）

## 实现建议
1. 先用浏览器访问校招首页，确认 Moka 域名和 campusId
2. 用 curl 探测 API 端点和响应结构
3. 实现时参考 Moka 通用模式，保留字段映射的灵活性
4. delay >= 2s（Moka 系统限流较严格）

## 验收标准
- 采集岗位数 >= 350
- 首/中/末页各至少1条岗位可核对
- campusId 提取逻辑可复用
