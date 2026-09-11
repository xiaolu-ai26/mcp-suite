"""Three real-scenario validations against staging_merged/jobs.json."""
import json
from pathlib import Path
from qiuzhao.tools import Jobs

OUT = Path('/Users/maxzhl/Projects/mcp-suite/research/qiuzhao-v3-launch-20260910/job_mvp')
jobs = Jobs(str(OUT / 'staging_merged/jobs.json'))
scenarios = OUT / 'scenario_tests'
scenarios.mkdir(exist_ok=True)


def dump(name, query, result):
    slim = {
        'query': query,
        'data_as_of': result.get('data_as_of'),
        'total': result.get('total'),
        'next_offset': result.get('next_offset'),
        'jobs': [{k: j.get(k) for k in ('id', 'job_title', 'recruitment_unit', 'cities',
                                          'job_category', 'recruitment_type_raw', 'cohort_raw',
                                          'deadline', 'deadline_type', 'application_url')}
                 for j in result.get('jobs', [])],
    }
    (scenarios / name).write_text(json.dumps(slim, ensure_ascii=False, indent=2))
    print(f'=== {name}: total={result.get("total")} returned={len(result.get("jobs", []))}')
    return slim


# a. 按背景检索：计算机专业 + 2027届 + 深圳
q1 = dict(major='计算机', cohort='2027', city='深圳', limit=8)
r1 = jobs.search(**q1)
dump('scenario_a_background.json', q1, r1)

# a2. also show the new optional filters work (company + recruitment_type)
q1b = dict(city='深圳', recruitment_type='校招', company='腾讯', limit=5)
r1b = jobs.search(**q1b)
dump('scenario_a2_newfilters.json', q1b, r1b)

# b. 三岗条件对照：选3个不同公司岗位对比
picks = []
for company in ['腾讯', '宝洁', '迈瑞']:
    res = jobs.search(company=company, limit=1)
    if res['jobs']:
        picks.append(res['jobs'][0])
q2 = dict(note='pick one job from 腾讯/宝洁/迈瑞 for side-by-side comparison')
dump('scenario_b_compare3.json', q2, {'data_as_of': jobs.load()[1], 'total': len(picks), 'jobs': picks})

# c. 明确截止与准备顺序：未来7天截止
q3 = dict(days=7)
r3 = jobs.deadlines(**q3)
dump('scenario_c_deadlines7d.json', q3, r3)

# Also show deadlines window wider for evidence
q3b = dict(days=30, limit=5)
r3b = jobs.deadlines(**q3b)
dump('scenario_c_deadlines30d.json', q3b, r3b)

print('\n--- sample a (computer+2027+shenzhen) ---')
for j in r1['jobs'][:5]:
    print(' ', j['job_title'], '|', j['cities'], '|', j.get('recruitment_type_raw'))
print('--- c (next-7d deadlines) ---')
for j in r3['jobs'][:5]:
    print(' ', j.get('deadline'), j['job_title'], '|', j['recruitment_unit'])
