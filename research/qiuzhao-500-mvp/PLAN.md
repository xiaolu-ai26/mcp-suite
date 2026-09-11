# 秋招MCP 500家企业MVP扩源方案

**日期**: 2026-09-10
**目标**: 快速将上线企业从~30家扩至500+家，每家1-3条有完整详情的合格岗位
**策略**: 广度优先，企业数量优先于单家岗位深度

---

## 一、当前基线

- 生产岗位: 15,767条
- 上线企业: ~30家（recruitment_unit去重）
- 生产URL: https://savegems.top/qiuzhao/
- 生产jobs.json: /var/lib/mcp-suite/jobs.json（服务器 root@114.215.188.109）
- 本地项目: /Users/maxzhl/Projects/mcp-suite/
- 已上线核心: 腾讯814、字节4171、阿里477、京东106、美团188、网易193、美的146、迈瑞58、小米100、中科创达125、百度10、滴滴16、大疆15、360 20、携程1、宝洁8、达能12、罗氏5、PwC3、LVMH1、阿迪1 等

---

## 二、企业候选池（去重后约1,500+家）

| 来源 | 文件路径 | 数量 | 说明 |
|---|---|---|---|
| 财富世界500强2026 | `research/qiuzhao-v3-launch-20260910/expansion_fortune500/fortune500_2026_full.jsonl` | 500 | **全球全部500家，不只中国** |
| 财富中国500强2026 | `research/qiuzhao-v3-launch-20260910/expansion_fortune500/merged_companies.jsonl` | 659 | 含世界500+中国500去重 |
| Forbes最佳雇主2025 | `research/qiuzhao-expansion-20260910/ranking_memberships.jsonl` | ~100 | 福利待遇排行榜（partial，需补全900家） |
| GPTW最佳职场2025 | `research/qiuzhao-expansion-20260910/ranking_memberships.jsonl` | 25 | complete |
| 外企候选 | `research/qiuzhao-v3-launch-20260910/expansion_foreign/foreign_companies.jsonl` | 100 | 含platform_hint（MokaHR/Phenom/Workday等） |
| 互联网候选 | `research/qiuzhao-v3-launch-20260910/expansion_internet/internet_companies.jsonl` | ~35 | 含entry_url和platform |
| 行业种子 | `research/qiuzhao-expansion-20260910/companies.jsonl` | 284 | 去重合并池 |

**优先级排序**:
1. 已登记有entry_url的企业（互联网35家 + 外企100家）→ 最快上线
2. 世界500强中国企业122家 → 招聘入口相对好找
3. 世界500强海外企业378家 → 找全球招聘页或中国区
4. Forbes最佳雇主900家 → 福利待遇标签
5. 其余候选池

---

## 三、采集方法论（广度优先，极致压缩单家耗时）

### 每家标准流程（目标15分钟内完成）
```
1. 找官方招聘入口（官网/careers页/已知ATS链接）
2. 打开列表第1页，取1-3条岗位
3. 访问详情页，提取：岗位名称、工作地点、岗位职责、任职要求、原链接
4. 映射到统一schema，补industry/recruitment_type/verified_at
5. 写入staging候选快照
6. 立即推进下一家
```

### 单家最低上线标准
- 至少1条，最多3条有完整详情的岗位
- 必须有：真实公司名、岗位名、工作地点、职责正文（>50字符）、原链接、核实时间
- 校招/实习/社招必须区分（recruitment_type）
- 行业标签基于企业主体（industry），不用岗位职能冒充
- 原文未披露的字段标"未披露"，不猜成"不限"

### ATS系统分组批量处理（复用适配器，大幅提速）
同一ATS系统的企业可复用采集逻辑：

