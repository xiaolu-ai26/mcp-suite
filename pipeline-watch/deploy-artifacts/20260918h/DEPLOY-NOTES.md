# 部署件 20260918h：站长最终口径版

**叠加顺序：从精灵现役 `20260918`（run.py / p1_pipeline.py / guopin.py / windows_collector.py，
无平台文件）一步覆盖即可。** 20260918b/c/d/e/f/g 均**未部署**，本包已把它们全部累积进来，
不需要再逐个叠加。本包未执行部署、未 SSH、未写库、未 push。

本包相对 20260918g 的变化（站长 2026-09-18 18:40 口径）：

1. `p1_pipeline.py`：`--platform-rotation` 默认由 **2 改为 1**（不轮转，924 家每天全跑）；
   平台公司默认 scope 由 `campus,intern` 改为 **`campus,intern,social`**（社招也跑；
   某公司仍可在 `p1_platform_companies.json` 的对象里用 `"scopes":[...]` 收窄）；
   `--workers` 上限由 6 放宽到 **64**；新增次日公平排序（未尝试单元次日优先）。
2. `deploy/windows_collector.py`：p1 步参数改为
   `--scope-timeout 600 --workers 8 --platform-workers 3 --max-run-seconds 18000`
   （以 `20260918b/windows_collector.py` 为底，只改这一行；同步段一字未动）。
   同平台单元启动间隔仍 ≥1s，`QIUZHAO_PLATFORM_REQUEST_INTERVAL` 逻辑未变。
3. 其余 10 个文件与 20260918g **逐字节相同**（哈希不变）。

## 覆盖文件

| 文件 | 目标路径 | 类型 |
|---|---|---|
| `p1_pipeline.py` | `qiuzhao/collector/p1_pipeline.py` | 覆盖（本次新版：不轮转 + 三 scope + 公平排序 + workers 8/64） |
| `windows_collector.py` | `deploy/windows_collector.py` | 覆盖（本次新版：只改 p1 那一行） |
| `guopin.py` | `qiuzhao/collector/guopin.py` | 覆盖（= 20260918g 版，含国聘自动专场） |
| `p1_platform_beisen.py` | `qiuzhao/collector/` | 新增（北森通用适配器） |
| `p1_platform_moka.py` | `qiuzhao/collector/` | 新增（Moka 通用适配器） |
| `p1_platform_workday.py` | `qiuzhao/collector/` | 新增（Workday CXS） |
| `p1_platform_successfactors.py` | `qiuzhao/collector/` | 新增（SAP SuccessFactors） |
| `p1_feishu_public.py` | `qiuzhao/collector/` | 新增/覆盖（飞书配置化 + `collect` 别名） |
| `p1_banks_01.py` | `qiuzhao/collector/` | 新增（银行批 1） |
| `alibaba_headless.py` | `qiuzhao/collector/` | 新增（阿里多实体 headless） |
| `tencent_music.py` | `qiuzhao/collector/` | 新增（腾讯音乐） |
| `p1_platform_companies.json` | `qiuzhao/collector/` | 覆盖（全平台段 + 清洗后公司名） |

`run.py` 本次不变，不放进本包（现役哈希仅记录在 `PROD-BACKUP-MANIFEST.txt`）。

## 关键说明

1. **默认全量**：不加 `--platform-rotation` 时 `companies_for_day()` 直接返回全部
   **924 家**（50 硬编码 + 874 平台/其它，无重复）；硬编码 50、银行 5、阿里 6、
   腾讯音乐 1、Workday 9、SF 3 本来就每天跑，现在平台 850 家也每天跑。
2. **三 scope**：平台公司（北森/Moka/飞书/Workday/SuccessFactors/银行）默认
   `campus,intern,social`。要收窄，在该公司配置对象里加 `"scopes":["campus","intern"]`
   （字符串或数组均可）。
3. **公平性兜底**：每个**已尝试**的 company/scope 记在 `data/p1-last-attempt.json`；
   若 `--max-run-seconds` 当天截断，次日 `plan_chains()` 把
   「有任一 scope 从未尝试」的公司排最前，其次重试队列里的失败单元，其余按上次尝试时间
   升序。连续 3 天失败仍降到最后。这保证硬件/网络抖动下每家至少隔日更新。
4. **并发**：全局 `--workers 8`，同平台 `--platform-workers 3`，同平台单元启动间隔 ≥1s，
   `QIUZHAO_PLATFORM_REQUEST_INTERVAL` 保持。Mac 零网络桩实测每单元子进程约 **162 MB**，
   8 路约 1.3 GB、12 路约 1.95 GB（详见收据 G 节）。
5. **计划任务参数无需改**：所有 p1 参数都写在 `deploy/windows_collector.py` 里，计划任务仍
   只调用该文件；覆盖后次日 06:10 自然生效，不需重启。

## Headless 依赖（阿里系 + 飞书招聘）

阿里集团招聘平台对非浏览器指纹请求返回 403，必须走 headless Chromium；飞书求职门户也用同一
headless 路径。腾讯音乐、银行、Workday/SF、北森/Moka 是纯 HTTP，不需要浏览器。

**部署时先检测（精灵 Windows，PowerShell）：**

```powershell
if (Test-Path "$env:LOCALAPPDATA\ms-playwright") { "PLAYWRIGHT-BROWSERS-PRESENT" }
else { "PLAYWRIGHT-BROWSERS-MISSING" }
```

总控 2026-09-18 实测：精灵 `%LOCALAPPDATA%\ms-playwright` **当前不存在**，因此需要安装。
**安装命令（由站长手动执行，本包未执行、未部署）：**

```bat
C:\mcp-suite-collector\.venv\Scripts\python.exe -m playwright install chromium
```

代码在找不到自带 Chromium 时会回退到系统 Chrome（`channel='chrome'`）。若精灵上没有 Chrome，
必须先执行上表命令安装 Chromium，否则阿里系与飞书公司会 blocked。

## 校验与回滚

```bash
# 在解压后的 20260918h 目录内
sha256sum -c SHA256SUMS.txt     # 或 macOS: shasum -c SHA256SUMS.txt，全部 OK
```

回滚：用 `PROD-BACKUP-MANIFEST.txt` 的 rollback 列恢复 `guopin.py` / `p1_pipeline.py` /
`windows_collector.py`（滚动源 `../20260918/` 同名文件），并删除 9 个新增文件。
