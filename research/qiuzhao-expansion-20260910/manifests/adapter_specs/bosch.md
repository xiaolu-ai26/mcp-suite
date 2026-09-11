# 博世 (bosch) 适配器规格

## 基本信息
- **Slug**: bosch
- **公司全称**: 博世（中国）投资有限公司
- **校招官网**: MokaHR系统托管
- **A阶段预期岗位数**: 180（校招）
- **实现优先级**: P2（第二优先级，MokaHR系统）

## API端点
MokaHR系统端点（需确认域名）：
- **列表接口**: `POST https://{company}.mohr.com/api/bifrost/job/list`
- **详情页**: `https://{company}.mohr.com/campus/position/{id}`

## 请求格式
```json
{
  "campusId": "{campus_id}",
  "pageIndex": 1,
  "pageSize": 10,
  "keyword": "",
  "jobCategoryIds": [],
  "cityCodes": [],
  "language": "zh-CN"
}
```
- Content-Type: `application/json`
- 博世为跨国企业，可能需要指定语言参数

## 分页机制
- 页码分页：`pageIndex` 从1开始
- 每页数量：`pageSize`
- 响应包含 `total` 字段
- 180岗约需 18 页（pageSize=10）

## 响应字段映射
| 响应字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` | `source_record_id`, `id` (前缀 bosch-) | 岗位ID |
| `jobName` / `title` | `job_title` | 岗位名称（可能中英混合） |
| `departmentName` | `recruiting_unit_raw` | 部门/事业部 |
| `cityName` | `cities` | 工作城市（上海、苏州、无锡、长沙等） |
| `jobCategoryName` | `job_category` | 岗位类别 |
| `educationName` | `education_raw` | 学历要求 |
| `majorRequirement` | `major_requirements_raw` | 专业要求 |
| `jobDescription` | `description_raw` | 岗位职责（可能中英双语） |
| `jobRequirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |

## 技术难点和阻塞
1. **双语内容**: 博世岗位描述可能中英混合，需保留原始文本
2. **MokaHR 版本**: 与宁德时代同属 MokaHR，可共享适配代码
3. **域名确认**: 博世的 MokaHR 域名需确认
4. **岗位数较少**: 180岗，可能部分岗位已关闭

## 实现建议
- 与宁德时代共享 MokaHR 适配器基础代码
- delay >= 2s
- 完整采集约需 40 秒
- 注意保留英文岗位信息

## 验收标准
- 采集岗位数 >= 140
- 首/中/末页各至少1条岗位可核对
- 双语内容正确保留
