# 美的 (midea) 适配器规格

## 基本信息
- **Slug**: midea
- **公司全称**: 美的集团股份有限公司
- **校招官网**: https://careers.midea.com （Vue SPA）
- **A阶段预期岗位数**: 146（校招）
- **实现优先级**: P3（第三优先级，自建SPA需浏览器渲染）

## 技术架构
- 前端：Vue.js SPA
- 后端 API：需通过浏览器 DevTools 捕获 XHR 请求
- 常见模式：SPA 调用内部 REST API，可能有签名或 token

## 预期 API 端点（需探测确认）
```
POST https://careers.midea.com/api/job/list
或
GET https://careers.midea.com/api/recruitment/jobs?page=1&size=10
```

## 请求格式
- 需先访问首页获取 CSRF token 或 session cookie
- 可能需要 `Authorization` header（匿名 token）
- Referer: `https://careers.midea.com/`

## 分页机制
- 待探测：可能为页码分页或 offset 分页
- 146岗约需 15 页（pageSize=10）

## 预期字段映射
| 预期字段 | 目标字段 | 说明 |
|---------|---------|------|
| `id` / `jobId` | `source_record_id`, `id` (前缀 midea-) | 岗位ID |
| `jobName` / `title` | `job_title` | 岗位名称 |
| `departmentName` | `recruiting_unit_raw` | 部门/事业部 |
| `cityName` / `workLocation` | `cities` | 工作城市（佛山、深圳、上海等） |
| `jobCategory` | `job_category` | 岗位类别 |
| `education` | `education_raw` | 学历要求 |
| `major` | `major_requirements_raw` | 专业要求 |
| `description` | `description_raw` | 岗位职责 |
| `requirement` | `requirement_raw` | 任职要求 |
| `publishTime` | `published_at` | 发布时间 |

## 技术难点和阻塞
1. **SPA 渲染**: 纯 HTML 不包含岗位数据，必须捕获 XHR API
2. **API 签名**: 美的自建系统可能有请求签名机制，需逆向
3. **反爬**: 自建系统可能有较严格的反爬措施
4. **需浏览器探测**: 首次必须用浏览器 DevTools 捕获 API 请求

## 实现建议
1. **必须先用浏览器**访问 careers.midea.com，打开 DevTools Network 面板
2. 筛选 XHR/Fetch 请求，找到岗位列表 API
3. 复制请求为 cURL，验证是否可在无浏览器环境下复现
4. 若有签名/token，分析生成逻辑
5. delay >= 2s

## 验收标准
- API 端点已确认且可无浏览器调用
- 采集岗位数 >= 120
- 首/中/末页各至少1条岗位可核对
