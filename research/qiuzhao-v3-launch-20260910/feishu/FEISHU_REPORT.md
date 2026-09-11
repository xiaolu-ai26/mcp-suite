# 秋招岗位库 v3 — 飞书多维表格导入报告

- 任务线：秋招 MCP v3 · A线 #3（飞书多维表格创建与数据导入）
- 执行日期：2026-09-10（Asia/Shanghai）
- 执行账号：Max（user 身份，lark-cli）

## 1. 多维表格链接

- **Base 名称**：秋招岗位库 v3 - 20260910
- **Base 链接**：https://my.feishu.cn/base/U2dabn806aNfExsdyPdc2KfBnzc
- **base_token**：`U2dabn806aNfExsdyPdc2KfBnzc`
- **权限范围**：私有（Max 个人云空间），未开启任何外部分享/匿名访问；未配置角色或高级权限。仅创建者可打开。

## 2. 表结构

### 表1：岗位总表（精选岗位镜像）
- table_id：`tbljKHa4WSLm8n1x`
- 主字段：岗位名称（文本）
- 字段清单（17）：

| 字段 | 类型 | 说明 |
|---|---|---|
| 岗位名称 | 文本（主字段） | |
| job_id | 文本 | 岗位唯一ID（生产快照） |
| 公司名称 | 文本 | |
| 招聘单位 | 文本 | |
| 行业 | 单选 | 邮政物流/通信运营/航天军工/能源电力/机械制造/银行金融/互联网/其他 |
| 招聘性质 | 单选 | 校招/社招/实习/未知 |
| 毕业届别 | 文本 | |
| 工作地点 | 文本 | 多城市用「、」分隔 |
| 岗位大类 | 文本 | |
| 投递截止 | 日期(yyyy-MM-dd) | |
| 截止类型 | 单选 | 明确/未披露 |
| 原链接 | URL | source_url |
| 投递入口 | URL | application_url |
| 来源 | 文本 | |
| 状态 | 单选 | open/expired/removed/unverified |
| 复核时间 | 日期时间(yyyy-MM-dd HH:mm) | reviewed_at |
| 备注 | 文本 | |

### 表2：来源状态表（企业处理状态）
- table_id：`tblG0N8cAKFOgSIG`
- 主字段：公司名称（文本）
- 字段清单（12）：

| 字段 | 类型 | 说明 |
|---|---|---|
| 公司名称 | 文本（主字段） | |
| company_slug | 文本 | 企业唯一 slug |
| 行业 | 文本 | |
| 榜单归属 | 多选 | 财富世界500强/财富中国500强/Forbes最佳雇主/GPTW最佳雇主/行业种子 |
| 官方招聘入口 | URL | |
| 平台类型 | 单选 | 自建/Moka/北森/Workday/Phenom/TalentBrew/无门户/未知 |
| 处理状态 | 单选 | 未开始/入口已证实/采集中/有可用岗位部分覆盖/声明范围完整/未发现适用岗位/尚未开放/访问受阻/待核验/维护逾期 |
| 预计岗位数 | 数字(整数) | |
| 已采集岗位数 | 数字(整数) | |
| 阻塞原因 | 文本 | |
| 最后探源时间 | 日期(yyyy-MM-dd) | |
| 适配器规格 | 文本 | api endpoint / detail_url_pattern |

完整机读定义见 `table_schema.json`。

## 3. 导入数量与构成

### 岗位总表：112 条（≥100，精选镜像，非全量）
- 数据源：生产快照 `qiuzhao/data/jobs.json`（9191 条）+ 腾讯 staging `staging/tencent_jobs.json`（814 条）
- 选取策略：优先 2027 届校招、明确截止、多行业覆盖；按招聘单位分层抽样，每单位覆盖多个岗位大类；另取腾讯 24 条覆盖互联网行业
- 行业分布：通信运营 24、能源电力 24、互联网 24、邮政物流 12、航天军工 12、银行金融 10、机械制造 6
- 招聘性质：校招 112（数据集整体为 2027 届校招专场，无社招/实习主路径）
- 截止类型：明确 88、未披露 24（腾讯 staging 未披露截止）
- 状态：open 88、unverified 24（腾讯 staging 未投递验证）

