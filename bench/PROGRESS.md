# bench 模块进度（断点续跑用）

- 2026-09-10 阶段1 数据迁移：写 `bench/build_bench.py`（系统 python3 跑，venv 无 openpyxl），
  产出 `bench/data/bench.json` 485 条（A低粉爆款研究319 / B爆款雷达133 / C对标库49，按链接去重掉16）。
  源中间件 `bench/sources/radar_records.json`、`bench/sources/benchmark_lib_records.json`（飞书导出，含内部字段，不进产品文件）。
  已验证：脚本可重复运行；输出走字段白名单。
- 2026-09-10 阶段2 AI 补标签：`bench/sources/ai_tags_raw.tsv`(134 行) → `bench/sources/ai_tags.json`，
  build 时合并。A 批 319 条保留人工/原研究标签；B/C 共 134 条为 ai_filled；32 条只有链接为 url_only。已验证：build 输出 485 条、标题公式未归类仅 3 条。
- 2026-09-10 阶段3 工具与断言：`bench/tools.py`(bench_search/detail/taxonomy)、`bench/assert_clean.py`。
  已验证：`.venv/bin/python -m bench.assert_clean` 通过，收据 `bench/receipts/assert-clean.json`。
- 2026-09-10 阶段4 core 泛化：`core/store.py` PLANS 增 bench-monthly(29元/30天/200次)，兑换码前缀与 key 前缀按 plan 派生；
  `core/server.py` 按 MCP_PRODUCT 选工具集/静态页/数据。已验证：pytest 10 passed（含秋招 QZ- 行为回归）。
- 2026-09-10 阶段5 本地 e2e：`tests/e2e_bench_local.py` 全绿，收据 `bench/receipts/local-e2e-receipt.json`；
  线上格式断言在本地 8779 端口跑通全库 485 条，收据 `bench/receipts/assert-clean-local-online.json`。
- 2026-09-10 阶段6 部署：`deploy/deploy-bench.sh --apply` 成功。mcp-suite-bench.service @127.0.0.1:8769，
  nginx `^~ /bench/`，vhost sha256 部署前后一致，mcp-suite.service 未重启仍 active。
  已验证：/bench/health records=485、/qiuzhao/health jobs=9191、/shuju/ 200。
- 2026-09-10 阶段7 线上验收：`tests/e2e_bench_online.py` 全绿（收据 `bench/receipts/online-e2e-receipt.json`）；
  `bench/assert_clean.py --url https://savegems.top/bench` 全库 485/485 通过（收据 `bench/receipts/assert-clean-online.json`）；
  本机 Claude Code 隔离 MCP 配置真调三工具各一次通过；50 个备货码 `private/bench-monthly-stock-50.txt`（0600）经摘要核对全部未兑换。
- 2026-09-10 阶段8 抽验与披露：5 条链接实测，抖音/TikTok/xhslink 短链 3 条可开且标题标签相符，
  2 条小红书长链因时效参数失效打不开（对照实验证明非删除）。已把结论写进 `link_note` 字段、兑换页 FAQ 与教程页，
  收据 `bench/receipts/link-spotcheck-receipt.json`。README 增补 bench 章节。
- 待 Max 决定：439 条小红书长链的可打开性（是否接受「App 内按标题搜原文」的用法，或另行安排换发短链）。
- 2026-09-10 收尾：验收用 Claude Code 测试 key 已停用（线上 /mcp 返回 401），生产库活跃 key 归零；
  QZ- 备货 50/50 未兑换、BM- 备货 50/50 未兑换（另有 1 个未用的额外测试码在 private/bench-test-codes.txt）。
  vhost sha256 与部署前一致，mcp-suite.service ActiveEnterTimestamp 仍为 10:24:17（全程未重启）。本地临时服务已停。
- 2026-09-10 红线修复（自由文本内嵌互动数）：字段级早就没有互动数字段，但 `takeaway` 自由文本里内嵌了他人笔记的精确互动数
  （「收藏8615极高」「1.4w赞1.9w藏」「没爆(9赞)」等），旧 `assert_clean.py` 只查字段名黑名单和数值类型，扫不到句子里的数字。
  处理：改写规则逐条写进 `bench/build_bench.py` 的 `METRIC_SCRUB`（literal 片段→定性表达，由 `sanitize()` 在 build 时套用），
  `bench.json` 用 `build_bench.py` 重新生成而不是手改 JSON；共改 68 条记录 69 处（takeaway 68 处 + `xhs-666c0258…` 的 title_hook「涨粉8W」1 处），
  其余字段与三个 1-5 打分逐字节未变，记录数仍 485。改动前后逐条收据 `bench/receipts/metric-scrub-receipt.json`。
  刻意保留：他人原标题（含「小红书数据」「涨粉8W」两条，待 Max 决定）、`promised_result` 的「收藏10个…」（承诺动作非互动数）、
  收入数字（「单月10万」「收益7万」）、无数字的「破万」。
