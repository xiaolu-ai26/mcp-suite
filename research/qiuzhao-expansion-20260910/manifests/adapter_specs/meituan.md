# 美团 (meituan) 适配器规格

## 基本信息
- **Slug**: meituan
- **公司全称**: 北京三快科技有限公司（美团）
- **校招官网**: https://zhaopin.meituan.com
- **A阶段预期岗位数**: 604（应届189）
- **实现优先级**: P1（第一优先级，公开REST API）

## API端点
- **列表接口**: `POST https://zhaopin.meituan.com/api/official/job/getJobList`
- **详情页**: `https://zhaopin.meituan.com/web/position/{id}`

## 请求格式
```json
{
  "pageNo": 1,
  "pageSize": 10,
  "keyword": "",
  "jobType": 1,
  "jobFamilyCode": "",
  "cityCode": ""
}
```
- Content-Type: `application/json`
- Referer: `https://zhaopin.meituan.com/web/campus`

## 分页机制
- 页码分页：`pageNo` 从1开始
- 每页数量：`pageSize`（建议10-20）
- 响应包含 `total` 字段
- 需区分 `jobType`: 1=校招应届, 2=实习, 0=全部

## 响应字段映射
| 响应字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `jobId` | `source_record_id`, `id` (前缀 meituan-) | 岗位ID |
| `jobName` | `job_title` | 岗位名称 |
| `departmentName` / `bgName` | `recruiting_unit_raw` | 事业群/部门 |
| `cityName` | `cities` | 工作城市 |
| `jobFamilyName` | `job_category` | 岗位族 |
| `educationName` | `education_raw` | 学历要求 |
| `majorRequirement` | `major_requirements_raw` | 专业要求 |
| `jobDescription` | `description_raw` | 岗位职责 |
| `jobRequirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |
| `jobStatus` | `status` | 岗位状态（1=招聘中） |

## 技术难点和阻塞
1. **岗位类型过滤**: 需明确 `jobType=1` 只取应届校招，避免混入实习和社招
2. **事业群字段**: 美团有多个 BG（到店、到家、快驴等），字段可能为 `bgName`
3. **响应包装**: 美团 API 通常有 `{code: 0, data: {list: [], total: N}}` 结构

## 实现建议
- 设置 `jobType: 1` 仅采集应届校招
- delay >= 1.5s
- 应届189岗约需 19 页（pageSize=10），预计 30 秒
- 若需全部604岗则不设 jobType 过滤

## 验收标准
- 应届岗位数 >= 150
- 首/中/末页各至少1条岗位可核对
- 岗位状态字段正确解析
