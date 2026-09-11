#!/usr/bin/env python3
"""
归一化城市、岗位大类、毕业届别、专业字段，并更新jobs.json
"""
import json
import re
import shutil
import time
from collections import Counter

# 读取当前jobs.json
with open('/var/lib/mcp-suite/jobs.json') as f:
    jobs = json.load(f)

print(f"加载 {len(jobs)} 条岗位")

# 城市归一化
def normalize_city(city):
    if not city:
        return '未披露'
    city = str(city).strip()
    if city in ['未披露', '未知', '', 'null', 'None', '不限']:
        return '未披露'
    if city in ['全国', '中国', '全国各地', '全国多地', '全国各省市']:
        return '全国'
    if city in ['海外', '国外', '境外', '海外及其他']:
        return '海外'
    if '-' in city:
        parts = city.split('-')
        first = parts[0].strip()
        if first.endswith('市'):
            first = first[:-1]
        return first
    if city.endswith('市'):
        city = city[:-1]
    city = city.replace(' ', '')
    for sep in [',', '，', '/', '、', ';', '；']:
        if sep in city:
            city = city.split(sep)[0].strip()
            break
    city = re.sub(r'[（(].*?[）)]', '', city).strip()
    return city if city else '未披露'

# 岗位大类归一化
def normalize_job_category(category, job_title=''):
    if not category and not job_title:
        return '其他'
    category = str(category or '').strip()
    job_title = str(job_title or '').strip()
    combined = category + ' ' + job_title
    
    # 技术类
    tech_keywords = ['工程师', '开发', '算法', '前端', '后端', '全栈', '测试', '运维', '数据库', '安全', '架构', '数据', 'AI', '人工智能', '机器学习', '深度学习', '嵌入式', '硬件', '芯片', '通信', '网络', '软件', '程序员', '码农', '研发', '技术', 'java', 'python', 'c++', 'go', 'rust', 'ios', 'android', '大数据', '云计算', '区块链']
    for kw in tech_keywords:
        if kw.lower() in combined.lower():
            return '技术/研发'
    
    # 产品类
    product_keywords = ['产品', 'PM', '产品经理', '产品助理']
    for kw in product_keywords:
        if kw.lower() in combined.lower():
            return '产品'
    
    # 运营类
    operation_keywords = ['运营', '内容运营', '用户运营', '活动运营', '社群运营', '新媒体运营', '电商运营', '游戏运营']
    for kw in operation_keywords:
        if kw in combined:
            return '运营'
    
    # 市场类
    marketing_keywords = ['市场', '营销', '品牌', '公关', '推广', '广告', '策划', 'BD', '商务']
    for kw in marketing_keywords:
        if kw in combined:
            return '市场/营销'
    
    # 设计类
    design_keywords = ['设计', 'UI', 'UX', '视觉', '交互', '平面', '工业设计', '产品设计', '美术', '插画']
    for kw in design_keywords:
        if kw in combined:
            return '设计'
    
    # 销售类
    sales_keywords = ['销售', '客户经理', '客户成功', '售前', '售后', '渠道', '大客户', '销售代表', '销售经理']
    for kw in sales_keywords:
        if kw in combined:
            return '销售'
    
    # 职能类
    function_keywords = ['人力', 'HR', '行政', '财务', '会计', '法务', '审计', '采购', '供应链', '物流', '仓储', '客服', '支持', '助理', '秘书', '文员', '管培生', '管理培训生', '人事']
    for kw in function_keywords:
        if kw in combined:
            return '职能/支持'
    
    # 金融类
    finance_keywords = ['金融', '银行', '证券', '基金', '保险', '投资', '风控', '信贷', '投行', '分析师', '研究员']
    for kw in finance_keywords:
        if kw in combined:
            return '金融'
    
    # 咨询类
    consulting_keywords = ['咨询', '顾问', '战略', '管理咨询']
    for kw in consulting_keywords:
        if kw in combined:
            return '咨询'
    
    # 医疗类
    medical_keywords = ['医生', '护士', '医药', '医疗', '临床', '药剂', '检验', '影像', '护理']
    for kw in medical_keywords:
        if kw in combined:
            return '医疗/医药'
    
    # 制造类
    manufacturing_keywords = ['生产', '制造', '工艺', '质量', '质检', '设备', '机械', '电气', '自动化', '工厂', '车间']
    for kw in manufacturing_keywords:
        if kw in combined:
            return '制造/生产'
    
    # 科研类
    research_keywords = ['科研', '研究员', '科学家', '博士后', '实验室']
    for kw in research_keywords:
        if kw in combined:
            return '科研'
    
    # 教育类
    education_keywords = ['教师', '老师', '教育', '培训', '讲师', '教授', '助教']
    for kw in education_keywords:
        if kw in combined:
            return '教育/培训'
    
    # 法律类
    legal_keywords = ['律师', '法务', '法律', '合规']
    for kw in legal_keywords:
        if kw in combined:
            return '法律/合规'
    
    return '其他'