| ATS系统 | 典型企业 | 采集方式 |
|---|---|---|
| MokaHR (app.mokahr.com) | 宁德时代、博世、恒瑞、雀巢、百威、高露洁等 | SPA渲染或API |
| 北森 (career.beisen.com / *.zhiye.com) | 迈瑞、义翘神州、诺唯赞、众多国企 | 传统HTML或新版SPA |
| 飞书招聘 (*.jobs.f.mioffice.cn) | 小米、中科创达、广联达、理想等 | 公开API |
| Phenom (*.phenom.com) | 宝洁、强生、辉瑞等 | sitemap + API |
| Workday (*.workday.com) | 施耐德、诺唯赞、众多外企 | 标准API |
| SuccessFactors (*.successfactors.com) | 众多外企 | OData API |
| 自建站 | 腾讯、字节、阿里、京东、美团、网易、百度、滴滴等 | 各有公开API |

### 阻塞处理
- 需登录/验证码/付费 → 记录原因，立刻跳过，不绕过
- 403/406/500 → 尝试浏览器渲染，仍失败则记录跳过
- Site Under Construction → 记录跳过
- 单家超15分钟无详情 → 标记blocker，跳过
- 阻塞企业写入 `blocked_companies.jsonl`，不删除，后续复查

---

## 四、统一岗位Schema（必须遵守）

```json
{
  "job_id": "来源前缀_唯一ID",
  "job_title": "岗位名称",
  "recruitment_unit": "企业主体名称（统一去重用）",
  "source_name": "来源显示名，如'腾讯校园招聘官方网站'",
  "source_url": "列表页URL",
  "detail_url": "详情页URL",
  "cities": ["城市1", "城市2"],
  "industry": "企业行业，如'互联网/电商'",
  "recruitment_type": "校招|实习|社招",
  "job_category": "岗位职能/类别",
  "education_raw": "学历要求原文",
  "major_raw": "专业要求原文",
  "graduation_year": "毕业届别，如'2027届'",
  "description_raw": "岗位职责+任职要求原文（>50字符）",
  "deadline_text": "截止日期原文或'未披露'",
  "first_seen_at": "首次采集时间ISO8601",
  "verified_at": "核实时间ISO8601",
  "status": "open",
  "country": "中国|美国|德国|...",
  "fortune_rank": 123,
  "forbes_employer_rank": 45
}
```

---

## 五、发布流程

1. 每采集10-20家企业，合并为一个候选快照 `candidate_batch_N.json`
2. 与生产jobs.json去重（按detail_url或job_id）
3. 本地验证：字段完整性、正文非空、企业主体去重
4. 备份当前生产jobs.json到 `/opt/mcp-suite/deploy/backup-YYYYMMDD-HHMM/`
5. 上传新jobs.json，原子替换，`systemctl restart mcp-suite.service`
6. `curl https://savegems.top/qiuzhao/health` 验证
7. 线上抽查：jobs_search按企业名能查到、jobs_detail返回正文

---

## 六、安全红线（绝对不可违反）

- 不读取/覆盖/回滚 `access.sqlite3`（`private/`目录）
- 不修改套餐（39元/200次/日/2026-12-31）、额度、鉴权逻辑
- 不动正式库存（50枚备货码）、兑换记录、订单台账
- 不修改Nginx、其他站点、h5-laoban
- 不绕过登录、验证码、付费限制
- 不伪造岗位、测试结果或完成状态
- 不把"名单入库"写成"岗位完成"
- 生产部署必须备份后才能操作
- 未完成定时验收的来源标"首版快照/人工核实"，不冒充自动更新

---

## 七、验收指标

| 指标 | MVP目标 |
|---|---|
| 上线企业数（recruitment_unit去重） | 500+ |
| 每家有正文岗位 | ≥1条 |
| 岗位正文>50字符比例 | ≥90% |
| 行业筛选可用企业 | ≥80% |
| 阻塞企业有原因记录 | 100% |
| 线上jobs_search按企业可查 | 100%已发布企业 |
| 生产health正常 | 是 |

---

## 八、产出文件

- `candidate_batches/candidate_batch_*.json` — 每批候选岗位
- `blocked_companies.jsonl` — 阻塞企业及原因
- `published_companies.jsonl` — 已上线企业清单（企业名/岗位数/来源/发布时间）
- `expansion_progress.md` — 进度报告（目标/已上线/阻塞/剩余）
- 每批发布后的生产health截图/输出
