# 审查包文件来源清单 — source_manifest.md

> 任务编号：QIUZHAO-FIELD-AUDIT-20260910
> 打包时间：2026-09-10 北京时间
> 项目路径：/Users/maxzhl/Projects/mcp-suite/

---

## A. 实际字段与工具定义（A_field_definitions/）

| 文件 | 来源路径 | 版本/修改时间 | 是否去敏 | 去敏说明 |
|---|---|---|---|---|
| `tools.py` | `qiuzhao/tools.py` | 2026-09-10 10:21 | 否（无需去敏） | 无硬编码秘密，纯数据查询逻辑 |
| `server.py` | `core/server.py` | 2026-09-10 00:31 | 是（已确认无秘密） | 无硬编码API key/token/password；引用环境变量 `MCP_PUBLIC_BASE_URL`、`MCP_DB_PATH`、`MCP_JOBS_PATH`；引用 `private/access.sqlite3` 路径但不包含数据库内容；`PUBLIC_BASE` 默认值为公开URL `https://savegems.top/qiuzhao` |
| `store.py` | `core/store.py` | 2026-09-10 00:30 | 是（已确认无秘密） | 无硬编码秘密；API key和兑换码均运行时通过 `secrets` 模块生成；存储SHA256哈希而非明文；PLANS配置含套餐价格(39元)和过期时间，非秘密 |
| `collector/run.py` | `qiuzhao/collector/run.py` | 2026-09-10 01:09 | 否（无需去敏） | 含公开采集URL（中国邮政、国家能源、电信、中行官网），无秘密；UA字符串为公开标识 |
| `collector/ccb.py` | `qiuzhao/collector/ccb.py` | 2026-09-10 00:57 | 否（无需去敏） | 含建行公开招聘API URL和公告ID，无登录凭证；TLS兼容配置为公开技术参数 |
| `collector/guopin.py` | `qiuzhao/collector/guopin.py` | 2026-09-10 01:07 | 否（无需去敏） | 含国聘公开API URL和6个企业campaign domain，无秘密 |
| `tests/test_core.py` | `tests/test_core.py` | 2026-09-10 10:21 | 否（无需去敏） | 测试使用临时目录和生成的测试码，无硬编码秘密 |
| `tests/e2e_local.py` | `tests/e2e_local.py` | 2026-09-10 00:36 | 否（无需去敏） | 使用隔离测试数据库 `private/test-access.sqlite3`，运行时生成测试码；配置文件写入 `private/` 目录（权限600），不含实际密钥值 |
| `requirements.txt` | `requirements.txt` | 2026-09-10 00:35 | 否（无需去敏） | 纯依赖列表：fastmcp==2.14.7, uvicorn==0.52.4, httpx==0.28.1, beautifulsoup4 |
| `tools_list_static.json` | 静态分析生成 | 2026-09-10 | N/A | 基于源码静态分析的MCP工具列表推断，标记 `static_only`，非实际运行时捕获 |

---

## B. 真实数据与工具返回样例（B_data_samples/）

| 文件 | 来源 | 生成方式 | 记录数 | 是否去敏 |
|---|---|---|---|---|
| `job_samples.json` | `qiuzhao/data/jobs.json` | Python脚本抽取，保留原始键名/嵌套/空值 | 20条 | 是（原始数据中无个人信息，evidence_path为相对路径不含秘密） |
| `field_profile.json` | `qiuzhao/data/jobs.json` | Python脚本全量统计（9191条） | 全量统计 | 是（仅含统计数字，不含原始记录内容） |
| `tool_responses/` | - | - | - | 未放入真实工具响应（见下方说明） |

### 工具返回样例说明

三个MCP工具的真实返回样例**未放入本审查包**，原因：
1. `jobs_search`/`jobs_detail`/`jobs_deadlines` 的返回结构已在 `tools_list_static.json` 中详细描述
2. 线上e2e收据 `deploy/final-online-e2e-receipt.json`（只读参考）包含工具调用的统计数据（total、source_urls示例、data_as_of），但不含完整jobs数组
3. `job_samples.json` 中的20条记录即为 `jobs_search`/`jobs_detail` 返回中 `jobs` 数组元素的真实结构（经 `public()` 过滤后）
4. 如需完整工具响应，可在本地启动服务后调用获取（需API key）

---

## C. 工作进度与版本边界（C_progress/）

| 文件 | 来源 | 说明 |
|---|---|---|
| `pytest_test_core_output.txt` | 本次运行 `pytest tests/test_core.py -v` 的真实输出 | 6 passed in 0.24s |

---

## 根目录文件

| 文件 | 说明 |
|---|---|
| `FIELD_AUDIT.md` | 15列字段审计报告（工作1产出） |
| `HANDOFF.md` | 工作进度与版本边界 |
| `source_manifest.md` | 本文件 |
| `field_profile_script.py` | 字段覆盖率统计脚本（可复现） |
| `extract_samples.py` | 样本抽取脚本（可复现） |
| `qiuzhao-review-pack-20260910.zip` | 安全打包后的zip文件 |

---

## 去敏扫描记录

### 扫描模式
对所有打包文件执行了以下模式的grep扫描：
- `api_key`（变量名出现为正常代码，无硬编码值）
- `secret`（`secrets` 模块导入为正常，无硬编码秘密值）
- `token`（变量名出现为正常代码，无硬编码token值）
- `password`（未出现）
- `兑换码`（错误提示文案中出现，无实际兑换码值）
- `access.sqlite3`（仅路径引用，无数据库内容）

### 扫描结论
- 所有文件均**无硬编码秘密值**
- `server.py` 和 `store.py` 中的 `api_key`、`token`、`兑换码` 均为变量名/错误提示文案/运行时生成逻辑，不含实际值
- `private/` 目录下的任何文件**均未被打包**
- `.env` 文件**未被读取或打包**
- 证据文件路径（`evidence_path`、`announcement_evidence_path`、`directory_evidence_path`）为相对路径，不含秘密，但在工具返回中被 `public()` 过滤

### 无法可靠去敏的文件
- 无。所有纳入审查包的文件均可安全打包。

---

## 排除清单（未打包的文件）

| 排除项 | 原因 |
|---|---|
| `private/` 目录 | 权限 drwx------，含密钥、兑换码、access.sqlite3，硬性禁止读取 |
| `.env` | 可能含环境变量秘密 |
| `qiuzhao/data/evidence/` | 采集证据文件，体积大且可能含原始页面内容 |
| `qiuzhao/data/jobs.json` 全量 | 23MB，仅抽取20条样本和统计结果 |
| `deploy/final-online/` | 权限 drwx------ |
| `deploy/private/` | 权限 drwx------ |
| `__pycache__/`、`.pyc`、`.DS_Store` | 构建产物和系统文件 |
| `.git/` | 版本控制目录 |
| `.venv/` | 虚拟环境 |
| `research/qiuzhao-expansion-20260910/` | 扩源工作区，仅在HANDOFF.md中引用其状态，不复制文件 |
