# 秋招MCP岗位库自动化更新方案

**创建时间**: 2026-09-11
**目标**: 实现每日自动采集企业招聘岗位，无需人工浏览器操作

---

## 一、当前自动化现状

### 已实现的适配器（本地代码）
| 适配器 | 企业 | 采集方式 | 状态 |
|---|---|---|---|
| tencent.py | 腾讯 | 公开API | ✅ 已部署到服务器，可命令行运行 |
| bytedance.py | 字节跳动 | 公开API | ✅ 本地可用，未部署 |
| alibaba_headless.py | 阿里巴巴 | 无头浏览器 | ✅ 本地可用，未部署 |
| meituan.py | 美团 | 公开API/无头 | ✅ 本地可用，未部署 |
| midea.py | 美的 | 公开API/无头 | ✅ 本地可用，未部署 |
| mindray.py | 迈瑞 | 公开API/无头 | ✅ 本地可用，未部署 |
| netease.py | 网易 | 公开API/无头 | ✅ 本地可用，未部署 |
| guopin.py | 国聘 | 公开API | ✅ 已部署到服务器 |
| ccb.py | 建行 | 公开API | ✅ 已部署到服务器 |

### 未实现自动化的企业
- **北森系**（名创优品、喜茶、零跑、国轩、泡泡玛特等）：需浏览器采集，无公开API
- **MokaHR系**（理想、小鹏、蔚来等）：需数字ID，浏览器采集
- **企业自建站**（华为、OPPO、小红书等）：需浏览器采集
- **飞书招聘系**（米哈游、理想等）：API当前502不可用

### 服务器定时任务现状
- 服务器有cron，但**没有MCP岗位采集的定时任务**
- 腾讯适配器已部署但未配置定时运行
- 当前所有更新都是人工触发

---

## 二、自动化架构设计

### 分层采集策略

```
┌─────────────────────────────────────────────────┐
│              每日定时任务 (cron 02:00)           │
├─────────────────────────────────────────────────┤
│  第一层: API适配器 (快速, 高可靠)                │
│  ├── tencent.py (腾讯)                           │
│  ├── bytedance.py (字节)                         │
│  ├── alibaba.py (阿里)                           │
│  ├── meituan.py (美团)                           │
│  ├── netease.py (网易)                           │
│  ├── midea.py (美的)                             │
│  ├── mindray.py (迈瑞)                           │
│  └── guopin.py (国聘)                            │
├─────────────────────────────────────────────────┤
│  第二层: 无头浏览器采集 (中速, 需Playwright)     │
│  ├── 北森企业批量采集 (beisen_batch.py)          │
│  ├── MokaHR企业批量采集 (mokahr_batch.py)        │
│  └── 企业自建站批量采集 (selfbuilt_batch.py)     │
├─────────────────────────────────────────────────┤
│  第三层: 合并与发布                               │
│  ├── 去重 (按detail_url)                         │
│  ├── 字段规范化 (行业/招聘类型/城市)             │
│  ├── 备份旧快照                                   │
│  ├── 写入jobs.json                                │
│  ├── 重启mcp-suite.service                       │
│  └── 健康检查 + 日志记录                          │
└─────────────────────────────────────────────────┘
```

### 采集频率
- **API适配器**: 每日1次（凌晨2:00）
- **无头浏览器采集**: 每日1次（凌晨3:00，避开API采集高峰）
- **全量对账**: 每周1次（周日凌晨4:00，检查过期岗位）

---

## 三、具体实现方案

### 3.1 API适配器自动化（第一优先级）

**已有代码**: `/opt/mcp-suite/qiuzhao/collector/tencent.py`

**部署步骤**:
1. 将本地适配器（bytedance.py、alibaba_headless.py等）同步到服务器
2. 编写统一运行脚本 `run_daily.sh`
3. 配置cron定时任务

**统一运行脚本示例**:
```bash
#!/bin/bash
# /opt/mcp-suite/qiuzhao/collector/run_daily.sh
set -e

LOG_FILE="/var/log/mcp-collector/$(date +%Y%m%d).log"
mkdir -p /var/log/mcp-collector

echo "=== $(date) 开始每日采集 ===" >> $LOG_FILE

# 第一层: API适配器
cd /opt/mcp-suite
for adapter in tencent bytedance alibaba meituan netease midea mindray; do
    echo "[$(date)] 采集 $adapter..." >> $LOG_FILE
    python3 qiuzhao/collector/${adapter}.py >> $LOG_FILE 2>&1 || echo "[$adapter] 失败" >> $LOG_FILE
done

# 第二层: 无头浏览器采集（如果有Playwright）
if command -v playwright &> /dev/null; then
    echo "[$(date)] 无头浏览器采集..." >> $LOG_FILE
    python3 qiuzhao/collector/browser_batch.py >> $LOG_FILE 2>&1 || echo "浏览器采集失败" >> $LOG_FILE
fi

# 第三层: 合并发布
echo "[$(date)] 合并发布..." >> $LOG_FILE
python3 qiuzhao/collector/merge_and_publish.py >> $LOG_FILE 2>&1

echo "=== $(date) 采集完成 ===" >> $LOG_FILE
```

**cron配置**:
```bash
# 每日凌晨2点执行
0 2 * * * /opt/mcp-suite/qiuzhao/collector/run_daily.sh
```

### 3.2 北森企业批量采集（第二优先级）

**问题**: 北森API返回500，但网页可访问

**解决方案**: 用Playwright无头浏览器批量采集

