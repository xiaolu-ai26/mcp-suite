# tools.py 修改说明（v3 A线#4 岗位MVP）

## 目标
在保持三个工具（jobs_search / jobs_deadlines / jobs_detail）旧调用语义完全兼容的前提下，为 `jobs_search` 新增 4 个可选筛选参数。

## 修改范围
仅 `qiuzhao/tools.py` 的 `Jobs.search()` 方法签名与匹配逻辑。
未改动：`load()` / `public()` / `envelope()` / `deadlines()` / `detail()`，未改动 `server.py`、`store.py`、`private/`。

## 新增参数（全部可选，默认 None = 不筛选）

| 参数 | 作用 | 匹配字段 | 空值行为 |
|---|---|---|---|
| `company` | 公司名称关键词 | `recruitment_unit` / `contracting_entity` / `recruiting_unit_raw` / `parent_unit_raw` | None/空串不筛选 |
| `recruitment_type` | 招聘类型（校招/实习/社招） | `recruitment_type_raw` / `campaign_cohort_raw` | None/空串不筛选 |
| `industry` | 行业/职能关键词 | `job_category` / `hiring_department_raw` / `description_raw` | None/空串不筛选 |
| `region` | 地域大区（mainland/overseas） | `region` | None/空串不筛选 |

## 兼容性保证
- 新参数全部位于参数列表末尾，默认值 `None`；旧调用 `jobs.search(city, major, cohort, keyword, limit, offset)` 不传新参数时行为与旧版逐字节一致。
- 未知值处理：空值/None 直接跳过该条件（`has(query, values)` 中 `not query` 为真），不猜测、不报错。
- 旧参数（city/major/cohort/keyword）的匹配逻辑未变。

## 核心代码片段
```python
def search(self, city=None, major=None, cohort=None, keyword=None, limit=50, offset=0,
           company=None, recruitment_type=None, industry=None, region=None):
    rows, cutoff = self.load()

    def has(query, values):
        return (not query) or (query.strip().casefold() in json.dumps(values, ensure_ascii=False).casefold())

    def matches(row):
        pairs = [(city, [row.get("cities", [])]),
                 (major, [row.get("major_requirements_raw"), row.get("major_tags")]),
                 (cohort, [row.get("cohort_raw") or row.get("campaign_cohort_raw")]),
                 (keyword, [...原字段...]),
                 (company, [row.get("recruitment_unit"), row.get("contracting_entity"), ...]),
                 (recruitment_type, [row.get("recruitment_type_raw"), row.get("campaign_cohort_raw")]),
                 (industry, [row.get("job_category"), row.get("hiring_department_raw"), row.get("description_raw")]),
                 (region, [row.get("region")])]
        return all(has(query, values) for query, values in pairs)
```

## 验证
- `pytest tests/test_core.py` → 10 passed（含原 6 项核心用例 `test_jobs_preserve_facts_and_deadline_order`、`test_role_cohort_overrides_campaign_title` 等）。
- 新参数实测：`search(city='深圳', recruitment_type='校招', company='腾讯')` 返回 259 条；旧参数组合 `major='计算机', cohort='2027', city='深圳'` 返回 43 条。
