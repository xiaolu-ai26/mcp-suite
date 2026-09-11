#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build 100-company foreign-expansion candidate list.
Already investigated (from qiuzhao-expansion-20260910) are seeded with their prior status.
"""
import json, os

OUT = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"

# slug, cn_name, en_name, country, industry, known/guessed platform family
# status seeds:
prior = {
    # slug: (name, country, industry, platform, prior_status, note)
    "pg":         ("宝洁 Procter&Gamble", "美国", "快消", "Phenom", "有可用岗位部分覆盖", "完整-8个中国校招岗位已提取"),
    "bosch":      ("博世 Bosch", "德国", "汽车/工业", "MokaHR", "有可用岗位部分覆盖", "180校招岗位列表已获取，详情ID受SPA限制"),
    "accenture":  ("埃森哲 Accenture", "美国", "咨询/IT", "Workday", "partial", "需复核"),
    "loreal":     ("欧莱雅 L'Oreal", "法国", "快消/美妆", "MokaHR", "partial", "需复核"),
    "schneider":  ("施耐德电气 Schneider", "法国", "工业/能源", "Workday(疑似)", "访问受阻", "Workday 500 / se.com 403"),
    "unilever":   ("联合利华 Unilever", "英国", "快消", "自建", "访问受阻", "中国站Under Construction；UFLP2027已启动"),
    "astrazeneca":("阿斯利康 AstraZeneca", "英国/瑞典", "医药", "Workday", "partial", "需复核"),
}

# The remaining candidates to reach 100 (group-deduped), prioritized by China campus-recruit presence.
candidates = [
    # ---- FMCG / consumer ----
    ("nestle",   "雀巢 Nestle", "瑞士", "快消", "Workday/Phenom"),
    ("pepsico",  "百事 PepsiCo", "美国", "快消", "Workday"),
    ("cocacola", "可口可乐 Coca-Cola", "美国", "快消", "Workday"),
    ("mars",     "玛氏 Mars", "美国", "快消/宠物", "自建/Taleo"),
    ("danone",   "达能 Danone", "法国", "快消/食品", "Workday"),
    ("mondelez", "亿滋 Mondelez", "美国", "快消", "Workday"),
    ("colgate",  "高露洁 Colgate", "美国", "快消/日化", "Workday"),
    ("esteelauder","雅诗兰黛 EsteeLauder", "美国", "美妆", "Workday"),
    ("shiseido", "资生堂 Shiseido", "日本", "美妆", "自建"),
    ("johnson",  "强生 Johnson&Johnson", "美国", "医药/快消", "Workday"),
    ("kraftheinz","卡夫亨氏 KraftHeinz", "美国", "快消", "Workday"),
    ("abinbev",  "百威英博 ABInBev", "比利时", "饮料", "Workday"),
    ("diageo",   "帝亚吉欧 Diageo", "英国", "酒类", "Workday"),
    ("pernod",   "保乐力加 PernodRicard", "法国", "酒类", "Workday"),
    ("lvmh",     "路威酩轩 LVMH", "法国", "奢侈品", "TalentBrew"),
    ("nike",     "耐克 Nike", "美国", "零售/服饰", "Workday"),
    ("adidas",   "阿迪达斯 Adidas", "德国", "零售/服饰", "Workday"),
    ("ikea",     "宜家 IKEA", "瑞典", "零售", "Workday"),
    ("walmart",  "沃尔玛 Walmart", "美国", "零售", "自建/Taleo"),
    ("costco",   "开市客 Costco", "美国", "零售", "自建"),
    ("aldi",     "奥乐齐 Aldi", "德国", "零售", "自建"),
    ("carrefour","家乐福 Carrefour", "法国", "零售", "自建"),
    ("disney",   "迪士尼 Disney", "美国", "文娱", "Workday"),

    # ---- Tech ----
    ("microsoft","微软 Microsoft", "美国", "科技", "Workday"),
    ("google",   "谷歌 Google/Alphabet", "美国", "科技", "Greenhouse/自建"),
    ("amazon",   "亚马逊 Amazon", "美国", "科技/电商", "自建"),
    ("apple",    "苹果 Apple", "美国", "科技", "自建"),
    ("meta",     "Meta", "美国", "科技", "Greenhouse/自建"),
    ("nvidia",   "英伟达 NVIDIA", "美国", "科技/芯片", "Greenhouse"),
    ("intel",    "英特尔 Intel", "美国", "科技/芯片", "Workday"),
    ("amd",      "AMD", "美国", "科技/芯片", "Greenhouse"),
    ("cisco",    "思科 Cisco", "美国", "科技/网络", "Workday"),
    ("ibm",      "IBM", "美国", "科技/IT", "Workday"),
    ("oracle",   "Oracle", "美国", "科技/软件", "Taleo"),
    ("sap",      "SAP", "德国", "科技/软件", "SuccessFactors"),
    ("salesforce","Salesforce", "美国", "科技/软件", "Workday"),
    ("adobe",    "Adobe", "美国", "科技/软件", "Greenhouse"),
    ("qualcomm", "高通 Qualcomm", "美国", "科技/芯片", "自建"),
    ("ti",       "德州仪器 TexasInstruments", "美国", "科技/半导体", "自建"),

    # ---- Auto ----
    ("toyota",   "丰田 Toyota", "日本", "汽车", "自建"),
    ("vw",       "大众 Volkswagen", "德国", "汽车", "自建/SuccessFactors"),
    ("bmw",      "宝马 BMW", "德国", "汽车", "Workday"),
    ("mercedes", "奔驰 Mercedes-Benz", "德国", "汽车", "Workday"),
    ("tesla",    "特斯拉 Tesla", "美国", "汽车", "自建"),
    ("gm",       "通用汽车 GM", "美国", "汽车", "自建"),
    ("ford",     "福特 Ford", "美国", "汽车", "自建"),
    ("honda",    "本田 Honda", "日本", "汽车", "自建"),
    ("nissan",   "日产 Nissan", "日本", "汽车", "自建"),
    ("hyundai",  "现代 Hyundai", "韩国", "汽车", "自建"),
    ("stellantis","Stellantis", "荷兰", "汽车", "Workday"),

    # ---- Pharma ----
    ("pfizer",   "辉瑞 Pfizer", "美国", "医药", "Workday"),
    ("roche",    "罗氏 Roche", "瑞士", "医药", "自建"),
    ("novartis", "诺华 Novartis", "瑞士", "医药", "SuccessFactors"),
    ("merck",    "默沙东 MSD", "美国", "医药", "自建"),
    ("gsk",      "葛兰素史克 GSK", "英国", "医药", "Workday"),
    ("sanofi",   "赛诺菲 Sanofi", "法国", "医药", "Workday"),
    ("bayer",    "拜耳 Bayer", "德国", "医药/化工", "Workday"),
    ("takeda",   "武田 Takeda", "日本", "医药", "Workday"),
    ("boehringer","勃林格殷格翰 BI", "德国", "医药", "自建"),
    ("lilly",    "礼来 EliLilly", "美国", "医药", "自建"),
    ("abbvie",   "艾伯维 AbbVie", "美国", "医药", "Workday"),

    # ---- Finance ----
    ("jpmorgan", "摩根大通 JPMorgan", "美国", "金融", "自建"),
    ("hsbc",     "汇丰 HSBC", "英国", "金融", "自建"),
    ("citi",     "花旗 Citi", "美国", "金融", "自建"),
    ("goldmansachs","高盛 GoldmanSachs", "美国", "金融", "自建"),
    ("morganstanley","摩根士丹利 MorganStanley", "美国", "金融", "自建"),
    ("ubs",      "瑞银 UBS", "瑞士", "金融", "自建"),
    ("allianz",  "安联 Allianz", "德国", "金融/保险", "自建"),
    ("aig",      "AIG", "美国", "金融/保险", "自建"),
    ("bnp",      "巴黎银行 BNPParibas", "法国", "金融", "自建"),
    ("db",       "德意志银行 DeutscheBank", "德国", "金融", "自建"),
    ("sc",       "渣打 StandardChartered", "英国", "金融", "自建"),
    ("pingan",   "", None, None, None),  # placeholder removed below

    # ---- Consulting / prof services ----
    ("mckinsey", "麦肯锡 McKinsey", "美国", "咨询", "自建"),
    ("bcg",      "波士顿咨询 BCG", "美国", "咨询", "自建"),
    ("bain",     "贝恩 Bain", "美国", "咨询", "自建"),
    ("deloitte", "德勤 Deloitte", "英国", "咨询/审计", "自建/MokaHR"),
    ("pwc",      "普华永道 PwC", "英国", "咨询/审计", "自建/MokaHR"),
    ("ey",       "安永 EY", "英国", "咨询/审计", "自建/MokaHR"),
    ("kpmg",     "毕马威 KPMG", "荷兰", "咨询/审计", "自建/MokaHR"),

    # ---- Industrial / Energy / Materials ----
    ("siemens",  "西门子 Siemens", "德国", "工业/能源", "SuccessFactors"),
    ("abb",      "ABB", "瑞士", "工业/电气", "SuccessFactors"),
    ("honeywell","霍尼韦尔 Honeywell", "美国", "工业", "Workday"),
    ("mmm",      "3M", "美国", "工业/材料", "Workday"),
    ("ge",       "通用电气 GE", "美国", "工业/能源", "Workday"),
    ("shell",    "壳牌 Shell", "英国/荷兰", "能源", "SuccessFactors"),
    ("bp",       "BP", "英国", "能源", "自建"),
    ("total",    "道达尔 TotalEnergies", "法国", "能源", "自建"),
    ("caterpillar","卡特彼勒 Caterpillar", "美国", "工业/机械", "自建"),
    ("airliquide","液化空气 AirLiquide", "法国", "工业/化工", "自建"),
    ("basf",     "巴斯夫 BASF", "德国", "化工", "自建"),

    # ---- Logistics ----
    ("dhl",      "DHL/德国邮政", "德国", "物流", "SuccessFactors"),
    ("fedex",    "联邦快递 FedEx", "美国", "物流", "Workday"),
    ("ups",      "UPS", "美国", "物流", "自建"),
]

# remove placeholder
candidates = [c for c in candidates if c[0] != "pingan"]

rows = []
# prior done first
for slug, (name, country, industry, platform, status, note) in prior.items():
    rows.append({
        "slug": slug, "cn_name": name, "country": country, "industry": industry,
        "platform_hint": platform, "investigation_status": status,
        "prior_note": note, "china_campus_status": None,
        "job_count": None, "has_queryable_jobs": None,
        "entry_url": None, "sample_jobs": [], "blocker_reason": None,
    })
# new candidates
for slug, name, country, industry, platform in candidates:
    rows.append({
        "slug": slug, "cn_name": name, "country": country, "industry": industry,
        "platform_hint": platform, "investigation_status": "未开始",
        "prior_note": "", "china_campus_status": None,
        "job_count": None, "has_queryable_jobs": None,
        "entry_url": None, "sample_jobs": [], "blocker_reason": None,
    })

print("total companies:", len(rows))
assert len(rows) == 100, len(rows)

with open(os.path.join(OUT, "foreign_companies.jsonl"), "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("wrote foreign_companies.jsonl with", len(rows), "rows")
