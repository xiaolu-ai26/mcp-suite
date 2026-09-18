#!/usr/bin/env python3
"""Ingest a company CSV exported by the site owner (企查查/天眼查 VIP export).

Why this exists
---------------
Scraping 企查查 / 天眼查 / 爱企查 is not allowed (login + paid export + terms
forbid crawling), so the compliant path is: the owner exports a filtered CSV from
their own paid account and hands the file over. This tool turns that file into the
same canonical records the discovery pipeline uses:

    CSV rows -> canonical company name -> de-duplicate -> discovery record

Accepted columns (Chinese or English header, order independent)
---------------------------------------------------------------
必需(one of)  : 公司名称 / 企业名称 / company / company_name
建议          : 统一社会信用代码 / credit_code, 企业类型 / company_type,
                登记状态 / status, 参保人数 / insured_count, 行业 / industry,
                省份 / province, 城市 / city, 法定代表人 / legal_person,
                成立日期 / founded_at, 英文名 / company_en

Any extra columns are preserved verbatim in ``extra`` so nothing the owner
exported is lost.

Usage
-----
    python tools/ingest_company_csv.py --input export.csv --out pipeline-watch/foreign-imported.json
    python tools/ingest_company_csv.py --input export.csv --existing pipeline-watch/foreign-universe.json
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

ALIASES = {
    'company_cn': ['公司名称', '企业名称', '公司名', '企业名', 'company', 'company_name', 'name'],
    'credit_code': ['统一社会信用代码', '信用代码', 'credit_code', 'uscc'],
    'company_en': ['英文名', '英文名称', 'company_en', 'english_name'],
    'company_type': ['企业类型', '企业性质', '公司类型', 'company_type', 'type'],
    'status': ['登记状态', '经营状态', 'status', 'registration_status'],
    'insured_count': ['参保人数', '参保人员', 'insured_count', 'insured'],
    'industry': ['行业', '行业大类', '所属行业', 'industry'],
    'province': ['省份', '省', 'province'],
    'city': ['城市', '市', 'city'],
    'legal_person': ['法定代表人', '法人', 'legal_person'],
    'founded_at': ['成立日期', '成立时间', 'founded_at', 'established'],
    'registered_capital': ['注册资本', 'registered_capital'],
    'address': ['注册地址', '地址', 'address'],
}
# 外资口径：企业类型里带这些词的才进外企池
FOREIGN_TYPE_MARKERS = ['外商投资', '外商独资', '中外合资', '合资经营', '港澳台', '外资', '外国法人',
                        '中外合作', '台港澳']
# 登记状态白名单（存续/在业/开业 视为有效）
ACTIVE_STATUS = ['存续', '在业', '开业', '正常', '在营', '迁入', '迁出']
SUFFIX = re.compile(
    r'(有限公司|股份有限公司|有限责任公司|集团|股份|公司|投资|中国区|大中华区|中国|china|greater china)$', re.I)


def norm_header(name):
    return re.sub(r'[\s_\-（）()【】\[\]]', '', str(name or '')).lower()


def canonical_name(name):
    """公司名规范化：全角转半角、压缩空白、去首尾标点，保留官方全称的主体。"""
    text = str(name or '')
    text = text.translate({0x3000: ' ', 0xFF08: '(', 0xFF09: ')'})
    text = re.sub(r'[\u00a0\t\r\n]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip(' .,;；，、')
    return text


def dedupe_key(name):
    s = re.sub(r'[\s()（）·,，、.．\-—/*]', '', canonical_name(name)).lower()
    return SUFFIX.sub('', s)


def pick(row, field):
    for alias in ALIASES[field]:
        for key in row:
            if norm_header(key) == norm_header(alias):
                return str(row[key] or '').strip()
    return ''


def is_foreign_type(value):
    text = str(value or '')
    return any(marker in text for marker in FOREIGN_TYPE_MARKERS)


def is_active(value):
    text = str(value or '')
    if not text:
        return True  # 未提供登记状态时不因此拒绝，交由人工复核
    return any(marker in text for marker in ACTIVE_STATUS)


def parse_int(value):
    m = re.search(r'\d[\d,]*', str(value or ''))
    return int(m.group(0).replace(',', '')) if m else None


def ingest(text, min_insured=None, require_foreign_type=True, require_active=True):
    reader = csv.DictReader(io.StringIO(text))
    records, rejected, seen = [], [], {}
    for lineno, row in enumerate(reader, start=2):
        name = canonical_name(pick(row, 'company_cn'))
        if not name:
            rejected.append({'line': lineno, 'reason': 'missing_company_name', 'row': row})
            continue
        company_type = pick(row, 'company_type')
        status = pick(row, 'status')
        insured = parse_int(pick(row, 'insured_count'))
        if require_foreign_type and company_type and not is_foreign_type(company_type):
            rejected.append({'line': lineno, 'reason': 'not_foreign_type', 'company': name,
                             'company_type': company_type})
            continue
        if require_active and not is_active(status):
            rejected.append({'line': lineno, 'reason': 'inactive_status', 'company': name,
                             'status': status})
            continue
        if min_insured is not None and insured is not None and insured < min_insured:
            rejected.append({'line': lineno, 'reason': 'insured_below_min', 'company': name,
                             'insured_count': insured})
            continue
        key = dedupe_key(name)
        if key in seen:
            prev = seen[key]
            prev['duplicate_names'].append(name)
            if insured and (prev.get('insured_count') or 0) < insured:
                prev.update({'company_cn': name, 'insured_count': insured})
            continue
        industry = pick(row, 'industry')
        record = {
            'company_cn': name,
            'company_en': pick(row, 'company_en'),
            'credit_code': pick(row, 'credit_code'),
            'company_type': company_type,
            'status': status,
            'insured_count': insured,
            'industry': [industry] if industry else [],
            'province': pick(row, 'province'),
            'city': pick(row, 'city'),
            'legal_person': pick(row, 'legal_person'),
            'founded_at': pick(row, 'founded_at'),
            'registered_capital': pick(row, 'registered_capital'),
            'address': pick(row, 'address'),
            'sources': ['owner CSV export (企查查/天眼查 VIP)'],
            'ats': '', 'campus_url': '', 'in_config': False,
            'duplicate_names': [],
        }
        known = {a for aliases in ALIASES.values() for a in aliases}
        record['extra'] = {k: v for k, v in row.items()
                           if norm_header(k) not in {norm_header(a) for a in known}}
        seen[key] = record
        records.append(record)
    return {'generated_at': dt.date.today().isoformat(),
            'description': '由站长提供的企业 CSV 导出经 tools/ingest_company_csv.py 规范化后的记录',
            'filters': {'min_insured': min_insured, 'require_foreign_type': require_foreign_type,
                        'require_active': require_active},
            'summary': {'accepted': len(records), 'rejected': len(rejected)},
            'companies': records, 'rejected': rejected}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--out', default='')
    ap.add_argument('--existing', default='', help='existing universe json to mark already-known rows')
    ap.add_argument('--min-insured', type=int, default=None)
    ap.add_argument('--allow-non-foreign-type', action='store_true')
    ap.add_argument('--allow-inactive', action='store_true')
    args = ap.parse_args()
    text = Path(args.input).read_text(encoding='utf-8-sig')
    payload = ingest(text, min_insured=args.min_insured,
                     require_foreign_type=not args.allow_non_foreign_type,
                     require_active=not args.allow_inactive)
    if args.existing:
        existing = json.loads(Path(args.existing).read_text(encoding='utf-8'))
        known = {dedupe_key(c.get('company_cn') or '') for c in existing.get('companies', [])}
        for rec in payload['companies']:
            rec['already_known'] = dedupe_key(rec['company_cn']) in known
        payload['summary']['already_known'] = sum(1 for r in payload['companies'] if r['already_known'])
        payload['summary']['new'] = sum(1 for r in payload['companies'] if not r['already_known'])
    out = args.out or '-'
    body = json.dumps(payload, ensure_ascii=False, indent=1)
    if out == '-':
        print(body)
    else:
        Path(out).write_text(body, encoding='utf-8')
        print(json.dumps(payload['summary'], ensure_ascii=False), '->', out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
