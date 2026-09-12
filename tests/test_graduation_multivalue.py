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
