# 秋招MCP v3 条件2：筛选集成报告

**日期**: 2026-09-10
**任务**: 将 company / recruitment_type / industry / region 四个筛选真正接到 MCP
**结论**: **条件2 通过**

---

## 一、修改 Diff 摘要

### 1. `core/server.py` — jobs_search 工具参数声明

**变更**: 在 `jobs_search()` 函数签名中新增 4 个可选参数，并在调用 `jobs.search()` 时转发。

```diff
 def jobs_search(
     city: Annotated[str | None, Field(description="城市，如北京；未披露城市不会猜测", max_length=100)] = None,
     major: Annotated[str | None, Field(description="专业关键词", max_length=100)] = None,
     cohort: Annotated[str | None, Field(description="公告中明确写出的届别，如2027", max_length=100)] = None,
     keyword: Annotated[str | None, Field(description="单位/签约主体/岗位关键词", max_length=200)] = None,
+    company: Annotated[str | None, Field(description="企业/单位名称关键词，如中国邮政；在recruitment_unit等企业主体字段中做包含匹配", max_length=100)] = None,
+    recruitment_type: Annotated[str | None, Field(description="招聘类型，如校园招聘；未披露类型不推断", max_length=50)] = None,
+    industry: Annotated[str | None, Field(description="企业主体行业筛选（基于招聘单位所属行业）；当前数据集无企业行业字段，此筛选暂返回空结果，待数据管线补充后启用", max_length=100)] = None,
+    region: Annotated[str | None, Field(description="地域/城市关键词，如北京；在岗位城市字段中做包含匹配", max_length=100)] = None,
     limit: Annotated[int, Field(ge=1, le=100)] = 50,
     offset: Annotated[int, Field(ge=0)] = 0,
 ) -> dict:
-    """按城市、专业、届别、关键词筛选官方岗位，含状态、截止日、原公告URL、数据截至时间。可用offset翻页。"""
-    return jobs.search(city, major, cohort, keyword, limit, offset)
+    """按城市、专业、届别、关键词、企业、招聘类型、行业、地域筛选官方岗位，含状态、截止日、原公告URL、数据截至时间。可用offset翻页。"""
+    return jobs.search(city, major, cohort, keyword, limit, offset,
+                       company=company, recruitment_type=recruitment_type,
+                       industry=industry, region=region)
```

**未改动**: `jobs_deadlines`、`jobs_detail` 参数不变；鉴权、额度、兑换、套餐逻辑（store.py 及中间件）不动。

### 2. `qiuzhao/tools.py` — search() 筛选逻辑修正

**变更**: 修正 industry 和 region 的数据源指向。

```diff
-                     (industry, [row.get("job_category"), row.get("hiring_department_raw"), row.get("description_raw")]),
-                     (region, [row.get("region")])]
+                     # industry 数据源限制：当前数据集无企业主体行业标签字段（无 industry / enterprise_industry 等）。
+                     # job_category 是岗位职能（如"财务专员"），不能冒充企业行业（如"邮政物流"）。
+                     # 因此 industry 筛选在当前数据下始终返回空结果，等待后续数据管线补充企业行业字段后再启用。
+                     (industry, []),
+                     # region 数据源：数据中无独立 region 字段，使用 cities（城市列表）做地域/城市匹配。
+                     (region, [row.get("cities", [])])]
```

同时将 `recruitment_type` 的匹配值从 `campaign_cohort_raw`（届别标题）修正为 `nature_raw`（招聘性质字段）：

```diff
-                     (recruitment_type, [row.get("recruitment_type_raw"), row.get("campaign_cohort_raw")]),
+                     (recruitment_type, [row.get("recruitment_type_raw"), row.get("nature_raw")]),
```

---

## 二、四个筛选的测试查询结果

数据集：`qiuzhao/data/jobs.json`，共 9191 条记录。

| # | 筛选 | 查询参数 | 结果数 | 验证说明 |
|---|------|----------|--------|----------|
| 1 | 不传新参数（回归） | `limit=3` | 9191 | 与修改前一致，旧调用语义不变 |
| 2 | **company** | `company='中国邮政'` | **2648** | 正确匹配 recruitment_unit 含"中国邮政"的记录 |
| 3 | **recruitment_type** | `recruitment_type='校园招聘'` | **5016** | 正确匹配 recruitment_type_raw='校园招聘' 的记录 |
| 4 | **industry** | `industry='金融'` | **0** | 如预期返回空（无企业行业字段，不伪造） |
| 5 | **region** | `region='北京'` | **1128** | 正确匹配 cities 含"北京"的记录 |
| 6 | 组合 | `company='中国电信', region='北京'` | 0 | 数据集中中国电信无北京岗位（数据决定，非 bug） |
| 7 | 旧参数回归 | `city='上海', keyword='银行'` | 6 | 旧筛选逻辑不受影响 |

