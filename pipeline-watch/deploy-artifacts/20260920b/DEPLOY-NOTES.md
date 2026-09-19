# 部署件 20260920b：告警机器人（cc 机器人）飞书消息通道

**本包未部署、未 SSH 精灵、未碰阿里云、未读写生产 Base、未 push、未合并 main。**
目标机：**精灵（Windows）`C:\mcp-suite-collector`** 与 **Mac 侧 launchd 用的 checkout**。
本包把「要站长看见的告警走飞书消息」这条项目约定真正落地：新增 `qiuzhao/notify.py`
（cc 机器人自建应用 → tenant_access_token → 发消息），并把三处告警接上同一个 notifier：
①飞书续表创建成功/失败 ②数据过期（freshness）③精灵飞书同步失败。
**凭据不在本包里，由站长自己放置（§3）；执行者不传输、不打印、不落盘任何凭据值。**

## 1. 本包内容（5 个文件，不含测试）

| 文件 | 目标路径（精灵） | 动作 |
|---|---|---|
| `notify.py` | `qiuzhao\notify.py` | **新增**：唯一的告警通道实现（令牌缓存/刷新、发送、重试一次、降级写文件、CLI） |
| `notify_targets.json` | `qiuzhao\data\notify_targets.json` | **新增**：告警目标（站长 open_id 已填；`chat_id` 留空，见 §4） |
| `lark_continuation.py` | `qiuzhao\collector\lark_continuation.py` | 覆盖：`record_alert` 默认改用共享 notifier（= 20260919m 版 + 告警钩子） |
| `lark_sync_daemon.py` | `qiuzhao\collector\lark_sync_daemon.py` | 覆盖：同步 attempt 失败时发 `lark_sync_failed` 告警（= 20260919m 版 + 3 行钩子） |
| `freshness_notify_mac.sh` | **Mac**：`<checkout>/deploy/freshness_notify_mac.sh` | 覆盖：新鲜度/同步告警先走飞书，发不出去才退回 AI 留言板（**不上精灵**） |

`SHA256SUMS.txt` 为本目录 5 个文件；生成后已 `shasum -a 256 -c` 全 OK，且与分支
`feat/cc-bot-notifier` 源码逐字节一致。

## 2. 叠加顺序（**先 a、再 m、最后 b**）

```
精灵现役 20260918k(含 20260919k p1 热修)
        └─ 20260919g / h / i （1056~1069 家，未部署，可选）
              └─ 20260919a  飞书整表重灌
                    └─ 20260919m  飞书续表自动创建（含 lark_continuation.py）
                          └─ 20260920b  ← 本包
```

- 本包的 `lark_continuation.py` / `lark_sync_daemon.py` **基线就是 20260919m 的版本**（diff 只有
  告警钩子，见下），所以必须叠在 m 之后；**m 尚未部署时直接铺本包会带来 m 的配套期望**
  （m 同时改了 `sync_lark_multivalue.py`，本包不含它）。
- **只想先开告警通道、不想动同步逻辑**：可只铺 `notify.py` + `notify_targets.json`
  （+ Mac 侧 `freshness_notify_mac.sh`）。此时续表告警与同步失败告警还不会被调用
  （那两处钩子分别在 m 版模块里），其它渠道（新鲜度）已经可用。
- 本包与 `20260918k` / `20260919k` 无冲突：不改 `p1_pipeline.py`、不改
  `windows_collector.py`、不改 `p1_platform_companies.json`。

**与 20260919m 的差异（逐字节核过，只有告警钩子）**

| 文件 | 相对 m 的改动 |
|---|---|
| `lark_continuation.py` | `record_alert()`：`notifier=None` 时改用 `qiuzhao.notify` 默认通道；调用结果记进 `notifier_result`；文件告警照旧写 |
| `lark_sync_daemon.py` | 新增 `alert_sync_failed()`；`run()` / `run_local()` 的 `status='failed'` 分支各加一行调用（异常被吞，不影响原 raise 行为） |

## 3. 凭据放置（站长自己做，执行者不碰凭据内容）

应用：站长 2026-09-20 提供的飞书自建应用（"cc 机器人"），凭据值只在
`~/.config/qiuzhao-cc-bot.env`（Mac，已由总控放好，权限 600）。精灵与 Mac 都需要各自的副本：

