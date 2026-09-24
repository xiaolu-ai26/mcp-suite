# mcp-suite：两个付费 MCP 产品

同一份 `core/` 基建，按 `MCP_PRODUCT` 选择产品：`qiuzhao`（秋招国央企岗位库）与 `bench`（AI 赛道爆款拆解库）。两个产品各自一个 systemd 单元、各自一段 nginx location、各自的静态页，共用一个鉴权兑换数据库 `/var/lib/mcp-suite/access.sqlite3`。

- 秋招岗位库：见下方「秋招岗位库 MCP」章节
- AI 赛道爆款拆解库：见文末「bench · AI 赛道爆款拆解库 MCP」章节

## 开发工作方式（2026-09-23 起）

本地只保留两个入口：主检出目录 `mcp-suite`（`main`，发布基线；线上按文件逐个部署，对应关系见 [维护文档](docs/qiuzhao-daily-delivery.md)）和 `mcp-suite-dev` worktree（`dev`，日常改动）。GitHub 仓库 `xiaolu-ai26/mcp-suite`（公开仓库）是唯一远端，不再用一次性 worktree 堆积本地目录。

流程：在 `mcp-suite-dev` 改代码 → 跑 `pytest`（见下方“运行与维护”）→ 确认无误后把改动合回 `main` → 部署到采集机/服务器 → 部署验证通过后再把 `dev` 已上线的提交视为“可以在 `main` 上长期保留”。`main` 任何时候都应等于当前线上生产代码，未部署的改动只留在 `dev`，不提前合入 `main`。线上按文件逐个部署，已核对范围见维护文档 §6。

## 秋招岗位库 MCP

已部署至 HTTPS 线上服务。截至 **2026-09-24 19:41（北京时间）**：服务器接受版本 `07205aef` 有 171,976 条原始记录；在线服务与飞书原 Base 为同一版本的投影 170,038 行（Base 11 张子表），其中校招 64,593、实习 22,126、社招 83,319；状态 unverified 145,454、open 23,975、expired 609，`unverified` 不计作已确认可投。招聘单位 6,642 个、公司名称 4,682 个均为名称标签数，不是集团数。当日首轮 3,372 个采集单位全部尝试，成功 2,856、partial 188、blocked 328，另有 74 个单位的定向补采单独统计；来源成功率未到 100%，每日无人值守的飞书交付尚未验收。日更链路、交付时序、PR 与部署证据、遗留风险和待审批优化见 [秋招日更交付维护文档](docs/qiuzhao-daily-delivery.md)。

| 入口 | URL |
|---|---|
| MCP（Streamable HTTP） | https://savegems.top/qiuzhao/mcp |
| 兑换页 | https://savegems.top/qiuzhao/ |
| 四客户端接入教程 | https://savegems.top/qiuzhao/guide |
| 只读数据健康状态 | https://savegems.top/qiuzhao/health |

## 历史：2026-09-10 首发快照（非当前数据）

以下为首发时 `deploy/final-online/jobs.json` 对应的线上快照（9,191 条），仅作历史记录，复核日期均为 **2026-09-10，北京时间**。整体返回的 `data_as_of / 数据截至时间` 是全库最新一条的复核时间 **10:32:38**，不是所有岗位在同一时刻都更新；每条保留独立 `reviewed_at`。

| 集团/机构体系 | 岗位记录 | 本组最新复核时间 | 本次覆盖范围 |
|---|---:|---|---|
| 中国邮政集团 | 2,648 | 06:11:26 | 邮政官网公告授权的智联 2027 校招专场，完整公开分页；排除 3 条导航/投递入口记录 |
| 国家能源集团 | 422 | 06:46:07 | 官网校园招聘列表与各岗位详情，完整分页 |
| 中国电信集团 | 10 | 06:46:39 | 最新校园招聘页及已导入岗位复核；不是全站，10 条均为未核实可投状态 |
| 中国银行 | 14 | 06:46:41 | 官网公告明确列出的 10 个总行直属机构、14 个岗位类别；不扩成未具名的分行岗位 |
| 中国建设银行 | 39 | 10:25:09 | 2027 总部计划的 39 个部门岗位标识；岗位名为“部门经办岗”，部门独立记录；不访问要求登录的详情 API |
| 中国移动集团 | 1,610 | 10:27:43 | 国聘官方企业专场，按正常公司选择器分段，完整 ID 核验 |
| 中国能源建设股份有限公司 | 634 | 10:28:13 | 国聘官方校招专场；排除 16 条社招或性质冲突记录；41 条未核实可投状态 |
| 中国广核集团 | 8 | 10:28:19 | 国聘官方企业专场默认校园招聘分组 |
| 中国机械科学研究总院集团 | 72 | 10:28:25 | 国聘官方企业专场默认校园招聘分组 |
| 中国航天科工集团 | 1,165 | 10:29:15 | 国聘官方企业专场；排除 14 条社招；51 条未核实可投状态 |
| 中国联通集团 | 2,569 | 10:32:38 | 国聘官方企业专场，按正常公司选择器分段，完整 ID 核验 |

