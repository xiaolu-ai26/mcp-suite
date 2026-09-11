# 义翘神州 (sinobiological) 适配器规格

## 基本信息
- **Slug**: sinobiological
- **公司全称**: 北京义翘神州科技股份有限公司
- **校招官网**: 北森传统版（HTML表格）
- **A阶段预期岗位数**: 24（校招）
- **实现优先级**: P2（第二优先级，北森传统版HTML）

## 数据来源
北森传统版不提供 JSON API，岗位列表以 HTML 表格形式渲染在页面中：
- **列表页**: `https://{company}.zhiye.com/Campus/JobList`
- **详情页**: `https://{company}.zhiye.com/Campus/JobDetail/{id}`

## 采集方式
- **GET 请求**获取列表页 HTML
- 使用 BeautifulSoup 解析表格行
- 每行包含：岗位名称、部门、工作地点、学历要求、发布日期、详情链接
- 详情页需二次 GET 获取完整描述

## HTML 解析要点
- 表格通常在 `<table class="job-list">` 或类似选择器中
- 详情链接在 `<a href="/Campus/JobDetail/{id}">` 中
- 分页通过 URL 参数 `?pageIndex=N` 实现
- 24岗可能1-2页即完成

## 字段映射
| HTML 元素 | 目标字段 | 说明 |
|---------|---------|------|
| 岗位名称列 | `job_title` | 表格第一列 |
| 部门列 | `recruiting_unit_raw` | 表格第二列 |
| 工作地点列 | `cities` | 表格第三列 |
| 学历列 | `education_raw` | 表格第四列 |
| 发布日期列 | `published_at` | 表格第五列 |
| 详情页描述 | `description_raw` | 详情页正文 |
| 详情页要求 | `requirement_raw` | 详情页任职要求 |
| 详情链接 ID | `source_record_id`, `id` (前缀 sinobiological-) | URL 中的 id |

## 技术难点和阻塞
1. **无 JSON API**: 必须解析 HTML，脆弱性较高（页面结构变化即失效）
2. **北森传统版**: 页面可能包含大量模板代码，需精确定位表格
3. **详情页采集**: 24个详情页需逐一请求，增加采集时间
4. **岗位数少**: 仅24岗，验证样本有限

## 实现建议
- 参考 run.py 中 `chnenergy` 的 HTML 解析模式
- 使用 BeautifulSoup 的 CSS 选择器定位表格
- 先采集列表，再按需采集详情
- delay >= 1.5s
- 完整采集预计 1 分钟

## 验收标准
- 采集岗位数 >= 20
- 首/末页各至少1条岗位可核对
- 详情页描述正确提取
