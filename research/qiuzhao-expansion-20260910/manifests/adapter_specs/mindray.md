# 迈瑞医疗 (mindray) 适配器规格

## 基本信息
- **Slug**: mindray
- **公司全称**: 深圳迈瑞生物医疗电子股份有限公司
- **校招官网**: 北森系统托管
- **A阶段预期岗位数**: 20+（校招）
- **实现优先级**: P2（第二优先级，北森系统）

## API端点
北森（Beisen）系统标准端点：
- **列表接口**: `POST https://{company}.zhiye.com/api/job/list` 或北森云 API
- **详情页**: `https://{company}.zhiye.com/job/detail/{id}`

北森系统常见 API 模式：
```
POST /api/job/search
Content-Type: application/json
{
  "pageIndex": 1,
  "pageSize": 10,
  "keyword": "",
  "jobType": "CAMPUS",
  "locationId": ""
}
```

## 请求格式
- 北森系统通常需要先访问首页获取 `token` 或 `csrfToken`
- 部分北森站点使用 GraphQL 接口
- Referer 必须为对应校招页面

## 分页机制
- 页码分页：`pageIndex` 从1开始
- 每页数量：`pageSize`
- 响应包含 `totalCount` 字段
- 20+岗可能1-2页即完成

## 响应字段映射
| 响应字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `jobId` | `source_record_id`, `id` (前缀 mindray-) | 岗位ID |
| `jobName` / `title` | `job_title` | 岗位名称 |
| `departmentName` | `recruiting_unit_raw` | 部门/产品线 |
| `cityName` / `workLocation` | `cities` | 工作城市（深圳、南京、北京等） |
| `jobCategoryName` | `job_category` | 岗位类别 |
| `educationName` | `education_raw` | 学历要求 |
| `majorRequirement` | `major_requirements_raw` | 专业要求（生物医学、电子、计算机等） |
| `jobDescription` | `description_raw` | 岗位职责 |
| `jobRequirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |

## 技术难点和阻塞
1. **北森 API 多样性**: 北森系统有多个版本（传统版、云版、GraphQL版），需首次确认
2. **Token 机制**: 北森云 API 可能需要动态 token
3. **岗位数少**: 仅20+岗，可能校招尚未全面启动
4. **域名确认**: 迈瑞医疗的北森域名需确认（可能是 mindray.zhiye.com）

## 实现建议
- 首次需用浏览器确认北森版本和 API 结构
- 若为 GraphQL 接口，需构造正确的查询语句
- delay >= 1.5s
- 完整采集预计 30 秒内

## 验收标准
- 采集岗位数 >= 15
- 首/末页各至少1条岗位可核对
- 北森 API 版本已确认
