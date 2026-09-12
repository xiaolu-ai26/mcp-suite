import csv
import json
from pathlib import Path
from qiuzhao.normalize import normalize_records
from qiuzhao.collector import export_csv


def test_multivalue_refresh_retains_raw_and_legacy_compatibility():
    row = {'id': 'x', 'cohort_raw': '2026届或2027届', 'recruitment_type': '校园招聘',
           'graduation_year_normalized': '2027届', 'graduation_years': ['2027届']}
    normalize_records([row])
    assert row['graduation_years'] == ['2027届', '2026届']
    assert row['graduation_year_basis'] == {'2026届': '岗位写明', '2027届': '岗位写明'}
    assert row['cohort_raw'] == '2026届或2027届'
    assert row['graduation_year_normalized'] == '2027届'
    assert not any(normalize_records([row]).values())
    row['cohort_raw'] = '2028届'
    normalize_records([row])
    assert row['graduation_years'] == ['2028届']


def test_unknown_p1_cohort_is_not_invented():
    row = {'id': 'x', 'p1_company': '大疆', 'recruitment_type': '校园招聘',
           'published_at': '2026-09-12', 'graduation_years': ['2027届']}
    normalize_records([row])
    assert row['graduation_years'] == []
    assert row['graduation_year_note'] == '未注明'


def test_csv_exports_all_cohorts_from_old_snapshot(tmp_path, monkeypatch):
    source = tmp_path / 'jobs.json'
    source.write_text(json.dumps([{'id': 'x', 'cohort_raw': '2026届、2027届',
        'graduation_year_normalized': '2027届', 'recruitment_type': '校园招聘'}]))
    monkeypatch.setattr(export_csv, 'JOBS_FILE', source)
    out = tmp_path / 'out.csv'
    assert export_csv.export_jobs(out)
    with out.open(encoding='utf-8-sig') as stream:
        row = next(csv.DictReader(stream))
    assert row['毕业届别'] == '2027届、2026届'
    assert set(json.loads(row['届别依据'])) == {'2026届', '2027届'}


def test_explicit_multiple_major_categories_without_description_guessing():
    from qiuzhao.v4_fields import major_categories_of
    row = {'major_requirements_raw': '计算机科学、电子信息、机械工程', 'major_normalized': '计算机类'}
    assert major_categories_of(row) == ['计算机类', '电子信息类', '机械制造类']
    assert major_categories_of({'description_raw': '开发软件及电子系统', 'major_normalized': '计算机类'}) == []
    normalize_records([row])
    assert row['major_categories'] == ['计算机类', '电子信息类', '机械制造类']
    row['major_requirements_raw'] = '专业不限'
    normalize_records([row])
    assert row['major_categories'] == []


def test_role_cohort_precedes_generic_campaign_and_job_bound_exception():
    from qiuzhao.v4_fields import graduation_of, graduation_conflicts_of
    row={'cohort_raw':'仅2026届','campaign_cohort_raw':'2027届校园招聘','recruitment_type':'校园招聘'}
    assert graduation_of(row)[0]==['2026届']
    assert graduation_conflicts_of(row)[0]['years']==['2027届']
    row.update(source_record_id='verified-role',campaign_job_ids=['verified-role'],
               campaign_cohort_raw='面向2027届及优秀2026届高校毕业生')
    assert graduation_of(row)[0]==['2027届','2026届']
    assert graduation_conflicts_of(row)==[]


def test_campaign_scoped_legacy_label_does_not_hide_role_multiyear():
    from qiuzhao.v4_fields import graduation_of
    row={'cohort_raw':'2027届','cohort_scope':'campaign_announcement','recruitment_type':'校园招聘',
         'description_raw':'任职要求：2026/2027届本科及以上学历，计算机相关专业。'}
    assert graduation_of(row)[0]==['2027届','2026届']
    row['description_raw']='其中部分境外岗位面向2025年6月至2027年10月毕业的学生。'
    assert graduation_of(row)[0]==['2027届']
    row['description_raw']='仅2026届，不接受2027届毕业生。'
    assert graduation_of(row)[0]==['2026届']


def test_negative_role_clause_and_unrelated_also_allowed_do_not_expand():
    from qiuzhao.v4_fields import graduation_of
    row={'cohort_raw':'仅2026届，不接受2027届','campaign_cohort_raw':'2027届校园招聘',
         'recruitment_type':'校园招聘'}
    assert graduation_of(row)[0]==['2026届']
    row={'job_title':'2027届校招','description_raw':'仅限2026届毕业生；无实习经历也可',
         'recruitment_type':'校园招聘'}
    assert graduation_of(row)[0]==['2026届']


