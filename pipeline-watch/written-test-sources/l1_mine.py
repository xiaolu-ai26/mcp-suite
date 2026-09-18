# -*- coding: utf-8 -*-
"""L1 库内流程句挖掘(只读)。精灵上经 stdin 运行,只 print,不写任何文件。

口径(站长 2026-09-19):
  有笔试 = 官方明文写了笔试/测评/在线测试/机考/OT 等任一做题环节
  免笔试 = 官方公布了完整流程,流程里没有任何做题环节
"""
import json
import re
import sys
from collections import Counter, defaultdict

PATH = sys.argv[1] if len(sys.argv) > 1 else r"C:\mcp-suite-collector\data\jobs.json"

SENT_SPLIT = re.compile(r"[。；;\n\r]+")
# 招聘阶段(按环节类型分组,免笔试要求至少覆盖 3 类且含"入口")

STAGE = (
    ("apply", re.compile(r"网申|网上申请|在线申请|线上申请|简历投递|投递简历|申请职位|在线投递|邮箱投递")),
    ("screen", re.compile(r"简历筛选|简历初筛|初筛|筛选简历|资格审查|资格审核|资质审查|简历评估|简历筛选及面试")),
    ("test", re.compile(r"笔试|机考|上机考试|在线考试|统一考试|专业考试|综合考试|在线测试|线上测试|"
                        r"能力测试|性格测试|心理测试|职业测试|认知能力|游戏化测评|"
                        r"测评|"
                        r"\bOT\b|online\s*test|assessment")),
    ("interview", re.compile(r"面试|初面|复试|终面|专业面试|综合面试|业务面试|HR面试|面谈")),
    ("offer", re.compile(r"offer|录用|拟录用|发放入职|签约|入职|体检|背景调查|背调|政审")),
)
CHAIN = re.compile(r"→|->|—>|➔|➜|⇒|›|»|—|－|依次|流程为|流程是|招聘流程|环节|步骤|阶段")
EXCLUDE = re.compile(r"若|如发现|虚假|伪造|有权|不得|禁止|须知|敬告|声明|承诺|个人信息|第三方|培训机构|"
                     r"未经授权|保留.*权利|举报|投诉|骗子|诈骗")
DUTY = re.compile(r"负责|协助|参与|组织|安排|支持|跟进|统筹|承接|完成.*工作|岗位职责|工作职责")
CONDITIONAL = re.compile(r"优秀|优先|部分岗位|视情况|酌情|可免|免予|豁免|绿色通道|直通")
EXEMPT_WORD = re.compile(r"免笔试|无需笔试|无笔试|不设笔试|不用笔试|不需要笔试|免去笔试|跳过笔试|免除笔试")
MAX_SENT = 240

FIELD_KEYS = ("description_raw", "application_instructions", "job_requirement_raw",
              "qualification_raw", "pending_note")
COMPANY_KEYS = ("p1_company", "canonical_company", "recruitment_unit", "company",
                "recruitment_unit_raw", "parent_unit_raw")


def iter_rows(path):
    decoder = json.JSONDecoder()
    with open(path, "r", encoding="utf-8") as fh:
        buf = fh.read(1 << 22)
        idx = buf.find("[")
        if idx < 0:
            return
        pos = idx + 1
        while True:
            n = len(buf)
            while pos < n and buf[pos] in " \t\r\n,":
                pos += 1
            if pos >= n:
                more = fh.read(1 << 22)
                if not more:
                    return
                buf = buf[pos:] + more
                pos = 0
                continue
            if buf[pos] == "]":
                return
            try:
                obj, end = decoder.raw_decode(buf, pos)
            except ValueError:
                more = fh.read(1 << 22)
                if not more:
                    return
                buf = buf[pos:] + more
                pos = 0
                continue
            yield obj
            pos = end
            if pos > (1 << 21):
                buf = buf[pos:]
                pos = 0
                more = fh.read(1 << 22)
                if not more and not buf:
                    return
                buf += more


def norm(text):
    return re.sub(r"\s+", "", text or "")


def company_of(row):
    for key in COMPANY_KEYS:
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def url_of(row):
    for key in ("source_url", "detail_url", "application_url", "announcement_url", "campaign_url"):
        v = row.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return ""


def stages_of(sentence):
    return {name for name, pat in STAGE if pat.search(sentence)}


