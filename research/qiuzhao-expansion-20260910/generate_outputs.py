#!/usr/bin/env python3
"""Generate ranking_memberships.jsonl, companies.jsonl, and evidence files."""
import json
from datetime import datetime, timezone, timedelta

OUT = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-expansion-20260910"
RETRIEVED_AT = "2026-09-10T11:20:00+08:00"
CST = timezone(timedelta(hours=8))

# ============================================================
# RANKING DATA
# ============================================================

# Fortune Global 500 2026 - ranks 1-100 (partial)
fortune_global = [
    (1, "亚马逊", "AMAZON.COM"), (2, "沃尔玛", "WALMART"),
    (3, "国家电网有限公司", "STATE GRID"), (4, "联合健康集团", "UNITEDHEALTH GROUP"),
    (5, "沙特阿美公司", "SAUDI ARAMCO"), (6, "苹果公司", "APPLE"),
    (7, "麦克森公司", "MCKESSON"), (8, "Alphabet公司", "ALPHABET"),
    (9, "CVS Health公司", "CVS HEALTH"), (10, "中国石油天然气集团有限公司", "CHINA NATIONAL PETROLEUM"),
    (11, "伯克希尔－哈撒韦公司", "BERKSHIRE HATHAWAY"), (12, "中国石油化工集团有限公司", "SINOPEC GROUP"),
    (13, "大众公司", "VOLKSWAGEN"), (14, "丰田汽车公司", "TOYOTA MOTOR"),
    (15, "埃克森美孚", "EXXON MOBIL"), (16, "Cencora公司", "CENCORA"),
    (17, "中国建筑集团有限公司", "CHINA STATE CONSTRUCTION ENGINEERING"), (18, "微软", "MICROSOFT"),
    (19, "摩根大通公司", "JPMORGAN CHASE"), (20, "开市客", "COSTCO WHOLESALE"),
    (21, "信诺集团", "CIGNA GROUP"), (22, "壳牌公司", "SHELL"),
    (23, "鸿海精密工业股份有限公司", "HON HAI PRECISION INDUSTRY"), (24, "嘉能可", "GLENCORE"),
    (25, "托克集团", "TRAFIGURA GROUP"), (26, "三星电子", "SAMSUNG ELECTRONICS"),
    (27, "嘉德诺健康集团", "CARDINAL HEALTH"), (28, "英伟达公司", "NVIDIA"),
    (29, "中国工商银行股份有限公司", "INDUSTRIAL & COMMERCIAL BANK OF CHINA"),
    (30, "Meta Platforms公司", "META PLATFORMS"), (31, "Elevance Health公司", "ELEVANCE HEALTH"),
    (32, "Centene公司", "CENTENE"), (33, "英国石油公司", "BP"),
    (34, "美国银行", "BANK OF AMERICA"), (35, "中国农业银行股份有限公司", "AGRICULTURAL BANK OF CHINA"),
    (36, "雪佛龙", "CHEVRON"), (37, "中国建设银行股份有限公司", "CHINA CONSTRUCTION BANK"),
    (38, "福特汽车公司", "FORD MOTOR"), (39, "通用汽车公司", "GENERAL MOTORS"),
    (40, "道达尔能源公司", "TOTALENERGIES"), (41, "京东集团股份有限公司", "JD.COM"),
    (42, "中国人寿保险（集团）公司", "CHINA LIFE INSURANCE"), (43, "Stellantis集团", "STELLANTIS"),
    (44, "中国银行股份有限公司", "BANK OF CHINA"), (45, "花旗集团", "CITIGROUP"),
    (46, "家得宝", "HOME DEPOT"), (47, "房利美", "FANNIE MAE"),
    (48, "中国平安保险（集团）股份有限公司", "PING AN INSURANCE"),
    (49, "中国铁路工程集团有限公司", "CHINA RAILWAY ENGINEERING GROUP"), (50, "宝马集团", "BMW GROUP"),
    (51, "梅赛德斯-奔驰集团", "MERCEDES-BENZ GROUP"), (52, "克罗格", "KROGER"),
    (53, "中国移动通信集团有限公司", "CHINA MOBILE COMMUNICATIONS"), (54, "西班牙国家银行", "BANCO SANTANDER"),
    (55, "本田汽车", "HONDA MOTOR"), (56, "阿里巴巴集团控股有限公司", "ALIBABA GROUP HOLDING"),
    (57, "中国铁道建筑集团有限公司", "CHINA RAILWAY CONSTRUCTION"), (58, "法国巴黎银行", "BNP PARIBAS"),
    (59, "中国中信集团有限公司", "CITIC GROUP"), (60, "威瑞森电信", "VERIZON COMMUNICATIONS"),
    (61, "Phillips 66公司", "PHILLIPS 66"), (62, "汇丰银行控股公司", "HSBC HOLDINGS"),
    (63, "马拉松原油公司", "MARATHON PETROLEUM"), (64, "俄罗斯联邦储蓄银行", "SBERBANK"),
    (65, "德国电信", "DEUTSCHE TELEKOM"), (66, "中国交通建设集团有限公司", "CHINA COMMUNICATIONS CONSTRUCTION"),
    (67, "安联保险集团", "ALLIANZ"), (68, "中国华润有限公司", "CHINA RESOURCES"),
    (69, "StoneX集团", "STONEX GROUP"), (70, "州立农业保险公司", "STATE FARM INSURANCE"),
    (71, "房地美", "FREDDIE MAC"), (72, "现代汽车", "HYUNDAI MOTOR"),
    (73, "哈门那公司", "HUMANA"), (74, "法国电力公司", "ELECTRICITE DE FRANCE"),
    (75, "美国电话电报公司", "AT&T"), (76, "三菱商事株式会社", "MITSUBISHI"),
    (77, "高盛集团", "GOLDMAN SACHS GROUP"), (78, "恒力集团有限公司", "HENGLI GROUP"),
    (79, "美国康卡斯特电信公司", "COMCAST"), (80, "美国富国银行", "WELLS FARGO"),
    (81, "华为投资控股有限公司", "HUAWEI INVESTMENT & HOLDING"),
    (82, "台积公司", "TAIWAN SEMICONDUCTOR MANUFACTURING"),
    (83, "中国海洋石油集团有限公司", "CHINA NATIONAL OFFSHORE OIL"),
    (84, "摩根士丹利", "MORGAN STANLEY"), (85, "信实工业公司", "RELIANCE INDUSTRIES"),
    (86, "中国南方电网有限责任公司", "CHINA SOUTHERN POWER GRID"),
    (87, "山东能源集团有限公司", "SHANDONG ENERGY GROUP"), (88, "瓦莱罗能源公司", "VALERO ENERGY"),
    (89, "俄罗斯天然气工业股份公司", "GAZPROM"), (90, "戴尔科技公司", "DELL TECHNOLOGIES"),
    (91, "比亚迪股份有限公司", "BYD"), (92, "印度人寿保险公司", "LIFE INSURANCE CORP. OF INDIA"),
    (93, "雀巢公司", "NESTLE"), (94, "安盛", "AXA"), (95, "Equinor公司", "EQUINOR"),
    (96, "塔吉特公司", "TARGET"), (97, "腾讯控股有限公司", "TENCENT HOLDINGS"),
    (98, "皇家阿霍德德尔海兹集团", "ROYAL AHOLD DELHAIZE"),
    (99, "中国五矿集团有限公司", "CHINA MINMETALS"),
    (100, "中国宝武钢铁集团有限公司", "CHINA BAOWU STEEL GROUP"),
]

