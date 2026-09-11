# 汇川技术 (inovance) 适配器规格

## 基本信息
- **Slug**: inovance
- **公司全称**: 深圳市汇川技术股份有限公司
- **校招官网**: https://recruit.inovance.com （Vue SPA）
- **A阶段预期岗位数**: 392（校招）
- **实现优先级**: P3（第三优先级，自建SPA需浏览器渲染）

## 技术架构
- 前端：Vue.js SPA
- 后端 API：需通过浏览器 DevTools 捕获
- 汇川技术招聘系统可能为自研

## 预期 API 端点（需探测确认）
```
POST https://recruit.inovance.com/api/job/list
或
GET https://recruit.inovance.com/api/recruitment/jobs?page=1
```

## 请求格式
- 需先访问首页获取 session/token
- Referer: `https://recruit.inovance.com/`

## 分页机制
- 待探测：可能为页码分页
- 392岗约需 40 页（pageSize=10）

## 预期字段映射
| 预期字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `jobId` | `source_record_id`, `id` (前缀 inovance-) | 岗位ID |
| `jobName` / `title` | `job_title` | 岗位名称 |
| `departmentName` | `recruiting_unit_raw` | 部门/产品线 |
| `cityName` / `workLocation` | `cities` | 工作城市（深圳、苏州、西安等） |
| `jobCategory` | `job_category` | 岗位类别 |
| `education` | `education_raw` | 学历要求 |
| `major` | `major_requirements_raw` | 专业要求（电气、自动化、计算机等） |
| `description` | `description_raw` | 岗位职责 |
| `requirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |

## 技术难点和阻塞
1. **SPA 渲染**: 必须捕获 XHR API
2. **自研系统**: 汇川技术可能使用自研招聘系统，API 结构需探测
3. **岗位量大**: 392岗，采集时间较长
4. **工业自动化领域**: 专业要求较细分，需保留原始文本

## 实现建议
1. 必须先用浏览器 DevTools 捕获 API
2. 验证 API 可无浏览器复现
3. delay >= 2s
4. 完整采集约需 2-3 分钟

## 验收标准
- API 端点已确认
- 采集岗位数 >= 300
- 首/中/末页各至少1条岗位可核对
