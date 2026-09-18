# 部署件 20260918g：collector-next-2 一步到位累积包

**叠加顺序：从精灵现役 `20260918`（run.py / p1_pipeline.py / guopin.py / windows_collector.py，
无平台文件）一步覆盖即可。** 20260918b/c/d/e/f 均**未部署**，本包已把它们全部累积进来，
不需要再逐个叠加。本包未执行部署、未 SSH、未写库、未 push。

## 覆盖文件

| 文件 | 目标路径 | 类型 |
|---|---|---|
| `guopin.py` | `qiuzhao/collector/guopin.py` | 覆盖（20260918b 版，含国聘自动专场） |
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖（累积版：五个注册块 + 905 家调度安全） |
| `windows_collector.py` | `deploy/windows_collector.py` | 覆盖（= 20260918b 版，逐字未改；同步段一字未动） |
| `p1_platform_beisen.py` | `qiuzhao/collector/` | 新增（北森通用适配器） |
| `p1_platform_moka.py` | `qiuzhao/collector/` | 新增（Moka 通用适配器） |
| `p1_platform_workday.py` | `qiuzhao/collector/` | 新增（Workday CXS） |
| `p1_platform_successfactors.py` | `qiuzhao/collector/` | 新增（SAP SuccessFactors） |
| `p1_feishu_public.py` | `qiuzhao/collector/` | 新增/覆盖（飞书配置化 + `collect` 别名修复） |
| `p1_banks_01.py` | `qiuzhao/collector/` | 新增（银行批 1） |
| `alibaba_headless.py` | `qiuzhao/collector/` | 新增（阿里多实体 headless） |
| `tencent_music.py` | `qiuzhao/collector/` | 新增（腾讯音乐） |
| `p1_platform_companies.json` | `qiuzhao/collector/` | 覆盖（beisen/moka/feishu/workday/successfactors 全段 + 清洗后公司名） |

`run.py` 本次不变，不放进本包（现役哈希仅记录在 `PROD-BACKUP-MANIFEST.txt`）。

## 关键说明

1. **`p1_pipeline.py` 是累积版**：注册块顺序 = 平台北森/Moka → 银行 → 阿里/腾讯音乐 →
   Workday/SuccessFactors → 飞书（`setdefault`）。`DEFAULT_COMPANIES` = 50 硬编码 + 874 平台/其它，
   共 **924 家**（无重复），比任务预估的 920 略多（闲鱼表实际写入 477 北森 + 301 生效 Moka +
   72 生效飞书）。配置里公司名已按「闲鱼表公司名优先、站点后缀清洗」统一（见
   `pipeline-watch/company-name-cleanup.csv`）。
2. **飞书入口修复**：`p1_feishu_public.py` 之前只有 `collect_platform`，而管线子进程契约要求
   `collect(company, scope, output_dir)`；本包补上 `collect = collect_platform` 别名，否则 72 家
   飞书租户在日链中会全部被记 blocked。新增单测
   `test_every_registry_module_exposes_the_collect_contract` 守住该契约。
3. **scope 默认**：平台公司（北森/Moka/飞书/Workday/SuccessFactors/银行）默认只跑
   `campus` + `intern`，`social` 默认跳过；硬编码 50 家与阿里/腾讯音乐保持三 scope。
   某平台公司要开 social，在该公司配置对象里加 `"scopes": ["campus","intern","social"]`
   （字符串或数组均可）。
4. **平台限流**：`p1_pipeline.run()` 按上游主机分组（zhiye.com / app.mokahr.com /
   jobs.feishu.cn / myworkdayjobs.com / successfactors / banks / alibaba / tencent_music），
   同组同时最多 2 个单元，同组单元启动间隔默认 ≥1s（`--platform-workers` / `--platform-interval`）；
   跨平台仍受 `--workers`（精灵 4）限制。管线还注入 `QIUZHAO_PLATFORM_REQUEST_INTERVAL`
   给支持的适配器（Workday/SF），显式传入的值不会被降低。
5. **分日轮转**：`--platform-rotation N` 只对配置驱动的北森/Moka/飞书按 slug 哈希分 N 组，
   每天跑一组；硬编码 50、银行、阿里/腾讯音乐、Workday/SF **每天照跑**。
   **默认 N=2**（推荐值；耗时估算见 `RECEIPT-collector-next-2.md`）。传 `--platform-rotation 1`
   关闭轮转跑全量（约 924 家中的平台全量）。该参数有默认值，因此
   `windows_collector.py` 无需新增参数，同步段保持 20260918b 原样。
6. **硬上限与重试语义**：`--max-run-seconds 18000`（精灵链已传）仍是硬上限；重试队列
   （`p1-retry-queue.json`）语义未变，失败单元次日优先、连续 3 天失败降到最后。
7. **离线验证**：`--workers 4` 混合 10 家 live 跑 38s，全部 ≤15 请求/租户（见收据第 5 节）；
   大华/商汤因硬编码适配器会逐条抓详情、无法满足 ≤15 请求硬约束，改用零网络桩验证链路/序号/注册。

## Headless 依赖（阿里系 + 飞书招聘；本次未在精灵执行）

阿里集团招聘平台对非浏览器指纹请求返回 403，必须走 headless Chromium；飞书求职门户也用同一
headless 路径。腾讯音乐、银行、Workday/SF、北森/Moka 是纯 HTTP，不需要浏览器。

**精灵（Windows）安装命令（由站长手动执行，本包未执行、未部署）：**

```bat
C:\mcp-suite-collector\.venv\Scripts\python.exe -m playwright install chromium
```

代码在找不到自带 Chromium 时会回退到系统 Chrome（`channel='chrome'`）。若精灵上没有 Chrome，
必须先执行上表命令安装 Chromium。

## 校验与回滚

```bash
# 在解压后的 20260918g 目录内
sha256sum -c SHA256SUMS.txt     # 或 macOS: shasum -c SHA256SUMS.txt，全部 OK
```

回滚：用 `PROD-BACKUP-MANIFEST.txt` 的 rollback 列恢复 `guopin.py` / `p1_pipeline.py` /
`windows_collector.py`（滚动源 `../20260918/` 同名文件），并删除 9 个新增文件。