# Fortune China 500 2026 - ranks 1-35 (partial)
fortune_china = [
    (1, "国家电网有限公司"), (2, "中国石油天然气集团有限公司"),
    (3, "中国石油化工集团有限公司"), (4, "中国建筑集团有限公司"),
    (5, "鸿海精密工业股份有限公司"), (6, "中国工商银行股份有限公司"),
    (7, "中国农业银行股份有限公司"), (8, "中国建设银行股份有限公司"),
    (9, "京东集团股份有限公司"), (10, "中国人寿保险（集团）公司"),
    (11, "中国银行股份有限公司"), (12, "中国平安保险（集团）股份有限公司"),
    (13, "中国铁路工程集团有限公司"), (14, "中国移动通信集团有限公司"),
    (15, "阿里巴巴集团控股有限公司"), (16, "中国铁道建筑集团有限公司"),
    (17, "中国中信集团有限公司"), (18, "中国交通建设集团有限公司"),
    (19, "中国华润有限公司"), (20, "恒力集团有限公司"),
    (21, "华为投资控股有限公司"), (22, "台积公司"),
    (23, "中国海洋石油集团有限公司"), (24, "中国南方电网有限责任公司"),
    (25, "山东能源集团有限公司"), (26, "比亚迪股份有限公司"),
    (27, "腾讯控股有限公司"), (28, "中国五矿集团有限公司"),
    (29, "中国宝武钢铁集团有限公司"), (30, "中国电力建设集团有限公司"),
    (31, "国家能源投资集团有限责任公司"), (32, "厦门建发集团有限公司"),
    (33, "浙江荣盛控股集团有限公司"), (34, "中国邮政集团有限公司"),
    (35, "中国人民保险集团股份有限公司"),
]

# Forbes World's Best Employers 2025 - ranks 1-100 (partial, from Chinese repost)
forbes_employers = [
    (1, "微软"), (2, "达美航空"), (3, "Alphabet"), (4, "Adobe"),
    (5, "宝马集团"), (6, "英伟达"), (7, "索尼"), (8, "IBM"),
    (9, "苹果"), (10, "乐高集团"), (11, "三星电子"), (12, "好市多"),
    (13, "思科系统"), (14, "Shopify"), (15, "劳力士"), (16, "万豪国际"),
    (17, "耐克"), (18, "HubSpot"), (19, "空中客车"), (20, "任天堂"),
    (21, "希尔顿"), (22, "Salesforce"), (23, "富达投资"), (24, "博世"),
    (25, "罗技"), (26, "沃尔沃集团"), (27, "摩根大通"), (28, "标准银行集团"),
    (29, "罗氏"), (30, "凯悦酒店"), (31, "美国运通"), (32, "英特尔"),
    (33, "宜家"), (34, "戴尔科技"), (35, "香奈儿"), (36, "勃林格殷格翰"),
    (37, "罗尔斯·罗伊斯控股"), (38, "洛克希德·马丁"), (39, "阿迪达斯"),
    (40, "大众集团"), (41, "西门子"), (42, "圣米格尔"), (43, "Spotify"),
    (44, "欧莱雅"), (45, "SAP"), (46, "丰田集团"), (47, "辉瑞"),
    (48, "梅赛德斯-奔驰集团"), (49, "南非第一国民银行"), (50, "迅达"),
    (51, "萨班奇控股"), (52, "喜力"), (53, "诺华"), (54, "马来西亚国家石油化学"),
    (55, "露华浓"), (56, "四季酒店及度假村"), (57, "礼来"), (58, "Rossmann"),
    (59, "亚马逊"), (60, "PayPal"), (61, "诺斯罗普·格鲁曼"), (62, "强生"),
    (63, "彪马"), (64, "普拉达"), (65, "沙特阿美"), (66, "默克"),
    (67, "诺和诺德"), (68, "意大利国家电力公司 Enel"), (69, "五十铃汽车"),
    (70, "巴斯夫"), (71, "宝洁"), (72, "大阪煤气"), (73, "LVMH"),
    (74, "松下"), (75, "竹中工务店"), (76, "东京海上控股"), (77, "本田汽车"),
    (78, "网飞"), (79, "米其林集团"), (80, "施耐德电气"), (81, "甲骨文"),
    (82, "Ace Hardware"), (83, "雅马哈"), (84, "法航-荷航集团"),
    (85, "卡特彼勒"), (86, "百加得"), (87, "山特维克"), (88, "资生堂"),
    (89, "微芯科技"), (90, "万事达卡"), (91, "波士顿科学"), (92, "Expedia 集团"),
    (93, "Visa"), (94, "沙特基础工业公司 SABIC"), (95, "康迪泰克汽车系统"),
    (96, "佳明"), (97, "阿巴萨集团"), (98, "日本烟草"), (99, "国家电网公司"),
    (100, "ABB"),
]

