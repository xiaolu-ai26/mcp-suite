# 宁德时代 (catl) 适配器规格

## 基本信息
- **Slug**: catl
- **公司全称**: 宁德时代新能源科技股份有限公司
- **校招官网**: MokaHR系统托管
- **A阶段预期岗位数**: 601（校招）
- **实现优先级**: P2（第二优先级，MokaHR系统）

## API端点
MokaHR（Moka 新版）系统端点：
- **列表接口**: `POST https://{company}.mohr.com/api/bifrost/job/list` 或 `https://app.mokahr.com/api/bifrost/job/list`
- **详情页**: `https://{company}.mohr.com/campus/position/{id}`

注意：MokaHR 是 Moka 的新版本，域名可能为 `.mohr.com` 而非 `.mokahr.com`。

## 请求格式
```json
{
  "campusId": "{campus_id}",
  "pageIndex": 1,
  "pageSize": 10,
  "keyword": "",
  "jobCategoryIds": [],
  "cityCodes": [],
  "recruitmentType": "CAMPUS"
}
```
- Content-Type: `application/json`
- 可能需要 `x-csrf-token`

## 分页机制
- 页码分页：`pageIndex` 从1开始
- 每页数量：`pageSize`
- 响应包含 `total` 字段
- 601岗约需 61 页（pageSize=10）

## 响应字段映射
| 响应字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `jobId` | `source_record_id`, `id` (前缀 catl-) | 岗位ID |
| `jobName` / `title` | `job_title` | 岗位名称 |
| `departmentName` | `recruiting_unit_raw` | 部门/研究院 |
| `cityName` / `workLocation` | `cities` | 工作城市（宁德、上海、溧阳等） |
| `jobCategoryName` | `job_category` | 岗位类别 |
| `educationName` | `education_raw` | 学历要求 |
| `majorRequirement` | `major_requirements_raw` | 专业要求（电化学、机械、电气等） |
| `jobDescription` | `description_raw` | 岗位职责 |
| `jobRequirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |

## 技术难点和阻塞
1. **MokaHR vs Moka**: 宁德时代使用 MokaHR（新版），API 路径和字段可能与旧版 Moka 不同
2. **域名确认**: 需确认是 `.mohr.com` 还是 `.mokahr.com` 域名
3. **campusId**: 需从校招首页提取
4. **岗位量大**: 601岗，采集时间较长，需注意限流

## 实现建议
- 首次需用浏览器确认 MokaHR 域名和 API 结构
- 可与恒瑞/康龙化成共享 Moka 基础代码，但需区分版本
- delay >= 2s
- 完整采集约需 2-3 分钟

## 验收标准
- 采集岗位数 >= 500
- 首/中/末页各至少1条岗位可核对
- MokaHR API 结构已确认
