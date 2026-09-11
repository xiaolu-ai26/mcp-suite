# 本地 ~/Projects/mcp-suite 与线上 live-baseline 差异清单

生成时间：2026-09-11 21:30（北京时间）。范围：`core/`、`qiuzhao/` 下的 `.py` 与 static 文件。`<` = 本地（9/10 版），`>` = 线上。
线上基线：`live-baseline/`（server.py sha256 `08143798…dccd`，tools.py sha256 `77ffdb61…0d52`）。

## 内容不同的文件

| 文件 | 行数（本地 → 线上） | 说明 |
|---|---|---|
| core/server.py | 253 → 530 | 线上多了 3 个 jobs_search 参数（job_category、graduation_year、major_category，jobs_search 从 10 个参数变 13 个）；新增分销账本 `DistributionStore`，以及 `/wechat-qr.png`、`/api/changelog`、`/api/distribution/*`、`/admin`（内联 HTML）、`/admin.css`、`/admin.js`、6 个 `/img/guide/*` 图片路由、`/api/admin/{stats,codes,delete_code,generate}` 管理接口。 |
| core/store.py | 177 → 184 | qiuzhao-2026 套餐改为 59.9 元、30 天、每日 999999 次；`generate_codes` 会把明文 `code_plain` 写进 redemption_codes（建表语句里没有这一列，说明线上库是手工加的列）；新增 `delete_code`。 |
| qiuzhao/tools.py | 90 → 126 | 新增 `MISSING_QUERIES_FILE`：搜索无结果时写入 `/var/lib/mcp-suite/missing_queries.jsonl`；新增 job_category、graduation_year、major_category 三种筛选；city 同时匹配 city_normalized；无结果时的提示文案加了"已记录"。 |
| qiuzhao/collector/run.py | 284 → 265 | 线上版去掉了 tencent、bytedance、meituan、netease、midea、mindray、alibaba 七个新源的调度入口（本地版有），merged 字典对缺 id 的记录做了兜底。 |
| core/static/index.html | 110 → 326 | 线上兑换页大改：新增价格、用法场景（9 个卡片）、用户评价、更新日志、推荐分销、FAQ 等区块。 |
| core/static/app.js | 182 → 292 | 线上新增评价渲染、分销推荐链接表单、更新日志加载、用量滚动条等前端逻辑。 |
| core/static/site.css | 6 → 375 | 线上是展开后的完整样式表，覆盖新增区块；本地是 6 行压缩版。 |
| core/static/guide.html | 21 → 21 | 接入指南的 WorkBuddy、豆包工作、千问办公三节改成分步列表，头部结构调整，Claude Code / Hermes 文案微调。 |

## 仅线上存在

| 文件 | 说明 |
|---|---|
| core/distribution.py | 分销账本（独立 SQLite，默认 `/var/lib/mcp-suite/distribution.db`）。 |
| core/static/admin.html / admin.css / admin.js | 管理后台前端（兑换码生成与管理、分销统计）。 |
| core/static/changelog.json | 更新日志数据。 |
| core/static/wechat-qr.png | 微信二维码。 |
| core/static/img/guide/*.png, *.jpeg | 接入指南截图（豆包、WorkBuddy、千问各 2 张）。 |
| qiuzhao/collector/auto_collect.py | 自动采集脚本。 |
| qiuzhao/collector/export_csv.py | 导出 CSV 脚本（生成 /var/lib/mcp-suite/*_latest.csv）。 |

## 仅本地存在

| 文件 | 说明 |
|---|---|
| qiuzhao/collector/{alibaba_headless,base_headless,bytedance,meituan,midea,mindray,netease}.py | 本地的新源采集器，线上 `/opt/mcp-suite` 没有这些文件（线上 run.py 也不再调用它们）。 |

## 结论

本地 `core/`、`qiuzhao/` 比线上旧，不能当基线。本任务的两个发布包都从 `live-baseline/` 派生，没有改动本地 `~/Projects/mcp-suite` 的 core/、qiuzhao/、private/、deploy/、.venv。
