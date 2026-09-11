#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate FOREIGN_EXPANSION_REPORT.md from foreign_companies.jsonl."""
import json, os
from collections import Counter, defaultdict
BASE = "/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/expansion_foreign"
rows=[json.loads(l) for l in open(os.path.join(BASE,"foreign_companies.jsonl"),encoding="utf-8")]

N=len(rows)
st=Counter(r["investigation_status"] for r in rows)
queryable=sum(1 for r in rows if r.get("has_queryable_jobs")==True)
covered=[r for r in rows if r["investigation_status"]=="有可用岗位部分覆盖"]
entry=[r for r in rows if r["investigation_status"]=="入口已证实"]
blocked=[r for r in rows if r["investigation_status"]=="访问受阻"]
nofit=[r for r in rows if r["investigation_status"]=="未发现适用岗位"]
partial=[r for r in rows if r["investigation_status"]=="partial"]

lines=[]
A=lines.append
A("# 外企100家扩源报告（秋招MCP v3 · B线#7）")
A("")
A("- 生成时间：2026-09-10")
A("- 任务：外企100家扩源，中国校招/应届项目优先")
A("- 企业来源：财富世界500强（非中国企业378家中选取）+ 用户指定行业标杆，按集团去重")
A("- 输出目录：`expansion_foreign/`")
A("  - `foreign_companies.jsonl`：100家登记")
A("  - `staging/{slug}/jobs.json`：每家岗位采集（仅staging，不碰生产）")
A("")
A("## 一、总览")
A("")
A(f"| 指标 | 数量 |")
A(f"|---|---|")
A(f"| 目标企业数 | 100 |")
A(f"| 已逐家处理 | {N} |")
A(f"| 有可查询岗位企业（has_queryable_jobs=true） | {queryable} |")
A(f"| 其中：已提取≥1条真实中国校招岗位（有可用岗位部分覆盖） | {len(covered)} |")
A(f"| 入口已证实但本轮未逐岗枚举JD | {len(entry)} |")
A(f"| 访问受阻 | {len(blocked)} |")
A(f"| 未发现适用岗位（中国大陆校招） | {len(nofit)} |")
A(f"| 历史partial待复核 | {len(partial)} |")
A("")
A("> 说明：严格按“有至少1条符合中国校招范围、具备真实详情的岗位才计有可查询岗位企业”。"
  "本轮真正逐岗提取到真实JD详情的为 **36家**（有可用岗位部分覆盖）；"
  "其余57家为“入口已证实”——官方招聘域名/校招项目页已验证存在且可按China筛选，"
  "但本轮未逐岗抓取全部JD列表（多为Workday/SuccessFactors/自建SPA，需渲染或分页枚举，标partial后续补）。"
  "未用全球社招总量或海外名录替代内地校招计数。")
A("")
A("## 二、状态分布")
A("")
A("| 处理状态 | 数量 |")
A("|---|---|")
for k,v in st.most_common():
    A(f"| {k} | {v} |")
A("")
A("## 三、访问受阻（blocker）")
A("")
for r in blocked:
    A(f"- **{r['cn_name']}** (`{r['slug']}`)：{r.get('blocker_reason') or '—'}")
A("")
A("## 四、未发现中国大陆适用校招岗位")
A("")
for r in nofit:
    A(f"- **{r['cn_name']}** (`{r['slug']}`)：{r.get('blocker_reason') or '—'}")
A("")
A("## 五、历史partial待复核")
A("")
for r in partial:
    A(f"- **{r['cn_name']}** (`{r['slug']}`)：{r.get('prior_note') or '—'}")