# GPTW World's Best Workplaces 2025 - complete 25
gptw_workplaces = [
    (1, "Hilton", "McLean, Virginia, United States", "Hospitality"),
    (2, "DHL Express", "Bonn, Bonn, Germany", "Transportation"),
    (3, "Cisco", "San Jose, California, United States", "Information Technology"),
    (4, "Accenture", "Dublin, Ireland", "Professional Services"),
    (5, "Marriott International", "Bethesda, Maryland, United States", "Hospitality"),
    (6, "AbbVie", "North Chicago, Illinois, United States", "Biotechnology & Pharmaceuticals"),
    (7, "TP", "Paris, Ile de france, France", "Professional Services"),
    (8, "Stryker", "Portage, Michigan, United States", "Manufacturing & Production"),
    (9, "Salesforce", "San Francisco, California, United States", "Information Technology"),
    (10, "MetLife", "New York City, United States", "Financial Services & Insurance"),
    (11, "ServiceNow", "Santa Clara, California, United States", "Information Technology"),
    (12, "Specsavers", "Whiteley, Hampshire, United Kingdom", "Retail"),
    (13, "Siemens Healthineers", "Erlangen, Bayern, Germany", "Health Care"),
    (14, "Experian", "Dublin, Ireland", "Information Technology"),
    (15, "Nvidia", "Santa Clara, California, United States", "Information Technology"),
    (16, "Cadence", "San Jose, CA, United States", "Information Technology"),
    (17, "Allianz", "Munich, Bavaria, Germany", "Financial Services & Insurance"),
    (18, "Dow", "Midland, MI, United States", "Manufacturing & Production"),
    (19, "Viatris", "Canonsburg, Pennsylvania, United States", "Biotechnology & Pharmaceuticals"),
    (20, "Adobe", "San Jose, California, USA", "Information Technology"),
    (21, "CrowdStrike", "Austin, Texas, United States", "Information Technology"),
    (22, "SC Johnson", "Racine, Wisconsin, United States of America", "Manufacturing & Production"),
    (23, "Trek Bicycle", "Waterloo, Wisconsin, United States", "Retail"),
    (24, "Hilti", "Schaan, Liechtenstein", "Construction & Infrastructure"),
    (25, "Admiral Group", "Cardiff, Wales,United Kingdom", "Financial Services & Insurance"),
]

# ============================================================
# LIST METADATA
# ============================================================
lists_meta = {
    "fortune_global_500_2026": {
        "list_name": "财富世界500强 2026",
        "publisher": "Fortune / 财富中文网",
        "year": 2026,
        "publish_date": "2026-07-28",
        "publisher_total_entries": 500,
        "actually_retrieved_entries": 100,
        "list_completeness": "partial",
        "retrieval_method": "web.fetch 直接抓取财富中文网榜单页（第1页，排名1-100）；分页URL(_2.htm)返回link dead，剩余400条未获取",
        "blocker_reason": "榜单分页为JavaScript/AJAX渲染，简单URL分页不可用；未使用浏览器渲染获取剩余页",
        "evidence_url": "https://www.fortunechina.com/fortune500/c/2026-07/28/content_475298.htm",
    },
    "fortune_china_500_2026": {
        "list_name": "财富中国500强 2026",
        "publisher": "Fortune / 财富中文网",
        "year": 2026,
        "publish_date": "2026-07-21",
        "publisher_total_entries": 500,
        "actually_retrieved_entries": 35,
        "list_completeness": "partial",
        "retrieval_method": "web.fetch 直接抓取财富中文网榜单页（默认每页35条，第1页，排名1-35）；分页URL(_2.htm)返回link dead",
        "blocker_reason": "榜单分页为JavaScript/AJAX渲染，每页可切换至150条或All但需JS交互；简单URL分页不可用",
        "evidence_url": "https://www.fortunechina.com/fortune500/c/2026-07/21/content_475181.htm",
    },
    "forbes_best_employers_2025": {
        "list_name": "Forbes World's Best Employers 2025",
        "publisher": "Forbes / Statista",
        "year": 2025,
        "publish_date": "2025-10-08",
        "publisher_total_entries": 900,
        "actually_retrieved_entries": 100,
        "list_completeness": "partial",
        "retrieval_method": "forbes.com原站web.fetch返回'site not supported for access'；通过中文转载文章(10100.com)获取前100名表格；Forbes Europe文章仅含方法论和个别排名引用",
        "blocker_reason": "forbes.com原站反爬/不支持直接抓取；完整900家名单需浏览器渲染或付费墙；转载来源仅含前100名",
        "evidence_url": "https://www.forbes.com/lists/worlds-best-employers/",
    },
    "gptw_best_workplaces_2025": {
        "list_name": "Fortune/Great Place To Work World's Best Workplaces 2025",
        "publisher": "Great Place To Work / Fortune",
        "year": 2025,
        "publish_date": "2025",
        "publisher_total_entries": 25,
        "actually_retrieved_entries": 25,
        "list_completeness": "complete",
        "retrieval_method": "web.fetch 直接抓取greatplacetowork.com榜单页，完整25家表格（含排名、公司名、地点、行业）",
        "blocker_reason": None,
        "evidence_url": "https://www.greatplacetowork.com/worlds-best-workplaces",
    },
}

