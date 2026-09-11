# 发布检查清单 — QIUZHAO-EXPANSION-20260910

**任务编号**: QIUZHAO-EXPANSION-20260910
**当前状态**: **生产未执行** — 本清单为Max明确授权后才执行的步骤
**生成日期**: 2026-09-10

---

## ⚠️ 前置条件

**生产部署必须获得Max明确批准。** 当前所有工作均为本地交付，未部署、未替换服务器持久数据、未变更定时任务。

---

## 一、发布前必须完成（当前未完成）

### 1.1 B阶段适配器完成
- [ ] 腾讯适配器实现并可重复执行
- [ ] 字节跳动适配器实现并可重复执行
- [ ] 每家至少3条真实岗位核对（首/中/末页样例）
- [ ] 所有需发布范围做完整分页枚举
- [ ] staging jobs输出到 staging/ 目录
- [ ] 运行manifest记录到 manifests/（起止时间、页数、预期与实际唯一ID数、异常）

### 1.2 数据质量审查
- [ ] staging岗位与现有9,191条快照去重（跨源强证据去重，不按标题强并）
- [ ] 届别验证：明确2026的岗位不因2027活动标题误入
- [ ] 地域验证：海外/港澳台岗位单列，不混入内地可投计数
- [ ] 社招不混入校招；一般实习与应届全职分开
- [ ] 多城市存cities数组不成倍计数
- [ ] 活动页、岗位大类、招聘计划、真实职位分别记录粒度
- [ ] 未披露字段保持空值，不猜测

### 1.3 回归测试
- [ ] tests/test_core.py 6项通过
- [ ] tests/e2e_local.py 端到端通过（需本地服务+隔离DB）
- [ ] 三个现有工具（jobs_search/jobs_deadlines/jobs_detail）旧调用语义不破坏
- [ ] 旧ID不重建
- [ ] 新增筛选参数不影响默认查询

### 1.4 榜单与企业库补全
- [ ] 财富世界500强剩余400条（浏览器渲染）
- [ ] 财富中国500强剩余465条（浏览器渲染）
- [ ] Forbes最佳雇主剩余800条（需解决反爬）
- [ ] 阻塞企业跟进：施耐德（Workday租户ID）、联合利华（微信校招入口）、诺唯赞（Workday恢复）

---

## 二、授权后发布步骤（按顺序执行）

### 2.1 备份
```sh
# 备份当前生产代码和数据
ssh server "cp /opt/mcp-suite/qiuzhao/data/jobs.json /opt/mcp-suite/qiuzhao/data/jobs.json.bak.$(date +%Y%m%d)"
ssh server "cp /var/lib/mcp-suite/access.sqlite3 /var/lib/mcp-suite/access.sqlite3.bak.$(date +%Y%m%d)"
```
- [ ] 代码快照备份
- [ ] jobs.json备份
- [ ] access.sqlite3备份（不下载、不展示内容）

### 2.2 核对生产路径和服务归属
- [ ] 确认服务器代码路径 /opt/mcp-suite
- [ ] 确认持久数据路径 /var/lib/mcp-suite
- [ ] 确认服务 mcp-suite.service
- [ ] 确认Nginx配置 /qiuzhao/ 前缀
- [ ] 确认不影响 h5-laoban 及其他站点

### 2.3 部署新适配器代码
- [ ] 上传新适配器文件（qiuzhao/collector/tencent.py、bytedance.py等）
- [ ] 更新 collector-daily.sh 加入新源（错峰执行，每源预算/超时/失败退避）
- [ ] 不覆盖现有 run.py、ccb.py、guopin.py
- [ ] 不修改 core/server.py、core/store.py、qiuzhao/tools.py 的现有逻辑

### 2.4 数据合并与原子切换
- [ ] 各源独立快照不并发写生产jobs.json
- [ ] 单一发布步骤合并并原子切换
- [ ] 保留版本号、校验值（SHA-256）、回滚快照
- [ ] 未审查的源快照不覆盖持久数据库

### 2.5 重启与验证
- [ ] 仅重启 mcp-suite.service
- [ ] 不覆盖 access.sqlite3
- [ ] 验证 /health 正常
- [ ] 验证三个工具线上调用成功（使用隔离测试凭证，不消耗备货码）
- [ ] 验证旧调用兼容、分页及字段保真
- [ ] 验证新增岗位可查询

### 2.6 定时验收
- [ ] 等待至少两次真实定时运行（北京时间06:10）
- [ ] 每次运行有起止、日志、结果和last_success_at
- [ ] 连续48小时无成功复核标stale
- [ ] 手动运行两次不能冒充定时运行两次
- [ ] 至少两次真实定时运行后才标scheduled_verified

---

## 三、回滚方案

### 3.1 代码回滚
```sh
# 恢复备份代码
ssh server "cp /opt/mcp-suite/qiuzhao/collector/*.bak /opt/mcp-suite/qiuzhao/collector/"
ssh systemctl restart mcp-suite.service
```

### 3.2 数据回滚
```sh
# 恢复备份jobs.json（不碰access.sqlite3）
ssh server "cp /var/lib/mcp-suite/jobs.json.bak.YYYYMMDD /var/lib/mcp-suite/jobs.json"
ssh systemctl restart mcp-suite.service
```

### 3.3 回滚验证
- [ ] /health 正常
- [ ] 三个工具返回旧快照数据
- [ ] 额度/鉴权未受影响
- [ ] 定时任务正常运行

---

## 四、绝对禁止事项

| 禁止项 | 原因 |
|---|---|
| 覆盖 access.sqlite3 | 生产鉴权数据库，含用户兑换记录 |
| 重新生成或消耗50个备货码 | 正式库存，不可动 |
| 修改39元套餐/每日200次/有效期至2026-12-31 | 套餐配置真源在store.py PLANS |
| 修改鉴权逻辑 | 影响所有现有用户 |
| 覆盖或修改 h5-laoban | 其他站点，不属于本项目 |
| 跳过备份直接部署 | 无回滚能力 |
| 用开发副本覆盖生产DB | 数据丢失风险 |
| 未经历定时运行就标scheduled_verified | 假验收 |
| 把预告当在招岗位 | 数据真实性 |
| 429/解析空页触发批量下架 | 误删风险 |

---

## 五、当前生产状态确认

| 项目 | 当前值 | 是否变更 |
|---|---|---|
| 生产部署 | 已部署（旧基线9,191条） | 否 |
| 线上服务 | https://savegems.top/qiuzhao/mcp | 未重启 |
| 定时任务 | 北京时间06:10 | 未变更 |
| 套餐 | 39元/200次/2026-12-31 | 未变更 |
| 备货码 | 50个未兑换 | 未消耗 |
| access.sqlite3 | 生产数据库 | 未覆盖 |
| 新增适配器 | 本地开发中 | 未部署 |
| staging数据 | 空 | 未合并 |

---

*本清单在Max明确批准后逐项执行。每步完成后标记并保留证据。未授权前所有步骤保持未执行状态。*
