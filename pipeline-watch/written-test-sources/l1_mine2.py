# -*- coding: utf-8 -*-
"""补充挖掘:完整流程句(重点找流程里没有做题环节的公司)。只读,只 print。"""
import json
import re
import sys
from collections import Counter, defaultdict

PATH = sys.argv[1] if len(sys.argv) > 1 else r"C:\mcp-suite-collector\data\jobs.json"
SENT_SPLIT = re.compile(r"[。；;\n\r]+")
STAGE = (
    ("apply", re.compile(r"网申|网上申请|在线申请|线上申请|简历投递|投递简历|在线投递|邮箱投递|报名")),
    ("screen", re.compile(r"简历筛选|简历初筛|初筛|筛选简历|资格审查|资格审核|资质审查|简历评估")),
    ("test", re.compile(r"笔试|机考|上机考试|在线考试|统一考试|专业考试|综合考试|在线测试|线上测试|"
                        r"能力测试|性格测试|心理测试|职业测试|认知能力|游戏化测评|测评")),
    ("interview", re.compile(r"面试|初面|复试|终面|专业面试|综合面试|业务面试|HR面试|面谈")),
    ("offer", re.compile(r"offer|录用|拟录用|签约|入职|体检|背景调查|背调|政审|考察|公示")),
)
CHAIN = re.compile(r"→|->|—>|➔|➜|⇒|›|»|—|－|依次|流程|程序|环节|步骤|阶段")
EXCLUDE = re.compile(r"若|如发现|虚假|伪造|有权|不得|禁止|须知|敬告|声明|承诺|个人信息|第三方|培训机构|"
                     r"未经授权|保留.*权利|举报|投诉|骗子|诈骗|待遇|薪酬|福利|补贴|保险|公积金")
DUTY = re.compile(r"负责|协助|参与|组织|安排|支持|跟进|统筹|承接|岗位职责|工作职责|你将|任职要求|岗位要求")
COMPANY_KEYS = ("p1_company", "canonical_company", "recruitment_unit", "company",
                "recruitment_unit_raw", "parent_unit_raw")
FIELD_KEYS = ("description_raw", "application_instructions", "pending_note")


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


def company_of(row):
    for key in COMPANY_KEYS:
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def main():
    bucket = defaultdict(lambda: {"count": 0, "urls": Counter(), "ids": [], "sources": Counter()})
    for row in iter_rows(PATH):
        comp = company_of(row)
        if not comp:
            continue
        texts = [row.get(k) for k in FIELD_KEYS if isinstance(row.get(k), str) and row.get(k)]
        if not texts:
            continue
        seen = set()
        for sentence in SENT_SPLIT.split("\n".join(texts)):
            s = re.sub(r"\s+", "", sentence or "")
            if not s or len(s) > 220 or s in seen:
                continue
            seen.add(s)
            if EXCLUDE.search(s):
                continue
            stages = {name for name, pat in STAGE if pat.search(s)}
            if len(stages) < 3:
                continue
            if not (CHAIN.search(s) or len(stages) >= 4):
                continue
            if DUTY.search(s) and not CHAIN.search(s):
                continue
            kind = "有做题" if "test" in stages else "无做题"
            b = bucket[(comp, kind, s)]
            b["count"] += 1
            for key in ("source_url", "detail_url", "application_url", "announcement_url", "campaign_url"):
                v = row.get(key)
                if isinstance(v, str) and v.startswith("http"):
                    b["urls"][v] += 1
                    break
            if len(b["ids"]) < 3 and row.get("id"):
                b["ids"].append(str(row.get("id")))
            sn = row.get("source_name")
            if isinstance(sn, str) and sn:
                b["sources"][sn] += 1
    rows = []
    for (comp, kind, tmpl), b in bucket.items():
        rows.append({"company": comp, "kind": kind, "count": b["count"], "evidence": tmpl,
                     "urls": [u for u, _ in b["urls"].most_common(2)],
                     "sample_ids": b["ids"], "sources": [s for s, _ in b["sources"].most_common(2)]})
    rows.sort(key=lambda r: (r["kind"], -r["count"]))
    json.dump({"templates": rows}, sys.stdout, ensure_ascii=False, indent=1)
    print("", file=sys.stdout)


if __name__ == "__main__":
    main()