计数按唯一原始岗位/计划标识计算，不按城市或招聘人数倍增。567 是来源披露的招聘单位名称标签数量，不是经法律主体核验的独立公司数量。`contracting_entity` 在未披露时保持空值。

`open` 反映公开来源状态及日期，并不承诺某位求职者符合资格或一定能够投递。专场标题的年份不能覆盖岗位明确条件：当前国聘记录中有 91 条岗位原文明确 2026 届或 2026 年应届毕业生、且未写 2027，按 2027 查询时不得因专场标题而命中。工具优先匹配 `cohort_raw`，仅在岗位未披露时使用 `campaign_cohort_raw`，响应通过 `cohort_filter_scope` 标明依据。

未写明的学历、专业、届别、截止日均不猜测。未来截止查询只纳入明确日期且有效的记录，按截止日期倒排。每个结果带原公告/官方岗位 URL；没有结果时返回空链接列表和放宽条件建议。已下架记录保留 `removed`，不会被通用过期逻辑改成 `expired`。

## 套餐与库存

`core/store.py` 的 `PLANS["qiuzhao-2026"]` 是套餐配置真源：**59.9 元标准价，兑换激活起 30 天有效，每天工具调用上限 999999**（实质不限量）。早鸟价按当时已兑换的正式码排名浮动：第 1–10 单 29.9 元、第 11–50 单 39.9 元、第 51–100 单 49.9 元，之后恢复 59.9 元标准价；`sale_ends_at` 为 2027-12-31。线上 `GET /api/pricing` 可实时查当前档位、已售数量与当前价，不要照抄本文档的固定数字。

可售库存 = 生产数据库中 `code_kind='formal'` 且尚未兑换（`redeemed_at IS NULL`）的兑换码数量。正式码只能在生产服务器上生成，本机不生成、也不持有正式码：

```sh
cd /opt/mcp-suite && sudo -u mcp-suite .venv/bin/python -m core.admin generate-codes \
  --db /var/lib/mcp-suite/access.sqlite3 \
  --out /var/lib/mcp-suite/<批次文件名>.txt \
  --count <数量> --plan qiuzhao-2026 --kind formal
```

以 `mcp-suite` 系统用户执行（服务本身也以该用户运行：systemd `WorkingDirectory=/opt/mcp-suite`，venv 为 `/opt/mcp-suite/.venv`）；`--db` 必须指向生产库 `/var/lib/mcp-suite/access.sqlite3`。`--kind` 现为必填参数（见 `core/admin.py`），只能是 `formal`（正式码，可售，一经生成永久不可删除）或 `test`（测试码，可随时删除，且不计入早鸟排名）。脚本对 `--out` 使用独占创建防止覆盖已有批次文件，且只打印文件位置与数量，不输出兑换码明文。

**2026-09-17** 已在生产库生成 20 个正式码（`plan=qiuzhao-2026`，全部未兑换）。此前本机 `private/qiuzhao-2026-stock-50.txt` 所称的“首发库存 50 码”经核实并不对应生产库存（生成当时生产库正式码为 0），已归档为 `private/archive/NOT-IN-PROD-qiuzhao-2026-stock-50.txt`，不代表可售库存，也不在生产数据库中。库存与 API key 不入代码库或日志。

API key 在兑换响应中只展示一次；丢失后可凭原兑换码调用 `POST /recover`（`core/server.py`）校验并轮换出新 key，按客户端 IP 哈希限流，不是找回原 key 明文。数据库只存兑换码/key 摘要；用量日志只记匿名 key ID、产品、工具和时间，不记录查询参数或简历。

## 首发验收（2026-09-10，历史）

