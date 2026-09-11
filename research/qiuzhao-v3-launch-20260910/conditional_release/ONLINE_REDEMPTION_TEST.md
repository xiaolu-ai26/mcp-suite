# 条件1：线上兑换与复制回归测试报告

- **执行时间**：2026-09-10 15:38–15:55（北京时间）
- **测试环境**：生产 `https://savegems.top/qiuzhao/`（nginx → 127.0.0.1:8768，mcp-suite.service）
- **执行人**：自动化回归（bu 平面真实浏览器 + 服务器端脚本验证）
- **结论**：**条件1 通过 ✅**

---

## 1. 静态文件备份留痕

备份目录：`/opt/mcp-suite/deploy/backup-static-20260910-v3/`

| 文件 | 线上当前 SHA256 | 备份后 SHA256 | 一致性 |
|---|---|---|---|
| index.html | `0bcdc1edcebc51b0a62fb8c30b9156ec79c0986300798489964d906b96362006` | `0bcdc1edcebc51b0a62fb8c30b9156ec79c0986300798489964d906b96362006` | ✅ 一致 |
| site.css | `210aaee5039d7487cdd7bb59aeb910b51460b4b4fa09906d610a1f9285e39dd4` | `210aaee5039d7487cdd7bb59aeb910b51460b4b4fa09906d610a1f9285e39dd4` | ✅ 一致 |
| app.js | `5f727050e86b0667a19b3df80064ee3196dd064f2ac9d95dca2ac73cd894dfd4` | `5f727050e86b0667a19b3df80064ee3196dd064f2ac9d95dca2ac73cd894dfd4` | ✅ 一致 |
| guide.html | `6fd0b42fa20b6d2f7d1f8e456fb2db5e7698f6875480cb0b4ba6e331bd4190e4` | `6fd0b42fa20b6d2f7d1f8e456fb2db5e7698f6875480cb0b4ba6e331bd4190e4` | ✅ 一致 |

> 注：线上4个文件 SHA256 前缀与 v3 新包一致（0bcdc1ed / 210aaee5 / 5f727050 / 6fd0b42f），确认已是 v3 版本。备份仅作留痕，未覆盖原文件。

---

## 2. 测试兑换码

- 生成方式：`/opt/mcp-suite/.venv/bin/python` 调用 `core/store.py` 的 `Store.generate_codes(1, "qiuzhao-2026")`
- 套餐：qiuzhao-2026（秋招季）
- **兑换码 SHA256（明文不入报告）**：`e516b5e60656508079664693a927c3de75e833f2127137ca41365be926416037`
- 生成前 redemption_codes 总数：108；生成后：109（仅 +1，未修改任何已有行）
- 该码为测试码，不属于正式库存；已在本次测试中兑换，无法撤销（见第5节清理说明）

---

## 3. 浏览器真实回归测试结果

### 3.1 打开线上兑换页
- **结果**：✅ 通过
- 证据：`https://savegems.top/qiuzhao/` 正常加载，显示步骤1"兑换"表单、¥39/秋招季、有效期至2026.12.31、每天200次提示。页面注明"只在本页内存中处理凭证，不写入本网站的浏览器持久存储"。

### 3.2 输入测试码并提交兑换
- **结果**：✅ 通过
- 证据：提交后页面进入步骤2"接入 AI"，显示"✓ 兑换成功"。

### 3.3 兑换成功后显示真实 key（qz_ 前缀）
- **结果**：✅ 通过
- 证据：展开"查看将复制的指令"后，`#key-display` input 值以 `qz_` 开头，长度46字符（`qz_aQG…s5j8`，已脱敏）。

### 3.4 额度 200/200 与有效期
- **结果**：✅ 通过
- 证据：页面显示"今日剩余 / 每日额度 **200 / 200**"，"有效至（北京时间）**2026-12-31**"。
- 服务器端 entitlement 确认：`product=qiuzhao, expires_at=2027-01-01T00:00:00+08:00, daily_limit=200`。

### 3.5 点击复制，剪贴板含真实 key 和 /mcp 接入地址
- **结果**：✅ 通过
- 证据：勾选隐私同意框后 `#copy-prompt` 按钮启用，点击后页面提示"已复制"。通过拦截 `navigator.clipboard.writeText` 捕获剪贴板内容（974字符），确认包含：
  - `qz_` 前缀真实 key（在 Authorization Bearer 头中）
  - MCP 接入地址：`https://savegems.top/qiuzhao/mcp`
  - 完整 mcpServers JSON 配置（type=http, url, headers.Authorization=Bearer qz_***）
  - 安全约束文本（key 不放入 URL/日志/群聊等）

