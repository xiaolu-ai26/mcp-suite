#!/usr/bin/env python3
"""
归一化城市、岗位大类、毕业届别字段，并更新jobs.json
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

# 城市归一化（进一步处理"北京-海淀区"这种）
def normalize_city_final(city):
    if not city:
        return '未披露'
    city = str(city).strip()
    
    # 特殊值
    if city in ['未披露', '未知', '', 'null', 'None', '不限']:
        return '未披露'
    if city in ['全国', '中国', '全国各地', '全国多地', '全国各省市']:
        return '全国'
    if city in ['海外', '国外', '境外', '海外及其他']:
        return '海外'
    
    # 处理"北京-海淀区"、"北京市-北京"这种
    if '-' in city:
        parts = city.split('-')
        first = parts[0].strip()
        # 如果第一部分是城市名，直接用
        if first.endswith('市'):
            first = first[:-1]
        return first
    
    # 处理"北京市"
    if city.endswith('市'):
        city = city[:-1]
    
    # 处理"北京 市"
    city = city.replace(' ', '')
    
    # 如果包含多个城市，取第一个
    for sep in [',', '，', '/', '、', ';', '；']:
        if sep in city:
            city = city.split(sep)[0].strip()
            break
    
    # 去除括号内容
    city = re.sub(r'[（(].*?[）)]', '', city).strip()
    
    return city if city else '未披露'

# 岗位大类归一化
def normalize_job_category(category):
    if not category:
        return '其他'
    category = str(category).strip()
    
    # 技术类
    tech_keywords = ['工程师', '开发', '算法', '前端', '后端', '全栈', '测试', '运维', '数据库', '安全', '架构', '数据', 'AI', '人工智能', '机器学习', '深度学习', '嵌入式', '硬件', '芯片', '通信', '网络', '软件', '程序员', '码农', '研发', '技术', 'java', 'python', 'c++', 'go', 'rust', 'ios', 'android', '大数据', '云计算', '区块链']
    for kw in tech_keywords:
        if kw.lower() in category.lower():
            return '技术/研发'
    
    # 产品类
    product_keywords = ['产品', 'PM', '产品经理', '产品助理']
    for kw in product_keywords:
        if kw.lower() in category.lower():
            return '产品'
    
    # 运营类
    operation_keywords = ['运营', '内容运营', '用户运营', '活动运营', '社群运营', '新媒体运营', '电商运营', '游戏运营']
    for kw in operation_keywords:
        if kw in category:
            return '运营'
    
    # 市场类
    marketing_keywords = ['市场', '营销', '品牌', '公关', '推广', '广告', '策划', 'BD', '商务']
    for kw in marketing_keywords:
        if kw in category:
            return '市场/营销'
    
    # 设计类
    design_keywords = ['设计', 'UI', 'UX', '视觉', '交互', '平面', '工业设计', '产品设计', '美术', '插画']
    for kw in design_keywords:
        if kw in category:
            return '设计'
    
    # 销售类
    sales_keywords = ['销售', '客户经理', '客户成功', '售前', '售后', '渠道', '大客户', '销售代表', '销售经理']
    for kw in sales_keywords:
        if kw in category:
            return '销售'
    
    # 职能类
    function_keywords = ['人力', 'HR', '行政', '财务', '会计', '法务', '审计', '采购', '供应链', '物流', '仓储', '客服', '支持', '助理', '秘书', '文员', '管培生', '管理培训生', '人事']
    for kw in function_keywords:
        if kw in category:
            return '职能/支持'
    
    # 金融类
    finance_keywords = ['金融', '银行', '证券', '基金', '保险', '投资', '风控', '信贷', '投行', '分析师', '研究员']
    for kw in finance_keywords:
        if kw in category:
            return '金融'
    
    # 咨询类
    consulting_keywords = ['咨询', '顾问', '战略', '管理咨询']
    for kw in consulting_keywords:
        if kw in category:
            return '咨询'
    
    # 医疗类
    medical_keywords = ['医生', '护士', '医药', '医疗', '临床', '药剂', '检验', '影像', '护理']
    for kw in medical_keywords:
        if kw in category:
            return '医疗/医药'
    
    # 制造类
    manufacturing_keywords = ['生产', '制造', '工艺', '质量', '质检', '设备', '机械', '电气', '自动化', '工厂', '车间']
    for kw in manufacturing_keywords:
        if kw in category:
            return '制造/生产'
    
    # 科研类
    research_keywords = ['科研', '研究员', '科学家', '博士后', '实验室']
    for kw in research_keywords:
        if kw in category:
            return '科研'
    
    # 教育类
    education_keywords = ['教师', '老师', '教育', '培训', '讲师', '教授', '助教']
    for kw in education_keywords:
        if kw in category:
            return '教育/培训'
    
    # 法律类
    legal_keywords = ['律师', '法务', '法律', '合规']
    for kw in legal_keywords:
        if kw in category:
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

# 统计
city_counter = Counter()
job_category_counter = Counter()
graduation_year_counter = Counter()

# 更新每条岗位
updated_count = 0
for job in jobs:
    # 城市归一化
    cities = job.get('cities', [])
    normalized_cities = []
    if isinstance(cities, list):
        for c in cities:
            normalized = normalize_city_final(c)
            if normalized and normalized not in normalized_cities:
                normalized_cities.append(normalized)
    elif isinstance(cities, str):
        normalized = normalize_city_final(cities)
        if normalized:
            normalized_cities.append(normalized)
    
    # 取第一个城市作为主城市（用于单选筛选）
    primary_city = normalized_cities[0] if normalized_cities else '未披露'
    job['city_normalized'] = primary_city
    job['cities_normalized'] = normalized_cities
    city_counter[primary_city] += 1
    
    # 岗位大类归一化
    jc = job.get('job_category', '')
    normalized_jc = normalize_job_category(jc)
    job['job_category_normalized'] = normalized_jc
    job_category_counter[normalized_jc] += 1
    
    # 毕业届别归一化
    gy = job.get('graduation_year', '') or job.get('cohort_raw', '')
    normalized_gy = normalize_graduation_year(gy)
    job['graduation_year_normalized'] = normalized_gy
    graduation_year_counter[normalized_gy] += 1
    
    updated_count += 1

print(f"更新了 {updated_count} 条岗位")

# 统计结果
print("\n=== 城市归一化结果（前50）===")
print(f"唯一城市数: {len(city_counter)}")
for city, count in city_counter.most_common(50):
    print(f"  {city}: {count}")

print("\n=== 岗位大类归一化结果 ===")
for category, count in job_category_counter.most_common():
    print(f"  {category}: {count}")

print("\n=== 毕业届别归一化结果 ===")
for year, count in graduation_year_counter.most_common():
    print(f"  {year}: {count}")

# 备份
backup_path = f'/var/lib/mcp-suite/jobs.json.bak.normalized.{time.strftime("%Y%m%d-%H%M%S")}'
shutil.copy('/var/lib/mcp-suite/jobs.json', backup_path)
print(f"\n备份: {backup_path}")

# 保存更新后的jobs.json
with open('/var/lib/mcp-suite/jobs.json', 'w') as f:
    json.dump(jobs, f, ensure_ascii=False, indent=2)

print(f"已保存更新后的jobs.json")

# 保存归一化选项（用于飞书单选字段）
options = {
    'cities': [city for city, _ in city_counter.most_common(200)],  # 前200个城市
    'job_categories': [category for category, _ in job_category_counter.most_common()],
    'graduation_years': [year for year, _ in graduation_year_counter.most_common()]
}

with open('/tmp/normalized_options.json', 'w') as f:
    json.dump(options, f, ensure_ascii=False, indent=2)

print(f"\n归一化选项已保存到 /tmp/normalized_options.json")
print(f"城市选项数: {len(options['cities'])}")
print(f"岗位大类选项数: {len(options['job_categories'])}")
print(f"毕业届别选项数: {len(options['graduation_years'])}")
