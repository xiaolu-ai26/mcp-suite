# 康龙化成 (pharmaron) 适配器规格

## 基本信息
- **Slug**: pharmaron
- **公司全称**: 康龙化成（北京）新药技术有限公司
- **校招官网**: Moka系统托管
- **A阶段预期岗位数**: 584（校招）
- **实现优先级**: P2（第二优先级，Moka系统）

## API端点
Moka系统标准端点（需首次探测确认域名）：
- **列表接口**: `POST https://{company}.mokahr.com/api/bifrost/job/list`
- **详情页**: `https://{company}.mokahr.com/campus/position/{id}`

## 请求格式
```json
{
  "campusId": "{campus_id}",
  "pageIndex": 1,
  "pageSize": 10,
  "keyword": "",
  "jobCategoryIds": [],
  "cityCodes": [],
  "jobNature": "CAMPUS"
}
```
- Content-Type: `application/json`
- Referer: 对应校招页面

## 分页机制
- 页码分页：`pageIndex` 从1开始
- 每页数量：`pageSize`（建议10-20）
- 响应包含 `total` 字段
- 584岗约需 59 页（pageSize=10）

## 响应字段映射
| 响应字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` | `source_record_id`, `id` (前缀 pharmaron-) | 岗位ID |
| `jobName` | `job_title` | 岗位名称 |
| `departmentName` / `orgName` | `recruiting_unit_raw` | 部门/实验室 |
| `cityName` | `cities` | 工作城市（北京、上海、宁波等） |
| `jobCategoryName` | `job_category` | 岗位类别 |
| `educationName` | `education_raw` | 学历要求 |
| `majorRequirement` | `major_requirements_raw` | 专业要求（化学、生物、药学等） |
| `jobDescription` | `description_raw` | 岗位职责 |
| `jobRequirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |

## 技术难点和阻塞
1. **Moka 域名确认**: 康龙化成的 Moka 域名需确认（可能是 pharmaron.mokahr.com）
2. **campusId 提取**: 需从首页提取校招项目 ID
3. **岗位地点分散**: 康龙化成有北京、上海、宁波、绍兴等多个基地，城市字段需正确解析
4. **专业要求**: 医药行业专业要求较细分，需保留原始文本

## 实现建议
- 与恒瑞医药共享 Moka 适配器基础代码
- 首次运行需人工确认域名和 campusId
- delay >= 2s
- 完整采集约需 2 分钟

## 验收标准
- 采集岗位数 >= 450
- 首/中/末页各至少1条岗位可核对
- 城市字段包含多个基地