A("")
A("## 六、按行业分布")
A("")
ind=Counter()
for r in rows:
    # 粗归并行业
    raw=r["industry"] or "其他"
    for key,label in [("快消","快消/食品"),("饮料","快消/食品"),("酒类","快消/食品"),("美妆","快消/美妆"),("奢侈品","快消/美妆"),
                      ("科技","科技"),("咨询","咨询/专业服务"),("审计","咨询/专业服务"),
                      ("金融","金融"),("保险","金融"),("汽车","汽车"),("医药","医药"),
                      ("工业","工业/能源/材料"),("能源","工业/能源/材料"),("化工","工业/能源/材料"),
                      ("零售","零售/物流"),("物流","零售/物流"),("文娱","文娱")]:
        if key in raw: ind[label]+=1; break
    else: ind["其他"]+=1
A("| 行业簇 | 数量 |")
A("|---|---|")
for k,v in ind.most_common(): A(f"| {k} | {v} |")
A("")
A("## 七、已提取真实中国校招岗位的企业（36家，部分覆盖）")
A("")
for r in sorted(covered, key=lambda x:x["slug"]):
    sj=r.get("sample_jobs") or []
    sjtxt="；".join(f"{s['title']}（{s.get('location','')}）" for s in sj[:2])
    A(f"- **{r['cn_name']}**：{r.get('china_campus_status','')} — 例：{sjtxt}")
A("")
A("## 八、主要招聘平台分布")
A("")
plat=Counter()
for r in rows:
    p=(r.get("platform") or "未知")
    for key in ["MokaHR","Workday","51job","自建","SuccessFactors","Phenom","Greenhouse","tupu360","avature","hotjob","智联","smartdeer","Taleo"]:
        if key.lower() in p.lower(): plat[key]+=1; break
    else: plat["其他/混合"]+=1
for k,v in plat.most_common(): A(f"- {k}: {v}")
A("")
A("## 九、关键发现")
A("")
A("1. **外企在华校招2027届整体活跃**：快消、医药、汽车、科技、咨询、金融、工业、物流八大行业均有集团直管校招/管培生项目在招。")
A("2. **平台高度集中**：MokaHR（雀巢/百威/亿滋/高露洁/特斯拉/大众/福特/英伟达/普华永道）、Workday（科技/医药/工业巨头）、51job校招专题（雅诗兰黛/汇丰/瑞银/联合利华历史）、自建中国ATS（达能/默克/罗氏/诺华/西门子/微软）是主流。")
A("3. **中国区可直接查询的标杆**：达能careersite、诺华novartis.com.cn、罗氏careers.roche.com/cn、奔驰career.mercedes-benz.com.cn、西门子jobs.siemens.com.cn、苹果jobs.apple.com(CHNC)、百事pepsicojobs.com/china —— 这些页面可web.fetch直出岗位列表。")
A("4. **受阻/弱信号**：施耐德(Workday 500/se.com 403)、联合利华(中国站Under Construction)、Meta(中国大陆无校招)、家乐福(业务收缩)、Costco/奥乐齐(以门店零售为主)。")
A("5. **差额说明（诚实报）**：目标100家已全部逐家处理入口验证，但“完整枚举JD列表+详情”的仅少数（宝洁为历史完整案例）；本轮多数企业为“入口已证实/部分覆盖”，未承诺完整覆盖100家中国校招岗位全量。海外/社招/实习未混入内地可投计数。")
A("")
A("## 十、后续建议")
A("")
A("- 对57家“入口已证实”企业，按其平台（Workday/SuccessFactors/自建SPA）逐一渲染分页、枚举中国校招JD并补全详情。")
A("- 施耐德/联合利华走浏览器渲染或人工确认MokaHR/自建校招入口，替代当前blocker结论。")
A("- 3家历史partial（埃森哲/欧莱雅/阿斯利康）按本轮统一标准复核升级。")
A("")
open(os.path.join(BASE,"FOREIGN_EXPANSION_REPORT.md"),"w",encoding="utf-8").write("\n".join(lines))
print("wrote FOREIGN_EXPANSION_REPORT.md")
print("covered",len(covered),"entry",len(entry),"blocked",len(blocked),"nofit",len(nofit),"partial",len(partial),"queryable",queryable)
