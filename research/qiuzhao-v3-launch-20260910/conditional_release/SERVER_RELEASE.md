# 条件5：服务器备份与发布报告

## 发布时间
2026-09-10 16:02 (UTC+8)

## 备份
- 备份目录：服务器 /opt/mcp-suite/deploy/backup-pre-v3-release-20260910/
- 备份内容：server.py(12K)、tools.py(4.3K)、jobs.json(23M, 9191条)、access.sqlite3(80K, 权限600)
- 备份SHA256SUMS已记录

## 发布内容
| 文件 | 操作 | 说明 |
|---|---|---|
| core/server.py | 替换 | 新增4个MCP筛选参数声明与转发 |
| qiuzhao/tools.py | 替换 | 修复industry(不用job_category冒充)、region(用cities)、recruitment_type(用nature_raw) |
| qiuzhao/collector/tencent.py | 新增 | 腾讯适配器(未加入每日采集run.py) |
| /var/lib/mcp-suite/jobs.json | 原子替换 | 9191→9199条合格子集 |
| access.sqlite3 | **未修改** | 仅条件1添加1个测试码，未覆盖 |
| bytedance.py | **未上传** | 校招过滤未解决，不启用 |

## 数据变化
- 发布前：9,191条（postal 2648 + guopin 6058 + chnenergy 422 + telecom 10 + boc 14 + ccb 39）
- 发布后：9,199条（postal 2648 + guopin 6058 + chnenergy 422 + ccb 39 + boc 14 + midea 10 + pg 8）
- 净变化：+8（新增美的10+宝洁8，移除电信10条无届别无截止疑似社招岗）
- 待核实844条（腾讯814+迈瑞20+电信10）未发布，留在needs_review.jsonl

## 服务验证
- systemctl is-active: active
- /health (本地): {"status":"ok","jobs":9199,"data_as_of":"2026-09-10T14:53:37+08:00"}
- /health (Nginx): 同上
- MCP tools/list: 3工具，jobs_search含company/recruitment_type/industry/region四参数

## 筛选验证（生产环境实查）
| 筛选 | 查询 | 结果 |
|---|---|---|
| company | 中国邮政 | 2648 |
| recruitment_type | 校园招聘 | 5016 |
| region | 北京 | 1132 |
| industry | 金融 | 0（无企业行业字段，不伪造） |
| 无筛选(兼容) | - | 9199 |
| cohort(旧功能) | 2027 | 8672 |
| 新增源可查 | 美的/宝洁 | 10/8 |

## 未变更确认
- 39元套餐/200次/日/2026-12-31有效期：未变更
- 正式50码：未消耗（条件1/5各添加1个测试码，非正式码）
- 定时任务(06:10)：未变更
- h5-laoban及其他站点：未修改
- Nginx配置：未修改
- tencent.py未加入collector run.py，不影响每日采集

## 回滚方案
1. 恢复backup-pre-v3-release-20260910/中的server.py和tools.py到/opt/mcp-suite/
2. 恢复backup中的jobs.json到/var/lib/mcp-suite/jobs.json（原子替换）
3. systemctl restart mcp-suite.service
4. 不回滚access.sqlite3（持续变化的生产数据）
5. 验证/health返回9191

## 结论
条件5：通过 ✅