- 2026-09-10 断言加固：`assert_clean.py` 新增两条规则——(1) 任何自由文本中「互动词+数字」双向命中即判失败，
  覆盖 万/w/小数/括号/个位数（总控给的正则是其子集，34/34 全覆盖），例外只有 2 条且逐条写在 `METRIC_NUMBER_ALLOW` 里带理由；
  (2) 任一文案面扫到 0 字符即判失败。回归验证：对清洗前的旧数据跑 → 68 条失败、退出码 1；对清洗后跑 → 通过、退出码 0。
- 2026-09-10 收据疑点已查明：`assert-clean-online.json` 里 `copy:README.md=0` 是因为那次线上扫描（15:19）早于 README 补 bench 章节（15:21），
  `copy_body()` 找不到 `## …bench…` 标题时静默返回空串，规则等于没跑还报绿。现在改成判失败（已用无 bench 章节的临时 README 实测触发），
  并顺手修了 `--copy` 指到仓库外路径时 `relative_to()` 崩溃的问题。本轮本地与线上收据 README 均为 4349 字符。
- 2026-09-10 重新上线：没跑 deploy-bench.sh 全量流程（这次只是换数据）。线上先就地备份
  `/var/lib/mcp-suite/bench.json.bak-20260910-154121`，再 scp 临时文件→校验 sha256→`mv -f` 原子替换，只重启 mcp-suite-bench.service；
  另同步了 `bench/assert_clean.py`、`bench/build_bench.py` 到 /opt/mcp-suite。vhost 未动、nginx 未 reload、sha256 前后一致，
  `mcp-suite.service` ActiveEnterTimestamp 仍是 10:24:17（未重启）。收据 `bench/receipts/metric-scrub-deploy-receipt.json`。
  验收：`/bench/health` records=485、`/qiuzhao/health` jobs=9191、`/shuju/` 200、`/bench/` 与 `/bench/guide` 200、
  线上 `assert_clean.py --url https://savegems.top/bench` 全库 485/485 通过（`bench/receipts/assert-clean-online.json`）、pytest 10 passed。
  跑线上断言时把已停用的验收测试 key 临时启用、扫完立刻停用，未新发码、未动 50 个 BM- 备货码；扫完 `/bench/mcp` 无 key 仍 401、可用 bench key 为 0。
- 待 Max 决定（本次未改，维持现状）：① `xhs-6a25314d0000000035030e23` 的 title「我把 Obsidian 做成了小红书数据看板」含禁用词「小红书数据」；
  ② `xhs-666c0258000000001c0207a2` 的 title「用AI做儿童绘本🔥涨粉8W」含他人笔记的涨粉数。两条都按「原标题照出」保留，脚本只记提示不判失败。
- 2026-09-10 15:56 生产鉴权库凭据清理（只改 `access.sqlite3` 三行 `disabled`，未动代码、服务、兑换码）：核验发现「活跃 key 归零」的说法不准确，
  `api_keys` 实有 3 行 `disabled=0` —— `3391530e775234729a67ea61`（qiuzhao，有效期到 2027-01-01，0 次调用，15:41 线上兑换回归测试遗留，从未停用）、
  `0e77f69957b648dac8009077` 与 `88b5e8e9d709cfc53652de33`（bench，`e2e_bench_online.py` 的 `expire_remote()` 只改 `expires_at` 不置 `disabled`，故已过期但标志位仍启用）。
  操作前用 `sqlite3 .backup` 做一致性备份 `/var/lib/mcp-suite/access.sqlite3.bak-20260910-155558`（0600，mcp-suite，`integrity_check=ok`），
  再单条事务 `UPDATE api_keys SET disabled=1 WHERE id IN (三个 key_id) AND disabled=0`，`changes()=3`，无 DELETE。
  复核：`disabled=1` 共 8 行、活跃 0 个；表行数 8/8/109/7/127 前后一致；两批备货码 100 个 code_hash 的 sha256 前后同为 `0b7aad3e…`（bench-monthly 50/50、qiuzhao-2026 50/50 全未兑换）。
  服务未重启（`mcp-suite.service` ActiveEnterTimestamp 仍 10:24:17、MainPID 1699882、NRestarts=0）：`_authorize()` 每次请求新开连接查 `disabled`，改行即刻生效。
  `/bench/health` records=485、`/qiuzhao/health` jobs=9191、两个 `/mcp` 无 key 均 401。