# ============================================================
# 80 SEED COMPANIES (8 groups x 10)
# ============================================================
# Format: (slug, canonical_name, aliases, industry_tags, employer_type, homepage)
seeds = [
    # Group 1: 互联网/内容
    ("tencent_holdings", "腾讯控股有限公司", ["腾讯", "Tencent", "Tencent Holdings"], ["互联网", "内容", "社交", "游戏"], "民营", "https://www.tencent.com"),
    ("bytedance", "字节跳动有限公司", ["字节跳动", "ByteDance", "抖音"], ["互联网", "内容", "短视频", "AI"], "民营", "https://www.bytedance.com"),
    ("alibaba_group", "阿里巴巴集团控股有限公司", ["阿里巴巴", "Alibaba", "阿里"], ["互联网", "电商", "云计算"], "民营", "https://www.alibabagroup.com"),
    ("jd_com", "京东集团股份有限公司", ["京东", "JD.com", "JD"], ["互联网", "电商", "物流"], "民营", "https://www.jd.com"),
    ("meituan", "美团", ["美团", "Meituan", "大众点评"], ["互联网", "本地生活", "外卖"], "民营", "https://www.meituan.com"),
    ("baidu", "百度", ["百度", "Baidu"], ["互联网", "搜索", "AI", "自动驾驶"], "民营", "https://www.baidu.com"),
    ("netease", "网易", ["网易", "NetEase"], ["互联网", "游戏", "音乐", "教育"], "民营", "https://www.163.com"),
    ("kuaishou", "快手", ["快手", "Kuaishou"], ["互联网", "短视频", "直播"], "民营", "https://www.kuaishou.com"),
    ("xiaohongshu", "小红书", ["小红书", "Xiaohongshu", "RED"], ["互联网", "内容", "社交电商"], "民营", "https://www.xiaohongshu.com"),
    ("bilibili", "哔哩哔哩", ["哔哩哔哩", "B站", "Bilibili"], ["互联网", "内容", "视频", "游戏"], "民营", "https://www.bilibili.com"),
    # Group 2: 电子/半导体/硬件
    ("huawei", "华为投资控股有限公司", ["华为", "Huawei"], ["电子", "通信设备", "半导体", "手机", "云计算"], "民营", "https://www.huawei.com"),
    ("zte", "中兴通讯股份有限公司", ["中兴通讯", "ZTE", "中兴"], ["电子", "通信设备"], "国企", "https://www.zte.com.cn"),
    ("xiaomi", "小米集团", ["小米", "Xiaomi", "红米"], ["电子", "手机", "IoT", "智能硬件"], "民营", "https://www.mi.com"),
    ("oppo", "OPPO", ["OPPO", "欧加", "一加"], ["电子", "手机", "智能硬件"], "民营", "https://www.oppo.com"),
    ("vivo", "vivo", ["vivo", "维沃", "iQOO"], ["电子", "手机", "智能硬件"], "民营", "https://www.vivo.com"),
    ("dji", "大疆创新科技有限公司", ["大疆", "DJI"], ["电子", "无人机", "智能硬件", "影像"], "民营", "https://www.dji.com"),
    ("hikvision", "杭州海康威视数字技术股份有限公司", ["海康威视", "Hikvision"], ["电子", "安防", "视频监控", "AI"], "国企", "https://www.hikvision.com"),
    ("lenovo", "联想集团有限公司", ["联想", "Lenovo"], ["电子", "PC", "服务器", "智能硬件"], "民营", "https://www.lenovo.com"),
    ("smic", "中芯国际集成电路制造有限公司", ["中芯国际", "SMIC"], ["电子", "半导体", "晶圆制造"], "国企", "https://www.smics.com"),
    ("gigadevice", "兆易创新科技集团股份有限公司", ["兆易创新", "GigaDevice"], ["电子", "半导体", "存储", "MCU"], "民营", "https://www.gigadevice.com"),
    # Group 3: 药企/研发服务
    ("hengrui_medicine", "江苏恒瑞医药股份有限公司", ["恒瑞医药", "Hengrui"], ["药企", "创新药", "研发"], "民营", "https://www.hengrui.com"),
    ("cspc", "石药控股集团有限公司", ["石药集团", "CSPC", "石药"], ["药企", "创新药", "制剂"], "民营", "https://www.cspc.com.cn"),
    ("qilu_pharma", "齐鲁制药集团有限公司", ["齐鲁制药", "Qilu Pharma"], ["药企", "仿制药", "生物药"], "民营", "https://www.qilu-pharma.com"),
    ("chia_tai_tianqing", "正大天晴药业集团股份有限公司", ["正大天晴", "Chia Tai Tianqing", "天晴"], ["药企", "创新药", "肝病"], "合资", "https://www.cttq.com"),
    ("wuxi_apptec", "无锡药明康德新药开发股份有限公司", ["药明康德", "WuXi AppTec"], ["药企", "CRO", "研发服务", "CDMO"], "民营", "https://www.wuxiapptec.com"),
    ("wuxi_biologics", "药明生物技术有限公司", ["药明生物", "WuXi Biologics"], ["药企", "CDMO", "生物药"], "民营", "https://www.wuxibiologics.com"),
    ("pharmaron", "康龙化成（北京）新药技术股份有限公司", ["康龙化成", "Pharmaron"], ["药企", "CRO", "研发服务"], "民营", "https://www.pharmaron.com"),
    ("asymchem", "凯莱英医药集团（天津）股份有限公司", ["凯莱英", "Asymchem"], ["药企", "CDMO", "小分子"], "民营", "https://www.asymchem.com"),
    ("tigermed", "杭州泰格医药科技股份有限公司", ["泰格医药", "Tigermed"], ["药企", "CRO", "临床研究"], "民营", "https://www.tigermedgrp.com"),
    ("innovent_biologics", "信达生物制药（苏州）有限公司", ["信达生物", "Innovent", "信达"], ["药企", "生物药", "创新药", "PD-1"], "民营", "https://www.innoventbio.com"),
    # Group 4: 医疗/生命科学补充
    ("mindray", "深圳迈瑞生物医疗电子股份有限公司", ["迈瑞医疗", "Mindray", "迈瑞"], ["医疗", "医疗器械", "生命科学"], "民营", "https://www.mindray.com"),
    ("united_imaging", "上海联影医疗科技股份有限公司", ["联影医疗", "United Imaging", "联影"], ["医疗", "医疗器械", "影像设备"], "民营", "https://www.united-imaging.com"),
    ("vazyme", "南京诺唯赞生物科技股份有限公司", ["诺唯赞", "Vazyme"], ["医疗", "生命科学", "分子生物学试剂", "IVD"], "民营", "https://www.vazyme.com"),
    ("sinobiological", "北京义翘神州科技股份有限公司", ["义翘神州", "Sino Biological", "义翘"], ["医疗", "生命科学", "重组蛋白", "抗体"], "民营", "https://www.sinobiological.com"),
    ("acrobiosystems", "北京百普赛斯生物科技股份有限公司", ["百普赛斯", "ACROBiosystems", "百普"], ["医疗", "生命科学", "重组蛋白", "抗体"], "民营", "https://www.acrobiosystems.com"),
    ("opm_biosciences", "上海奥浦迈生物科技股份有限公司", ["奥浦迈", "OPM Biosciences"], ["医疗", "生命科学", "细胞培养基", "CDMO"], "民营", "https://www.opmbiosciences.com"),
    ("genscript", "金斯瑞生物科技股份有限公司", ["金斯瑞", "GenScript", "传奇生物"], ["医疗", "生命科学", "基因合成", "CRO"], "民营", "https://www.genscript.com"),
    ("mgitech", "深圳华大智造科技股份有限公司", ["华大智造", "MGI", "华大"], ["医疗", "生命科学", "基因测序仪", "IVD"], "民营", "https://www.mgi-tech.com"),
    ("maccura", "迈克生物股份有限公司", ["迈克生物", "Maccura"], ["医疗", "IVD", "体外诊断"], "民营", "https://www.maccura.com"),
    ("joinn_labs", "北京昭衍新药研究中心股份有限公司", ["昭衍新药", "Joinn Labs", "昭衍"], ["医疗", "CRO", "药物评价", "非临床研究"], "民营", "https://www.joinn.com"),
    # Group 5: 制造/工业自动化
    ("midea", "美的集团股份有限公司", ["美的", "Midea", "美的集团"], ["制造", "家电", "工业自动化", "机器人"], "民营", "https://www.midea.com"),
    ("haier", "海尔智家股份有限公司", ["海尔", "Haier", "海尔智家"], ["制造", "家电", "智能家居"], "民营", "https://www.haier.com"),
    ("gree", "珠海格力电器股份有限公司", ["格力", "Gree", "格力电器"], ["制造", "家电", "空调"], "民营", "https://www.gree.com"),
    ("sany", "三一重工股份有限公司", ["三一重工", "SANY", "三一"], ["制造", "工程机械", "工业自动化"], "民营", "https://www.sany.com.cn"),
    ("inovance", "深圳市汇川技术股份有限公司", ["汇川技术", "Inovance", "汇川"], ["制造", "工业自动化", "伺服", "变频器", "新能源汽车"], "民营", "https://www.inovance.com"),
    ("estun", "南京埃斯顿自动化股份有限公司", ["埃斯顿", "Estun"], ["制造", "工业自动化", "工业机器人", "伺服"], "民营", "https://www.estun.com"),
    ("friendess", "上海柏楚电子科技股份有限公司", ["柏楚电子", "Friendess", "柏楚"], ["制造", "工业自动化", "激光切割控制系统", "数控"], "民营", "https://www.friendess.com"),
    ("zhaowei", "深圳市兆威机电股份有限公司", ["兆威机电", "Zhaowei", "兆威"], ["制造", "工业自动化", "微型传动系统", "精密零部件"], "民营", "https://www.zhaowei.com"),
    ("leaderdrive", "苏州绿的谐波传动科技股份有限公司", ["绿的谐波", "Leaderdrive", "绿的"], ["制造", "工业自动化", "谐波减速器", "精密传动"], "民营", "https://www.leaderdrive.com"),
    ("topband", "深圳市拓邦股份有限公司", ["拓邦股份", "Topband", "拓邦"], ["制造", "工业自动化", "智能控制器", "新能源"], "民营", "https://www.topband.com"),
    # Group 6: 汽车/新能源/材料
    ("byd", "比亚迪股份有限公司", ["比亚迪", "BYD"], ["汽车", "新能源", "动力电池", "电子"], "民营", "https://www.byd.com"),
    ("catl", "宁德时代新能源科技股份有限公司", ["宁德时代", "CATL", "宁王"], ["汽车", "新能源", "动力电池", "储能"], "民营", "https://www.catl.com"),
    ("geely", "浙江吉利控股集团有限公司", ["吉利", "Geely", "吉利汽车"], ["汽车", "新能源", "整车制造"], "民营", "https://www.geely.com"),
    ("xpeng", "广州小鹏汽车科技有限公司", ["小鹏", "XPeng", "小鹏汽车"], ["汽车", "新能源", "智能电动车", "自动驾驶"], "民营", "https://www.xiaopeng.com"),
    ("li_auto", "北京车和家信息技术有限公司", ["理想", "Li Auto", "理想汽车"], ["汽车", "新能源", "智能电动车", "增程式"], "民营", "https://www.lixiang.com"),
    ("nio", "上海蔚来汽车有限公司", ["蔚来", "NIO", "蔚来汽车"], ["汽车", "新能源", "智能电动车", "换电"], "民营", "https://www.nio.com"),
    ("leapmotor", "浙江零跑科技股份有限公司", ["零跑", "Leapmotor", "零跑汽车"], ["汽车", "新能源", "智能电动车"], "民营", "https://www.leapmotor.com"),
    ("sungrow", "阳光电源股份有限公司", ["阳光电源", "Sungrow"], ["汽车", "新能源", "光伏逆变器", "储能"], "民营", "https://www.sungrowpower.com"),
    ("deye", "宁波德业科技股份有限公司", ["德业股份", "Deye", "德业"], ["汽车", "新能源", "逆变器", "储能"], "民营", "https://www.deye.com.cn"),
    ("whchem", "万华化学集团股份有限公司", ["万华化学", "Wanhua Chemical", "万华"], ["汽车", "新能源", "化工新材料", "MDI"], "民营", "https://www.whchem.com"),
    # Group 7: 消费/物流
    ("procter_gamble", "宝洁公司", ["宝洁", "Procter & Gamble", "P&G"], ["消费", "日化", "个护", "家清"], "外资", "https://www.pg.com"),
    ("unilever", "联合利华", ["联合利华", "Unilever"], ["消费", "日化", "食品", "个护"], "外资", "https://www.unilever.com"),
    ("loreal", "欧莱雅", ["欧莱雅", "L'Oréal", "Loreal"], ["消费", "美妆", "个护"], "外资", "https://www.loreal.com"),
    ("nestle", "雀巢公司", ["雀巢", "Nestlé", "Nestle"], ["消费", "食品饮料", "咖啡", "宠物食品"], "外资", "https://www.nestle.com"),
    ("yili", "内蒙古伊利实业集团股份有限公司", ["伊利", "Yili", "伊利集团"], ["消费", "食品饮料", "乳制品"], "民营", "https://www.yili.com"),
    ("anta", "安踏体育用品有限公司", ["安踏", "ANTA", "安踏体育", "始祖鸟", "FILA"], ["消费", "运动服饰", "鞋类"], "民营", "https://www.anta.com"),
    ("pop_mart", "泡泡玛特国际集团有限公司", ["泡泡玛特", "POP MART", "盲盒", "LABUBU"], ["消费", "潮玩", "IP运营"], "民营", "https://www.popmart.com"),
    ("sf_express", "顺丰控股股份有限公司", ["顺丰", "SF Express", "顺丰速运"], ["消费", "物流", "快递", "供应链"], "民营", "https://www.sf-express.com"),
    ("cainiao", "菜鸟网络科技有限公司", ["菜鸟", "Cainiao", "菜鸟物流"], ["消费", "物流", "供应链", "快递"], "民营", "https://www.cainiao.com"),
    ("dhl", "DHL", ["DHL", "敦豪", "DHL Express"], ["消费", "物流", "快递", "国际供应链"], "外资", "https://www.dhl.com"),
    # Group 8: 跨国企业补充
    ("astrazeneca", "阿斯利康", ["阿斯利康", "AstraZeneca"], ["药企", "创新药", "跨国药企"], "外资", "https://www.astrazeneca.com"),
    ("roche", "罗氏", ["罗氏", "Roche", "霍夫曼-拉罗奇"], ["药企", "诊断", "创新药", "跨国药企"], "外资", "https://www.roche.com"),
    ("pfizer", "辉瑞", ["辉瑞", "Pfizer"], ["药企", "创新药", "疫苗", "跨国药企"], "外资", "https://www.pfizer.com"),
    ("novartis", "诺华", ["诺华", "Novartis"], ["药企", "创新药", "跨国药企"], "外资", "https://www.novartis.com"),
    ("siemens", "西门子", ["西门子", "Siemens"], ["制造", "工业自动化", "医疗", "能源", "跨国企业"], "外资", "https://www.siemens.com"),
    ("schneider_electric", "施耐德电气", ["施耐德电气", "Schneider Electric", "施耐德"], ["制造", "工业自动化", "能源管理", "跨国企业"], "外资", "https://www.se.com"),
    ("bosch", "博世", ["博世", "Bosch", "罗伯特·博世"], ["制造", "汽车零部件", "工业自动化", "跨国企业"], "外资", "https://www.bosch.com"),
    ("amazon", "亚马逊", ["亚马逊", "Amazon", "AWS"], ["互联网", "电商", "云计算", "跨国企业"], "外资", "https://www.amazon.com"),
    ("accenture", "埃森哲", ["埃森哲", "Accenture"], ["咨询", "IT服务", "数字化转型", "跨国企业"], "外资", "https://www.accenture.com"),
    ("hilton", "希尔顿", ["希尔顿", "Hilton", "希尔顿酒店"], ["消费", "酒店", "旅游休闲", "跨国企业"], "外资", "https://www.hilton.com"),
]

