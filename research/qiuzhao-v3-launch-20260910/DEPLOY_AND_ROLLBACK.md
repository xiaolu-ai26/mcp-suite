# 部署与回滚步骤 — v3

## 生产变更范围（待Max授权后执行）

### 1. 静态文件（4个，可独立先发布）
- core/static/index.html
- core/static/site.css
- core/static/app.js
- core/static/guide.html

备份位置：page_integration/backup_static_20260910/（含旧文件+SHA256）
新文件SHA已验证与包内MANIFEST一致。

### 2. 岗位数据（待验收后合并）
- staging_merged/jobs.json（10,043条）需通过质量审查后替换生产qiuzhao/data/jobs.json
- 当前生产仍为9,191条，未覆盖

### 3. 代码变更
- qiuzhao/tools.py（新增4个可选筛选参数，向后兼容）
- qiuzhao/collector/tencent.py（新增）
- qiuzhao/collector/bytedance.py（新增，当前仅社招）

### 4. 不变更
- access.sqlite3、39元套餐、200次/日、2026-12-31有效期
- 50个正式备货码
- 定时任务(06:10)
- h5-laoban及其他站点
- server.py、store.py

## 部署步骤（授权后）
1. 备份生产4个静态文件（已有本地备份）
2. 逐文件替换静态文件（FileResponse随读取生效，通常无需重启）
3. 验证线上路由、响应头、新页面内容
4. 岗位数据需单独验收后再合并
5. 代码变更需重启mcp-suite服务

## 回滚步骤
1. 恢复page_integration/backup_static_20260910/中的4个旧文件
2. 如已重启服务，再次重启
3. 验证/health和三工具正常
4. 不回滚access.sqlite3（持续变化的生产数据）
