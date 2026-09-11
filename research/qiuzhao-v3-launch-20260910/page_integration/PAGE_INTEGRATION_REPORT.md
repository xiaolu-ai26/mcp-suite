# 秋招 MCP v3 · A线#1 页面整合与本地测试报告

- 执行时间：2026-09-10（Asia/Shanghai）
- 任务：用 `/tmp/v3pack/qiuzhao-delivery-v3/core/static/` 的 4 个正式前端文件替换 `core/static/`，本地隔离环境回归与浏览器实测。
- 结论：**通过，可进入下一步（线上部署前需另走批准流程）。** 未部署到线上。

---

## 0. 硬性约束遵守情况

| 约束 | 结果 |
|---|---|
| 不改生产 `private/access.sqlite3` | ✅ 仅以只读 backup API 复制到 `/tmp`，生产文件 mtime 仍为 `Sep 10 00:35`，最终核对：50 码 / 0 兑换 / 0 key |
| 不碰正式 50 码 | ✅ 生产库 `total_codes=50, redeemed=0`；测试码只在 `/tmp` 副本生成（副本 53 码 = 50 正式 + 3 测试） |
| 不改 39 元套餐 / 200 额度 / 有效期 | ✅ `store.py` 未改；实测 `/usage` 返回 `price/expires_at=2027-01-01、daily_limit=200` 与 `PLANS` 一致 |
| 不改 `server.py` / `store.py` / `tools.py` | ✅ 本次只替换 4 个静态文件 |
| 不部署到线上 | ✅ 仅 `127.0.0.1:8768` loopback 本地服务，已停止 |
| 测试码/key 不写入报告正文 | ✅ 仅记录 sha256 前 16 位摘要（见下） |

---

## 1. 旧静态文件备份

备份目录：`backup_static_20260910/`，清单：`backup_manifest.json`。

| 文件 | 旧 SHA256（备份值=预期值，一致） |
|---|---|
| index.html | `abf584340853d2c013e4491ab8b3e3b36ae3929174acb38dd60ccfd9b33454aa` |
| site.css   | `1c2f0f3922938e6c558790436c04ee912edd1deaa34f474c9bf52823a5b521aa` |
| app.js     | `98b18f51b44c322de1a9b19f19bdbc10663b4db0c231cbc4a2c12cfdbddae493` |
| guide.html | `e162f3e4057b60c01ecd8cf7429966bd0e47d70c1e1fb0ba42013afce6e29154` |

4 个文件均 `sha256_match: true`。回滚方式：把该目录 4 个文件拷回 `core/static/` 即可。

## 2. 新静态文件替换

仅替换 4 个正式文件；**未部署** `preview.html`、`qa/`、`tests/`、`reference_snapshot/`。
包内文件 SHA 先与 `MANIFEST.json` 逐一核对一致，再拷贝。

| 文件 | 新 SHA256（安装后实测） | 字节 |
|---|---|---|
| index.html | `0bcdc1edcebc51b0a62fb8c30b9156ec79c0986300798489964d906b96362006` | 12736 |
| site.css   | `210aaee5039d7487cdd7bb59aeb910b51460b4b4fa09906d610a1f9285e39dd4` | 14672 |
| app.js     | `5f727050e86b0667a19b3df80064ee3196dd064f2ac9d95dca2ac73cd894dfd4` | 20885 |
| guide.html | `6fd0b42fa20b6d2f7d1f8e456fb2db5e7698f6875480cb0b4ba6e331bd4190e4` | 9265 |

`core/static/` 当前仅这 4 个文件。

---

## 3. 自动化测试结果

原始输出存于 `test_outputs/`。

| 测试 | 命令 | 结果 |
|---|---|---|
| 包内模板测试 | `cd /tmp/v3pack/qiuzhao-delivery-v3 && node tests/test_templates.cjs` | **9/9 PASS**（`template_tests_passed:9`），EXIT=0 |
| 包内契约快照 | `PYTHONPATH=tests/reference_snapshot .venv/bin/python -m pytest tests/reference_snapshot/tests/test_core.py -q` | **6 passed**，EXIT=0 |
| 项目原有测试 | `.venv/bin/python -m pytest tests/test_core.py -q` | **6 passed**，EXIT=0 |

说明：包内 reference_snapshot 测试用项目 `.venv` 解释器（系统 python3 无 pytest），通过 `PYTHONPATH` 指向快照副本，不覆盖现场后端。

---

## 4. 本地真实应用 + 浏览器实测

### 4.1 环境搭建
- 隔离库：用 SQLite 只读 backup API 把生产 `private/access.sqlite3` 复制到 `/tmp/qiuzhao-test-8768/access.sqlite3`（不写源库）。
- 测试码：仅在该 `/tmp` 副本上 `Store.generate_codes()` 生成 3 个测试码（`QZ-` 前缀，长度 35）。**明文不落报告**，仅记 sha256 前 16 位：
  - 测试码#1：`fb755fd9d3a81112`
  - 测试码#2：`dd31db5ff0be7021`
  - 测试码#3：`5eb4cbbbc48b590c`
- 服务：`uvicorn core.server:app`，`--host 127.0.0.1 --port 8768`，环境变量 `MCP_DB_PATH=/tmp/qiuzhao-test-8768/access.sqlite3`、`MCP_PUBLIC_BASE_URL=http://127.0.0.1:8768`、`MCP_JOBS_PATH=.../qiuzhao/data/jobs.json`。进程 env 已核对确为 `/tmp` 库。
- 启动前发现 8768 被上一轮遗留的本地测试进程（`MCP_DB_PATH=private/test-access.sqlite3`）占用，已停止后用本任务隔离库重启；该遗留进程非公网生产。
- 响应头确认：`content-security-policy: default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`，`cache-control: no-store`，`referrer-policy: no-referrer`。
- 实测后服务已停止，8768 已释放。