# 24 fixed exploration companies (by slug)
fixed_assigned = {
    "tencent_holdings", "bytedance", "alibaba_group", "jd_com", "meituan", "netease",
    "hengrui_medicine", "mindray", "pharmaron", "vazyme", "sinobiological", "astrazeneca",
    "midea", "byd", "catl", "inovance", "friendess", "zhaowei",
    "procter_gamble", "unilever", "loreal", "bosch", "schneider_electric", "accenture",
}

# ============================================================
# NAME MAPPING: ranking names -> seed slugs (for deduplication)
# ============================================================
# Maps various ranking entity names to seed company slugs
name_to_slug = {}
for slug, cname, aliases, tags, etype, hp in seeds:
    name_to_slug[cname] = slug
    for a in aliases:
        name_to_slug[a] = slug

# Additional explicit mappings for ranking names
rank_name_overrides = {
    # Fortune global
    "腾讯控股有限公司": "tencent_holdings",
    "阿里巴巴集团控股有限公司": "alibaba_group",
    "京东集团股份有限公司": "jd_com",
    "华为投资控股有限公司": "huawei",
    "比亚迪股份有限公司": "byd",
    "雀巢公司": "nestle",
    "中国移动通信集团有限公司": None,  # not in seeds, will be new
    "中国建设银行股份有限公司": None,
    "中国银行股份有限公司": None,
    "国家电网有限公司": None,
    "鸿海精密工业股份有限公司": None,
    "台积公司": None,
    "中国平安保险（集团）股份有限公司": None,
    "微软": None,
    "苹果公司": None,
    "Alphabet公司": None,
    "英伟达公司": None,
    "三星电子": None,
    "宝马集团": None,
    # Forbes
    "微软": None, "Alphabet": None, "Adobe": None, "英伟达": None,
    "苹果": None, "三星电子": None, "思科系统": None, "希尔顿": "hilton",
    "博世": "bosch", "西门子": "siemens", "欧莱雅": "loreal", "诺华": "novartis",
    "辉瑞": "pfizer", "亚马逊": "amazon", "宝洁": "procter_gamble",
    "施耐德电气": "schneider_electric", "宝马集团": None, "大众集团": None,
    "罗氏": "roche", "梅赛德斯-奔驰集团": None, "英特尔": None, "戴尔科技": None,
    "耐克": None, "阿迪达斯": None, "彪马": None, "LVMH": None,
    "万豪国际": None, "Salesforce": None, "IBM": None, "索尼": None,
    "乐高集团": None, "好市多": None, "Shopify": None, "劳力士": None,
    "HubSpot": None, "空中客车": None, "任天堂": None, "富达投资": None,
    "罗技": None, "沃尔沃集团": None, "摩根大通": None, "标准银行集团": None,
    "凯悦酒店": None, "美国运通": None, "宜家": None, "香奈儿": None,
    "勃林格殷格翰": None, "罗尔斯·罗伊斯控股": None, "洛克希德·马丁": None,
    "圣米格尔": None, "Spotify": None, "SAP": None, "丰田集团": None,
    "南非第一国民银行": None, "迅达": None, "萨班奇控股": None, "喜力": None,
    "马来西亚国家石油化学": None, "露华浓": None, "四季酒店及度假村": None,
    "礼来": None, "Rossmann": None, "PayPal": None, "诺斯罗普·格鲁曼": None,
    "强生": None, "普拉达": None, "沙特阿美": None, "默克": None,
    "诺和诺德": None, "意大利国家电力公司 Enel": None, "五十铃汽车": None,
    "巴斯夫": None, "大阪煤气": None, "松下": None, "竹中工务店": None,
    "东京海上控股": None, "本田汽车": None, "网飞": None, "米其林集团": None,
    "甲骨文": None, "Ace Hardware": None, "雅马哈": None, "法航-荷航集团": None,
    "卡特彼勒": None, "百加得": None, "山特维克": None, "资生堂": None,
    "微芯科技": None, "万事达卡": None, "波士顿科学": None, "Expedia 集团": None,
    "Visa": None, "沙特基础工业公司 SABIC": None, "康迪泰克汽车系统": None,
    "佳明": None, "阿巴萨集团": None, "日本烟草": None, "国家电网公司": None,
    "ABB": None, "达美航空": None,
    # GPTW
    "Hilton": "hilton", "DHL Express": "dhl", "Cisco": None,
    "Accenture": "accenture", "Marriott International": None, "AbbVie": None,
    "TP": None, "Stryker": None, "Salesforce": None, "MetLife": None,
    "ServiceNow": None, "Specsavers": None, "Siemens Healthineers": None,
    "Experian": None, "Nvidia": None, "Cadence": None, "Allianz": None,
    "Dow": None, "Viatris": None, "Adobe": None, "CrowdStrike": None,
    "SC Johnson": None, "Trek Bicycle": None, "Hilti": None, "Admiral Group": None,
}

