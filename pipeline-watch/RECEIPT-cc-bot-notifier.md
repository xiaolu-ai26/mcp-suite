# 收据 · 告警机器人（cc 机器人）飞书消息通道（`feat/cc-bot-notifier`）

- 执行者：DeepSeek Harness（执行会话）。基线 `feat/lark-auto-continuation` f652e087；
  worktree `/Users/maxzhl/Projects/mcp-suite-ccbot`（本机，未用外接盘）。
- 结论：**通道已建成并真实发出 3 条消息，三处告警已接同一个 notifier；未部署、未 push、
  未合并 main、未碰阿里云与生产 Base、未在精灵或 Mac 上做任何覆盖。** 唯一需要站长做的两件事：
  ①把凭据文件放到精灵（§5 第 1–2 步）②修 Mac 侧 launchd 路径（§5 第 4–5 步，**它现在是坏的**）。

## 1. 交付物

| 文件 | 说明 |
|---|---|
| `qiuzhao/notify.py` | 新增 636 行：飞书告警通道（令牌缓存/刷新、lark-cli 或开放平台接口、重试一次、降级、CLI） |
| `qiuzhao/data/notify_targets.json` | 新增：告警目标（`user_id` 已填，`chat_id` 留空待站长） |
| `qiuzhao/collector/lark_continuation.py` | `record_alert` 的 notifier 钩子接默认通道（文件告警照旧写） |
| `qiuzhao/collector/lark_sync_daemon.py` | 同步 attempt 失败 → `lark_sync_failed` 告警 |
| `deploy/freshness_notify_mac.sh` | 新鲜度/同步告警先走飞书，发不出去才退回 AI 留言板 |
| `qiuzhao/data/notify_targets.json` 入库例外 | `.gitignore` 放行该文件（会话 id 不是凭据；缺了它会静默降级） |
| `tests/test_notify.py` | 新增 28 条单测 |
| `tests/conftest.py` | 新增 autouse fixture：**任何测试都不许真发飞书消息** |
| 部署件 | `pipeline-watch/deploy-artifacts/20260920b/`（5 文件 + SHA256SUMS + DEPLOY-NOTES + PROD-BACKUP-MANIFEST） |
| 证据 | `pipeline-watch/cc-bot-evidence/`（离线端到端演练脚本 + 输出、凭据泄漏扫描脚本） |

## 2. 通道实现（`qiuzhao/notify.py`）

- **凭据**：只从环境变量 `CC_BOT_APP_ID` / `CC_BOT_APP_SECRET`，或仓库之外的 env 文件
  （默认 `~/.config/qiuzhao-cc-bot.env`，可用 `QIUZHAO_CC_BOT_ENV_FILE` 覆盖）读；
  读到后只存在于内存。**凭据值不进代码、配置、日志、收据、提交、测试夹具、返回值**——
  所有对外字符串过 `redact()`（值替换 + `Bearer`/`t-`/`app_secret` 形状兜底）。
- **令牌**：`tenant_access_token` 进程内缓存（`threading.Lock` + 单调时钟），到期前 300 秒刷新；
  平台返回令牌失效码（99991661/99991663/99991664/99991668）时同一次投递内强制刷新重试一次。
- **传输**：`auto` 先看本机 `lark-cli`——**只有当 `lark-cli whoami` 的应用就是本机器人时**
  才走 `lark-cli im +messages-send --as bot`（本机确实就是同一个应用，见 §4），否则直接调
  开放平台 `im/v1/messages`。精灵没有 lark-cli → 走接口。可用 `QIUZHAO_NOTIFY_TRANSPORT` 强制。
- **目标**：`qiuzhao/data/notify_targets.json` 的 `chat_id`（群，优先）/`user_id`（open_id）
  /`email`；环境变量可临时覆盖。**值留空时降级写文件，不发。**
- **降级**：发送失败重试一次，仍失败 → 整条告警（时间/事件/关键数值/详情/要站长做什么）追加到
  `notify-alerts.jsonl`（默认 `$QIUZHAO_DATA_DIR/notify-alerts.jsonl`）。`notify()` **不抛异常**，
  最外层还有兜底 `except`；`QIUZHAO_NOTIFY_DISABLE=1` 可整体关闭通道。
- **消息形状**（真实发出的一条，节选）：
  ```
  【秋招告警】cc 机器人通知通道测试
  时间: 2026-09-20T01:17:12+08:00
  事件: test
  关键数字: capacity.free=7; capacity.limit=20000; capacity.used=19993; group=互联网科技岗; table=互联网科技岗·续表3
  要站长做什么: 无需操作;收到这条就说明告警通道可用
  ```

## 3. 三处接入（共用同一个 notifier）