# 毕业届别归一化
def normalize_graduation_year(text):
    if not text:
        return '未披露'
    text = str(text)
    years = re.findall(r'20\d{2}', text)
    if years:
        for year in years:
            if f'{year}届' in text or f'{year}年' in text or f'{year} 届' in text:
                return f'{year}届'
        return f'{max(years)}届'
    return '未披露'

# 专业归一化
def normalize_major(major_text):
    if not major_text:
        return '未披露'
    major_text = str(major_text)
    
    # 计算机类
    cs_keywords = ['计算机', '软件', '人工智能', '大数据', '网络工程', '信息安全', '物联网', '数据科学', '机器学习', '深度学习', '算法', '程序设计', '软件工程', '计算机科学', '计算机技术', '网络空间安全', '数字媒体技术', '游戏设计']
    for kw in cs_keywords:
        if kw in major_text:
            return '计算机类'
    
    # 电子信息类
    ee_keywords = ['电子', '通信', '自动化', '电气', '微电子', '信息工程', '电子信息', '通信工程', '自动化', '电气工程', '电子科学', '集成电路', '光电', '电磁场', '信号处理']
    for kw in ee_keywords:
        if kw in major_text:
            return '电子信息类'
    
    # 机械制造类
    mech_keywords = ['机械', '制造', '材料', '能源', '动力', '工程力学', '机械工程', '机械设计', '材料科学', '材料工程', '能源与动力', '车辆工程', '汽车', '航空航天', '船舶', '兵器', '核工程']
    for kw in mech_keywords:
        if kw in major_text:
            return '机械制造类'
    
    # 金融经济类
    fin_keywords = ['金融', '经济', '会计', '财务', '统计', '投资', '保险', '证券', '银行', '财政', '税收', '审计', '金融工程', '金融学', '经济学', '会计学', '财务管理', '统计学', '国际经济', '贸易']
    for kw in fin_keywords:
        if kw in major_text:
            return '金融经济类'
    
    # 医药生物类
    med_keywords = ['医学', '药学', '护理', '生物', '临床', '基础医学', '预防医学', '口腔', '中医', '中药', '药剂', '检验', '影像', '康复', '公共卫生', '生物医学', '生物技术', '生物工程', '制药']
    for kw in med_keywords:
        if kw in major_text:
            return '医药生物类'
    
    # 管理类
    mgmt_keywords = ['管理', '工商管理', '人力资源', '市场营销', '行政管理', '公共管理', '旅游管理', '酒店管理', '物流管理', '供应链', '项目管理', '企业管理', '管理科学', '工业工程', '电子商务']
    for kw in mgmt_keywords:
        if kw in major_text:
            return '管理类'
    
    # 文科类
    arts_keywords = ['中文', '新闻', '法律', '法学', '外语', '英语', '日语', '翻译', '教育', '汉语言', '传播学', '广告学', '社会学', '心理学', '哲学', '历史', '政治学', '国际关系', '公共事业']
    for kw in arts_keywords:
        if kw in major_text:
            return '文科类'
    
    # 理科类
    sci_keywords = ['数学', '物理', '化学', '地理', '海洋', '大气', '环境', '生态学', '应用数学', '应用物理', '应用化学', '统计学', '信息与计算科学']
    for kw in sci_keywords:
        if kw in major_text:
            return '理科类'
    
    # 设计艺术类
    design_keywords = ['设计', '美术', '艺术', '音乐', '舞蹈', '戏剧', '影视', '动画', '摄影', '雕塑', '绘画', '视觉传达', '环境设计', '产品设计', '服装', '工业设计']
    for kw in design_keywords:
        if kw in major_text:
            return '设计艺术类'
    
    # 农业类
    agri_keywords = ['农学', '农业', '园艺', '植物保护', '动物科学', '动物医学', '林学', '园林', '水产', '食品', '粮食', '农业资源']
    for kw in agri_keywords:
        if kw in major_text:
            return '农业类'
    
    return '其他'