def resolve_slug(name):
    """Try to resolve a ranking entity name to a seed company slug."""
    if name in rank_name_overrides:
        return rank_name_overrides[name]
    if name in name_to_slug:
        return name_to_slug[name]
    # Try partial matching
    for slug, cname, aliases, tags, etype, hp in seeds:
        if cname in name or name in cname:
            return slug
        for a in aliases:
            if a.lower() == name.lower() or a in name or name in a:
                return slug
    return None

# ============================================================
# GENERATE ranking_memberships.jsonl
# ============================================================
ranking_entries = []

def add_ranking(list_id, year, name, rank, source_url):
    slug = resolve_slug(name)
    ranking_entries.append({
        "list_id": list_id,
        "year": year,
        "ranked_entity_name": name,
        "rank": rank,
        "company_id": slug,  # 待关联 - resolved where possible, null otherwise
        "source_url": source_url,
        "retrieved_at": RETRIEVED_AT,
    })

fg_url = lists_meta["fortune_global_500_2026"]["evidence_url"]
for rank, name, eng in fortune_global:
    add_ranking("fortune_global_500_2026", 2026, name, rank, fg_url)

fc_url = lists_meta["fortune_china_500_2026"]["evidence_url"]
for rank, name in fortune_china:
    add_ranking("fortune_china_500_2026", 2026, name, rank, fc_url)