| # | 告警 | 接入点 | 事件类型 | 触发时机 |
|---|---|---|---|---|
| ① | 飞书建续表成功/失败 | `lark_continuation.record_alert()`：`notifier=None` 时改用 `qiuzhao.notify.default_notifier()`，结果写进 `notifier_result`；run 目录的 `continuation-alerts.jsonl` 照旧写 | `continuation_created` / `continuation_create_failed` / `continuation_validation_failed` / `continuation_live_invalid` | 精灵同步时自动建表（20260919m 上线后生效） |
| ② | 数据过期 | `deploy/freshness_notify_mac.sh` 第一段：freshness.json 非 ok → 事件 JSONL → `python -m qiuzhao.notify --batch-jsonl ... --fallback MSG_TMP` | `freshness_stale` / `freshness_lagging` / `freshness_unreachable` / `freshness_multi_problem` | launchd 每小时（**当前路径坏了，见 §5**） |
| ③ | 精灵飞书同步失败 | ①`lark_sync_daemon.run()/run_local()` 的 `status='failed'` 分支直接告警（精灵侧，最直接）；②上面同一脚本第二段（Mac 侧兜底，覆盖"没失败但 30h 没成功"） | `lark_sync_failed` / `lark_sync_stalled` | 精灵每次同步失败 / Mac 每小时巡检 |

三处共用 `qiuzhao.notify.notify()`：同一份凭据解析、同一份目标配置、同一份重试与降级逻辑，
消息都含「时间 + 事件类型 + 关键数字 + 要站长做什么（一句话）」。

## 4. 真实验证（不是模拟）

1. **凭据可用**：`python -m qiuzhao.notify --check` → `credentials: present`（来源＝env 文件）。
2. **真实发送 3 条**（全部 `sent=true`，站长私聊）：
   - 01:14:05 传输 `api`（开放平台接口，换 tenant_access_token）→ `message_id` 非空；
   - 01:14:09 传输 `lark-cli`（`--as bot`）→ `message_id` 非空；
   - 01:17:12 **走 ① 钩子链路的真实发送**：`record_alert(...)` → `channel='notifier'` →
     `notifier_result={'sent': True, 'channel': 'feishu'}`。
   - 为什么能直接发到站长：站长在 **cc 应用下的 open_id** 已写入 `notify_targets.json`
     （`user_id`，open_id 是按应用隔离的，这个值就是本应用读出来的）。
3. **降级不失败**：无凭据时 `record_alert()` → `notifier_result={'sent': False, 'reason': 'no_credentials'}`、
   告警文件多 1 行、**不抛异常**；`lark_sync_daemon.alert_sync_failed()` 同样把 `lark_sync_failed`
   写进告警文件。
4. **Mac 脚本离线端到端演练**（`pipeline-watch/cc-bot-evidence/mac-script-dryrun.sh`，假 ssh +
   空目标配置，不联网不发消息）：两条告警（`freshness_multi_problem` + `lark_sync_failed`）
   完整穿过脚本 → notifier → 告警文件；消息含时间/事件/关键数字/详情/要站长做什么；
   退出码 3；HOME 指向临时目录所以 AI 留言板也未写入。输出留档
   `pipeline-watch/cc-bot-evidence/mac-script-dryrun.out`。

## 5. 站长要做的（3–5 步；执行者不碰飞书后台、不传凭据）

