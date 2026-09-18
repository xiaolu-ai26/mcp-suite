"""公司名规范化：把公司身份字段收敛到「品牌/集团层」与「用人单位层」两个口径。

字段口径
--------
- ``canonical_company``：品牌/集团层规范名（腾讯 / 中国移动 / 比亚迪）。
- ``company`` / ``company_name``：对外展示名，恒等于 ``canonical_company``。
- ``recruitment_unit``：用人单位层（法人主体 / 分公司 / 部门）。
- ``recruiting_unit_raw``：来源原始串（腾讯是 TEG/IEG 这类部门码，国聘是法人全称）。

判定顺序
--------
第一条非空的字段作为证据：

    canonical_company -> company -> company_name -> recruitment_unit -> recruiting_unit_raw

``recruitment_unit`` 排在 ``recruiting_unit_raw`` 前面是有意的：raw 里可能是部门码
（腾讯的 TEG/IEG/CSG），拿它当品牌会得到 ``TEG``。

保守规则（第 5 步是默认结局）
----------------------------
1. ``aliases`` 精确命中（忽略空白、全半角括号、大小写）；
2. ``prefixes`` 前缀命中，且余串必须以法人/机构后缀收尾（用于「同一集团的多个法人主体」，
   例如 中国移动通信集团北京有限公司 -> 中国移动）；
3. 文本本身已是已知品牌 -> 原样返回；
4. 逐层剥掉法人后缀（有限公司/股份有限公司/集团/（中国）…）后命中已知品牌 -> 该品牌；
5. 以上都不中 -> **保留原名**，不猜。

已知品牌集合 = ``company_aliases.json`` 的 ``brands`` + 表里所有 canonical 目标
+ ``qiuzhao/collector/p1_platform_companies.json`` 各租户的规范公司名（可选，取不到就跳过）。
表里的 canonical 目标自动进集合，保证规范化幂等。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ALIASES_PATH = Path(__file__).parent / "data" / "company_aliases.json"
PLATFORM_COMPANIES_PATH = Path(__file__).parent / "collector" / "p1_platform_companies.json"

# 公司身份字段，按证据优先级排列。
EVIDENCE_FIELDS = ("canonical_company", "company", "company_name",
                   "recruitment_unit", "recruiting_unit_raw")

# 展示名三兄弟：规范化后三者必须相等。
DISPLAY_FIELDS = ("canonical_company", "company", "company_name")

# 第 4 步允许剥掉的尾巴，按顺序试，命中一个就切一刀再进下一轮。
# 「集团有限公司」不单独列：先切「有限公司」得到「…集团」这一层候选，
# 下一轮再切「集团」，这样两层的候选都能被品牌集合检验到。
_STRIP_SUFFIXES = (
    "股份有限公司", "有限责任公司", "有限公司",
    "集团", "公司", "(中国)",
    "总公司", "总部",
)

# 第 4 步剥完法人后缀后，再允许摘掉一个行业词——**只有当剩下的部分正好是已知品牌时才接受**。
# 例：小米科技有限公司 -> 小米科技 -> 小米；华为技术有限公司 -> 华为技术 -> 华为。
# 拿不准就不摘（北京银行股份有限公司 剥完是「北京银行」，本身不是品牌，保持原名）。
_STRIP_TAIL_WORDS = (
    "科技", "技术", "软件", "通信", "电子", "信息", "网络", "系统",
    "实业", "控股", "投资", "发展",
)

# 前缀命中时，余串必须以这些后缀收尾才算「同一集团的另一个法人主体」。
_ORG_TAIL = re.compile(
    r"^[\u4e00-\u9fffA-Za-z0-9（）()·\-]{0,24}"
    r"(有限公司|有限责任公司|股份有限公司|集团有限公司|公司|集团|分公司|分行|支行"
    r"|事业部|研究院|研究所|学院|大学|总局|总院|总部|中心|银行|局|厂)$"
)


def norm_key(value) -> str:
    """匹配键：去空白、全角括号折半角、大小写不敏感；不改动任何非空字符。"""
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("【", "[").replace("】", "]")
    return text.casefold()


def _load_platform_names():
    """平台配置里各租户的规范公司名（已由 p1_company_names.py 洗过一轮）。

    返回 {匹配键: (规范名, 依据)}，结构与 ``_load`` 的其它表一致——调用方统一按
    ``entry[0]`` 取规范名，这里若返回裸字符串就会退化成取首字符。
    """
    try:
        payload = json.loads(PLATFORM_COMPANIES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    names = {}
    for section, rows in payload.items():
        if section.startswith("_") or not isinstance(rows, dict):
            continue
        for value in rows.values():
            name = value if isinstance(value, str) else (
                value.get("name") if isinstance(value, dict) else None)
            if isinstance(name, str) and name.strip():
                names.setdefault(norm_key(name),
                                 (name.strip(), f"平台配置 {section} 段的规范公司名"))
    return names


def _load():
    try:
        payload = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    aliases, prefixes, brands = {}, {}, {}
    for key, spec in (payload.get("aliases") or {}).items():
        _add(aliases, key, spec)
    for key, spec in (payload.get("prefixes") or {}).items():
        _add(prefixes, key, spec)
    for key, spec in (payload.get("brands") or {}).items():
        # brands 段的键就是规范名，条目只带 basis。
        _add(brands, key, spec, key_is_canonical=True)
    # canonical 目标自动算已知品牌，保证 canonical_of(canonical) == canonical（幂等）。
    for table in (aliases, prefixes):
        for canonical, entry in table.values():
            brands.setdefault(norm_key(canonical), (canonical, "别名表 canonical 目标"))
    for key, entry in _load_platform_names().items():
        brands.setdefault(key, entry)
    return aliases, prefixes, brands


def _add(table, key, spec, key_is_canonical=False):
    key_norm = norm_key(key)
    if not key_norm:
        return
    if isinstance(spec, str):
        table[key_norm] = (spec, "")
        return
    if not isinstance(spec, dict):
        raise ValueError(f"company_aliases.json 条目必须是字符串或对象: {key!r}")
    canonical = str(spec.get("canonical") or (key if key_is_canonical else "")).strip()
    if not canonical:
        raise ValueError(f"company_aliases.json 条目缺少 canonical: {key!r}")
    table[key_norm] = (canonical, str(spec.get("basis") or "").strip())


_ALIASES, _PREFIXES, _BRANDS = _load()
# 前缀按长度降序，保证最长匹配（中国移动通信 优先于 中国移动）。
_PREFIX_KEYS = sorted(_PREFIXES, key=len, reverse=True)


def _peel_candidates(text):
    """逐层剥法人后缀，产出候选（顺序 = 剥离深度）。"""
    out = []
    current = text
    for _ in range(len(_STRIP_SUFFIXES)):
        changed = False
        for suffix in _STRIP_SUFFIXES:
            if current.endswith(suffix) and len(current) > len(suffix):
                current = current[: -len(suffix)].strip()
                if current and current not in out:
                    out.append(current)
                changed = True
                break
        if not changed:
            break
    return out


def canonical_of(value):
    """单个公司名文本 -> (规范名, 依据)。依据是给人看的短标签，便于抽查。"""
    raw = "" if value is None else str(value).strip()
    key = norm_key(raw)
    if not key:
        return "", "空值"
    hit = _ALIASES.get(key)
    if hit is not None:
        return hit[0], "alias"
    for prefix in _PREFIX_KEYS:
        if not key.startswith(prefix) or key == prefix:
            continue
        canonical = _PREFIXES[prefix][0]
        if key == norm_key(canonical):
            continue
        if _ORG_TAIL.match(key[len(prefix):]):
            return canonical, "prefix"
    if key in _BRANDS:
        return _BRANDS[key][0], "brand"
    for candidate in _peel_candidates(key):
        if candidate in _BRANDS:
            return _BRANDS[candidate][0], "peel"
        for word in _STRIP_TAIL_WORDS:
            if candidate.endswith(word) and len(candidate) > len(word):
                trimmed = candidate[: -len(word)]
                if trimmed in _BRANDS:
                    return _BRANDS[trimmed][0], "peel+tail"
    return raw, "keep"


def canonical_company_of(record):
    """按证据优先级取第一个非空字段做规范化；全空返回 ``("", "empty")``。"""
    if not isinstance(record, dict):
        return "", "empty"
    for field in EVIDENCE_FIELDS:
        value = record.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        canonical, basis = canonical_of(text)
        if canonical:
            return canonical, f"{field}:{basis}"
    return "", "empty"


def employer_unit_of(record):
    """用人单位层：优先来源原始串，其次已有的 recruitment_unit。"""
    if not isinstance(record, dict):
        return ""
    for field in ("recruiting_unit_raw", "recruitment_unit"):
        value = record.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def apply_to_record(record, stats=None):
    """就地写三层字段。返回 ``{字段: 是否发生变化}``。

    - ``canonical_company`` / ``company`` / ``company_name`` 一律对齐到规范名（展示名 = canonical）。
    - ``recruitment_unit`` / ``recruiting_unit_raw`` 只做单向补齐，**不覆盖任何已有非空值**：
      现役库里 recruitment_unit 无空值，这一步是 no-op；未来新记录用 raw 补齐，
      保证两层同源。把 recruitment_unit 改写成 raw 的用人单位层会改动 1.9 万行并影响
      industry 查表，属于另一件事。
    """
    changed = {}
    if not isinstance(record, dict):
        return changed
    canonical, _basis = canonical_company_of(record)
    if canonical:
        for field in DISPLAY_FIELDS:
            if record.get(field) != canonical:
                record[field] = canonical
                changed[field] = True
    unit = employer_unit_of(record)
    if unit:
        for field in ("recruitment_unit", "recruiting_unit_raw"):
            if not str(record.get(field) or "").strip():
                record[field] = unit
                changed[field] = True
    if stats is not None:
        for field in changed:
            stats[field] = stats.get(field, 0) + 1
    return changed


def table_info():
    """给收据/探针用的自检信息。"""
    return {
        "aliases": len(_ALIASES),
        "prefixes": len(_PREFIXES),
        "brands": len(_BRANDS),
        "platform_names": len(_load_platform_names()),
    }
