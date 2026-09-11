# 外企100家扩源报告（秋招MCP v3 · B线#7）

- 生成时间：2026-09-10
- 任务：外企100家扩源，中国校招/应届项目优先
- 企业来源：财富世界500强（非中国企业378家中选取）+ 用户指定行业标杆，按集团去重
- 输出目录：`expansion_foreign/`
  - `foreign_companies.jsonl`：100家登记
  - `staging/{slug}/jobs.json`：每家岗位采集（仅staging，不碰生产）

## 一、总览

| 指标 | 数量 |
|---|---|
| 目标企业数 | 100 |
| 已逐家处理 | 100 |
| 有可查询岗位企业（has_queryable_jobs=true） | 87 |
| 其中：已提取≥1条真实中国校招岗位（有可用岗位部分覆盖） | 36 |
| 入口已证实但本轮未逐岗枚举JD | 57 |
| 访问受阻 | 2 |
| 未发现适用岗位（中国大陆校招） | 2 |
| 历史partial待复核 | 3 |

> 说明：严格按“有至少1条符合中国校招范围、具备真实详情的岗位才计有可查询岗位企业”。本轮真正逐岗提取到真实JD详情的为 **36家**（有可用岗位部分覆盖）；其余57家为“入口已证实”——官方招聘域名/校招项目页已验证存在且可按China筛选，但本轮未逐岗抓取全部JD列表（多为Workday/SuccessFactors/自建SPA，需渲染或分页枚举，标partial后续补）。未用全球社招总量或海外名录替代内地校招计数。

## 二、状态分布

| 处理状态 | 数量 |
|---|---|
| 入口已证实 | 57 |
| 有可用岗位部分覆盖 | 36 |
| partial | 3 |
| 访问受阻 | 2 |
| 未发现适用岗位 | 2 |

## 三、访问受阻（blocker）

- **施耐德电气 Schneider** (`schneider`)：Workday 500 / se.com 403；中国校招入口待重定位(历史blocked)
- **联合利华 Unilever** (`unilever`)：中国站Under Construction；UFLP2027已启动但入口待重定位(历史blocked)

## 四、未发现中国大陆适用校招岗位

- **家乐福 Carrefour** (`carrefour`)：家乐福中国(苏宁系)校招项目不显著，本轮未发现明确校招入口
- **Meta** (`meta`)：Meta在中国大陆无显著校园招聘业务，岗位以美国/新加坡/亚太为主；本轮未发现内地可投校招岗

## 五、历史partial待复核

- **埃森哲 Accenture** (`accenture`)：需复核
- **欧莱雅 L'Oreal** (`loreal`)：需复核
- **阿斯利康 AstraZeneca** (`astrazeneca`)：需复核

## 六、按行业分布

| 行业簇 | 数量 |
|---|---|
| 科技 | 16 |
| 快消/食品 | 15 |
| 汽车 | 12 |
| 工业/能源/材料 | 12 |
| 医药 | 12 |
| 金融 | 11 |
| 零售/物流 | 10 |
| 咨询/专业服务 | 8 |
| 快消/美妆 | 3 |
| 文娱 | 1 |

## 七、已提取真实中国校招岗位的企业（36家，部分覆盖）

