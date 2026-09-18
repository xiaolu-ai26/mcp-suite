# -*- coding: utf-8 -*-
"""第一期 written_test 标注表生成:人工审核后的定标清单 -> qiuzhao/data/written_test_labels.json。

输入:
  l1_result.json   精灵全库 L1 流程句挖掘结果(0 请求)
  fetch_results.json  L2/L3 官方页面抓取结果(每站 <=2 次,间隔 >=2 秒)

输出的每条标注都带逐字原文、官方 URL、scope、basis、checked_at。
人工审核原则(站长 2026-09-19 口径):
  - 岗位职责里写"负责组织笔试/人才测评"的 HR 岗位描述不算公司有笔试(红线 9)。
  - "优秀者可免笔试""部分岗位需笔试"一律标 部分免笔试,限定语原样留在 evidence。
  - 读不到就是未注明,不进标注表。
"""
import csv
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
L1_PATH = ROOT / "l1_result.json"
FETCH_PATH = ROOT / "fetch_results.json"
OUT_LABELS = ROOT / "written_test_labels.json"
OUT_QUEUE = ROOT / "written-test-review-queue.csv"

TZ = datetime.timezone(datetime.timedelta(hours=8))
CHECKED_AT = "2026-09-19T02:40:00+08:00"

# ------------------------------------------------------------------ L1 定标(人工审核)

