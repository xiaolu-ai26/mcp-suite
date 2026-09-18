# -*- coding: utf-8 -*-
"""全库公司岗位数(只读)。"""
import json
import sys
from collections import Counter

PATH = sys.argv[1] if len(sys.argv) > 1 else r"C:\mcp-suite-collector\data\jobs.json"
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


def main():
    counts = Counter()
    rtypes = {}
    for row in iter_rows(PATH):
        name = ""
        for key in COMPANY_KEYS:
            v = row.get(key)
            if isinstance(v, str) and v.strip():
                name = v.strip()
                break
        if not name:
            continue
        counts[name] += 1
        rt = str(row.get("recruitment_type") or "未注明")
        rt_counter = rtypes.setdefault(name, Counter())
        rt_counter[rt] += 1
    payload = [{"company": c, "jobs": n, "recruitment_types": dict(rtypes[c])} for c, n in counts.most_common()]
    json.dump(payload, sys.stdout, ensure_ascii=False)
    print("", file=sys.stdout)


if __name__ == "__main__":
    main()
