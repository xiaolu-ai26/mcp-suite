# 部署件 20260919e：公司名字段规范化（normalize 阶段）

**未部署、未 SSH 写、未碰阿里云、未调飞书、未 push、未合并 main。**
本包只含 3 个运行时文件，叠加在精灵现役 **20260918k** 之上，一步覆盖。
分支 `feat/company-normalize`（基线 `feat/collector-next-3` f423084/2b123c2）。

## 为什么只改 3 个文件

规范化逻辑挂在 normalize 阶段（`deploy/windows_collector.py` 第 163 行已经在跑
`python -m qiuzhao.normalize --path <stage>/jobs.json`），所以**不需要改采集器、
不需要改调度、不需要改 `windows_collector.py`、不需要改 `p1_pipeline.py`**。

| 文件 | 精灵目标路径 | 类型 |
|---|---|---|
| `normalize.py` | `qiuzhao/normalize.py` | 覆盖（新增公司名步骤 + 统计口径；其余行为逐字节兼容） |
| `company_names.py` | `qiuzhao/company_names.py` | **新增**（判定顺序 + 保守规则 + 表加载） |
| `company_aliases.json` | `qiuzhao/data/company_aliases.json` | **新增**（别名/前缀/品牌表，目录也要新建） |

`SHA256SUMS.txt` 三行与分支源码逐字节一致（`shasum -a 256 -c` 全 OK）。

## 精灵侧（需要 Max 说“上线”才动）

1. 备份 `qiuzhao/normalize.py`；`qiuzhao/company_names.py` 与 `qiuzhao/data/` 当前不存在，
   只需在回滚时删除。
2. 覆盖/新增上表 3 个路径（`qiuzhao/data/` 目录要新建）。
3. 覆盖后自检：
   - `python -m py_compile qiuzhao\normalize.py qiuzhao\company_names.py`
   - `python -c "from qiuzhao import company_names as C; print(C.table_info())"`
     期望 `{'aliases': 19, 'prefixes': 3, 'brands': 953, 'platform_names': 893}`
   - `python -c "from qiuzhao.normalize import REPORTED_FIELDS; print(len(REPORTED_FIELDS))"` 期望 `20`
   - 对现役库跑一次 `python -m qiuzhao.normalize --path data\jobs.json --check`
     （`--check` 不写文件）：期望 `records 93519`、`would_change_existing 9`、
     `filled.canonical_company ≈ 26437`、`company_tables` 如上。
     **`would_change_existing` 没有任何代码消费**（全仓只有 `qiuzhao/normalize.py`
     自己计算并打印；`deploy/windows_collector.py` 只看 normalize 步骤的退出码），
     所以 9 这个非零值不构成拦截。9 条明细见收据第 6 节。
4. 回滚：还原 `qiuzhao/normalize.py` 到 `a53adaf33c891b5d8d8dd5b7531c0799b57666d5a62e987dc92ac22b9eb51b31`，
   删除 `qiuzhao/company_names.py` 与 `qiuzhao/data/company_aliases.json`。

## 服务器侧（阿里云）——**不改也能跑，要改必须站长确认**

- 展示名来自数据字段：`qiuzhao/v4_fields.py` 的 `company = canonical_company or recruitment_unit or company`。
  精灵发布到服务器的 `jobs.json` 里 `canonical_company` 已经全部非空，**服务器一行代码不改**
  就会返回规范名（腾讯 / 中国移动 / 中国邮政 …）。
- 但服务器上 `deploy/collector-daily.sh` 也有一行
  `"$PY" -m qiuzhao.normalize --path /var/lib/mcp-suite/jobs.json`。用旧代码跑这段**不会**
  破坏公司名（旧代码根本不碰这三个字段），只是服务器端不会自己推导规范名。
- 如果站长希望服务器端也具备同样的推导能力（例如服务器上重跑 normalize），需要把本包
  3 个文件同步到 `/opt/mcp-suite/` 对应路径（`/opt/mcp-suite/qiuzhao/data/` 需新建）。
  **这属于服务器写操作，必须站长明确确认后再做，本任务不做。**

## 行为要点（详见收据 RECEIPT-company-normalize.md）

- `canonical_company` / `company` / `company_name` 三字段在 normalize 后一律等于品牌/集团层规范名；
  `recruitment_unit` / `recruiting_unit_raw` 只做单向补齐，**不覆盖任何已有非空值**。
- 判定顺序：`canonical_company → company → company_name → recruitment_unit → recruiting_unit_raw`，
  然后 精确别名 → 前缀（余串须以法人/机构后缀收尾）→ 本身是品牌 → 剥法人后缀命中品牌 → **保留原名**。
- 幂等：干跑第二遍 `filled_total 0`、`would_change_existing 0`。
- 记录条数与 id 集合完全不变（前后 id 集合 sha256 相同）。
