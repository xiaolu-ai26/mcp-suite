import json
import re

# 读取当前jobs.json
with open('/var/lib/mcp-suite/jobs.json') as f:
    jobs = json.load(f)

print(f"加载 {len(jobs)} 条岗位")

# 专业归一化（修复版）
def normalize_major(major_text):
    if not major_text:
        return '未披露'
    if isinstance(major_text, list):
        major_text = ' '.join(str(m) for m in major_text)
    major_text = str(major_text)
    
    # 先移除"办公软件"、"应用软件"等容易误匹配的词
    major_text_clean = re.sub(r'办公软件|应用软件|办公应用|软件应用|熟练使用|掌握', '', major_text)
    
    # 计算机类（排除"办公软件"等）
    cs_keywords = ['计算机科学', '计算机技术', '计算机应用', '软件工程', '软件技术', '人工智能', '大数据', '网络工程', '信息安全', '物联网工程', '数据科学', '机器学习', '深度学习', '算法', '程序设计', '网络空间安全', '数字媒体技术', '游戏设计', '计算机类', '软件类']
    for kw in cs_keywords:
        if kw in major_text_clean:
            return '计算机类'
    
    # 电子信息类
    ee_keywords = ['电子信息', '电子科学', '通信工程', '通信技术', '自动化', '电气工程', '电气类', '微电子', '信息工程', '集成电路', '光电信息', '电磁场', '信号处理', '电子类']
    for kw in ee_keywords:
        if kw in major_text_clean:
            return '电子信息类'
    
    # 机械制造类
    mech_keywords = ['机械工程', '机械设计', '机械制造', '材料科学', '材料工程', '材料类', '能源与动力', '能源动力', '动力工程', '车辆工程', '汽车服务', '航空航天', '船舶与海洋', '兵器类', '核工程', '工程力学', '机械类', '热能与动力', '能源类']
    for kw in mech_keywords:
        if kw in major_text_clean:
            return '机械制造类'
    
    # 金融经济类
    fin_keywords = ['金融学', '金融工程', '经济学', '经济统计学', '会计学', '财务管理', '审计学', '投资学', '保险学', '财政学', '税收学', '统计学', '国际经济', '国际贸易', '金融类', '经济类', '财会类']
    for kw in fin_keywords:
        if kw in major_text_clean:
            return '金融经济类'
    
    # 医药生物类
    med_keywords = ['临床医学', '基础医学', '预防医学', '口腔医学', '中医学', '中药学', '药学', '药物制剂', '护理学', '医学检验', '医学影像', '康复治疗', '公共卫生', '生物医学', '生物技术', '生物工程', '制药工程', '医学类', '药学类', '生物类']
    for kw in med_keywords:
        if kw in major_text_clean:
            return '医药生物类'
    
    # 管理类
    mgmt_keywords = ['工商管理', '人力资源', '市场营销', '行政管理', '公共管理', '旅游管理', '酒店管理', '物流管理', '供应链管理', '项目管理', '企业管理', '管理科学', '工业工程', '电子商务', '管理类']
    for kw in mgmt_keywords:
        if kw in major_text_clean:
            return '管理类'
    
    # 文科类
    arts_keywords = ['汉语言文学', '新闻学', '传播学', '广告学', '法学', '法律', '英语', '日语', '翻译', '教育学', '社会学', '心理学', '哲学', '历史学', '政治学', '国际关系', '公共事业', '中国语言文学', '外国语言文学', '文科类']
    for kw in arts_keywords:
        if kw in major_text_clean:
            return '文科类'
    
    # 理科类
    sci_keywords = ['数学与应用数学', '信息与计算科学', '物理学', '应用物理学', '化学', '应用化学', '地理科学', '海洋科学', '大气科学', '环境科学', '生态学', '理科类']
    for kw in sci_keywords:
        if kw in major_text_clean:
            return '理科类'
    
    # 设计艺术类
    design_keywords = ['视觉传达', '环境设计', '产品设计', '服装与服饰', '工业设计', '美术学', '绘画', '雕塑', '摄影', '动画', '音乐学', '舞蹈学', '戏剧影视', '艺术设计', '设计类', '艺术类']
    for kw in design_keywords:
        if kw in major_text_clean:
            return '设计艺术类'
    
    # 农业类
    agri_keywords = ['农学', '园艺', '植物保护', '动物科学', '动物医学', '林学', '园林', '水产养殖', '食品科学', '食品质量', '粮食工程', '农业资源', '农业类', '食品类']
    for kw in agri_keywords:
        if kw in major_text_clean:
            return '农业类'
    
    return '其他'

# 统计
major_counter = {}
updated_count = 0

for job in jobs:
    major_raw = job.get('major_requirements_raw', '') or job.get('major_tags', '')
    if isinstance(major_raw, list):
        major_raw = ' '.join(str(m) for m in major_raw)
    
    old_major = job.get('major_normalized', '未披露')
    new_major = normalize_major(major_raw)
    
    if old_major != new_major:
        job['major_normalized'] = new_major
        updated_count += 1
    
    major_counter[new_major] = major_counter.get(new_major, 0) + 1

print(f"更新了 {updated_count} 条岗位的专业归一化")
print("\n=== 专业归一化结果（修复后）===")
for major, count in sorted(major_counter.items(), key=lambda x: -x[1]):
    print(f"  {major}: {count}")

# 保存
with open('/var/lib/mcp-suite/jobs.json', 'w') as f:
    json.dump(jobs, f, ensure_ascii=False, indent=2)

print("\n已保存更新后的jobs.json")