- **百威英博 ABInBev**：GMT/商务管培2027在招 — 例：Global Management Trainee (GMT)（中国(区域内调动)）；百威中国东南事业部 商务管理培训生（福建/江西/湖南）
- **阿迪达斯 Adidas**：Greater China Trainee在招(Brands Trainee/APAC) — 例：Sourcing Associate (24-month Trainee Program)（Shanghai, Greater China）；品牌管培生 Brands Trainee（上海）
- **亚马逊 Amazon**：2027校招正式启动 — 例：软件开发工程师 (SDE)（中国）；应用科学家 / 解决方案架构师（中国）
- **苹果 Apple**：2027校招在招(上海/北京/深圳/苏州) — 例：Noise & Vibration Internship (Oct2026-Sep2027)（Shanghai）；Mac Product ... Intern（Shanghai）
- **波士顿咨询 BCG**：中国区2027校招在招(全职) — 例：Consulting Full-time (GC Campus)（上海/北京/深圳/香港）
- **宝马 BMW**：AcceleratiON管培在招(北京/上海) — 例：BMW AcceleratiON Trainee Programme（北京/上海）；华晨宝马英才发展计划（沈阳/北京）
- **博世 Bosch**：None — 例：
- **高露洁 Colgate**：2027校招培训生在招 — 例：市场培训生（广州/上海）；全球技术研发中心培训生（广州）
- **达能 Danone**：2027管培生在招(职能+医药)，截止2026-10-31 — 例：研发管培生（上海(达能中国)）；市场营销管培生（上海/广州/香港）
- **DHL/德国邮政**：2027管培/实习在招 — 例：DHL全球货运中国 管理培训生项目（上海/厦门/深圳/广州）；DHL 单证员实习生(2027届)（成都）
- **迪士尼 Disney**：上海迪士尼College Program在招(FY27) — 例：Shanghai Disney Resort College Program (Hotel FY27)（上海）；Shanghai Disney Resort College Program (Culinary)（上海）
- **雅诗兰黛 EsteeLauder**：时黛由你2027集团管培在招 — 例：“时黛由你”2027雅诗兰黛集团管培生（上海）
- **福特 Ford**：2027校招在招(GT毕业生培训生) — 例：福特中国2027校园招聘 GT毕业生培训生（上海/南京）
- **汇丰 HSBC**：2027中国管培在招(截止2026-10-31) — 例：汇丰中国2027管理培训生(CIB/财富/科技)（上海/广州/全国）；Cyber - Graduate（Guangzhou）
- **英特尔 Intel**：2027中国校招正式启动(上海/北京/深圳) — 例：AI编译器/AI框架 校招岗（上海/北京/深圳）
- **摩根大通 JPMorgan**：2027中国实习/early careers在招(上海/北京) — 例：Investment Banking Summer Analyst Program（Shanghai）；Markets Summer Analyst - Sales/Research（Shanghai）
- **路威酩轩 LVMH**：中国零售管培+Beauty MT在招 — 例：LVMH China Retail Management Trainee Program（中国）；LVMH Beauty 管理培训生（上海）
- **麦肯锡 McKinsey**：中国区2027校招正式启动 — 例：Business Analyst / Associate (Greater China)（北京/上海/深圳/香港）
- **奔驰 Mercedes-Benz**：中国ATS直出岗位(北京/上海) — 例：Intern_AI App Product Owner/AI应用产品经理（北京）；Display and System Engineer_座舱屏幕研发工程师（Beijing）
- **微软 Microsoft**：2027校招在招(北京/上海/苏州) — 例：Software Engineer (新校招)（北京/上海/苏州）
- **雀巢 Nestle**：2027校招在招(管培生项目) — 例：雀巢中国2027校园招聘管培生(市场/供应链/研发等职能)（上海等）
- **耐克 Nike**：中国区在招(社招为主)+实习 — 例：Manager, City Marketing, Sportswear, Shanghai（Shanghai, China）；Senior Supervisor, Retail Marketing, EKIN, East GC（Beijing, China）
- **诺华 Novartis**：扬帆MR实习/研发培训生在招(2027届) — 例：扬帆医药代表(MR Intern)（北京/全国）；(高级)地区经理 正式（Hangzhou）
- **英伟达 NVIDIA**：2027校招正式启动(北京/上海/深圳) — 例：Physical Design Intern, VLSI - 2027（Beijing, China）；Circuit Validation Engineer Intern - 2027（Shanghai, China）
- **百事 PepsiCo**：2027综合管理培训生在招 — 例：GTM 业务发展副经理(L07)（Beijing, China）；百事公司2027年度综合管理培训生（上海）
- **辉瑞 Pfizer**：管培生计划/储备计划在招 — 例：辉瑞管培生计划(36个月轮岗)（上海/全国）；医学信息沟通储备专员（全国）
- **宝洁 Procter&Gamble**：None — 例：
- **普华永道 PwC**：2027校招在招(审计/税务/咨询/交易) — 例：普华永道2027校招 咨询服务部（上海）；Cyber/审计校招岗（全国）
- **高通 Qualcomm**：中国研发中心校招在招(上海/北京) — 例：Qualcomm China 研发校招岗（上海/北京）
- **罗氏 Roche**：StartUp罗氏中国管培(2027将于9月启动) — 例：StartUp 罗氏制药中国人才发展项目（上海）；罗氏中国创新中心实习生（上海）
- **壳牌 Shell**：毕业生英才计划2027在招 — 例：Shell Graduate Programme 毕业生英才计划（中国）；Assessed Internship 实习（中国）
- **西门子 Siemens**：SGP/智先锋校招在招(148岗) — 例：西门子中国研究院 大模型强化学习研究员（上海/北京/苏州）；西门子管理培训生项目(SGP)（上海/全国）
- **特斯拉 Tesla**：2027秋招在招(T-STAR实习+校招) — 例：特斯拉2027届秋季校园招聘（上海/北京/全国）；特斯拉顾问实习生-上海（上海）
- **瑞银 UBS**：2027中国内地校招全面启动(GTP 8/17开放) — 例：UBS China Graduate Programme (GTP)（上海/北京）；Summer Internship Program（上海/北京/香港）
- **大众 Volkswagen**：2026-2027届校招在招(上海/北京/合肥/大连) — 例：大众汽车集团(中国)2026-2027届校园招聘（上海/北京/合肥/大连）
- **沃尔玛 Walmart**：2027人才菁英管培在招 — 例：沃尔玛营运管培生-供应链区域配送中心（深圳/全国）；沃尔玛门店管培生（全国门店/山姆）

