# 联合利华(Unilever)中国区校招证据摘录

## 官方归属证据
- 全球招聘官网: https://careers.unilever.com/
- 页面标题: "A bright, new future"
- 摘录: "Every day, 3.4 billion people around the world enjoy our products..."
- 中国官网: https://www.unilever.com.cn/
- 中国招聘页: https://www.unilever.com.cn/careers/ → "Site Under Construction" (建设中)

## 招聘平台识别
- 平台: 联合利华自建招聘平台 (careers.unilever.com)
- 职位搜索页: https://careers.unilever.com/en/search-jobs
- 全球职位总数: 255个，37页
- 职位分类: GBS, Customer Development, R&D, Supply Chain, Marketing, Communications, GDT, Finance, HR, Legal

## 中国区校招信息
- **UFLP (Unilever Future Leaders Programme) 2027管理培训生招聘已启动**
  - 确认来源: 交大就业，发布于2026-09-06
  - URL: https://m.sohu.com/a/1072513412_121106832/
  - 这是联合利华中国区核心校招项目

## 阻塞原因
1. 中国区招聘页 (unilever.com.cn/careers/) 显示"Site Under Construction"，无法获取中国区职位
2. 全球招聘页 (careers.unilever.com) URL参数过滤不生效:
   - ?location=China → 仍显示255个全球职位
   - ?keyword=graduate&location=China → 仍显示255个全球职位
   - ?keyword=trainee&location=Shanghai → 仍显示255个全球职位
   - 筛选功能为纯前端JS交互，无法通过URL参数触发
3. UFLP 2027校招已确认启动，但官方申请入口未在全球招聘页找到，可能通过微信公众号或专门校招网站
4. 全球职位列表中未发现明确标注为China/Shanghai的校招/管培岗位(前7页均为菲律宾、加拿大、巴西、墨西哥、美国等地区职位)
5. 采集时间: 2026-09-10

## 已知全球职位样例(非中国区，仅作平台功能佐证)
1. Rigids Area Engineer - Cavite, Central Luzon (菲律宾)
2. Senior Key Account Manager - Costco & Dollar/Value - Toronto, Ontario (加拿大)
3. Senior Supply Chain Financial Analyst - Foods - Hoboken, NJ (美国)