def classify(sentence):
    """-> (kind|None, confidence, limited)。confidence: high/medium/low。"""
    if EXCLUDE.search(sentence):
        return None, "", False
    stages = stages_of(sentence)
    chain = bool(CHAIN.search(sentence))
    has_test = "test" in stages
    if has_test:
        limited = bool(CONDITIONAL.search(sentence))
        strong = re.search(r"笔试|机考|上机考试|在线考试|统一考试|在线测评|线上测评|在线测试|线上笔试|统一笔试|专业考试|综合考试", sentence)
        if strong and (chain or len(stages) >= 3):
            return "有笔试", "high", limited
        if strong:
            return "有笔试", "medium", limited
        if chain or len(stages) >= 3:
            return "有笔试", "medium", limited
        return "有笔试", "low", limited
    if DUTY.search(sentence) and not chain:
        return None, "", False
    if len(stages) >= 4:
        return "免笔试", "high", False
    if len(stages) >= 3 and ("apply" in stages or "screen" in stages) and chain:
        return "免笔试", "high", False
    return None, "", False


def main():
    rows_total = 0
    with_desc = 0
    companies = Counter()
    bucket = defaultdict(lambda: {"count": 0, "confidence": Counter(), "urls": Counter(),
                                  "sources": Counter(), "rtypes": Counter(), "ids": [],
                                  "all_ids": set(), "limited": False})
    exempt_rows = 0
    exempt_samples = []
    test_field_rows = 0
    pool = defaultdict(lambda: {"有笔试": 0, "免笔试": 0})

    for row in iter_rows(PATH):
        rows_total += 1
        if rows_total % 20000 == 0:
            print("... %d" % rows_total, file=sys.stderr)
        if row.get("written_test"):
            test_field_rows += 1
        comp = company_of(row)
        if comp:
            companies[comp] += 1
        texts = []
        for key in FIELD_KEYS:
            v = row.get(key)
            if isinstance(v, str) and v.strip():
                texts.append(v)
        if not texts:
            continue
        with_desc += 1
        joined = "\n".join(texts)
        if EXEMPT_WORD.search(joined):
            exempt_rows += 1
            if len(exempt_samples) < 40:
                m = EXEMPT_WORD.search(joined)
                start = max(0, m.start() - 120)
                exempt_samples.append({"company": comp, "id": row.get("id"), "url": url_of(row),
                                       "evidence": norm(joined[start:m.end() + 160])})
        if not comp:
            continue
        seen = set()
        for sentence in SENT_SPLIT.split(joined):
            s = norm(sentence)
            if not s or len(s) > MAX_SENT:
                continue
            kind, conf, limited = classify(s)
            if not kind:
                continue
            if s in seen:
                continue
            seen.add(s)
            b = bucket[(comp, kind, s)]
            b["count"] += 1
            b["confidence"][conf] += 1
            b["limited"] = b["limited"] or limited
            u = url_of(row)
            if u:
                b["urls"][u] += 1
            sn = row.get("source_name") or ""
            if sn:
                b["sources"][str(sn)] += 1
            rt = row.get("recruitment_type") or ""
            if rt:
                b["rtypes"][str(rt)] += 1
            if row.get("id"):
                b["all_ids"].add(str(row.get("id")))
                if len(b["ids"]) < 3:
                    b["ids"].append(str(row.get("id")))
            pool[comp][kind] += 1

    out = {"path": PATH, "rows_total": rows_total, "rows_with_text": with_desc,
           "companies_total": len(companies), "rows_with_written_test_field": test_field_rows,
           "rows_with_exempt_word": exempt_rows, "exempt_samples": exempt_samples, "templates": []}
    for (comp, kind, tmpl), b in sorted(bucket.items(), key=lambda kv: (-kv[1]["count"], kv[0][0])):
        out["templates"].append({
            "company": comp, "kind": kind, "count": b["count"], "evidence": tmpl,
            "confidence": dict(b["confidence"]), "conditional": b["limited"],
            "sample_ids": b["ids"], "job_id_count": len(b["all_ids"]),
            "job_ids": sorted(b["all_ids"])[:400],
            "urls": [u for u, _ in b["urls"].most_common(3)],
            "sources": [s for s, _ in b["sources"].most_common(3)],
            "recruitment_types": dict(b["rtypes"].most_common(3)),
        })
    has_ids = defaultdict(set)
    ex_ids = defaultdict(set)
    for (comp, kind, tmpl), b in bucket.items():
        (has_ids if kind == "有笔试" else ex_ids)[comp] |= b["all_ids"]
    out["company_overlap"] = [
        {"company": c, "has_test_jobs": len(has_ids[c]), "exempt_jobs": len(ex_ids[c]),
         "overlap_jobs": len(has_ids[c] & ex_ids[c])}
        for c in sorted(set(has_ids) | set(ex_ids), key=lambda c: -(len(has_ids[c]) + len(ex_ids[c])))]
    out["company_pool"] = [
        {"company": c, "jobs": companies[c], "has_test": v["有笔试"], "exempt": v["免笔试"]}
        for c, v in sorted(pool.items(), key=lambda kv: -(kv[1]["有笔试"] + kv[1]["免笔试"]))
    ]
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print("", file=sys.stdout)


if __name__ == "__main__":
    main()
