# 比亚迪 (byd) 适配器规格

## 基本信息
- **Slug**: byd
- **公司全称**: 比亚迪股份有限公司
- **校招官网**: https://job.byd.com （Vue SPA）
- **A阶段预期岗位数**: 386（校招）
- **实现优先级**: P3（第三优先级，自建SPA需浏览器渲染）

## 技术架构
- 前端：Vue.js SPA
- 后端 API：需通过浏览器 DevTools 捕获
- 比亚迪招聘系统可能为自研或第三方定制

## 预期 API 端点（需探测确认）
```
POST https://job.byd.com/api/recruitment/job/list
或
GET https://job.byd.com/api/job/search?pageNum=1&pageSize=10
```

## 请求格式
- 需先访问首页获取 session/token
- 可能需要特定 header（如 `X-Requested-With`）
- Referer: `https://job.byd.com/`

## 分页机制
- 待探测：可能为页码分页
- 386岗约需 39 页（pageSize=10）

## 预期字段映射
| 预期字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `jobId` | `source_record_id`, `id` (前缀 byd-) | 岗位ID |
| `jobName` / `postName` | `job_title` | 岗位名称 |
| `departmentName` / `orgName` | `recruiting_unit_raw` | 部门/事业部（弗迪、腾势等） |
| `cityName` / `workLocation` | `cities` | 工作城市（深圳、西安、长沙等） |
| `jobCategory` | `job_category` | 岗位类别 |
| `education` | `education_raw` | 学历要求 |
| `major` | `major_requirements_raw` | 专业要求（车辆、电子、机械等） |
| `description` | `description_raw` | 岗位职责 |
| `requirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |

## 技术难点和阻塞
1. **SPA 渲染**: 必须捕获 XHR API
2. **比亚迪系统**: 可能为自研系统，API 结构不标准
3. **岗位量大**: 386岗，采集时间长
4. **事业部众多**: 比亚迪有多个事业部（弗迪电池、弗迪动力、腾势等），部门字段需正确解析

## 实现建议
1. 必须先用浏览器 DevTools 捕获 API
2. 验证 API 是否可无浏览器复现
3. 若有反爬，分析 token/签名逻辑
4. delay >= 2s
5. 完整采集约需 2-3 分钟

## 验收标准
- API 端点已确认
- 采集岗位数 >= 300
- 首/中/末页各至少1条岗位可核对
- 事业部字段正确解析
