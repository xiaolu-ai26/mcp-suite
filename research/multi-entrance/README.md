# multi-entrance 复核证据(2026-09-19)

本目录只保留可复现的探针脚本与各租户的 `report.json` 摘要;原始 portal.html / list JSON 已删除(避免仓库膨胀,原始件在本机 /tmp 与执行日志里)。

## 脚本
- `probe_moka_list.py` —— 只读 Moka 列表探针:打开 portal 取 `aesIv`,分页 `POST /api/outer/ats-apply/website/jobs/v2`,按 `hireMode`/`commitment` 分类计数,20 次以下请求、每次 sleep 2s。
  用法:`python probe_moka_list.py <org/site> --site-url <portal-url>`
- 平台适配器批量探针(执行时放在 /tmp,未入库):给定 platform+key,写临时配置后调用真实适配器 `collect(...)`,`max_requests` 封顶。

## 摘要
- `moka-probe/nestlezgc-91899|91898|124026/report.json` —— 雀巢三入口列表计数
- `moka-probe/ey-166374|ey-102474/report.json` —— 安永校招+社招双租户
- `moka-probe/bshg-140686|tesa-142951/report.json` —— 博西家电 / 德莎

完整结论见 `pipeline-watch/RECEIPT-multi-entrance.md`。
