# 网易 (netease) 适配器规格

## 基本信息
- **Slug**: netease
- **公司全称**: 网易（杭州）网络有限公司
- **校招官网**: https://campus.163.com
- **A阶段预期岗位数**: 10（互联网项目）
- **实现优先级**: P1（第一优先级，公开REST API）

## API端点
- **列表接口**: `GET https://campus.163.com/api/campuspc/position/getJobList`
- **详情页**: `https://campus.163.com/app/pc/detail?id={id}`

## 请求格式
```
GET https://campus.163.com/api/campuspc/position/getJobList?pageNum=1&pageSize=10&projectId=1
```
- Query 参数：`pageNum`, `pageSize`, `projectId`
- projectId 区分招聘项目（互联网项目、游戏项目等）

## 分页机制
- 页码分页：`pageNum` 从1开始
- 每页数量：`pageSize`
- 响应包含 `total` / `totalCount` 字段
- 岗位数极少（10岗），可能1页即完成

## 响应字段映射
| 响应字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `jobId` | `source_record_id`, `id` (前缀 netease-) | 岗位ID |
| `jobName` / `positionName` | `job_title` | 岗位名称 |
| `departmentName` | `recruiting_unit_raw` | 部门 |
| `workCity` / `cityName` | `cities` | 工作城市 |
| `jobCategory` | `job_category` | 岗位类别 |
| `education` | `education_raw` | 学历要求 |
| `major` | `major_requirements_raw` | 专业要求 |
| `description` | `description_raw` | 岗位描述 |
| `requirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |

## 技术难点和阻塞
1. **岗位数极少**: 仅10岗（互联网项目），可能网易游戏等其他项目有更多岗位，需遍历所有 projectId
2. **项目隔离**: 不同招聘项目（互联网、游戏、音乐、有道）有独立 projectId，需分别采集
3. **GET 接口**: 参数在 URL query 中，需注意 URL 编码

## 实现建议
- 先调用项目列表接口获取所有有效 projectId
- 对每个 projectId 分别分页采集
- delay >= 1.0s
- 预计总岗位数可能远超10（含所有项目）

## 验收标准
- 至少采集互联网项目10岗
- 若发现更多项目，一并采集
- 首/末页各至少1条岗位可核对
