# written-test-sources · 第一期标注的可复现材料

> 全部为本期「笔试情况 / 免笔试」字段的原始材料。精灵侧脚本一律通过 `ssh ... python.exe -X utf8 -` 从 stdin 传入、只 print,**未在精灵上写任何文件**。

| 文件 | 说明 |
|---|---|
| `l1_mine.py` | L1 主挖掘:精灵全库 93,519 条岗位描述按公司聚类流程句(笔试/测评/免笔试),输出 `l1_result.json` |
| `l1_mine2.py` | L1 补充挖掘:完整流程句(找"流程里没有做题环节"的公司),输出 `l1_flows.json` |
| `l1_urls.py` | 提取库内官方公告/专场 URL 线索(241 家),输出 `l1_urls.json` |
| `l1_company_counts.py` | 全库公司 → 岗位数(company_of 口径),输出 `l1_company_counts2.json` |
| `l1_result.json` | L1 主结果:888 个流程模板 + 93 家候选公司 + 岗位交集校验 |
| `l1_flows.json` | L1 补充结果:57 个完整流程句(29 家含"无做题"流程) |
| `l1_urls.json` / `l1_company_counts2.json` | 库内 URL 线索 / 公司岗位数 |
| `fetch_pages.py` | L2/L3 抓取器:每站 ≤2 次、全局 ≤150 次、间隔 ≥2.2 秒;自动 charset 识别 + 直连重试 |
| `urls_batch1..5.json` | 5 批抓取清单(共 56 次请求) |
| `fetch_results.json` | 抓取结果(http 状态/编码/命中句/证据文件路径) |
| `evidence/*.txt` | 每个官方页面的逐字正文(编码已修正),人工审核与复核都用它 |
| `build_labels.py` | **定标脚本**:内含人工审核后的 58 条定标清单(L1/L2/L3 + 流程句),输出标注表与复核队列 |
| `coverage_estimate.json` | 覆盖岗位数估算明细 |
| `../written-test-review-queue.csv` | 复核队列(低置信度,不自动入库) |
| `../RECEIPT-written-test.md` / `../DEPLOY-written-test.md` | 收据 / 部署说明 |

重新生成标注表:
```bash
/Users/maxzhl/Projects/mcp-suite/.venv/bin/python build_labels.py
```
(依赖同目录的 `l1_result.json`、`l1_flows.json`、`fetch_results.json`;输出 `written_test_labels.json` 和 `written-test-review-queue.csv`)