L1_PICKS = [
    # (公司 key, 标签, [证据逐字子串...], 备注, 别名)
    ("科大讯飞", "部分免笔试",
     ["此岗位为科大讯飞集团统一招聘岗位，人员通过简历筛选、笔试、初试、复试、终审等环节后录用",
      "此岗位为科大讯飞集团统一招聘岗位，人员通过简历筛选、初试、复试、终审等环节后录用"],
     "同一集团两类岗位描述并存:含笔试 89 条、不含笔试 84 条,故按部分免笔试收录,原文两条都保留",
     ["科大讯飞股份有限公司"]),
    ("快手", "有笔试", ["*本岗位需要参加在线笔试"],
     "岗位描述明文;另有 2 条“本岗位需要参加在线测评”", []),
    ("中国航发哈尔滨轴承有限公司", "有笔试", ["简历接收→简历筛选→素质测评→面试→签订就业协议"], "", []),
    ("海南南繁种业集团有限公司", "有笔试",
     ["招聘程序包括个人报名、资格审查、综合测评、背景调查、人事档案审核、体检、录用等程序"], "", []),
    ("罗氏制药中国", "有笔试", ["在线测评：2026年9月中旬-10月下旬"], "官方申请时间表里的在线测评环节", []),
    ("中科寒武纪科技股份有限公司", "有笔试", ["注：本岗位设置笔试环节，请留意邮件或短信通知"], "", []),
    ("北京力天世技系统集成有限公司", "有笔试", ["面试流程：线下笔试+面试（1~2轮）"], "", []),
    ("易车", "有笔试", ["网申通过的同学会收到线上测评的通知"], "", []),
    ("网易", "有笔试", ["*该岗位可能会有笔试"], "官方措辞保留“可能”", []),
    ("中国人保", "有笔试",
     ["后续如收到笔试通知，请按时参加", "集团本级校招岗位简历接收截止时间为10月中旬，且仅组织2026年10月一个批次的笔试"], "",
     ["中国人民保险集团股份有限公司"]),
    ("中国平安财产保险股份有限公司莆田中心支公司", "有笔试",
     ["根据笔试及专业面试情况，双选分配至精算、数据（分析/挖掘）等相关岗位"], "", []),
    ("中建七局第四建筑有限公司", "有笔试", ["通过中国建筑2027届校园招聘统一考试，取得有效成绩"], "", []),
    ("平安银行股份有限公司佛山分行", "有笔试",
     ["线上笔试：8月23日、9月6日、9月19日、10月11日、10月25、11月8日、11月15，笔试时间为60分钟"], "", []),
    ("广岩国际投资有限责任公司", "有笔试",
     ["对于未招录到合适人选的岗位，公司可能长期开放并分阶段组织符合资格的候选人进入能力测评及后续招聘流程"], "", []),
    ("中信证券股份有限公司天津分公司", "有笔试", ["线上测评与线下面试"], "", []),
    ("中建新科建设发展有限公司", "有笔试", ["通过中国建筑2027年校园招聘在线考试"], "", []),
    ("北京银行", "有笔试", ["本次招聘面试、笔试、体检等相关信息，均通过邮件或手机短信进行通知"], "",
     ["北京银行股份有限公司"]),
    ("山西致捷康达商贸有限公司", "有笔试", ["在线测评"], "", []),
    ("广东省韶铸集团有限公司", "有笔试", ["应聘流程：网申/报名→简历筛选→笔试→面试→体检→入职前公示→入职"], "",
     ["广东省韶铸集团有限公司（韶关铸锻总厂）"]),
    ("影石Insta360", "有笔试", ["该岗位在初试通过后会有笔试环节，旨在加深又双向了解，望提前知悉"], "", []),
    ("阿斯利康", "有笔试", ["笔试与面试评估（次年4-6月）"], "", []),
    ("中科创达", "有笔试", ["简历初筛-笔试-技术面-HR面试-心理测试-Offer发放-签三方"], "", []),
    ("中衍高新材料（江西）有限公司", "有笔试",
     ["招录流程：初筛——线上笔试——面试——背景调查——体验——录用"], "", []),
    ("北京市石景山区宏成学科培训学校", "有笔试",
     ["投递简历→人力线上/电话沟通初面→复试（试讲20-30分钟，笔试1个小时）→入职签约"], "", []),
    ("北京通州城市运营管理集团有限公司", "有笔试", ["本次招聘采取笔试、心理测评及面试相结合的方式进行"], "", []),
    ("国元证券股份有限公司洛阳滨河南路证券营业部", "有笔试",
     ["求职者需经过面试、笔试后方可入职，笔试内容是需剪辑一个视频小样"], "", []),
    ("山东天岳先进科技股份有限公司", "有笔试",
     ["简历投递→简历初筛→HR电话沟通→测评+笔试→业务面试→offer审批发放→三方签约"], "", []),
    ("广州市城市规划勘测设计研究院有限公司雄安分院", "有笔试",
     ["面试流程：简历筛选→线上面试→线下面试→笔试→终面"], "", []),
    ("开封市东基电力有限公司", "有笔试", ["后续笔试通知，请关注邮箱动态"], "", []),
    ("江苏八十万卷楼数字图书有限公司", "有笔试", ["凡应聘者均需笔试面试"], "", []),
    ("海南省农垦投资控股集团有限公司", "有笔试",
     ["招聘程序包括个人报名、资格审查、笔试、面试、考察、体检、录用等环节"], "", []),
    ("瑞众人寿保险有限责任公司海南分公司", "有笔试",
     ["本年度校招遵循双志愿原则，仅有一次线上笔试机会，请务必了解是否符合任职资格，审慎选择志愿，认真对待笔试"], "", []),
    ("用友网络", "有笔试", ["面试：现场笔试，笔试通过当场复试"], "", []),
    ("阿里巴巴", "有笔试", ["本岗位需要完成工程笔试"], "另有“本岗位需要完成算法笔试”", []),
    ("字节跳动", "部分免笔试",
     ["Candidates who pass resume screening will be invited to participate in Our Company's technical online assessment."],
     "岗位描述英文模板 30 条写通过简历筛选后参加 technical online assessment;官方专题页同时写明是否笔试按岗位匹配度判断",
     []),
    ("联想", "有笔试",
     ["Applications will undergo a resume screening process, and shortlisted candidates will be invited to complete a Leadership Skills Assessment through SHL, our assessment partner."],
     "官方英文岗位描述:简历筛选后参加 SHL 测评", []),
    ("中国航天科工集团有限公司", "有笔试", ["前期笔试面试培训后，再进行岗位的分配"], "", []),
    ("北京航天科工世纪卫星科技有限公司", "有笔试", ["前期笔试面试培训后，再进行岗位的分配"], "", []),
    ("北京亦庄国际投资发展有限公司", "有笔试", ["实习后安排实习答辩及笔试，通过者可发放offer留用"], "", []),
    ("米哈游", "部分免笔试",
     ["（可选）AI作品：欢迎在投递时附上令你感到骄傲的AI成果/工具设计（最好游戏或运营工作存在一定关联性），并附上创作思路和迭代记录，优秀者可免笔试直通面试！",
      "具体志愿信息将在笔试环节收集"],
     "限定性豁免:优秀者可免笔试直通面试;同时招聘方向在笔试环节收集志愿", []),
    ("美团", "部分免笔试", ["熟练掌握SQL（有SQL笔试环节）"],
     "限定性豁免:仅部分技术岗写明有 SQL 笔试环节,其余岗位描述未见笔试", []),
    ("中信建投证券股份有限公司海南分公司", "有笔试",
     ["校招流程：网申（9月-2027年4月）→笔试面试（11月-2027年4月）→实习考核、录用（2027年1-6月）"], "", []),
    ("中建六局第七建设有限公司", "有笔试", ["通过中建测评考试"], "中国建筑系统统一测评考试", []),
    ("安徽兴华智锻科技有限公司", "有笔试", ["需通过背景调查与综合素质测评"], "", []),
    ("滴滴", "有笔试", ["笔试面试均会考察相关技能"],
     "官方岗位描述写明笔试与面试都会考察相关技能", []),
    ("重庆长安跨越商用车有限公司", "免笔试",
     ["线上/线下投递简历—面试—准备入职资料、完成入职体检—报到入职"], "官方岗位描述公布完整流程,无做题环节", []),
    ("悦联商业(好邻居便利店)", "免笔试", ["投递简历-初筛-面试-入职"],
     "官方岗位描述公布完整流程,无做题环节", []),
    ("成都益尔听力技术有限公司", "免笔试",
     ["简历筛选→线上初试→线下复试→Offer发放→带薪3天试岗期→正式入职培训"],
     "官方岗位描述公布完整流程,无做题环节", []),
]

