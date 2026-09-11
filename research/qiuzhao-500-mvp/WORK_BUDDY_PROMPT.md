# 秋招MCP 500家企业MVP扩源 — 执行提示词

请将以下内容完整复制给work buddy执行：

---

## 任务：秋招岗位MCP 500家企业MVP扩源采集

### 背景
秋招岗位MCP产品已上线生产（https://savegems.top/qiuzhao/），当前约30家企业/15,767条岗位。目标是快速扩至500+家企业上线，每家先1-3条有完整详情的合格岗位即可，不追求单家全量。

### 项目路径
- 本地项目: /Users/maxzhl/Projects/mcp-suite/
- 生产服务器: root@114.215.188.109
- 生产jobs.json: /var/lib/mcp-suite/jobs.json
- 生产代码: /opt/mcp-suite/
- 服务: mcp-suite.service (systemctl restart mcp-suite.service)
- 健康检查: curl https://savegems.top/qiuzhao/health

### 企业候选池（按优先级处理）

1. **外企100家（有platform_hint，最快）**:
   /Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign/foreign_companies.jsonl
   字段: slug, cn_name, country, industry, platform_hint(MokaHR/Phenom/Workday/自建等)

2. **互联网35家（有entry_url）**:
   /Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_internet/internet_companies.jsonl
   字段: slug, name, platform, entry_url, job_count

3. **财富世界500强全部500家（全球，不只中国）**:
   /Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_fortune500/fortune500_2026_full.jsonl
   字段: rank, cn_name, en_name, country, revenue, detail_link

4. **去重合并池284家**:
   /Users/maxzhl/Projects/mcp-suite/research/qiuzhao-expansion-20260910/companies.jsonl

5. **Forbes最佳雇主+GPTW**:
   /Users/maxzhl/Projects/mcp-suite/research/qiuzhao-expansion-20260910/ranking_memberships.jsonl

### 已上线企业（不要重复采集）
腾讯、字节跳动、阿里巴巴、京东、美团、网易（主站/互娱/雷火）、美的、迈瑞医疗、小米、中科创达、百度、滴滴、大疆创新、360集团、携程、贝壳找房、虎牙直播、58同城、得物、叠纸游戏、莉莉丝游戏、广联达、爱奇艺、易车、宝洁、达能、罗氏、普华永道、LVMH、阿迪达斯，以及中国邮政/联通/移动/航天科工/能源建设/国家能源/机械总院/建行/中行等国企。

### 每家采集流程（15分钟内完成，不纠缠）
1. 从候选池取一家未上线企业
2. 找官方招聘入口（官网careers页 / 已知ATS链接 / 搜索引擎）
3. 打开列表第1页，取1-3条岗位
4. 访问详情页，提取: 岗位名称、工作地点、岗位职责正文、任职要求、原链接
5. 映射到统一schema（见下），补industry/recruitment_type/verified_at
6. 写入候选快照，立即推进下一家
7. 阻塞企业（需登录/验证码/403/406/超15分钟无详情）记录原因后跳过

### 统一岗位Schema
```json
{
  "job_id": "公司slug_序号",
  "job_title": "岗位名称",
  "recruitment_unit": "企业主体中文名",
  "source_name": "企业名+招聘官网",
  "source_url": "列表页URL",
  "detail_url": "详情页URL",
  "cities": ["城市"],
  "industry": "企业行业（如互联网/快消/制造/医药/金融）",
  "recruitment_type": "校招|实习|社招",
  "job_category": "岗位类别",
  "education_raw": "学历原文或未披露",
  "major_raw": "专业原文或未披露",
  "graduation_year": "2027届或未披露",
  "description_raw": "职责+要求原文（必须>50字符）",
  "deadline_text": "截止日期或未披露",
  "first_seen_at": "2026-09-10T...",
  "verified_at": "2026-09-10T...",
  "status": "open",
  "country": "中国/美国/德国等",
  "fortune_rank": 数字或null,
  "forbes_employer_rank": 数字或null
}
```

### ATS系统分组（复用逻辑批量处理）
- MokaHR: app.mokahr.com/campus-recruitment/xxx — SPA渲染
- 北森: *.zhiye.com / career.beisen.com — 传统HTML或SPA
- 飞书招聘: *.jobs.f.mioffice.cn — 公开API
- Phenom: *.phenom.com — sitemap+API
- Workday: *.workday.com — 标准API
- 自建站: 各有公开API，用浏览器开发者工具找XHR请求

### 发布流程（每10-20家一批）
1. 合并候选快照，与生产jobs.json去重（按detail_url）
2. 备份: ssh root@114.215.188.109 "cp /var/lib/mcp-suite/jobs.json /opt/mcp-suite/deploy/backup-$(date +%Y%m%d-%H%M)/jobs.json"
3. 上传新jobs.json，原子替换
4. ssh root@114.215.188.109 "systemctl restart mcp-suite.service"
5. curl https://savegems.top/qiuzhao/health 验证
6. 线上抽查: 按企业名搜索能查到、详情返回正文

### 安全红线（绝对不可违反）
- 不读取/覆盖/回滚 access.sqlite3（private/目录，权限drwx------）
- 不修改套餐(39元/200次/日/2026-12-31)、额度、鉴权逻辑
- 不动正式库存(50枚备货码)、兑换记录、订单台账
- 不修改Nginx、其他站点、h5-laoban
- 不绕过登录、验证码、付费限制
- 不伪造岗位、测试结果或完成状态
- 不把"名单入库"写成"岗位完成"
- 未完成定时验收的来源标"首版快照/人工核实"

### 产出文件（写到 /Users/maxzhl/Projects/mcp-suite/research/qiuzhao-500-mvp/）
- candidate_batches/candidate_batch_*.json — 每批候选岗位
- blocked_companies.jsonl — 阻塞企业及原因
- published_companies.jsonl — 已上线企业清单
- expansion_progress.md — 进度报告

### 目标
- 上线企业数(recruitment_unit去重): 500+家
- 每家≥1条有正文(>50字符)的岗位
- 校招/实习/社招分开
- 行业标签基于企业主体
- 阻塞企业100%有原因记录

### 执行要求
- 连续执行，不要每几家就停下来等指令
- 广度优先，不追求单家全量
- 每批发布后线上验证
- 最终报告: 已上线企业数、岗位数、阻塞企业数及原因、剩余候选数

---

以上为完整提示词。