### 来源状态表：74 条
- 24 家已探源企业（`sources_registry.jsonl`）：完整状态
  - 声明范围完整 9（腾讯/字节/阿里/京东/网易/恒瑞/迈瑞/药明康德/三盛）
  - 有可用岗位部分覆盖 5（美团/AstraZeneca/L'Oréal/Bosch/Accenture）
  - 访问受阻 5（NovoProtein/波驰/兆威/联合利华/施耐德）
  - 入口已证实 4（美的/比亚迪/宁德时代/汇川）
  - 待核验 1（P&G）
- 50 家企业清单登记（`companies.jsonl` 中 investigation_status=pending、且未与上述 24 家 slug 重复）：处理状态=未开始，平台类型=未知，优先取有榜单归属的企业

## 4. 视图配置（岗位总表）

| 视图 | view_id | 配置 |
|---|---|---|
| 表格（默认） | vew0uCIf7c | 默认 grid |
| 按行业分组 | vewjaqL5g2 | group by 行业（升序） |
| 校招岗位 | vewnK7nLDw | filter：招聘性质 == 校招（当前命中 112 条） |
| 按地域分组 | vewVrpGCVP | group by 工作地点（升序） |
| 截止日期排序 | vewDczmKHJ | sort by 投递截止（升序） |

来源状态表保留默认「表格」视图，未额外建视图（任务未要求）。

## 5. 同步范围声明（重要）

- **飞书表是精选镜像，不是全量。** 岗位总表仅 112 条精选，真源为服务器岗位快照：
  - 生产快照：`qiuzhao/data/jobs.json`（9191 条）
  - 腾讯 staging：`research/qiuzhao-expansion-20260910/staging/tencent_jobs.json`（814 条）
- **查询真源仍是服务器岗位快照**，飞书仅用于浏览、分组、人工复核视图；数据可能滞后，以服务器快照为准。
- **未同步任何敏感信息**：无用户凭证、无简历、无 API key / 兑换码 / 额度信息、无 cookie/token。导入 CSV 与 JSON 均已脱敏。
- 后台校验、额度依赖、兑换逻辑均不转移到飞书；飞书不承担任何运行时校验职责。

## 6. 产物清单

```
feishu/
├── FEISHU_REPORT.md          # 本报告
├── table_schema.json          # 表结构机读定义
├── prep_data.py               # 数据准备脚本（可复跑）
├── table1_fields.json         # 表1字段定义
├── table2_fields.json         # 表2字段定义
└── import_data/
    ├── jobs_selected.csv      # 112 条精选岗位（UTF-8 BOM）
    ├── jobs_selected.json     # lark-cli batch_create 载荷
    ├── source_status.csv      # 74 条来源状态
    └── source_status.json     # lark-cli batch_create 载荷
```

## 7. 阻塞与限制说明

- **飞书授权**：Max user 身份授权正常，无阻塞。
- **容量**：单批 batch_create 上限 200 条，本任务 112/74 条均单批写入，未触发 1254104 限流。
- **权限**：Base 为 Max 私有，未做分享；如需团队访问需另行配置分享/角色（本轮未授权，按约束不主动扩权）。
- **数据口径**：
  - 「行业」为按招聘单位名映射的粗粒度分类（生产快照无结构化行业字段），仅用于分组浏览，不等于企业工商行业。
  - 「招聘性质」统一为校招：数据集来源为国聘/官网 2027 校招专场，未发现社招/实习主路径。
  - 腾讯 staging 24 条 status=unverified、截止未披露，已如实保留。
- **视图**：按招聘性质要求的「校招/社招/实习」三筛选项，当前数据集全为校招，故仅建「校招岗位」筛选视图；社招/实习视图待后续数据接入后再建。