**实现思路**:
```python
# beisen_batch.py
from playwright.sync_api import sync_playwright
import json

BEISEN_COMPANIES = [
    ("miniso", "名创优品", "消费/零售"),
    ("heytea", "喜茶", "消费/零售"),
    ("leapmotor", "零跑汽车", "制造/工业"),
    ("gotion", "国轩高科", "制造/工业"),
    ("popmart", "泡泡玛特", "消费/零售"),
    # ... 更多北森企业
]

def collect_beisen(slug, name, industry):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"https://{slug}.zhiye.com/campus/jobs", wait_until="networkidle")
        text = page.inner_text("body")
        # 解析岗位列表
        jobs = parse_jobs_from_text(text, name, industry)
        browser.close()
        return jobs
```

**服务器部署Playwright**:
```bash
pip install playwright
playwright install chromium
```

### 3.3 MokaHR企业批量采集（第三优先级）

**问题**: MokaHR需要数字ID，不带ID跳转"页面不存在"

**解决方案**: 
1. 预先收集每家企业的MokaHR数字ID（通过搜索引擎或手动查找）
2. 用Playwright访问正确的URL格式：`https://app.mokahr.com/campus-recruitment/{slug}/{numeric_id}#/jobs`

**MokaHR ID清单**（需补充）:
| 企业 | slug | 数字ID | 状态 |
|---|---|---|---|
| 理想汽车 | lixiang | 待查找 | 阻塞 |
| 小鹏汽车 | xiaopeng | 待查找 | 阻塞 |
| 蔚来汽车 | nio | 待查找 | 阻塞 |
| 宁德时代 | catl | 待查找 | 阻塞 |

### 3.4 合并与发布脚本

```python
# merge_and_publish.py
import json
import shutil
from datetime import datetime

# 1. 读取所有采集结果
all_new_jobs = []
for f in ["tencent.json", "bytedance.json", "beisen_batch.json", ...]:
    try:
        with open(f) as fp:
            all_new_jobs.extend(json.load(fp))
    except:
        pass

# 2. 读取现有岗位库
with open("/var/lib/mcp-suite/jobs.json") as f:
    existing_jobs = json.load(f)

# 3. 去重（按detail_url）
existing_urls = set(j.get("detail_url", "") for j in existing_jobs)
added = 0
for job in all_new_jobs:
    url = job.get("detail_url", "")
    if url and url not in existing_urls:
        existing_jobs.append(job)
        existing_urls.add(url)
        added += 1

# 4. 备份
backup_path = f"/var/lib/mcp-suite/jobs.json.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
shutil.copy("/var/lib/mcp-suite/jobs.json", backup_path)

# 5. 写入
with open("/var/lib/mcp-suite/jobs.json", "w") as f:
    json.dump(existing_jobs, f, ensure_ascii=False)

# 6. 重启服务（由外部脚本执行）
print(f"新增 {added} 条岗位，总计 {len(existing_jobs)} 条")
```

---

## 四、实施路线图

### 阶段一: API适配器自动化（1-2天）
- [ ] 将本地适配器同步到服务器
- [ ] 编写统一运行脚本 `run_daily.sh`
- [ ] 测试每个适配器能否独立运行
- [ ] 配置cron定时任务
- [ ] 验证首次自动采集结果

### 阶段二: 北森无头浏览器采集（2-3天）
- [ ] 服务器安装Playwright + Chromium
- [ ] 编写 `beisen_batch.py` 批量采集脚本
- [ ] 测试5家北森企业采集
- [ ] 集成到 `run_daily.sh`
- [ ] 验证自动采集结果

### 阶段三: MokaHR和自建站采集（3-5天）
- [ ] 收集MokaHR企业数字ID清单
- [ ] 编写 `mokahr_batch.py`
- [ ] 编写 `selfbuilt_batch.py`（针对有明确招聘页面的企业）
- [ ] 集成到每日任务
- [ ] 全量验证

### 阶段四: 监控与告警（1天）
- [ ] 采集日志轮转与保留
- [ ] 失败告警（邮件/飞书通知）
- [ ] 每日采集报告（新增岗位数、失败企业数）
- [ ] 健康检查自动化

---

## 五、风险与应对

| 风险 | 影响 | 应对方案 |
|---|---|---|
| 企业API变更/下线 | 对应企业采集失败 | 适配器失败不影响其他企业，日志记录，人工排查 |
| 反爬限制（IP封禁） | 浏览器采集失败 | 降低采集频率，加随机延迟，使用代理IP |
| 服务器资源不足 | Playwright运行慢/崩溃 | 限制并发数，分时段采集，监控内存 |
| 岗位数据重复 | 库膨胀 | 严格按detail_url去重，定期清理过期岗位 |
| 采集失败导致空发布 | 数据丢失 | 发布前备份，新增为0时不覆盖，告警通知 |

---

## 六、当前可立即执行的步骤

1. **部署腾讯适配器定时任务**（已部署，只需加cron）
2. **同步本地适配器到服务器**（bytedance、alibaba、meituan等）
3. **编写 `run_daily.sh` 统一脚本**
4. **测试API适配器能否在服务器独立运行**
5. **服务器安装Playwright**（为北森采集做准备）

---

## 七、不做的事情

- 不修改生产鉴权库（access.sqlite3）
- 不修改套餐、额度、兑换逻辑
- 不修改Nginx和其他站点
- 不绕过验证码、登录或付费限制
- 不采集用户私有数据
- 不删除现有岗位数据（只新增，过期标记不删除）

---

**下一步**: 先执行阶段一，将已有API适配器配置成每日定时任务。需要用户确认是否允许在服务器添加cron任务。