### 3.6 key 不在 URL / localStorage / sessionStorage
- **结果**：✅ 通过
- 证据：
  - URL：`https://savegems.top/qiuzhao/`，`href.includes('qz_')` = **False**
  - localStorage：仅有 Doubao 客户端自身配置（deviceId、AB实验等），`Object.values(localStorage).some(v => v.includes('qz_'))` = **False**
  - sessionStorage：仅 `__tea_session_id`，含 qz_ 检测 = **False**

### 3.7 刷新页面，key 不自动找回
- **结果**：✅ 通过
- 证据：刷新（新标签导航）后页面回到步骤1兑换表单，兑换码输入框为空（placeholder "QZ-…"），不显示任何已兑换凭证。截图：`screenshots/04-refresh-returns-to-form.png`。

### 3.8 再次提交同一码，被拒绝
- **结果**：✅ 通过
- 证据：输入同一测试码再次提交，页面显示红色错误提示："**兑换码无效或已使用。请检查输入；已兑换请使用保存的 key。**"，停留在兑换表单，不进入步骤2。截图：`screenshots/05-replay-rejected.png`。

### 3.9 /usage 接口不扣额
- **结果**：✅ 通过
- 证据：用测试 key 连续调用 `GET https://savegems.top/qiuzhao/usage` 两次：
  - 第1次：`{"product":"qiuzhao","expires_at":"2027-01-01T00:00:00+08:00","daily_limit":200,"remaining_today":200}`
  - 第2次：`{"product":"qiuzhao","expires_at":"2027-01-01T00:00:00+08:00","daily_limit":200,"remaining_today":200}`
  - remaining_today 两次均为 200，**未扣减**。（/usage 调用 `store.authorize()` 只读不写；只有真实工具调用经 `consume()` 才扣额。）

---

## 4. guide 页验证

- **结果**：✅ 通过
- 证据：`GET https://savegems.top/qiuzhao/guide` 返回 HTTP 200，9265 字节（与服务器 guide.html 大小一致）。
- 页面标题：`接入指南 · 秋招岗位库`
- 内容确认：服务器名称 qiuzhao、地址 `https://savegems.top/qiuzhao/mcp`、传输 Streamable HTTP、Header `Authorization: Bearer YOUR_API_KEY`（占位符，不含真实 key）。
- 截图：`screenshots/06-guide-page.png`。

---

## 5. 清理与影响说明

- 测试码已兑换，**无法撤销**（redeem 是幂等不可逆操作，redeemed_at 已写入）。
- 该码为本次回归专用测试码，**不属于正式50码库存**；其对应 key 已激活（disabled=0），但仅用于验证，不会对外分发。
- **正式码未受影响**：
  - bench-monthly 套餐：54 码（3已兑换，51未兑换）—— 未变动
  - qiuzhao-2026 套餐：55 码（其中 5 已兑换，含本次测试码1个；50未兑换）
  - `access.sqlite3` 仅通过 `Store` API 追加了 1 行 redemption_codes + 1 行 api_keys + 1 行 entitlements，未覆盖、未删除任何已有数据。
- 未修改 server.py / store.py / tools.py；未重启 mcp-suite.service。
- 临时脚本已从服务器 /tmp 清理。

---

## 6. 截图清单

| 文件 | 对应测试项 |
|---|---|
| `screenshots/04-refresh-returns-to-form.png` | 3.7 刷新后回到兑换表单，key 不自动找回 |
| `screenshots/05-replay-rejected.png` | 3.8 重复提交同一码，红色错误提示"兑换码无效或已使用" |
| `screenshots/06-guide-page.png` | 4 guide 页正常访问，显示 /mcp 配置 |

> 兑换成功页（3.2/3.3/3.4）与复制成功态（3.5）在测试流程中已实时截取于临时路径，但因浏览器会话后续标签切换导致临时文件被覆盖；该两步的证据以上文 DOM 文本与剪贴板捕获为准（页面文本含"兑换成功""200/200""2026-12-31"，剪贴板拦截含完整 mcpServers JSON）。

---

## 7. 硬性约束遵守确认

| 约束 | 遵守情况 |
|---|---|
| 不覆盖 access.sqlite3 | ✅ 仅 Store API 追加写入，未覆盖 |
| 不动正式50码 | ✅ 未删除/修改任何已有 redemption_codes 行 |
| 不改套餐额度 | ✅ daily_limit=200 未变 |
| 不修改 server.py/store.py/tools.py | ✅ 全程只读未改 |
| 不重启服务 | ✅ 未执行 systemctl restart |
| 测试码明文不写入报告 | ✅ 仅记录 SHA256 摘要 |
| 不绕过任何限制 | ✅ 走真实浏览器+真实 HTTP 请求 |

---

## 最终结论

**条件1（线上兑换与复制回归测试）：通过 ✅**

全部 9 项浏览器/接口回归测试 + guide 页验证均通过，正式库存未受影响，可进入下一条件。
