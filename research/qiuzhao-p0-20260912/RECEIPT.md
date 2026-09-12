# 秋招采集 P0 修复收据

完成时间：2026-09-12 20:52 Asia/Shanghai。用户授权派发 subagent 修复 P0。

## 修改与边界

- `qiuzhao/collector/auto_collect.py`：腾讯子进程非零、超时、缺失本轮输出、source_state失败/不完整、结果计数不一致均返回失败；main返回1，跳过腾讯合并、成功日志和重启。经过核验的空列表仍是成功。每轮独立临时目录避免复用旧 staging。
- `tests/test_auto_collect_p0.py`：8项行为验证。
- 生产 `/opt/mcp-suite/qiuzhao/collector/tencent.py` 权限 root:root 600→644，内容未改。
- 未修改 collector-daily.sh；它原本已能将 auto_collect 非零码写入失败状态。
- 未改采集来源、合并策略、届别逻辑、数据、凭证、数据库、nginx或套餐。未重启服务。

## 基线与部署

本地基线 0e9250b89243ae05d8f0d37ee22bf2dbf61213d5，原 checkout clean，隔离 worktree `/Users/maxzhl/Projects/mcp-suite-p0-20260912`。
遵循 deploy skill 的预检、备份、核验；通用注册表无此项目，按既有固定路径最小替换，避免全目录 rsync。磁盘60%。确认采集锁空闲，并在同一 flock 锁内校验线上原哈希、备份、替换和修权限。

真实前置备份：
- `/opt/mcp-suite/qiuzhao/collector/auto_collect.py.bak.p0-20260912`
  SHA256 `b28a9b0ccd67bf7bd8e41ea0382583f2aa6954d54cb1d05760ff440f353ab1b2`
- `/opt/mcp-suite/qiuzhao/collector/tencent.py.bak.p0-20260912`
  SHA256 `278c971c46e1cff0205ded332970b8f351d27ebfe95bbd8660345269d10c4a0e`

部署后 auto_collect SHA256 `ac7d45140fca738d380191a33d912ee07b5e28ed6d37956e1c44de5316c6032b`，与本地一致；腾讯内容哈希与备份一致。auto_collect权限 root:root755、腾讯root:root644。

## 验证

- 8个 unittest 通过：成功零条、成功非空、非零失败、超时、exit0但部分失败、缺失本轮输出、数量不一致、失败不合并/发布/重启。
- 4种 cron shell 隔离 fixture 通过：auto_collect=1、全0、基础采集=1、auto_collect=124；状态及进程码一致。macOS无flock，fixture仅替代锁命令；生产锁另行真实核验。
- git diff --check通过。
- code-reviewer独立审查无阻断；采纳失败日志准确性与非空成功测试建议。
- 生产以 mcp-suite账号导入腾讯及auto_collect模块成功。
- 20:51:45—20:52:07，以mcp-suite账号运行修复后的run_tencent_collector，输出仅写自动清理临时目录：真实腾讯采集成功895条，必须满足source_state success、complete、expected_total与collected_jobs一致。没有调用main或merge。
- 生产数据前后SHA256相同：jobs.json `950ca5efedbf69e7cd7aec36a2d1136f78ef7710ff7aa9dd9351cf1b9214254f`；cron-status.json `e6c71db670ad07742effdc1f3b2d75812c4031eada04433a639f73766c9d6da8`。
- 公网health：status=ok，jobs=25631，data_as_of=2026-09-12T06:55:17+08:00；mcp-suite.service active。

## 剩余验收

P0代码和生产权限修复完成，真实腾讯隔离采集通过。895条没有合并上线，不能当成线上新增数量。现有cron每天06:10运行；下一次定时全链路及最终cron-status仍待自然执行验收。今日历史status未重写。没有新建监控自动化。
