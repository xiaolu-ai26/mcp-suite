# 采集缺口报告 — 用 2026-09-20 真实数据跑出的样例(证据)

本目录是 `feat/gap-report` 的缺口报告在**真实生产数据**上的输出,用于核对报告口径
是否与总控 2026-09-20 09:40 的实测一致。所有输入都是**只读**取得的,没有 `--apply`、
没有写库、没有写飞书、没有在精灵上落任何文件。

## 输入(只读取得)

| 文件 | 来源(精灵) | 说明 |
|---|---|---|
| 当日 p1 状态 | `C:\mcp-suite-collector\runs\20260920\data\p1-runs\20260920T064151\status.json`(2026-09-20 11:43:27) | 958 个已完成单元。经 `slim-status.py` 只保留报告需要的字段后导出为 388 KB 的 JSON(未在精灵落盘) |
| 前一日 p1 状态 | `C:\mcp-suite-collector\runs\20260918\data\p1-status.json` | 118 个单元,用作「与前一日对比」的真实基线 |

`slim-status.py` 通过 ssh 以 stdin 传给精灵的正式 venv 执行,**只 print 到 stdout**,
不写任何文件:

```bash
ssh -i ~/.ssh/id_ed25519_lzh_qiuzhao -o IdentitiesOnly=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=yes -l 'LZH\-LZH-' 192.168.31.204 \
  'C:\mcp-suite-collector\.venv\Scripts\python.exe -X utf8 - "C:\mcp-suite-collector\runs\20260920\data\p1-runs\20260920T064151\status.json"' \
  < slim-status.py > status-20260920.json
```

## 生成

```python
from qiuzhao.collector import collection_gap as gap
gap.publish(json.load(open('status-20260918.json')), '<runs>/20260918', previous=None)
gap.publish(json.load(open('status-20260920.json')), '<runs>/20260920')   # previous='auto'
```

## 交付文件

| 文件 | 说明 |
|---|---|
| `status-20260920-slim.json` | **原始输入快照**:当日 958 个单元(瘦身后的 status) |
| `status-20260918-slim.json` | **原始输入快照**:前一日 118 个单元 |
| `collection-gap-20260920.json` | 当日报告(958 个单元全量 + 汇总 + 对比) |
| `collection-gap-20260920.md` | 同一报告的人类可读版(摘要 / 声称完整却少采 / partial TOP20 / 公司维度 / 与 9-18 对比 / 无总数的单元 / 全部单元) |
| `collection-gap-20260918.json` | 前一日基线报告(仅用于对比) |
| `collection-gap-alert-20260920.jsonl` | 阈值告警落盘(2 条) |

输入快照留在仓库里,是为了让总控**不依赖精灵**就能独立复算:

```python
import json
from qiuzhao.collector import collection_gap as gap
gap.publish(json.load(open('status-20260918-slim.json')), '<tmp>/20260918', previous=None)
out = gap.publish(json.load(open('status-20260920-slim.json')), '<tmp>/20260920')
assert out['summary']['total_gap'] == 2636
```

(精灵上的 `runs\20260920\...` 会随 runs 目录清理消失;快照留着,证据链才完整。)

## 关键数字(与总控 09:40 实测逐条对照)

| 指标 | 本报告 | 总控 2026-09-20 09:40 | 一致 |
|---|---|---|---|
| 已完成单元 | 958 | 958 | ✅ |
| 站点自报总数可比对 | 834 | (未给) | — |
| 完全吻合 | 814 | — | — |
| 站点不报总数 | 124 | 124 | ✅ |
| 声称 complete 却少采 | 2 个(商汤科技 intern 66/70、social 86/87),合计 5 条 | 2 个,合计差 5 条 | ✅ |
| 老实标 partial 且少采 | 18 个单元 | 18 个 | ✅ |
| partial 缺口合计 | 2631 条 | 2631 条 | ✅ |
| 其中美团 | 2588 条(social 2180 / intern 259 / campus 149) | 2588 条(social 320/2500、intern 140/399、campus 40/189) | ✅ |
| 总缺口 | 2636 条(= 2631 + 5) | — | — |
| TOP3 缺口公司 | 美团 2588、米哈游 14、金山办公 7 | 美团一家占 2588 | ✅ |

## 告警(阈值:声称完整却少采 > 0,或单公司缺口 > 200)

```json
{"event": "collection_gap.complete_but_short", "severity": "critical", "count": 2, "gap": 5,
 "units": ["商汤科技/intern 66/70", "商汤科技/social 86/87"]}
{"event": "collection_gap.company_gap", "severity": "warning", "company": "美团", "gap": 2588,
 "threshold": 200, "scopes": ["social:2180", "intern:259", "campus:149"]}
```

本分支**没有** `qiuzhao/notify.py`(它在 `feat/cc-bot-notifier`),所以 `notify` 字段
如实记录降级原因,告警落在 `collection-gap-alert-20260920.jsonl`。合并 `20260920b` 后
同一处会走飞书推送,报告模块不需要再改。

## 与前一日对比(9-18 → 9-20)

`previous_date=20260918`:新出现缺口 12 个、缺口变大 3 个、收窄 2 个、已消除 4 个。
(9-18 的 p1 只跑完 118 个单元,所以「新出现」里包含大量当天没轮到的单元 ——
这正是对比功能的用途:区分「本来就没有」和「昨天有今天没了」。)

## 复现性说明

`slim-status.py` 只做字段裁剪,不做任何计算;报告的全部数字由
`qiuzhao/collector/collection_gap.py` 从 coverage 的 `expected_total` 与
`collected_jobs` 直接算出,没有读代码猜、没有人工调整。