fe_url = lists_meta["forbes_best_employers_2025"]["evidence_url"]
for rank, name in forbes_employers:
    add_ranking("forbes_best_employers_2025", 2025, name, rank, fe_url)

gw_url = lists_meta["gptw_best_workplaces_2025"]["evidence_url"]
for rank, name, loc, ind in gptw_workplaces:
    add_ranking("gptw_best_workplaces_2025", 2025, name, rank, gw_url)

with open(f"{OUT}/ranking_memberships.jsonl", "w", encoding="utf-8") as f:
    for entry in ranking_entries:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

print(f"ranking_memberships.jsonl: {len(ranking_entries)} entries")

# ============================================================
# GENERATE companies.jsonl
# ============================================================
# Build company dict from seeds
companies = {}
for slug, cname, aliases, tags, etype, hp in seeds:
    companies[slug] = {
        "company_id": slug,
        "canonical_name": cname,
        "aliases": aliases,
        "industry_tags": tags,
        "employer_type": etype,
        "source_discovered_from": ["80种子"],
        "ranking_memberships": [],
        "homepage_url": hp,
        "investigation_status": "assigned" if slug in fixed_assigned else "pending",
        "notes": "",
    }

# Add ranking memberships to seed companies
for entry in ranking_entries:
    slug = entry["company_id"]
    if slug and slug in companies:
        rm = {"list_id": entry["list_id"], "year": entry["year"], "rank": entry["rank"]}
        if rm not in companies[slug]["ranking_memberships"]:
            companies[slug]["ranking_memberships"].append(rm)
        if "榜单" not in companies[slug]["source_discovered_from"]:
            list_label = entry["list_id"].replace("_2026", "").replace("_2025", "")
            if list_label not in companies[slug]["source_discovered_from"]:
                companies[slug]["source_discovered_from"].append(list_label)