1. **精灵（Windows，跑续表/同步告警的那台）**：新建
   `C:\Users\LZH-LZH-\.config\qiuzhao-cc-bot.env`，两行：
   ```
   CC_BOT_APP_ID=<站长自己的值>
   CC_BOT_APP_SECRET=<站长自己的值>
   ```
   文件**不要放在** `C:\mcp-suite-collector\` 里（会被后续部署覆盖、也会进备份包）。
   若放到别处，给计划任务 `Qiuzhao-Collector-Daily` 的运行账户加一条环境变量
   `QIUZHAO_CC_BOT_ENV_FILE=<该文件绝对路径>` 即可。
2. **Mac**：`~/.config/qiuzhao-cc-bot.env` 已就位（600），无需再动。
3. **阿里云服务器**：本包**不需要**凭据（服务器只写 `freshness.json`，告警由 Mac 侧发起）。
4. 权限收紧：Windows 上把该文件的 ACL 只留给运行账户（其它用户/组移除）；
   代码只读该文件，不会复制、回显或写回。

**缺凭据时的行为**：`notify()` 不抛异常，把整条告警（时间/事件/关键数字/要站长做什么）
追加到 `notify-alerts.jsonl`（默认 `$QIUZHAO_DATA_DIR/notify-alerts.jsonl`，可用
`QIUZHAO_NOTIFY_ALERT_PATH` 指定），主流程完全不受影响。

## 4. 告警目标（`notify_targets.json`）

- 已填 `user_id`：站长在**本应用**下的 open_id（私聊直发，2026-09-20 真实发送验证通过）。
- `chat_id` 留空：`chat_id` 一旦填入**优先于** `user_id`。建议站长把机器人拉进一个运维群后，
  用 `python -m qiuzhao.notify --list-chats` 拿到 `oc_...`（需要应用有 `im:chat:readonly`），
  填进 `chat_id`，这样告警群里多人可见、也不依赖个人私聊。
- 临时覆盖（不写配置）：`QIUZHAO_NOTIFY_CHAT_ID` / `QIUZHAO_NOTIFY_USER_ID` /
  `QIUZHAO_NOTIFY_EMAIL`。
- 传输选择：`auto`（默认）= 本机 `lark-cli` 绑定的应用就是本机器人时走
  `lark-cli im +messages-send --as bot`，否则直接调开放平台接口；可用
  `QIUZHAO_NOTIFY_TRANSPORT=api|lark-cli` 强制。精灵上没有 lark-cli，会走接口。

## 5. 部署后自检（每条都可独立执行）

```powershell
# 精灵（正式 venv）
cd C:\mcp-suite-collector
.\.venv\Scripts\python.exe -X utf8 -m qiuzhao.notify --check     # 凭据/目标/告警文件就绪情况
.\.venv\Scripts\python.exe -X utf8 -m qiuzhao.notify --event test --text "部署自检"
```
```bash
# Mac（launchd 用的那个 checkout）
cd <checkout>
.venv/bin/python -m qiuzhao.notify --check
bash deploy/freshness_notify_mac.sh     # 正常时应无输出；有告警时飞书收到消息
```
- 期望：`--check` 显示 `credentials: present`、`target: user_id:ou_...`（或 `chat_id:oc_...`）。
- 降级自检（不联网、不发消息）：
  `QIUZHAO_CC_BOT_ENV_FILE=/nonexistent python -m qiuzhao.notify --event test` →
  退出码 3、告警写进 `notify-alerts.jsonl`、**不抛异常**。
- 继续沿用可回退：覆盖前备份 `qiuzhao\notify.py`（新文件则记 ABSENT）、
  `qiuzhao\collector\lark_continuation.py`、`qiuzhao\collector\lark_sync_daemon.py`。

## 6. Mac 侧现状（**部署前必读**）

- launchd `com.maxzhl.qiuzhao-freshness`（每小时 :47）当前 `ProgramArguments` 指向
  `/Users/maxzhl/Projects/mcp-suite-watch/deploy/freshness_notify_mac.sh`，
  **该目录已不存在**，所以这个任务现在每次都 `last exit code = 78 (EX_CONFIG)`——
  也就是说**新鲜度/同步告警这两路目前根本没在跑**（AI 留言板最后一条是 2026-09-18 11:47）。
- 要真正收到 ②③ 两类告警，需要（**属于部署动作，本任务未执行**）：
  1. 把本 checkout（含 `qiuzhao/notify.py`、`qiuzhao/data/notify_targets.json`、
     `deploy/freshness_notify_mac.sh`）放到一个固定路径，例如
     `~/Projects/mcp-suite`（main）或新建 `~/Projects/mcp-suite-watch`；
  2. 把 plist 的 `ProgramArguments[1]` 与 `WorkingDirectory` 指到该路径；
  3. `launchctl unload/load ~/Library/LaunchAgents/com.maxzhl.qiuzhao-freshness.plist`；
  4. 手动跑一次脚本确认飞书收到（或确认无告警时不发）。
- 本包不改 plist、不碰 `~/Library/LaunchAgents/`。

## 7. 安全与验证

- 凭据只从环境变量或仓库之外的 env 文件读；**代码/配置/日志/收据/测试夹具里没有凭据值**。
  单测用假凭据断言：日志、告警文件、返回值都不出现凭据（含 `Bearer`/`t-` 形状）。
- 工作区凭据扫描：`pipeline-watch/cc-bot-evidence/secret-leak-scan.py`
  → `{"ok": true, "files_scanned": 1804, "files_with_credentials": 0}`（扫描值不回显）。
- 真实发送：2026-09-20 向站长私聊发出 3 条（API 通道 1 条、lark-cli 通道 1 条、
  `record_alert` 钩子链路 1 条），全部 `sent=true`；证据见收据。
