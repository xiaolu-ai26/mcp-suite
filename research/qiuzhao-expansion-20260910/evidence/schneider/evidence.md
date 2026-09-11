# 施耐德电气(Schneider Electric)中国区校招证据摘录

## 官方归属证据
- 中国官网: https://www.se.com/cn/
- 招聘页(英文): https://www.se.com/cn/en/careers/overview.jsp (web.fetch可访问)
- 页面含: "为什么选择施耐德电气？"、"专业人才"、"销售及服务"、"数字化与工程"、"学生和青年专业人才"
- 职位筛选: 按"分类"和"地点"过滤

## 招聘平台识别
- 疑似平台: Workday (外企常用)
- 尝试的Workday URL:
  - https://schneiderelectric.wd5.myworkdayjobs.com/SchneiderElectric → HTTP 500
  - https://schneiderelectric.wd1.myworkdayjobs.com/Careers → HTTP 500
- se.com直接访问:
  - https://www.se.com/cn/en/careers/ → HTTP 403 (curl)
  - https://www.se.com/cn/zh/careers/ → link dead (web.fetch)
  - https://www.se.com/cn/en/careers/overview.jsp → 可访问(web.fetch)，但职位列表为JS渲染未显示

## 阻塞原因
1. Workday API端点返回HTTP 500，无法获取职位数据
2. se.com/cn/en/careers/ 返回403，禁止自动化访问
3. overview.jsp页面可访问但职位列表通过JS动态加载，web.fetch无法提取具体职位
4. 未找到施耐德电气中国区2027校园招聘的专门入口或职位列表
5. 采集时间: 2026-09-10

## 已知信息
- 施耐德电气中国区有"学生和青年专业人才"招聘分类
- 全球招聘可能通过Workday系统，但中国区租户ID未确认
- 需要进一步通过浏览器交互或官方微信公众号获取校招职位