def test_older_explicit_cohort_is_retained_and_not_unspecified_for_2027(tmp_path):
    from qiuzhao.v4_fields import graduation_of
    from qiuzhao.tools import Jobs
    from qiuzhao.collector.p1_pipeline import validate_result
    raw={'id':'old','cohort_raw':'2021届提前批','recruitment_type':'校园招聘','source_record_id':'old',
         'job_title':'研发工程师','description_raw':'2021届本科毕业生','recruitment_unit':'普联',
         'detail_url':'https://careers.tp-link.com/job/old','status':'open'}
    assert graduation_of(raw)[0]==['2021届']
    payload={'jobs':[raw],'coverage':{'status':'partial','complete':False,'collected_jobs':1,'scope_evidence':'official campus channel'}}
    checked=validate_result(payload,'TP-LINK普联','campus')['jobs'][0]
    assert checked['status']=='unverified' and '届别较旧' in checked['status_note']
    path=tmp_path/'jobs.json';path.write_text(json.dumps([checked]))
    jobs=Jobs(path)
    assert jobs.search(graduation_year='2027届')['total']==0
    assert jobs.search(graduation_year='2021届')['total']==1


def test_contextual_short_years_and_full_range_do_not_match_salary_or_age():
    from qiuzhao import v4_fields as V
    assert V.title_years('【27校招 - 联合动力】研发岗')==[2027]
    assert V.title_years('工程师-27届秋招')==[2027]
    assert V.years_in('26/27届')==[2026,2027]
    assert V.years_in('2025-2027届本科及以上学历毕业生')==[2025,2026,2027]
    assert V.title_years('薪资27万，27岁以内，内部编码2027009')==[]
    assert V.description_years('薪资27万，27岁以内')==[]


def test_open_graduation_bound_matches_future_year_without_enumerating(tmp_path):
    from qiuzhao import v4_fields as V
    from qiuzhao.tools import Jobs
    raw={'id':'open','recruitment_type':'实习招聘','description_raw':'28届及以后在读硕士及以上学历',
         'job_title':'算法实习生','source_url':'https://example.com/job/open','application_url':'https://example.com/job/open'}
    item,_=V.convert(raw)
    assert item['graduation_years']==['2028届']
    assert item['graduation_year_constraints']['min_year']==2028
    path=tmp_path/'jobs.json';path.write_text(json.dumps([raw]));jobs=Jobs(path)
    assert jobs.search(graduation_year='2027届')['total']==0
    assert jobs.search(graduation_year='2029届')['explicit_total']==1
    assert jobs.search(graduation_year='2030届')['explicit_total']==1
    raw['description_raw']+='，不接受2029届'
    item,_=V.convert(raw)
    assert Jobs._m_grad(item,'2029届',False) is None


def test_negated_open_range_never_creates_positive_eligibility():
    from qiuzhao import v4_fields as V
    from qiuzhao.tools import Jobs
    raw={'cohort_raw':'仅限2027届，不接受2028届及以后','recruitment_type':'校园招聘'}
    item,_=V.convert(raw)
    assert item['graduation_years']==['2027届']
    assert Jobs._m_grad(item,'2029届',False) is None
    assert Jobs._m_grad(item,'2030届',False) is None
    raw['cohort_raw']='2028届及以后不适用'
    assert V.graduation_constraints_of(raw)=={}
    raw['cohort_raw']='2027届及以后，不接受2028届及以后'
    bounds=V.graduation_constraints_of(raw)
    assert bounds['min_year']==2027 and bounds['max_year']==2027


def test_explicit_social_recruitment_preserves_role_cohorts_and_unrestricted_notice(tmp_path):
    from qiuzhao import v4_fields as V
    from qiuzhao.tools import Jobs
    explicit={'id':'specific','recruitment_type':'社会招聘','job_title':'初级EMS产品经理（25-26届）',
              'description_raw':'任职要求：24-25届优秀毕业生，本科及以上学历',
              'source_url':'https://example.com/job/specific','application_url':'https://example.com/job/specific'}
    assert V.graduation_of(explicit)[0]==['2025届','2024届']
    unrestricted={'id':'general','recruitment_type':'社会招聘','job_title':'软件工程师','description_raw':'负责软件开发',
                  'source_url':'https://example.com/job/general','application_url':'https://example.com/job/general'}
    path=tmp_path/'jobs.json';path.write_text(json.dumps([explicit,unrestricted]));jobs=Jobs(path)
    assert jobs.search(graduation_year='2027届')['total']==0
    result=jobs.search(graduation_year='2027届',recruitment_type='社会招聘')
    assert result['total']==1 and result['jobs'][0]['id']=='general'
    assert result['jobs'][0]['match']['graduation_year']=='社招不限届别'
    assert jobs.search(graduation_year='2025届',recruitment_type='社会招聘')['total']==2
