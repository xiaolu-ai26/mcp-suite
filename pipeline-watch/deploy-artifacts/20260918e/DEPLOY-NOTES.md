# 20260918e 部署说明（阿里 5 家子公司 + 腾讯音乐）

## 本次改动文件
| 文件 | 性质 |
|---|---|
| `qiuzhao/collector/alibaba_headless.py` | 重写：单入口 `categoryType=freshman` 的阿里 headless 适配器 → 多实体/多批次可配置 p1 适配器 |
| `qiuzhao/collector/tencent_music.py` | 新增：腾讯音乐 `join.tencentmusic.com` 专用适配器 |
| `qiuzhao/collector/p1_pipeline.py` | 仅在既有 REGISTRY 注册块之后追加独立注册块（append-only，未改动其它行） |

## 叠加顺序
在 `20260918c`（银行批次 1）之后叠加。`p1_pipeline.py` 采用 append-only 注册块；若其它并行批次（如 `20260918d`）也已部署，合并时保留各批次注册块，不要整体覆盖。

## 注册与日链
`p1_pipeline` 的 `DEFAULT_COMPANIES = [*COMPANIES, *平台公司, *银行, *本批次阿里/腾讯]`，日链 `windows_collector.py` 调 p1 时不传 `--companies`，因此新增 7 家会自动进入日链，无需改 `windows_collector.py`。新增：阿里巴巴、淘天、阿里云、高德、饿了么、菜鸟、腾讯音乐。

## Headless 依赖（阿里系；本次未在精灵执行）
阿里集团招聘平台对非浏览器指纹请求 403，必须走 headless Chromium。腾讯音乐是纯 HTTP 接口，不需要浏览器。

**精灵（Windows）安装命令（需要时由站长手动执行，本包未执行、未部署）：**

```bat
C:\mcp-suite-collector\.venv\Scripts\python.exe -m playwright install chromium
```

代码在找不到自带 Chromium 时会回退到系统 Chrome（`channel='chrome'`）。若精灵上没有 Chrome，则必须先装上表命令对应的 Chromium。

## 节流与预算
- 阿里：每次页面/请求间隔 ≥2s（`QIUZHAO_ALIBABA_MIN_INTERVAL`，默认 2.0）；每实体 ≤40 次（`QIUZHAO_ALIBABA_REQUEST_BUDGET`，默认 40）。
- 腾讯音乐：`QIUZHAO_TME_MIN_INTERVAL`（默认 2.0）/ `QIUZHAO_TME_REQUEST_BUDGET`（默认 40）。
- 全程只读：无登录、无验证码、不逆向签名；仅公开列表/详情。

## 本地只读实测证据
`/Volumes/臭垃圾桶/生财MCP/_worktrees/ali-tencent-out/run/summary.json`（7 家 status/complete/条数/字段可用率）与各 `run/<slug>/campus/result.json` + 页面证据。