| 检查 | 结果与证据 |
|---|---|
| 本地鉴权与并发 | `tests/test_core.py` 共 6 项通过：原子兑换、220 次并发扣额仅 200 次成功、权限与过期、午夜重置、字段保真、岗位届别优先于专场标题 |
| 本地 HTTP/MCP 与页面 | 新码兑换、重复码拒绝、三工具、额度 200→197、过期拒绝均通过；Chrome 实际页面兑换、390px 移动端排版通过，截图已遮盖 key；见 `docs/local-e2e-receipt.json`、`docs/ui-receipt.json` |
| 真实 Claude Code 线上调用 | **已通过**。使用现有 Max 会员、隔离 MCP 配置和额外测试 key；`jobs_search`、`jobs_deadlines`、`jobs_detail` 各实际调用 1 次，三个 tool_result 均有真实岗位、原 URL 和截至时间，线上剩余额度实读 197；见 `docs/claude-code-online-e2e.jsonl` |
| Claude 验证的快照范围 | 本次实际调用发生于新增数据重启之前，使用 3,094 条的四源快照、截至 06:46:41。最终 9,191 条新库另外进行线上 HTTP/MCP 复核，不把旧快照的 Claude 结果冒充新库计数验证 |
| 最终新库线上 HTTP/MCP | 9,191 条快照的三工具均实查成功，未来 90 天明确截止结果 5,007 条，额度 200→197；2027 查询逐页遍历 87 页、8,654 条，与最终快照预期一致，91 条明确 2026 的岗位误匹配 **0**；所有结果保留原 URL 和复核时间。见 [最终线上验收收据](deploy/final-online-e2e-receipt.json) |
| 国聘独立数据审查 | 6,058 条唯一记录；六个集团各取 1 条，对原 API 白名单证据核对岗位、单位、学历、城市、截止、发布日期、校招性质和描述均通过；30 条社招/性质冲突记录被排除 |
| 跨来源 5 条抽验 | 邮政 1、国家能源 1、建行 1、国聘 2，实际重新读取官方公告/API 并对照已存记录，全通过；见 `deploy/final-online/sample_verification.json` |
| 已有四源任务保活与定时 | systemd 专属服务保活；手动 cron 2026-09-10 00:54:21 开始、01:31:34 成功结束；已安装定时任务实际于 06:10 触发，06:46:42 成功结束；见 `deploy/cron-four-source-receipt.json` |
| 新增源服务器增量复核 | 建行与国聘已在服务器持锁实际重跑，2026-09-10 10:32:39 完成，最终 9,191 条、0 个采集报警；见 [新增源服务器增量回执](deploy/new-sources-production-receipt.json)、`deploy/final-online/summary.json`、`deploy/final-online/alerts.json` |

夜间 `docs/claude-code-e2e.jsonl` 中的 429 是历史失败记录：当时会员会话额度未恢复，不能视为成功；上午已完成真实重试并以新的线上收据为准。WorkBuddy、豆包工作、Cherry Studio 教程依据一手资料编写，截图位置明确标为待补，尚未完成这三个客户端的实机兼容验收。

本任务完成的是岗位数据服务、鉴权兑换、库存、教程和部署验收。**没有配置小红书平台自动发货、上架商品、发布视频或取得销售订单**，这些状态不能由服务上线替代。

## 运行与维护

