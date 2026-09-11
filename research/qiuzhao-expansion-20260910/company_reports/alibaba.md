# 阿里巴巴 (Alibaba) 校招源探源报告

**任务编号**: QIUZHAO-EXPANSION-20260910  
**采集时间**: 2026-09-10  
**采集方式**: 浏览器渲染访问 (mac_computer_use_tool bu 平面)

---

## 1. 官方归属证据

- **attribution_evidence_url**: https://talent.alibaba.com/
- **attribution_evidence_excerpt**: 阿里巴巴集团招聘门户页脚 "Powered by 阿里巴巴集团 © 2026 阿里巴巴集团版权所有"；校招域名 campus-talent.alibaba.com 为 alibaba.com 子域名；联系电话 0571-28285927（杭州阿里总部区号）
- **homepage_url**: https://www.alibabagroup.com/
- **official_entry_url**: https://talent.alibaba.com/ (集团招聘门户，各业务集团独立招聘)
- **campus_entry_url**: https://campus-talent.alibaba.com/campus/index
- **job_list_url**: https://campus-talent.alibaba.com/campus/position?batchId=100000760001
- **detail_url_pattern**: https://campus-talent.alibaba.com/campus/position/{numeric_id}

## 2. 读取方式

- **access_mode**: requires_rendering (SPA，API需CSRF token)
- **authentication_required_for_read**: false
- **authentication_required_for_apply**: true (投递需登录，可投递多个业务集团，每集团1次机会，最多2个意向)
- **source_kind**: 企业自建
- **platform_family**: 阿里巴巴自建招聘系统 (集团门户+各业务集团独立)
- **platform_version_hint**: batchId=100000760001 (2027届秋招批次)

### 已发现 API 端点

| 方法 | 端点 | 用途 |
|------|------|------|
| POST | /position/search?_csrf={token} | 岗位搜索/列表 |
| POST | /searchCondition/list?_csrf={token} | 筛选条件 |
| GET | /user/getUser?_csrf={token} | 用户信息 |

**注意**: API 需要 CSRF token，需先访问页面获取 cookie/token 后再调用。

## 3. 分页信息

- **pagination_type**: page_number
- **expected_total**: 477 (页面显示"全部在招职位（477）")
- **observed_unique_total**: 10 (首页可见，共48页)
- **completeness**: partial (仅采集首页样例)

## 4. 招聘范围

- **scope_country_region**: 中国内地为主 (北京、广州、杭州、上海、深圳、成都)，含海外业务(阿里国际)
- **scope_recruitment_type**: 混合 (应届校招 + 实习 + 顶尖人才计划)
- **scope_campaign**: 2027届秋招 (阿里巴巴2027届应届生)
- **届别要求**: 2026-11-01 至 2027-10-31 毕业的海内外应届生
- **地域分布**: 北京、广州、杭州、上海、深圳、成都
- **招聘项目**: 阿里巴巴2027届应届生、阿里巴巴日常实习生、阿里巴巴研究型实习生、阿里星-27届应届生
- **业务集团**: 阿里巴巴控股集团、淘天集团、淘宝闪购、飞猪、阿里国际数字商业集团、阿里云、Token Foundry、千问办公、千问事业部、平头哥、高德地图、虎鲸文娱集团、盒马、阿里健康、灵犀互娱

## 5. 真实岗位样例

| # | 岗位标题 | 类别 | 性质 | 届别/项目 | 工作地点 | 更新日期 | 详情URL |
|---|---------|------|------|----------|---------|---------|---------|
| 1 | AI应用算法工程师 | 技术类 | 应届 | 2027届应届生 | 北京/广州/杭州/上海 | 2026-09-03 | https://campus-talent.alibaba.com/campus/position/199907740040 |
| 2 | Agent Infra工程师 | 技术类 | 应届 | 2027届应届生 | 北京/广州/杭州/上海/深圳 | 2026-09-03 | https://campus-talent.alibaba.com/campus/position/199907640058 |
| 3 | AI应用研发工程师 | 技术类 | 应届 | 2027届应届生 | 北京/广州/杭州/上海/深圳 | 2026-08-24 | (列表页可见) |
| 4 | AI Infra工程师 | 技术类 | 应届 | 2027届应届生 | 北京/成都/广州/杭州/上海/深圳 | 2026-08-24 | (列表页可见) |

**岗位1详情摘要 (AI应用算法工程师)**:
- 毕业要求: 2026-11-01 至 2027-10-31
- 笔试方向: 【算法】阿里巴巴集团27届秋招
- 职责: 大模型能力产品化，包括需求定义、应用架构(Prompt/RAG/微调/Agent)、数据飞轮、模型后训练(SFT/RL/PPO/GRPO)、评测体系、生产交付
- 要求: 计算机/数学/统计学硕士博士优先；顶会论文加分；熟悉Transformer/LLM、SFT/DPO/RL、Agent/RAG/Memory/Tool-Use/MCP；精通Python与Pytorch；了解Megatron-LM/vLLM/DeepSpeed

## 6. 任务状态

- **integration_stage**: samples_confirmed
- **run_health**: ok
- **blocker_reason**: 无 (API需CSRF token，但页面渲染可正常读取)

## 7. 调查过程记录

1. 访问 https://talent.alibaba.com/campus → 重定向到集团招聘门户 https://talent.alibaba.com/?lang=zh
2. 门户为各业务集团导航页，通过JS提取到"阿里巴巴校园招聘官网"链接 → https://campus-talent.alibaba.com/campus/index
3. 校招首页显示2027届应届生(2026.11-2027.10毕业)、阿里星人才计划、研究型/日常实习生
4. 点击"职位"→ 进入 /campus/position?batchId=100000760001，显示477个在招职位，48页
5. 通过 network_requests 发现 API: POST /position/search (需CSRF token)
6. 验证岗位详情页 /campus/position/{id}，完整获取岗位描述、要求、届别要求
7. 确认集团招聘门户页脚版权声明作为归属证据

## 8. 适配器开发建议

- API需CSRF token: 需先GET页面获取cookie中的CSRF token，再POST /position/search
- 页面渲染方式更稳定: 可直接抓取列表页HTML解析岗位卡片
- 详情页URL可直接访问，无需额外参数
- batchId=100000760001 为2027届秋招批次ID，可通过 /searchCondition/list 获取
- 全量477条，48页，注意请求频率