### company 匹配样本
```
- 中国邮政集团有限公司 | 古交市分公司-金融柜员岗 | ['太原']
- 中国邮政集团有限公司 | 清徐县分公司-金融柜员岗 | ['太原']
```

### recruitment_type 匹配样本
```
- 中国移动通信集团有限公司 | recruitment_type_raw=校园招聘
```

### region 匹配样本
```
- 中国移动通信集团有限公司 | cities=['北京-海淀区']
- 中国移动通信集团有限公司 | cities=['北京']
```

---

## 三、测试通过情况

```
$ .venv/bin/python -m pytest tests/test_core.py -v

tests/test_core.py::test_atomic_redemption PASSED
tests/test_core.py::test_atomic_daily_limit PASSED
tests/test_core.py::test_expiry_product_and_invalid PASSED
tests/test_core.py::test_midnight_resets_and_handshake_free PASSED
tests/test_core.py::test_jobs_preserve_facts_and_deadline_order PASSED
tests/test_core.py::test_role_cohort_overrides_campaign_title PASSED
tests/test_core.py::test_qiuzhao_code_and_key_format_unchanged PASSED
tests/test_core.py::test_bench_plan_is_thirty_days_from_activation PASSED
tests/test_core.py::test_quota_message_uses_plan_limit PASSED
tests/test_core.py::test_bench_returns_links_tags_and_no_body PASSED

============================== 10 passed in 0.26s ==============================
```

**10/10 全部通过**（要求至少 6 项原测试通过）。

---

## 四、industry 筛选的数据源说明

### 现状
当前数据集（`qiuzhao/data/jobs.json`，9191 条记录）中**不存在企业主体行业标签字段**。数据中所有字段如下：

```
announcement_evidence_path, announcement_url, application_url, campaign_cohort_raw,
campaign_url, cities, cohort_raw, cohort_scope, contracting_entity, deadline,
deadline_scope, deadline_type, description_raw, directory_evidence_path, education_raw,
education_scope, evidence_path, hiring_department_raw, id, job_category, job_listing_url,
job_title, job_title_scope, major_requirements_raw, major_tags, nature_raw,
parent_unit_raw, published_at, published_at_scope, record_kind, recruiting_unit_raw,
recruitment_type_raw, recruitment_unit, requirements_scope, reviewed_at, source_group_key,
source_is_apply_raw, source_name, source_record_id, source_status_raw, source_url,
status, status_note
```

### 各字段辨析
| 字段 | 含义 | 是否可作为企业行业 |
|------|------|---------------------|
| `job_category` | 岗位职能分类（如"财务专员/助理"、"柜员"） | **否** — 这是岗位职能，不是企业行业 |
| `hiring_department_raw` | 招聘部门名称（如"中国邮政集团有限公司总部"） | 否 — 这是部门名 |
| `nature_raw` | 招聘性质（如"校招"） | 否 — 这是招聘性质，不是行业 |
| `recruitment_unit` | 招聘企业名称（如"中国邮政集团有限公司"） | 否 — 这是企业名，需要外部行业映射才能转为行业标签 |

### 处理方式
- industry 筛选参数**已暴露在 MCP schema 中**，客户端可正常传入
- 传入 industry 时，因无企业行业数据源，**始终返回空结果（total=0）**，并返回引导 suggestion
- **不伪造行业映射**（不从企业名推断行业，不用 job_category 冒充）
- MCP 工具描述中已明确标注"当前数据集无企业行业字段，此筛选暂返回空结果"
- 待数据管线补充企业行业字段（如接入国标行业分类、证监会行业分类等）后，仅需修改 tools.py 中 `(industry, [])` 一行即可启用

---

## 五、硬性约束遵守确认

| 约束 | 遵守情况 |
|------|----------|
| 不改兑换鉴权额度逻辑 | ✅ store.py 及中间件未动 |
| 不破坏旧调用语义 | ✅ 不传新参数时 total=9191，与修改前完全一致；10/10 测试通过 |
| 不修改生产服务器 | ✅ 仅修改本地文件 |
| 不读取 private/ 目录 | ✅ 未访问 |
| 行业筛选不伪造数据 | ✅ industry 返回空，代码中标注数据源限制 |

---

## 六、最终结论

**条件2：通过。**

- 4 个筛选参数（company / recruitment_type / industry / region）已完整暴露在 `jobs_search` MCP 工具 schema 中
- 参数正确转发到 `qiuzhao/tools.py` 的 `Jobs.search()` 方法
- company 和 recruitment_type 和 region 筛选可用且返回正确结果
- industry 筛选因数据源缺失诚实返回空结果，不伪造
- 旧功能完全兼容，10/10 测试通过