# ------------------------------------------------------------------ L2/L3 官方页面定标

PAGE_PICKS = [
    ("中国银行", "有笔试", "公告原文", "笔试由中国银行统一组织",
     "https://www.boc.cn/aboutboc/bi4/202603/t20260311_25654053.html", []),
    ("中国邮政", "有笔试", "公告原文", "网上申请—简历接收和筛选—线上笔试—面试—体检及背景调查—发放offer—签署就业协议",
     "https://www.chinapost.com.cn/cn/report/2609/1176-1.htm", []),
    ("中国建设银行", "有笔试", "公告原文", "中国建设银行-中德住房储蓄银行2026年度校园招聘统一笔试及性格测评公告",
     "https://job1.ccb.com/cn/job/announcement.html?annoId=20260903163254718082", []),
    ("百度", "有笔试", "FAQ", "注册并应聘→简历筛选（10-15个工作日）→笔试（10-15个工作日）→面试（10-15个工作日）→录用",
     "https://talent.baidu.com/mobile/recruit/help.html", []),
    ("小米", "有笔试", "流程页", "专项能力测试+性格测评",
     "https://hr.xiaomi.com/website/campus.html", []),
    ("普华永道", "有笔试", "流程页", "在线测评是校招流程中的一个重要环节，请务必在收到在线测评邀请的48小时内完成测评",
     "https://www.pwccn.com/zh/careers/students.html", ["普华永道 PwC"]),
    ("华为", "部分免笔试", "FAQ", "非研发类岗位：您需参加考试（部分岗位涉及）、语言测评（部分岗位涉及）、综合测评",
     "https://career.huawei.com/reccampportal/portal5/faq.html", []),
    ("中国邮政储蓄银行", "有笔试", "公告原文", "择优甄选确定入围笔试人员",
     "https://www.psbc.com/cn/gyyc/rczp/xyzp/202609/t20260907_460394.html", []),
    ("国家能源集团", "部分免笔试", "公告原文", "统一笔试（博士研究生免笔试）",
     "https://zhaopin.chnenergy.com.cn/annc/showgg?id=6a152f40-7fe5-460e-ad37-0024acafd8c9", []),
    ("玛氏", "有笔试", "流程页", "Assessment:",
     "https://careers.mars.com/global/en/how-to-join-us", []),
    ("微软", "有笔试", "FAQ", "Accommodation requests during the assessment stage",
     "https://careers.microsoft.com/v2/global/en/hiringfaqs.html", []),
    ("中国电信", "部分免笔试", "公告原文",
     "除中国电信集团有限公司组织的统一线上笔试外(部分单位参与，以后续通知为准)，本次招聘由中国电信集团所属分子公司根据招聘计划，根据简历筛选情况，自行组织笔试、面试",
     "https://www.chinatelecom.com.cn/ct/zp/165144.html", ["中国电信集团有限公司"]),
]