### 4.2 用例 a–g 结果

| 项 | 期望 | 实测 | 证据 |
|---|---|---|---|
| a 兑换一次成功 | 输入测试码→得 API key | ✅ 成功标题"兑换成功"，`key_display` 长度 46、前缀 `qz_`（真实 key 非占位符），额度 `200/200`，有效至 `2026-12-31`；页面 URL 仍为 `/` | 03_success_clients.png；K1 sha256[:16]=`8ddcb7b9c0fafb28` |
| b 重复码拒绝 | 同码再提应被拒 | ✅ 前端 UI 提示"兑换码无效或已使用。请检查输入；已兑换请使用保存的 key。"，成功面板保持隐藏；同源 POST `/redeem` 同码返回 **HTTP 400 `{"error":"兑换码无效或已使用，每个兑换码只能领取一次。"}`** | 浏览器实测 + 网络 |
| c 不同浏览器/上下文不同 key | 新标签页得到不同 key | ✅ 全新标签页初始无 key（`success-panel` 隐藏、`key_display` 长度 0）；兑换码#2 得 K2，sha256[:16]=`1e17f346f60bef38` ≠ K1 `8ddcb7b9c0fafb28` | 新标签实测 |
| d 复制含真实 key（非占位符） | 复制文本含真实 `qz_` key | ✅ 可见预览（mask）不含真实 key；挂钩 `navigator.clipboard.writeText` 捕获实际复制文本，**含真实 `qz_` key、含 `/mcp` 接入地址**，与掩码预览不同；UI 显示"已复制" | 03_success_clients.png；K3 sha256[:16]=`195e56b4090ee679` |
| e key 不出现于 URL/localStorage/sessionStorage | 三查皆否 | ✅ `location.href` 不含 key；`localStorage`/`sessionStorage` 中序列化后均搜不到 key（现存 6+1 项为 Doubao 浏览器自身遥测/客户端键，非本站 app.js 写入；`app.js` 全文无 `localStorage/sessionStorage/cookie/history` 调用） | devtools 等价 JS 检查 |
| f `/usage` 校验不扣额 | 多次调用额度不变 | ✅ 连续 3 次 `GET /usage`（Bearer key）均返回 `remaining_today=200`；库侧 `usage_log=0`、`daily_usage=0`（未产生任何工具消耗） | http_get + SQLite 只读查询 |
| g 刷新后 key 不自动找回 | 刷新回兑换表单 | ✅ `location.reload()` 后回到兑换表单：`redeem-panel` 显示、`success-panel` 隐藏、`key_display` 长度 0、输入框清空 | 浏览器实测 |

补充：`/health` 返回 `{"status":"ok","jobs":9191,...}`；`/config` 返回本地 `mcp_url`。`/guide` 页面正常渲染（04_guide_page.png）。

### 4.3 浏览器证据清单（`browser_evidence/`）
- `01_initial_page.png`：兑换首页（v3 版式、¥39、9,191 条记录、内存持凭证提示）
- `03_success_clients.png`：兑换成功 + 客户端选择 + "已复制"提示
- `04_guide_page.png`：接入指南页

---

## 5. 生产 / 隔离库最终对账

| 库 | total_codes | redeemed | api_keys | usage_log | daily_usage |
|---|---|---|---|---|---|
| 生产 `private/access.sqlite3`（只读） | 50 | 0 | 0 | 0 | 0 |
| `/tmp` 测试副本 | 53（50 正式+3 测试） | 3 | 3 | 0 | 0 |

生产文件 mtime 未变（`Sep 10 00:35`），确认未被本次测试写入。

---

## 6. 阻塞 / 如实记录

1. **CSP / 浏览器限制**：`script-src 'self'`、`style-src 'self'`，前端未加载外部脚本/字体/CDN，无 CSP 报错；未遇到需绕过的 CSP 限制。`navigator.clipboard.writeText` 在该本地上下文中成功，无需走手动复制回退弹窗。
2. **截图/JS 偶发超时**：内置浏览器 `bu.screenshot()` 与个别 `js()` 调用出现 `timed out`（重发后成功）；其中 `02_redeem_success.png` 一次未存盘，但 `03_success_clients.png` 已完整呈现兑换成功态，不影响结论。
3. **标签页焦点**：内置浏览器 `resync` 总附着到当前可见标签；为规避多标签焦点切换，"不同上下文不同 key"通过新开标签页完成，未使用系统隐身窗口（内置浏览器无独立隐身入口，新开标签页即全新 JS 上下文，等价验证目的）。
4. **未实测**：真实 AI 客户端（WorkBuddy/Codex 等）连接器真实接通、跨客户端共用额度、200 次上限与 00:00 重置的端到端——这些需接真实客户端，超出本页整合范围，包 MANIFEST 亦标注为"未与现场网页逐行合并、非线上发布收据"。
5. **guide.html 文案**：指南页文档示例中硬编码展示 `https://savegems.top/qiuzhao/mcp`（生产地址），本地测试时属正常文案；上线后应与实际 `MCP_PUBLIC_BASE_URL` 一致。

---

## 7. 结论
4 文件已按包 MANIFEST 替换，备份可回滚；包内模板/契约测试 9+6 通过，项目原有 6 测试通过；本地隔离环境浏览器实测 a–g 全部通过；生产库与正式 50 码未被触碰。**A线#1 页面整合与本地测试完成，无阻塞项。**