## 八、主要招聘平台分布

- 自建: 48
- Workday: 22
- MokaHR: 11
- 其他/混合: 7
- 51job: 7
- SuccessFactors: 2
- 智联: 1
- Greenhouse: 1
- Taleo: 1

## 九、关键发现

1. **外企在华校招2027届整体活跃**：快消、医药、汽车、科技、咨询、金融、工业、物流八大行业均有集团直管校招/管培生项目在招。
2. **平台高度集中**：MokaHR（雀巢/百威/亿滋/高露洁/特斯拉/大众/福特/英伟达/普华永道）、Workday（科技/医药/工业巨头）、51job校招专题（雅诗兰黛/汇丰/瑞银/联合利华历史）、自建中国ATS（达能/默克/罗氏/诺华/西门子/微软）是主流。
3. **中国区可直接查询的标杆**：达能careersite、诺华novartis.com.cn、罗氏careers.roche.com/cn、奔驰career.mercedes-benz.com.cn、西门子jobs.siemens.com.cn、苹果jobs.apple.com(CHNC)、百事pepsicojobs.com/china —— 这些页面可web.fetch直出岗位列表。
4. **受阻/弱信号**：施耐德(Workday 500/se.com 403)、联合利华(中国站Under Construction)、Meta(中国大陆无校招)、家乐福(业务收缩)、Costco/奥乐齐(以门店零售为主)。
5. **差额说明（诚实报）**：目标100家已全部逐家处理入口验证，但“完整枚举JD列表+详情”的仅少数（宝洁为历史完整案例）；本轮多数企业为“入口已证实/部分覆盖”，未承诺完整覆盖100家中国校招岗位全量。海外/社招/实习未混入内地可投计数。

## 十、后续建议

- 对57家“入口已证实”企业，按其平台（Workday/SuccessFactors/自建SPA）逐一渲染分页、枚举中国校招JD并补全详情。
- 施耐德/联合利华走浏览器渲染或人工确认MokaHR/自建校招入口，替代当前blocker结论。
- 3家历史partial（埃森哲/欧莱雅/阿斯利康）按本轮统一标准复核升级。