# ------------------------------------------------------------------ 复核队列(低置信度,不进标注表)

REVIEW_QUEUE = [
    ("亿道集团", "免笔试", "简历投递----简历筛选----招募及面试-----offer发放----开启工作----薪资&奖金&荣誉发放",
     "https://emdoor1.zhiye.com/campus/job/da4c7f47-074f-40e2-9715-478ed7303485", "疑似校园大使招募流程,需人工确认是否覆盖正式校招岗位"),
    ("京东", "部分免笔试", "部分岗位需要进行AI面试或在线笔试",
     "https://campus.jd.com/", "线索来自 2026-09-18 调研报告转述,本次未在官方页面直接读到原文,需回源核实"),
    ("宁德时代", "有笔试", "熟悉人力资源管理相关业务，掌握人力资源规划与配置方法、职位分析、人才测评",
     "https://talent.catl.com/social-recruitment/catlhr/96144", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("小鹏汽车", "有笔试", "制定培训考核机制（如笔试、实操、满意度调研等）",
     "https://xiaopeng.jobs.feishu.cn/index/position/7413218070358968630/detail", "培训岗职责,非招聘笔试"),
    ("海康威视", "有笔试", "负责招聘、培训、任职资格、人才测评、薪酬、绩效", 
     "https://campushr.hikvision.com/JobDetails.html", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("大疆", "有笔试", "关注行业人才测评与AI面试等前沿动态",
     "https://apply.careers.dji.com/social-recruitment/dji/170070", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("吉利汽车", "有笔试", "5年以上大型企业人才甄选、招聘或人才测评相关经验",
     "https://job.geely.com/social-recruitment/geely/96123", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("蔚来汽车", "有笔试", "跟踪设备技师及工程师团队能力建设，学习地图，能力测评",
     "https://nio.jobs.feishu.cn/intern/position/7523036756864125225/detail", "员工能力建设语境,非招聘测评"),
    ("长城汽车", "有笔试", "精通招聘流程和各类招聘渠道的运作机制，熟练掌握人才测评技术",
     "https://zhaopin.gwm.cn/SU692d3058ea11b01b6c54d0ea/pb/posDetail.html", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("安克创新", "有笔试", "熟练使用统计分析工具和人才测评测评系统",
     "https://career.anker.com.cn/larkJobDetail/", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("理想汽车", "有笔试", "掌握人才测评工具和方法",
     "https://www.lixiang.com/employ/detail/16743.html", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("金山办公", "有笔试", "协助进行招聘心理测评的实施与结果分析",
     "https://join.wps.cn/campus-recruitment/wps/41436", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("青春知行", "有笔试", "应届生求职大单位笔试精讲40小时",
     "https://www.iguopin.com/job/detail?id=42150339482247097", "求职培训课程介绍,与招聘流程无关"),
    ("东风汽车集团股份有限公司奕派汽车科技分公司", "有笔试", "负责对接高校、组织宣讲、笔试面试安排、offer发放",
     "https://www.iguopin.com/job/detail?id=211676580617915043", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("巨人网络", "有笔试", "全权负责校招全流程落地，涵盖线上线下宣讲、笔试面试、offer发放",
     "https://app.mokahr.com/social-recruitment/ztgame/37485", "HR 岗位职责,按红线 9 不判定公司有笔试"),
    ("中国平安财产保险股份有限公司莆田中心支公司", "有笔试", "根据笔试及专业面试情况，双选分配",
     "https://www.iguopin.com/job/detail?id=215735456111788130", "已定标,此处保留原始 URL 备查"),
]


FLOW_PICKS = [
    ("安能集团一局（海南）建设发展有限公司", "免笔试",
     "报名、资格审查、面试、确定意向人选、体检、背景调查",
     "官方招聘公告程序完整且不含做题环节", []),
    ("海南海大科技园管理有限公司", "免笔试",
     "本次招聘按照报名与资格审查、面试和考察、体检、审议确定人选、公示与聘任签约等程序进行",
     "官方招聘公告程序完整且不含做题环节", []),
]


def build_flow_labels(flows):
    index = {}
    for item in flows.get("templates", []):
        index.setdefault(item["company"], []).append(item)
    labels, problems = [], []
    for key, value, needle, note, aliases in FLOW_PICKS:
        found = None
        for item in index.get(key, []):
            if _norm(needle) in _norm(item["evidence"]):
                found = item
                break
        if not found:
            problems.append("%s: 找不到流程句 %s" % (key, needle[:40]))
            continue
        labels.append({
            "key": key,
            "key_type": "company",
            "aliases": aliases,
            "written_test": value,
            "written_test_scope": "company",
            "written_test_basis": "岗位描述明文",
            "written_test_evidence": found["evidence"],
            "written_test_source_url": (found.get("urls") or [""])[0],
            "written_test_checked_at": CHECKED_AT,
            "confidence": "high",
            "source_layer": "L1-库内岗位描述",
            "note": note,
        })
    return labels, problems


# 少数标注公司自己的岗位记录没有 URL(内部 beisen 记录),用同集团官方招聘系统的岗位页补上。
URL_OVERRIDE = {
    "中国人保": "https://picc.zhiye.com/campus/job/3732212d-db85-4974-9041-0d3ead6f2b83",
}


def _norm(text):
    return re.sub(r"\s+", "", text or "")


def _tmpl_index(l1):
    index = {}
    for item in l1["templates"]:
        index.setdefault(item["company"], []).append(item)
    return index


def build_l1_labels(l1):
    index = _tmpl_index(l1)
    labels, problems = [], []
    for key, value, matches, note, aliases in L1_PICKS:
        names = [key] + list(aliases)
        evidence, url, counts = [], "", []
        for needle in matches:
            found = None
            for name in names:
                for item in index.get(name, []):
                    if _norm(needle) in _norm(item["evidence"]):
                        found = item
                        break
                if found:
                    break
            if not found:
                problems.append("%s: 找不到证据模板 %s" % (key, needle[:40]))
                continue
            if found["evidence"] not in evidence:
                evidence.append(found["evidence"])
            counts.append("%s %d 条" % (found["kind"], found["count"]))
            if not url and found.get("urls"):
                url = found["urls"][0]
        if not evidence:
            continue
        if not url:
            for name in names:
                for item in index.get(name, []):
                    if item.get("urls"):
                        url = item["urls"][0]
                        break
                if url:
                    break
        if not url:
            url = URL_OVERRIDE.get(key, "")
        labels.append({
            "key": key,
            "key_type": "company",
            "aliases": aliases,
            "written_test": value,
            "written_test_scope": "company",
            "written_test_basis": "岗位描述明文",
            "written_test_evidence": "\n".join(evidence),
            "written_test_source_url": url,
            "written_test_checked_at": CHECKED_AT,
            "confidence": "high" if len(evidence) > 1 or value != "有笔试" else "medium",
            "source_layer": "L1-库内岗位描述",
            "note": note or ("命中:%s" % "、".join(counts)),
        })
    return labels, problems


PAGE_EXTRA = {
    "字节跳动": ["HR会根据你的简历与岗位的匹配度判断是否需要笔试，请以实际安排为准"],
}


def _append_page_evidence(labels, fetch):
    by_company = {}
    for rec in fetch:
        by_company.setdefault(rec["company"], []).append(rec)
    for label in labels:
        for needle in PAGE_EXTRA.get(label["key"], []):
            for rec in by_company.get(label["key"], []):
                hit = ""
                for group in (rec.get("hits") or {}).values():
                    for sentence in group:
                        if _norm(needle) in _norm(sentence):
                            hit = sentence
                            break
                    if hit:
                        break
                if hit and hit not in label["written_test_evidence"]:
                    label["written_test_evidence"] += "\n" + hit
                    label["written_test_basis"] += "+官方页面"
                    if rec.get("url"):
                        label["written_test_source_url"] = rec["url"] if not label["written_test_source_url"] else label["written_test_source_url"]
                    break
    return labels


def build_page_labels(fetch):
    by_company = {}
    for rec in fetch:
        by_company.setdefault(rec["company"], []).append(rec)
    labels, problems = [], []
    for key, value, basis, needle, url, aliases in PAGE_PICKS:
        evidence = ""
        for rec in by_company.get(key, []):
            for group in (rec.get("hits") or {}).values():
                for sentence in group:
                    if _norm(needle[:24]) in _norm(sentence):
                        evidence = sentence
                        break
                if evidence:
                    break
            if evidence:
                break
        if not evidence:
            problems.append("%s: 页面证据未命中 %s" % (key, needle[:40]))
            continue
        labels.append({
            "key": key,
            "key_type": "company",
            "aliases": aliases,
            "written_test": value,
            "written_test_scope": "company",
            "written_test_basis": basis,
            "written_test_evidence": evidence,
            "written_test_source_url": url,
            "written_test_checked_at": CHECKED_AT,
            "confidence": "high",
            "source_layer": "L2/L3-官方页面",
            "note": "页面类型:%s" % basis,
        })
    return labels, problems


def main():
    l1 = json.loads(L1_PATH.read_text(encoding="utf-8"))
    flows = json.loads((ROOT / "l1_flows.json").read_text(encoding="utf-8"))
    fetch = json.loads(FETCH_PATH.read_text(encoding="utf-8"))
    l1_labels, p1 = build_l1_labels(l1)
    l1_labels = _append_page_evidence(l1_labels, fetch)
    page_labels, p2 = build_page_labels(fetch)
    flow_labels, p3 = build_flow_labels(flows)
    problems = p1 + p2 + p3

    labels = page_labels + flow_labels + l1_labels  # 页面/公告证据优先展示
    payload = {
        "version": 1,
        "updated_at": CHECKED_AT,
        "policy": {
            "有笔试": "官方公告/流程页/FAQ/岗位描述明文写了笔试、测评、在线测试、机考、OT 等任一做题环节",
            "免笔试": "官方公布了完整招聘流程且流程里没有任何笔试/测评环节;或官方明文写 免笔试/无笔试/直通面试",
            "部分免笔试": "限定性豁免(优才免笔试、优秀者可免笔试、部分岗位需笔试),限定语保留在 evidence",
            "未注明": "官方没公布流程或读不到;读不到不等于免笔试",
        },
        "source_layers": {
            "L1": "精灵库内岗位描述流程句聚类挖掘(0 次对外请求),按公司聚类,人工复核后定标",
            "L2": "官方招聘 FAQ/流程页(静态 HTML 直读)",
            "L3": "官方专场公告页(静态 HTML 直读)",
        },
        "requests_used": sum(1 for _ in fetch),
        "labels": labels,
    }
    OUT_LABELS.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    with OUT_QUEUE.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["公司", "候选标签", "原文", "链接", "不确定原因"])
        for company, value, evidence, url, reason in REVIEW_QUEUE:
            writer.writerow([company, value, evidence, url, reason])

    counts = {}
    for label in labels:
        counts[label["written_test"]] = counts.get(label["written_test"], 0) + 1
    print("labels=%d %s" % (len(labels), counts))
    print("queue=%d" % len(REVIEW_QUEUE))
    if problems:
        print("PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
