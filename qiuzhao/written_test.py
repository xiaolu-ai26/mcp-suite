"""笔试要求(written_test):公司/专场级标注表 + 岗位继承 + 岗位描述明文覆盖。

口径(站长 2026-09-19,写死在本模块,不随调用方变化):
    有笔试      官方公告/流程页/FAQ/岗位描述明文写了笔试、测评、在线测试、机考、OT 等任一做题环节。
    免笔试      官方公布了完整招聘流程,且流程里没有任何笔试/测评环节(例:网申 → 面试 → offer);
                或官方明文写"免笔试/无笔试/直通面试"。
    部分免笔试  限定性豁免:优才免笔试、优秀者可免笔试、部分岗位需笔试等,限定语必须留在 evidence 里。
    未注明      官方没公布流程,或读不到。读不到不等于免笔试。

每个标注都带 written_test_evidence(逐字原文)、written_test_source_url(官方页面)、
written_test_scope(company/campaign/job)、written_test_checked_at。

设计要点:
- 标注表是唯一真源(qiuzhao/data/written_test_labels.json);normalize 阶段把标注继承到岗位。
- 标注表缺失/为空时,resolve 返回 None,调用方不得改动记录里已有的值(避免误抹)。
- 岗位描述明文的优先级高于标注表;限定性豁免一律不标"免笔试"。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

UNSPECIFIED = "未注明"
VALUES = ("免笔试", "部分免笔试", "有笔试", "未注明")

FIELDS = ("written_test", "written_test_scope", "written_test_basis",
          "written_test_evidence", "written_test_source_url", "written_test_checked_at")

LABELS_PATH = Path(__file__).resolve().parent / "data" / "written_test_labels.json"

# 公司名归一化:去空白/括号注释/常见企业后缀。仅用于查表,不写回数据。
_WS = re.compile(r"\s+")
_PAREN = re.compile(r"[（(][^）)]*[）)]")
_SUFFIXES = ("股份有限公司", "有限责任公司", "集团有限公司", "有限公司", "集团", "公司")
COMPANY_KEYS = ("p1_company", "canonical_company", "recruitment_unit", "company",
                "recruitment_unit_raw", "parent_unit_raw")
CAMPAIGN_KEYS = ("source_name", "campaign_title", "campaign_name")

# ---------------------------------------------------------------- 岗位描述明文(高精度)

# 无条件式的"免笔试"明文,例如"本岗位免笔试"。
_EXEMPT_JOB = re.compile(r"(免笔试|无需笔试|无笔试|不设笔试|不用笔试|不需要笔试|免去笔试|跳过笔试|免除笔试)")
# 限定性豁免:"优秀者可免笔试""部分岗位免笔试"——只能标 部分免笔试。
_EXEMPT_LIMITED = re.compile(r"优秀|优先|部分|可免|免予|豁免|绿色通道|直通|内推")
# "本岗位需要参加在线笔试"。调研红线:岗位职责里出现"笔试安排/笔试通知"不算。
_REQUIRED_JOB = re.compile(
    r"(?:本岗位|该岗位|此岗位|本职位|该职位|此职位|本岗位的)[^。;；\n]{0,20}?"
    r"(?:需要|需|须|应|将|要)[^。;；\n]{0,10}?(?:参加|进行|完成|接受|安排)?[^。;；\n]{0,10}?"
    r"(笔试|在线测评|线上测评|在线测试|线上测试|机考|上机考试|在线考试)")
# 英文岗位描述里的等效明文,例如字节的 technical online assessment。
_REQUIRED_JOB_EN = re.compile(
    r"(?:invited to|required to|need to|will)\s+(?:participate in|complete|take|attend)?\s*"
    r"[^.\n]{0,60}?(online assessment|online test|written test|technical assessment)",
    re.I)

_WORK_DUTY = re.compile(r"负责|协助|参与|组织|安排|支持|跟进|统筹|招聘全流程|岗位职责|工作职责")

_BASIS_JOB = "岗位描述明文"


def normalize_company(name) -> str:
    """公司名归一化(查表用):去空白、去括号注释、循环去企业后缀。"""
    text = _WS.sub("", str(name or ""))
    text = _PAREN.sub("", text)
    for _ in range(3):
        for suffix in _SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix) + 1:
                text = text[: -len(suffix)]
                break
        else:
            break
    return text


def _record_companies(record):
    out = []
    for key in COMPANY_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in out:
            out.append(value.strip())
    return out


def _record_campaigns(record):
    out = []
    for key in CAMPAIGN_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in out:
            out.append(value.strip())
    return out


def load_labels(path=None):
    """标注表 -> {归一化 key: label};key_type=campaign 的条目同时进 campaign 表。

    返回 (company_table, campaign_table);文件缺失或损坏时两张表都是空 dict。
    """
    company, campaign = {}, {}
    target = Path(path) if path else LABELS_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return company, campaign
    for label in payload.get("labels") or []:
        if not isinstance(label, dict) or label.get("written_test") not in VALUES:
            continue
        entry = dict(label)
        keys = [entry.get("key") or ""] + list(entry.get("aliases") or [])
        table = campaign if entry.get("key_type") == "campaign" else company
        for key in keys:
            normalized = normalize_company(key)
            if normalized and normalized not in table:
                table[normalized] = entry
    return company, campaign


def lookup(record, tables):
    """岗位 -> 命中的标注条目(专场优先,其次公司;公司名支持去后缀后的前缀匹配)。"""
    company_table, campaign_table = tables if tables else ({}, {})
    for name in _record_campaigns(record):
        hit = campaign_table.get(normalize_company(name))
        if hit is not None:
            return hit
    for name in _record_companies(record):
        normalized = normalize_company(name)
        hit = company_table.get(normalized)
        if hit is not None:
            return hit
        # 库内常见 "中国银行股份有限公司北京市分行" 这类带层级后缀的写法。
        for key, label in company_table.items():
            if len(key) >= 4 and normalized.startswith(key):
                return label
    return None


def job_level(record):
    """岗位描述明文覆盖;证据不足时返回 None(不推断)。

    限定性豁免(优秀者可免笔试、部分岗位需笔试)一律落 部分免笔试,并在 evidence 里保留限定语。
    """
    text = record.get("description_raw")
    if not isinstance(text, str) or not text.strip():
        return None
    for sentence in re.split(r"[。;；\n\r]+", text):
        sentence = sentence.strip()
        if not sentence or len(sentence) > 240:
            continue
        if _EXEMPT_JOB.search(sentence):
            if _WORK_DUTY.search(sentence):
                continue
            value = "部分免笔试" if _EXEMPT_LIMITED.search(sentence) else "免笔试"
            return _label(value, "job", _BASIS_JOB, sentence, record, confidence="high")
        match = _REQUIRED_JOB.search(sentence)
        if match:
            if _WORK_DUTY.search(sentence) and "需要参加" not in sentence:
                continue
            return _label("有笔试", "job", _BASIS_JOB, sentence, record, confidence="high")
        match = _REQUIRED_JOB_EN.search(sentence)
        if match:
            return _label("有笔试", "job", _BASIS_JOB, sentence, record, confidence="medium")
    return None


def resolve(record, tables):
    """岗位最终标注:岗位明文 > 标注表(专场 > 公司)> None(调用方按未注明处理)。

    没有标注时不返回"未注明"条目,让调用方决定是否写默认值——这样标注表缺失也不会误抹已有数据。
    """
    job = job_level(record)
    if job:
        return job
    hit = lookup(record, tables)
    if not hit:
        return None
    scope = hit.get("written_test_scope") or ("campaign" if hit.get("key_type") == "campaign" else "company")
    return {
        "written_test": hit["written_test"],
        "written_test_scope": scope,
        "written_test_basis": hit.get("written_test_basis") or "",
        "written_test_evidence": hit.get("written_test_evidence") or "",
        "written_test_source_url": hit.get("written_test_source_url") or "",
        "written_test_checked_at": hit.get("written_test_checked_at") or "",
    }


def _label(value, scope, basis, evidence, record, confidence="high"):
    source = ""
    for key in ("source_url", "detail_url", "application_url", "announcement_url", "campaign_url"):
        candidate = record.get(key)
        if isinstance(candidate, str) and candidate.startswith("http"):
            source = candidate
            break
    return {
        "written_test": value,
        "written_test_scope": scope,
        "written_test_basis": basis,
        "written_test_evidence": evidence.strip(),
        "written_test_source_url": source,
        "written_test_checked_at": "",
        "confidence": confidence,
    }


def apply_to_record(record, tables, stats, checked_at_default=""):
    """把 resolve 的结果写进记录(幂等)。标注表为空时不做任何改动,返回 False。"""
    if not tables or not (tables[0] or tables[1]):
        return False
    resolved = resolve(record, tables) or {"written_test": UNSPECIFIED}
    for field in FIELDS:
        value = resolved.get(field) or ""
        if field == "written_test_checked_at" and value == "" and resolved["written_test"] != UNSPECIFIED:
            value = checked_at_default
        if field == "written_test":
            if record.get(field) != value:
                record[field] = value
                stats[field] += 1
            continue
        if value:
            if record.get(field) != value:
                record[field] = value
                stats[field] += 1
        elif record.get(field):
            record.pop(field, None)
            stats[field] += 1
    return True
