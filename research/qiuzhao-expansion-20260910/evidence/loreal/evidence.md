# 欧莱雅(L'Oréal)中国区校招证据摘录

## 官方归属证据
- 全球招聘官网: https://careers.loreal.com/
- 职位搜索页: https://careers.loreal.com/en_US/jobs
- 页面标题: "Life Is Too Short For A Boring Career"
- 摘录: "At L'Oréal, you'll find a career that feels as alive as you do."
- 中国总部: 上海，在中国拥有32个品牌，一个研发和创新中心，两家工厂(苏州和宜昌)，超过15,000名员工

## 招聘平台识别
- 平台: 欧莱雅自建招聘平台
- 职位总数: 999+ (全球)
- 职位分类: Digital Marketing, Marketing, Finance, HR, Operations, R&I, Data, Tech, Sales, Campus(4个), Manufacturing, Supply Chain等
- 职位详情URL模式: https://careers.loreal.com/en_US/jobs/JobDetail/{Job-Title}/{job-id}
  - 例: https://careers.loreal.com/en_US/jobs/JobDetail/L-OREAL-Taiwan-Pricing-Manager-Assistant-Pricing-Manager/255199

## 中国区职位(从全球搜索页提取)
URL参数过滤不生效(?keyword=trainee&location=Shanghai仍显示999+全球职位)，但在列表中发现以下上海职位:

### 职位样例
1. **(Jr.) Product Manager, H.R.**
   - 地点: Shanghai
   - 发布: 01-Aug-2026
   - 描述: "Define and steer the country strategy for the category consistent with the international brand positioning and the country's priorities... Define the strategic orientations and the 3-year marketing plan..."
   - 性质判断: Jr.级别，可能面向初级人才/应届毕业生，但非明确校招项目
   - 采集时间: 2026-09-10

2. **(Jr.) Product Manager, Shu Uemura**
   - 地点: Shanghai
   - 发布: 15-May-2026
   - 描述: "Own a product line within brand's portfolio — turning brand strategy into launches, campaigns and consumer experiences that bring the brand to life in China."
   - 性质判断: Jr.级别，中国区职位，但非明确校招项目
   - 采集时间: 2026-09-10

3. **(Jr.) Product Manager, Kiehl's**
   - 地点: Shanghai
   - 发布: 11-Jun-2026
   - 描述: "Own a product line within brand's portfolio — turning brand strategy into launches, campaigns and consumer experiences that bring the brand to life in China."
   - 性质判断: Jr.级别，中国区职位
   - 采集时间: 2026-09-10

## 中国区校招项目信息
- 欧莱雅中国面向应届毕业生开展:
  - **管理培训生项目 (Management Trainee)**
  - **区域销售培训生项目 (Regional Sales Trainee)**
  - 每年共计招募百余名青年才俊
  - 通过轮岗、培训与实践项目完成从"学生"到"职场人"的转变
- 来源: 品观网/界面新闻报道
- Campus分类在全球招聘页仅有4个职位，但未明确是否包含中国区

## 其他发现
- **Marketing Graduate - Professional Products Division** - Copenhagen (丹麦), 发布01-Oct-2026
  - 描述: "Are you a recent graduate with a passion for the beauty industry..."
  - 这是明确的graduate项目，但位于丹麦非中国区

## 阻塞原因
1. URL参数过滤不生效，无法通过?keyword=或?location=筛选中国区职位
2. 中国区管理培训生(MT)和区域销售培训生项目未在全球招聘页列出，可能通过微信公众号/小程序或专门校招网站招聘
3. 上海职位的详情URL未在web.fetch输出中显示(台湾职位有URL，上海职位无)，无法直接获取详情页
4. Campus分类仅4个职位，未确认是否包含中国区
5. 采集时间: 2026-09-10