FastMCP 2.14.7 / Python 3.11+，Streamable HTTP，单独运行于 `127.0.0.1:8768`。Nginx 将 `/qiuzhao/` 前缀剥离后转发；原 H5 与原主站配置的部署前后校验值保存在部署收据中。

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
MCP_DB_PATH=/var/lib/mcp-suite/access.sqlite3 \
MCP_JOBS_PATH=/var/lib/mcp-suite/jobs.json \
MCP_PUBLIC_BASE_URL=https://savegems.top/qiuzhao \
.venv/bin/uvicorn core.server:app --host 127.0.0.1 --port 8768 --no-access-log
```

服务器代码在 `/opt/mcp-suite`，持久数据和私密数据库在 `/var/lib/mcp-suite`。专属服务为 `mcp-suite.service`。首发时每日任务为服务器北京时间 06:10 运行 `deploy/collector-daily.sh`（历史）；按当前设计，秋招日更由 Windows 采集机计划任务采集并经 receiver 发布，服务器每小时受控激活已接受版本，飞书由另行启动的 Excel 导入交付（尚未接入采集流程自动调用；采集与激活已配置，但长期自动运行未验收），详见[维护文档](docs/qiuzhao-daily-delivery.md)。采集失败保留旧快照并写报警；国聘按各专场成功且完整的结果更新下架状态，失败专场保留既有记录。所有源码更新应先审查，只重启本服务，不覆盖持久数据库，不改其他站点。

关键业务路径：`core/server.py`、`core/store.py`、`qiuzhao/tools.py`、`qiuzhao/collector/run.py`、`ccb.py`、`guopin.py`。采集低频访问公开官方渠道；建行只兼容旧 TLS 握手，仍校验证书，不调用需要登录的岗位详情接口。

```sh
uv pip install --python .venv/bin/python pytest
.venv/bin/python -m pytest -q
# 仅使用隔离 private/test-access.sqlite3 启动本地 :8768 服务后：
.venv/bin/python -m tests.e2e_local
```

部署状态见 `deploy/deployment-receipt.json`，最终新库、届别检索和库存验收以 [最终线上验收收据](deploy/final-online-e2e-receipt.json) 为准；运行状态需用实际 `/health`、systemd 和服务器定时任务回执重新确认，不把本 README 的历史快照当作未来实时状态。

## bench · AI 赛道爆款拆解库 MCP

已部署至 HTTPS 线上服务。库中有 **485 条唯一记录**，全部来自 Max 已有的三批存量对标研究资产（`AI自媒体/04_对标参考/` 与两张飞书表），本次只做迁移、归一与标签补打，**没有做任何平台内容读取**。

| 入口 | URL |
|---|---|
| MCP（Streamable HTTP） | https://savegems.top/bench/mcp |
| 兑换页 | https://savegems.top/bench/ |
| 接入教程 | https://savegems.top/bench/guide |
| 只读数据健康状态 | https://savegems.top/bench/health |

### 数据来源与构成

| 批次 | 入库条数 | 标签来源 | 说明 |
|---|---:|---|---|
| `low_follower_viral_2026-06` | 319 | human（2026-06 低粉爆款研究的人工/原研究标签） | 每条带链接、原标题、选题分类、内容角度、钩子、痛点、承诺、受众、变现线索、可复刻分与拆解结论 |
| `viral_radar` | 117 | ai_filled | 飞书「爆款雷达」中 `来源=雷达` 的 133 条，按链接去重后 117 条；只有链接与原标题等公开元数据，标签与拆解结论由 AI 依据标题判断 |
| `benchmark_library` | 49 | 17 条 ai_filled、32 条 url_only | 飞书「对标库」中 `内容来源=对标参考/学习素材` 且链接指向真实内容平台的条目；原表无标题的 32 条按红线留空、不补标签、不编造 |

三批共 501 条输入，按链接/笔记 ID 去重掉 16 条，落地 485 条。飞书表中 `来源=aihot` 的 67 条 AI 资讯、`内容来源=我的发布` 与选题池均未入库。数据文件 `bench/data/bench.json` 由 `bench/build_bench.py` 离线生成（需 openpyxl，用系统 `python3` 跑），字段走白名单投影。

标签体系（`bench_taxonomy()` 返回，含各类条数）：选题分类 12 类、标题公式 16 类（7 个来自 `爆款标题模式库.md`，其余从 319 条自由文本归一而来）、内容角度 10 类、封面版式 7 类、粉丝区间 8 档、破圈分级 5 档。**封面版式本期 485 条全部未标注**——判定封面版式必须看封面图，本产品既不保存也不返回封面图，故只给出词表并在 `coverage_notes` 里说明，不用标题去猜。发布时间只有 259/485 条可考证，其余留空。

### 合规边界（这是产品能不能卖的前提）

接口只返回：公开链接、原标题、平台、内容形式、可考证的发布时间、粉丝量级区间、破圈分级词、原创标签、原创拆解结论、观察日期。**不返回**笔记/视频正文、逐字稿、图片、封面图与视频地址，**不返回**点赞/收藏/评论/分享/播放/精确粉丝数/赞粉比。粉丝只出区间，破圈只出分级词（现象级/强/中/观察/未分级），分级由原研究分档换算，原始数字不进落地文件也不进接口。

`bench/assert_clean.py` 对落地文件、文案面和线上接口返回做全库扫描断言，退出码非 0 表示不合规，结果写入 `bench/receipts/`：

```sh
.venv/bin/python -m bench.assert_clean                                   # 只扫本地文件与文案
BENCH_ASSERT_KEY=... .venv/bin/python -m bench.assert_clean --url https://savegems.top/bench
```

### 套餐与库存

`core/store.py` 的 `PLANS['bench-monthly']`：**29 元，兑换激活起 30 天有效，每天 200 次工具调用**。兑换码前缀 `BM-`，key 前缀 `bm_`；秋招的 `QZ-`/`qz_` 与固定秋招季有效期不受影响。首发库存文件 `private/bench-monthly-stock-50.txt`，50 个唯一兑换码，0600，已逐个摘要核对与生产库一致且全部未兑换。库存与 key 不入代码库、日志或报告。

### 实际验收（区分已验证与未验证）

| 检查 | 结果与证据 |
|---|---|
| 本地鉴权与工具单测 | `.venv/bin/python -m pytest -q` 10 项通过，含秋招 `QZ-` 码格式/`qz_` key/`valid_through=2026-12-31` 回归与 bench 30 天有效期、额度文案、工具过滤 |
| 本地 HTTP/MCP e2e | 新码兑换、重复码 400、跨产品码不被烧、三工具、额度 200→196、过期 403、无该产品权限 403 全通过；见 `bench/receipts/local-e2e-receipt.json` |
| 线上 HTTP/MCP e2e | 生产环境用额外测试码跑通兑换→调用→额度 200→197→过期 403；见 `bench/receipts/online-e2e-receipt.json` |
| 真实 Claude Code 线上调用 | **已通过**。隔离 MCP 配置 + 独立测试 key，`bench_search`/`bench_detail`/`bench_taxonomy` 各实际调用 1 次，返回真实记录与 485 条统计，线上剩余额度实读与调用次数一致 |
| 全库合规断言 | 线上分页遍历 485/485 条 + taxonomy + detail，规则全过；唯一提示是有 1 条他人**原标题**里出现了脚本禁用词表中的一个词；按「原标题照出」的决策原样保留，脚本对 `title` 字段只记提示不判失败，并在收据中写明该条 id。见 `bench/receipts/assert-clean-online.json` |
| 5 条链接抽验 | **部分失败，如实记录**：抖音、TikTok、换发 token 的 xhslink 短链 3 条可正常打开且标题/内容与标签相符；2 条小红书长链打不开。见下条与 `bench/receipts/link-spotcheck-receipt.json` |
| 秋招回归 | 线上 `/qiuzhao/health` 正常（9,191 条），用额外测试码真实调用 `jobs_search` 成功、额度 200→199，回归 key 随后停用；`mcp-suite.service` 全程未重启。另在本地以新 `core` 跑 `MCP_PRODUCT=qiuzhao` 复核三工具与 `QZ-` 行为一致，见 `bench/receipts/qiuzhao-regression-receipt.json`、`bench/receipts/qiuzhao-newcode-local-receipt.json` |

**链接可用性是本产品当前最大的已知缺陷**：库内 439/485 条是带时效参数的小红书笔记长链，2026-09-10 在已登录浏览器实测均无法直接渲染（跳 404 并提示需在小红书 App 内查看）。对照实验证明这不等于笔记已删除——一条确认存活的笔记去掉或换掉 token 后同样打不开。可行用法是拿返回的原标题到小红书 App 内搜原文，链接作为出处留档。该结论已写进接口返回的 `link_note`、兑换页常见问题与接入指南，未向买家隐瞒。

本次完成的是数据迁移与归一、AI 标签补打、三个工具、合规断言脚本、`core` 多产品泛化、兑换/教程页与部署验收。**没有上架商品、没有配置自动发货、没有发布视频、没有取得任何销售订单**，服务上线不能替代这些状态。

### 运行与维护

```sh
# 重建数据文件（需要 openpyxl，用系统 python3；.venv 里没有）
python3 bench/build_bench.py