**A. 让精灵也能发告警（续表 ①、同步 ③ 在精灵侧生效的前提）**
1. 在精灵 `C:\Users\LZH-LZH-\` 下新建 `.config\qiuzhao-cc-bot.env`，写入两行
   `CC_BOT_APP_ID=<应用 App ID>`、`CC_BOT_APP_SECRET=<应用 App Secret>`（值从飞书开放平台
   「凭证与基础信息」页取；**不要**放进 `C:\mcp-suite-collector\`）。若换路径，给计划任务
   `Qiuzhao-Collector-Daily` 加环境变量 `QIUZHAO_CC_BOT_ENV_FILE=<绝对路径>`。
2. 部署时按 `deploy-artifacts/20260920b/` 的叠加顺序铺文件（a → m → b），
   然后精灵上跑一次自检：`.\.venv\Scripts\python.exe -X utf8 -m qiuzhao.notify --check`
   与 `--event test --text "部署自检"`（应收到飞书消息）。

**B. 修 Mac 侧新鲜度/同步告警（现在根本没跑）**
3. 现状：launchd `com.maxzhl.qiuzhao-freshness` 指向的
   `/Users/maxzhl/Projects/mcp-suite-watch/` **已不存在**，任务每次 `last exit code = 78`；
   AI 留言板最后一条告警停在 2026-09-18 11:47。需要把该 checkout 恢复（或把 plist 指到
   一个含 `qiuzhao/notify.py` 与 `deploy/freshness_notify_mac.sh` 的固定路径）。
4. `launchctl unload ~/Library/LaunchAgents/com.maxzhl.qiuzhao-freshness.plist && launchctl load ...`，
   手动 `bash deploy/freshness_notify_mac.sh` 确认通道（无异常时脚本静默）。

**C.（可选，建议）把告警发到群而不是私聊**
5. 把 cc 机器人拉进一个运维群，在飞书开放平台给应用加 `im:chat:readonly`（读群列表）与
   `im:message:send_as_bot`（发消息）权限并发布版本；然后
   `python -m qiuzhao.notify --list-chats` 拿 `oc_...` 填进 `notify_targets.json` 的 `chat_id`
   （填了 `chat_id` 就优先于个人 `user_id`）。

> 本次没有「发不出去」的阻塞：私聊通道已实测可用。上面 1–4 是把 ①②③ 三类告警在**生产机**
> 上真正跑起来所需的动作；`chat_id` 只是可选的可见性改进。

## 6. 测试

- 新增 `tests/test_notify.py` **28 条，全绿**。覆盖：凭据缺失/目标缺失/告警文件写不进去都不抛异常；
  发送失败重试一次后降级、第二次成功不降级；令牌失效码触发一次强制刷新、令牌跨次复用；
  **假凭据断言日志、告警文件、返回值都不含凭据值/token 形状**；消息格式含时间/事件/关键数字/动作；
  批量接口只把降级事件写回兜底文件；`record_alert` 用默认通道、坏 notifier 不影响主流程；
  `lark_sync_daemon` 失败路径调用告警且吞掉告警自身的异常。
- `tests/conftest.py` 增加 autouse fixture `no_live_alerts`（`QIUZHAO_NOTIFY_DISABLE=1`）：
  告警通道默认开启，若不隔离，跑到告警分支的测试会**真的给站长发消息**（本机有真凭据）。
- **全量 `pytest tests/`：`3 failed / 696 passed / 55 skipped`**；
  基线 `feat/lark-auto-continuation` f652e087 同机同解释器为 `3 failed / 668 passed / 55 skipped`，
  **失败清单逐条相同、无新增**（`test_core::test_role_cohort_and_campaign_title_bases`、
  `test_p1_pipeline::test_timeout_publishes_only_validated_partial_checkpoint`、
  `test_schema::test_enum_check_fails_when_data_drifts`），新增 28 条即本次单测。
  两次运行的完整日志留档：`pipeline-watch/cc-bot-evidence/pytest-baseline-f652e087.log`
  与 `pytest-final-cef1d86b.log`（可直接对比失败清单）。
- 凭据泄漏扫描：`pipeline-watch/cc-bot-evidence/secret-leak-scan.py`
  → `{"ok": true, "files_scanned": 1804, "files_with_credentials": 0, "credential_values_checked": 2}`
  （只报数量，不回显值）。
- 兼容性：`/usr/bin/python3`(3.9.6) 与仓库 venv(3.12) 均可 `py_compile` 与运行；
  模块只用标准库（`urllib`/`json`/`subprocess`/`threading`），精灵 venv 无需新依赖。

## 7. 硬约束遵守

未部署、未覆盖精灵正式目录、未 SSH 精灵、未碰阿里云、未读写飞书生产 Base、未 push、
未合并 main、未终止任何进程、未使用 `git stash`、未在外接盘建 worktree。
**未读取/打印/落盘任何凭据值**：env 文件只被代码在运行时读入内存；收据与部署件里只有变量名。
调飞书接口只有「换令牌 + 发消息 + 读机器人所在群列表（0 个群）」三类；未新增/未改任何 Base 内容。

## 8. 遗留 / 待站长决策

1. **Mac 侧告警任务当前是坏的**（§5.B）：不是本次改动引入，但会让人误以为"没告警=没问题"。
2. **`chat_id` 未定**：现在是私聊；群聊需要应用加 `im:chat:readonly` 权限并发布版本（§5.C）。
3. **服务器侧 ② 仍是 Mac 远程读**：`deploy/freshness_watch.sh` 在阿里云只写 `freshness.json`，
   本包没动它（不碰阿里云）；若希望服务器自己发告警，需要另派一次带凭据放置的服务端部署。
4. **事件文案可调**：`qiuzhao/notify.py` 的 `EVENTS` 表集中维护标题与「要站长做什么」，
   站长若要改口径改这一处即可。
5. **告警去重**：同步失败是"每次失败都发"（精灵一天一次同步，量可控）；若以后加频，
   可在 notifier 里按 `event+status` 做窗口去重。