# 统计
city_counter = Counter()
job_category_counter = Counter()
graduation_year_counter = Counter()
major_counter = Counter()

# 更新每条岗位
updated_count = 0
for job in jobs:
    # 城市归一化
    cities = job.get('cities', [])
    normalized_cities = []
    if isinstance(cities, list):
        for c in cities:
            normalized = normalize_city(c)
            if normalized and normalized not in normalized_cities:
                normalized_cities.append(normalized)
    elif isinstance(cities, str):
        normalized = normalize_city(cities)
        if normalized:
            normalized_cities.append(normalized)
    
    primary_city = normalized_cities[0] if normalized_cities else '未披露'
    job['city_normalized'] = primary_city
    job['cities_normalized'] = normalized_cities
    city_counter[primary_city] += 1
    
    # 岗位大类归一化（同时参考job_title）
    jc = job.get('job_category', '')
    jt = job.get('job_title', '')
    normalized_jc = normalize_job_category(jc, jt)
    job['job_category_normalized'] = normalized_jc
    job_category_counter[normalized_jc] += 1
    
    # 毕业届别归一化
    gy = job.get('graduation_year', '') or job.get('cohort_raw', '')
    normalized_gy = normalize_graduation_year(gy)
    job['graduation_year_normalized'] = normalized_gy
    graduation_year_counter[normalized_gy] += 1
    
    # 专业归一化
    major_raw = job.get('major_requirements_raw', '') or job.get('major_tags', '')
    if isinstance(major_raw, list):
        major_raw = ' '.join(str(m) for m in major_raw)
    normalized_major = normalize_major(major_raw)
    job['major_normalized'] = normalized_major
    major_counter[normalized_major] += 1
    
    updated_count += 1

print(f"更新了 {updated_count} 条岗位")

# 统计结果
print("\n=== 城市归一化结果（前20）===")
print(f"唯一城市数: {len(city_counter)}")
for city, count in city_counter.most_common(20):
    print(f"  {city}: {count}")

print("\n=== 岗位大类归一化结果 ===")
for category, count in job_category_counter.most_common():
    print(f"  {category}: {count}")

print("\n=== 毕业届别归一化结果 ===")
for year, count in graduation_year_counter.most_common():
    print(f"  {year}: {count}")

print("\n=== 专业归一化结果 ===")
for major, count in major_counter.most_common():
    print(f"  {major}: {count}")

# 备份
backup_path = f'/var/lib/mcp-suite/jobs.json.bak.normalized_v2.{time.strftime("%Y%m%d-%H%M%S")}'
shutil.copy('/var/lib/mcp-suite/jobs.json', backup_path)
print(f"\n备份: {backup_path}")

# 保存更新后的jobs.json
with open('/var/lib/mcp-suite/jobs.json', 'w') as f:
    json.dump(jobs, f, ensure_ascii=False, indent=2)

print(f"已保存更新后的jobs.json")

# 保存归一化选项
options = {
    'cities': [city for city, _ in city_counter.most_common(200)],
    'job_categories': [category for category, _ in job_category_counter.most_common()],
    'graduation_years': [year for year, _ in graduation_year_counter.most_common()],
    'majors': [major for major, _ in major_counter.most_common()]
}

with open('/tmp/normalized_options_v2.json', 'w') as f:
    json.dump(options, f, ensure_ascii=False, indent=2)

print(f"\n归一化选项已保存到 /tmp/normalized_options_v2.json")
print(f"城市选项数: {len(options['cities'])}")
print(f"岗位大类选项数: {len(options['job_categories'])}")
print(f"毕业届别选项数: {len(options['graduation_years'])}")
print(f"专业选项数: {len(options['majors'])}")