# 本地起服务（隔离数据库与端口）
MCP_PRODUCT=bench MCP_DB_PATH=$PWD/private/test-access.sqlite3 \
MCP_BENCH_PATH=$PWD/bench/data/bench.json \
MCP_PUBLIC_BASE_URL=http://127.0.0.1:8779 \
.venv/bin/uvicorn core.server:app --host 127.0.0.1 --port 8779 --no-access-log
BENCH_E2E_BASE=http://127.0.0.1:8779 .venv/bin/python -m tests.e2e_bench_local

# 部署（默认 dry-run）
bash deploy/deploy-bench.sh
bash deploy/deploy-bench.sh --apply
```

线上跑在 `127.0.0.1:8769`，systemd 单元 `mcp-suite-bench.service`，nginx 段 `deploy/mcp-suite-bench.conf`（`^~ /bench/`）。数据文件在服务器上不被改写，每次部署整份替换 `/var/lib/mcp-suite/bench.json`；`access.sqlite3` 永不覆盖。部署脚本在动手前后各校验一次主 vhost 的 sha256，并在收尾时同时确认 `/bench/health`、`/qiuzhao/health` 与 `/shuju/` 三者仍正常。关键路径：`bench/build_bench.py`、`bench/tools.py`、`bench/assert_clean.py`、`core/server.py`、`core/store.py`。断点续跑记录见 `bench/PROGRESS.md`。