# Mark 24 fixed
for slug in fixed_assigned:
    if slug in companies:
        companies[slug]["investigation_status"] = "assigned"
        if "24家固定" not in companies[slug]["source_discovered_from"]:
            companies[slug]["source_discovered_from"].append("24家固定")

# Add ranking-only companies (not in seeds)
ranking_only_names = set()
for entry in ranking_entries:
    if entry["company_id"] is None:
        ranking_only_names.add(entry["ranked_entity_name"])

# Generate slugs for ranking-only companies
def make_slug(name):
    """Create a stable slug from a company name."""
    import re
    # Use English name if in parentheses
    m = re.search(r'[（(]([A-Z][A-Z0-9 &.\-]+)[)）]', name)
    if m:
        eng = m.group(1).strip()
        slug = re.sub(r'[^a-z0-9]+', '_', eng.lower()).strip('_')
        if slug:
            return slug
    # Chinese name -> pinyin-like slug (just use a hash-based stable id)
    import hashlib
    h = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"ranking_{h}"

existing_slugs = set(companies.keys())
for name in sorted(ranking_only_names):
    slug = make_slug(name)
    if slug in existing_slugs:
        slug = slug + "_" + hashlib.md5(name.encode()).hexdigest()[:4]
    existing_slugs.add(slug)
    
    # Determine industry tags from ranking context
    ind_tags = []
    # Check GPTW industry
    for rank, gname, loc, ind in gptw_workplaces:
        if gname == name:
            ind_tags.append(ind)
    # Check Forbes industry (from the Chinese article table - we'd need to re-extract)
    # For now, use generic tags based on name patterns
    
    # Collect ranking memberships
    rms = []
    for entry in ranking_entries:
        if entry["ranked_entity_name"] == name:
            rms.append({"list_id": entry["list_id"], "year": entry["year"], "rank": entry["rank"]})
    
    # Source discovered from
    sources = set()
    for rm in rms:
        list_label = rm["list_id"].replace("_2026", "").replace("_2025", "")
        sources.add(list_label)
    
    companies[slug] = {
        "company_id": slug,
        "canonical_name": name,
        "aliases": [],
        "industry_tags": ind_tags if ind_tags else ["unknown"],
        "employer_type": "unknown",
        "source_discovered_from": sorted(sources),
        "ranking_memberships": rms,
        "homepage_url": None,
        "investigation_status": "pending",
        "notes": "仅来自榜单条目，未在80家种子中；待进一步调研",
    }

# Write companies.jsonl
with open(f"{OUT}/companies.jsonl", "w", encoding="utf-8") as f:
    for slug in sorted(companies.keys()):
        f.write(json.dumps(companies[slug], ensure_ascii=False) + "\n")

seed_count = len(seeds)
ranking_only_count = len(ranking_only_names)
total = len(companies)
assigned_count = sum(1 for c in companies.values() if c["investigation_status"] == "assigned")
print(f"companies.jsonl: {total} total ({seed_count} seeds + {ranking_only_count} ranking-only)")
print(f"  assigned (24 fixed): {assigned_count}")
print(f"  pending: {total - assigned_count}")

# ============================================================
# WRITE LIST METADATA as evidence
# ============================================================
with open(f"{OUT}/evidence/list_versions.json", "w", encoding="utf-8") as f:
    json.dump(lists_meta, f, ensure_ascii=False, indent=2)
print("evidence/list_versions.json written")

# Write summary stats
stats = {
    "generated_at": RETRIEVED_AT,
    "ranking_memberships_total": len(ranking_entries),
    "by_list": {
        "fortune_global_500_2026": len(fortune_global),
        "fortune_china_500_2026": len(fortune_china),
        "forbes_best_employers_2025": len(forbes_employers),
        "gptw_best_workplaces_2025": len(gptw_workplaces),
    },
    "companies_total": total,
    "companies_seed": seed_count,
    "companies_ranking_only": ranking_only_count,
    "companies_assigned": assigned_count,
    "lists_completeness": {k: v["list_completeness"] for k, v in lists_meta.items()},
}
with open(f"{OUT}/evidence/generation_stats.json", "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)
print("evidence/generation_stats.json written")
print("\nDONE")
