"""Unit tests for the daily collection-gap report (feat/gap-report).

The shapes under test are the ones the 2026-09-20 morning run actually produced:
958 finished units, 814 matching their source's own total, 2 claiming ``complete``
while short (商汤科技 intern 66/70, social 86/87), 18 honest ``partial`` gaps
(美团 2588 of the 2631) and 124 units whose source never states a total.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qiuzhao.collector import collection_gap as gap


def unit(company, scope, *, expected, collected, status='success', complete=True,
         errors=(), published=True):
    return {f'{company}/{scope}': {
        'published': published,
        'coverage': {
            'company': company, 'scope': scope, 'status': status, 'complete': complete,
            'expected_total': expected, 'collected_jobs': collected,
            'errors': list(errors), 'pages_scanned': 3, 'pagination_exhausted': complete,
        },
    }}


def status(*units, started_at='2026-09-19T22:41:51+00:00'):
    results = {}
    for item in units:
        results.update(item)
    return {'started_at': started_at, 'results': results}


def by_key(rows):
    return {(row['company'], row['scope']): row for row in rows}


# --- 1. gap arithmetic ------------------------------------------------------ #

def test_gap_is_expected_minus_collected_and_never_negative():
    report = gap.build_report(status(
        unit('甲公司', 'campus', expected=100, collected=90, status='partial', complete=False),
        unit('乙公司', 'social', expected=50, collected=50),
        unit('丙公司', 'intern', expected=10, collected=12, status='partial', complete=False),
    ))
    rows = by_key(report['units'])
    assert rows[('甲公司', 'campus')]['gap'] == 10
    assert rows[('乙公司', 'social')]['gap'] == 0
    assert rows[('丙公司', 'intern')]['gap'] == 0, 'over-collection is not a negative gap'
    assert report['summary']['total_gap'] == 10


def test_missing_expected_total_is_listed_not_counted_as_match_or_gap():
    # 124 real units have no source total: no gap is computable, so they must be
    # reported separately instead of inflating either "matched" or "gap".
    report = gap.build_report(status(
        unit('有总数', 'campus', expected=20, collected=20),
        unit('没总数', 'campus', expected=None, collected=17, status='partial', complete=False),
    ))
    summary = report['summary']
    rows = by_key(report['units'])
    assert rows[('没总数', 'campus')]['gap'] is None
    assert summary['units_matched'] == 1
    assert summary['units_with_gap'] == 0
    assert summary['units_without_expected_total'] == 1
    assert [row['company'] for row in report['units_without_expected_total']] == ['没总数']
    assert summary['total_gap'] == 0


def test_complete_but_short_is_its_own_highlighted_class():
    report = gap.build_report(status(
        unit('商汤科技', 'intern', expected=70, collected=66),
        unit('商汤科技', 'social', expected=87, collected=86),
        unit('美团', 'social', expected=2500, collected=320, status='partial', complete=False),
    ))
    summary = report['summary']
    assert summary['units_complete_but_short'] == 2
    assert summary['complete_but_short_gap'] == 5
    assert summary['units_partial_with_gap'] == 1
    assert summary['partial_gap'] == 2180
    assert summary['total_gap'] == 2185
    assert [f"{r['company']}/{r['scope']}" for r in report['complete_but_short']] == \
        ['商汤科技/intern', '商汤科技/social']
    assert report['partial_gap_top'][0]['company'] == '美团'


def test_company_rollup_sums_scopes_and_ranks_by_gap():
    report = gap.build_report(status(
        unit('美团', 'social', expected=2500, collected=320, status='partial', complete=False),
        unit('美团', 'intern', expected=399, collected=140, status='partial', complete=False),
        unit('美团', 'campus', expected=189, collected=40, status='partial', complete=False),
        unit('米哈游', 'social', expected=663, collected=650, status='partial', complete=False),
    ))
    assert report['per_company'][0] == {
        'company': '美团', 'gap': 2588, 'gap_units': 3, 'complete_but_short': 0,
        'scopes': ['social:2180', 'intern:259', 'campus:149']}
    assert report['per_company'][1]['company'] == '米哈游'
    assert report['summary']['top3_companies'][:2] == [
        {'company': '美团', 'gap': 2588}, {'company': '米哈游', 'gap': 13}]


def test_units_are_sorted_by_gap_descending():
    report = gap.build_report(status(
        unit('小', 'campus', expected=10, collected=9, status='partial', complete=False),
        unit('大', 'campus', expected=100, collected=1, status='partial', complete=False),
        unit('中', 'campus', expected=50, collected=40, status='partial', complete=False),
    ))
    assert [row['company'] for row in report['units']] == ['大', '中', '小']


def test_error_preview_is_kept_but_bounded():
    errors = ['boom %d' % i for i in range(30)]
    report = gap.build_report(status(
        unit('甲', 'campus', expected=10, collected=1, status='partial', complete=False,
             errors=errors)))
    row = report['units'][0]
    assert row['error_count'] == 30
    assert row['error_preview'] == ['boom 0', 'boom 1', 'boom 2']


# --- 2. thresholds and alerts ---------------------------------------------- #

def test_no_alerts_when_every_unit_matches():
    report = gap.build_report(status(unit('甲公司', 'campus', expected=10, collected=10)))
    assert gap.evaluate_alerts(report) == []


def test_a_single_complete_but_short_unit_alerts_as_critical():
    report = gap.build_report(status(unit('商汤科技', 'intern', expected=70, collected=66)))
    alerts = gap.evaluate_alerts(report)
    assert len(alerts) == 1
    assert alerts[0]['event'] == 'collection_gap.complete_but_short'
    assert alerts[0]['severity'] == 'critical'
    assert alerts[0]['units'] == ['商汤科技/intern 66/70']


def test_partial_gaps_alone_alert_only_above_the_company_threshold():
    small = gap.build_report(status(
        unit('小缺口', 'campus', expected=10, collected=1, status='partial', complete=False)))
    assert gap.evaluate_alerts(small) == [], '9 missing postings is below the 200 threshold'

    big = gap.build_report(status(
        unit('美团', 'social', expected=2500, collected=320, status='partial', complete=False)))
    alerts = gap.evaluate_alerts(big)
    assert [alert['event'] for alert in alerts] == ['collection_gap.company_gap']
    assert alerts[0]['company'] == '美团' and alerts[0]['gap'] == 2180
    assert alerts[0]['threshold'] == gap.COMPANY_GAP_ALERT_THRESHOLD


def test_threshold_boundary_is_strictly_greater_than_200():
    exact = gap.build_report(status(
        unit('甲公司', 'campus', expected=300, collected=100, status='partial', complete=False)))
    over = gap.build_report(status(
        unit('甲公司', 'campus', expected=301, collected=100, status='partial', complete=False)))
    assert gap.evaluate_alerts(exact) == []
    assert len(gap.evaluate_alerts(over)) == 1


# --- 3. previous-day comparison -------------------------------------------- #

def test_comparison_detects_new_wider_narrowed_and_resolved_gaps():
    previous = gap.build_report(status(
        unit('甲公司', 'campus', expected=10, collected=10),                      # -> new gap
        unit('乙公司', 'campus', expected=100, collected=50, status='partial', complete=False),
        unit('丙公司', 'social', expected=100, collected=90, status='partial', complete=False),
        unit('丁公司', 'social', expected=100, collected=40, status='partial', complete=False),
    ), date='20260919')
    current = gap.build_report(status(
        unit('甲公司', 'campus', expected=10, collected=7, status='partial', complete=False),
        unit('乙公司', 'campus', expected=100, collected=20, status='partial', complete=False),
        unit('丙公司', 'social', expected=100, collected=99, status='partial', complete=False),
        unit('丁公司', 'social', expected=100, collected=90, status='partial', complete=False),
        unit('戊公司', 'intern', expected=5, collected=1, status='partial', complete=False),
    ), date='20260920', previous=previous)

    comparison = current['comparison']
    assert comparison['previous_date'] == '20260919'
    new_gaps = {(item['company'], item['scope']): item['first_seen']
                for item in comparison['new_gaps']}
    assert new_gaps == {('甲公司', 'campus'): False, ('戊公司', 'intern'): True}
    assert [(item['company'], item['delta']) for item in comparison['wider_gaps']] == \
        [('乙公司', 30)]
    assert [(item['company'], item['delta']) for item in comparison['narrowed_gaps']] == \
        [('丁公司', -50), ('丙公司', -9)]
    assert comparison['resolved_gaps'] == []


def test_comparison_reports_resolved_gaps_and_no_previous_report():
    previous = gap.build_report(status(
        unit('甲公司', 'campus', expected=10, collected=4, status='partial', complete=False)),
        date='20260919')
    current = gap.build_report(status(unit('甲公司', 'campus', expected=10, collected=10)),
                               date='20260920', previous=previous)
    assert [item['company'] for item in current['comparison']['resolved_gaps']] == ['甲公司']
    assert current['comparison']['new_gaps'] == []

    first = gap.build_report(status(unit('甲公司', 'campus', expected=10, collected=10)),
                             date='20260920', previous=None)
    assert first['comparison']['previous_report'] is False
    assert first['comparison']['new_gaps'] == []


def test_find_previous_report_picks_the_latest_earlier_date(tmp_path):
    for date, company in (('20260918', '前前日'), ('20260919', '前日'), ('20260921', '未来')):
        directory = tmp_path / date
        directory.mkdir()
        (directory / gap.REPORT_JSON).write_text(json.dumps({'date': date, 'company': company}),
                                                 encoding='utf-8')
    found = gap.find_previous_report(tmp_path / '20260920', '20260920')
    assert found['date'] == '20260919'
    assert gap.find_previous_report(tmp_path / '20260918', '20260918') is None


# --- 4. writing the report -------------------------------------------------- #

def test_publish_writes_json_and_markdown_atomically(tmp_path):
    payload = status(
        unit('商汤科技', 'intern', expected=70, collected=66),
        unit('美团', 'social', expected=2500, collected=320, status='partial', complete=False),
        unit('没总数', 'campus', expected=None, collected=3, status='blocked', complete=False),
    )
    outcome = gap.publish(payload, tmp_path / '20260920', previous=None)
    assert outcome['date'] == '20260920'
    assert outcome['summary']['total_gap'] == 2184
    assert outcome['summary']['top3_companies'][0] == {'company': '美团', 'gap': 2180}

    report = json.loads((tmp_path / '20260920' / gap.REPORT_JSON).read_text(encoding='utf-8'))
    assert report['date'] == '20260920'
    assert len(report['units']) == 3
    markdown = (tmp_path / '20260920' / gap.REPORT_MD).read_text(encoding='utf-8')
    assert '# 采集缺口报告 20260920' in markdown
    assert '最严重:声称 complete 却少采' in markdown
    assert '商汤科技' in markdown and '美团' in markdown
    assert '站点不报总数的单元(1 个)' in markdown
    # No temp files left behind.
    assert not list((tmp_path / '20260920').glob('*.tmp'))


def test_publish_auto_discovers_the_previous_day(tmp_path):
    gap.publish(status(unit('甲公司', 'campus', expected=10, collected=3,
                            status='partial', complete=False)),
                tmp_path / '20260919', previous=None)
    outcome = gap.publish(status(unit('甲公司', 'campus', expected=10, collected=3,
                                      status='partial', complete=False)),
                          tmp_path / '20260920')
    assert outcome['comparison']['previous_date'] == '20260919'
    assert outcome['comparison']['wider_gaps'] == 0
    assert outcome['comparison']['new_gaps'] == 0


def test_run_date_prefers_the_run_directory_over_the_utc_start(tmp_path):
    # A 06:10 CST run starts at 22:10 UTC the previous day: the folder name wins.
    payload = status(unit('甲', 'campus', expected=1, collected=1),
                     started_at='2026-09-19T22:41:51+00:00')
    assert gap.run_date(tmp_path / '20260920', payload) == '20260920'
    assert gap.run_date(tmp_path / 'p1-runs' / '20260920T064151', payload) == '20260920'
    assert gap.run_date(tmp_path / 'reports', {'started_at': '2026-09-19T22:41:51+00:00'}) == '20260920'


def test_default_run_root_maps_data_dir_to_the_date_directory(tmp_path):
    assert gap.default_run_root(tmp_path / '20260920' / 'data') == tmp_path / '20260920'
    assert gap.default_run_root(tmp_path / 'elsewhere' / 'data',
                                tmp_path / 'run') == tmp_path / 'run'
    assert gap.default_run_root(tmp_path / 'var' / 'lib') == tmp_path / 'var' / 'lib'


# --- 5. alert delivery ------------------------------------------------------ #

def test_alerts_are_written_to_a_file_when_notify_is_absent(tmp_path):
    payload = status(unit('美团', 'social', expected=2500, collected=320,
                          status='partial', complete=False))
    outcome = gap.publish(payload, tmp_path / '20260920', previous=None, notify_module=None)
    alert_path = tmp_path / '20260920' / gap.ALERT_FILE
    assert alert_path.is_file()
    lines = [json.loads(line) for line in alert_path.read_text(encoding='utf-8').splitlines()]
    assert [line['event'] for line in lines] == ['collection_gap.company_gap']
    assert lines[0]['company'] == '美团' and lines[0]['gap'] == 2180
    assert outcome['notify']['sent'] is False
    assert 'cc-bot-notifier' in outcome['notify']['reason']


def test_alerts_go_through_the_notify_module_when_present(tmp_path):
    class FakeNotify:
        def __init__(self):
            self.calls = []

        def notify(self, event, **kwargs):
            self.calls.append((event, kwargs))
            return {'sent': True}

    fake = FakeNotify()
    payload = status(unit('美团', 'social', expected=2500, collected=320,
                          status='partial', complete=False),
                     unit('商汤科技', 'intern', expected=70, collected=66))
    outcome = gap.publish(payload, tmp_path / '20260920', previous=None, notify_module=fake)
    events = [event for event, _ in fake.calls]
    assert events == ['collection_gap.complete_but_short', 'collection_gap.company_gap']
    fields = fake.calls[0][1]['fields']
    assert fields['count'] == 1 and fields['severity'] == 'critical'
    assert outcome['notify'] == {'channel': 'qiuzhao.notify', 'sent': True,
                                 'deliveries': outcome['notify']['deliveries']}
    assert outcome['notify']['sent'] is True


def test_a_broken_notifier_never_breaks_the_report(tmp_path):
    class Exploding:
        def notify(self, event, **kwargs):
            raise RuntimeError('boom')

    payload = status(unit('美团', 'social', expected=2500, collected=320,
                          status='partial', complete=False))
    outcome = gap.publish(payload, tmp_path / '20260920', previous=None,
                          notify_module=Exploding())
    assert (tmp_path / '20260920' / gap.REPORT_JSON).is_file()
    assert outcome['notify']['sent'] is False
    assert 'boom' in outcome['notify']['deliveries'][0]['error']


def test_no_alert_file_is_written_when_there_is_nothing_to_alert(tmp_path):
    payload = status(unit('甲公司', 'campus', expected=10, collected=10))
    outcome = gap.publish(payload, tmp_path / '20260920', previous=None)
    assert outcome['alerts'] == []
    assert outcome['alert_file'] is None
    assert not (tmp_path / '20260920' / gap.ALERT_FILE).exists()


# --- 6. the real 2026-09-20 shape ------------------------------------------- #

def test_the_2026_09_20_morning_shape_is_reproduced_end_to_end(tmp_path):
    """958 units, 814 matching, the 2 complete-but-short units and 美团's 2588."""
    units = []
    for index in range(814):
        units.append(unit('吻合%03d' % index, 'campus', expected=10, collected=10))
    units.append(unit('商汤科技', 'intern', expected=70, collected=66))
    units.append(unit('商汤科技', 'social', expected=87, collected=86))
    units.append(unit('美团', 'social', expected=2500, collected=320,
                      status='partial', complete=False))
    units.append(unit('美团', 'intern', expected=399, collected=140,
                      status='partial', complete=False))
    units.append(unit('美团', 'campus', expected=189, collected=40,
                      status='partial', complete=False))
    # The other 15 honest partial gaps add up to the remaining 43 postings.
    units.append(unit('米哈游', 'social', expected=663, collected=634,
                      status='partial', complete=False))
    for index in range(14):
        units.append(unit('零头%02d' % index, 'campus', expected=20, collected=19,
                          status='partial', complete=False))
    for index in range(124):
        units.append(unit('无总数%03d' % index, 'social', expected=None, collected=5,
                          status='blocked', complete=False))

    outcome = gap.publish(status(*units), tmp_path / '20260920', previous=None)
    summary = outcome['summary']
    assert summary['units_total'] == 958
    assert summary['units_matched'] == 814
    assert summary['units_with_expected_total'] == 834
    assert summary['units_complete_but_short'] == 2
    assert summary['complete_but_short_gap'] == 5
    assert summary['units_partial_with_gap'] == 18
    assert summary['partial_gap'] == 2588 + 43
    assert summary['total_gap'] == 5 + 2588 + 43
    assert summary['units_without_expected_total'] == 124
    assert summary['top3_companies'][0] == {'company': '美团', 'gap': 2588}
    assert outcome['alerts'][0]['event'] == 'collection_gap.complete_but_short'
    assert outcome['alerts'][1]['company'] == '美团'


# --- 7. the Windows chain surfaces the summary in receipt.json --------------- #

def _windows_collector():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / 'deploy' / 'windows_collector.py'
    spec = importlib.util.spec_from_file_location('windows_collector_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gap_summary_reads_the_report_when_p1_wrote_one(tmp_path):
    wc = _windows_collector()
    run = tmp_path / '20260920'
    stage = run / 'data'
    stage.mkdir(parents=True)
    payload = status(unit('商汤科技', 'intern', expected=70, collected=66))
    gap.publish(payload, run, previous=None)

    summary = wc.collection_gap_summary(run, stage)
    assert summary['available'] is True
    assert summary['units_complete_but_short'] == 1
    assert summary['complete_but_short_gap'] == 4
    assert summary['date'] == '20260920'
    assert summary['report'].endswith('collection-gap.json')


def test_gap_summary_rebuilds_the_report_when_p1_was_killed_before_its_final_step(tmp_path):
    # 2026-09-20: p1 hit its 18000s deadline and the 18100s step timeout killed it before
    # it could write the report.  The receipt must still carry the numbers.
    wc = _windows_collector()
    run = tmp_path / '20260920'
    stage = run / 'data'
    run_dir = stage / 'p1-runs' / '20260920T064151'
    run_dir.mkdir(parents=True)
    payload = status(unit('美团', 'social', expected=2500, collected=320,
                          status='partial', complete=False),
                     unit('美团', 'campus', expected=189, collected=40,
                          status='partial', complete=False))
    (run_dir / 'status.json').write_text(json.dumps(payload, ensure_ascii=False),
                                         encoding='utf-8')
    assert not (run / 'collection-gap.json').exists()

    summary = wc.collection_gap_summary(run, stage)
    assert summary['available'] is True
    assert summary['total_gap'] == 2329
    assert summary['top3_companies'] == [{'company': '美团', 'gap': 2329}]
    assert (run / 'collection-gap.json').is_file()
    assert (run / 'collection-gap.md').is_file()


def test_gap_summary_degrades_without_a_report_or_a_status(tmp_path):
    wc = _windows_collector()
    run = tmp_path / '20260920'
    (run / 'data').mkdir(parents=True)
    summary = wc.collection_gap_summary(run, run / 'data')
    assert summary['available'] is False
    assert 'no p1 run status' in summary['reason']


def test_gap_summary_reports_a_broken_report_instead_of_raising(tmp_path):
    wc = _windows_collector()
    run = tmp_path / '20260920'
    stage = run / 'data'
    stage.mkdir(parents=True)
    (run / gap.REPORT_JSON).write_text('{not json', encoding='utf-8')
    summary = wc.collection_gap_summary(run, stage)
    assert summary['available'] is False
    assert 'JSONDecodeError' in summary['error']


# --- 8. unknown is never 0; planned-but-not-started units ------------------- #

def _previous_gap_10():
    return gap.build_report(status(
        unit('甲公司', 'campus', expected=20, collected=10, status='partial', complete=False)),
        date='20260922')


def test_previous_gap_is_not_resolved_by_an_unknown_or_failed_round():
    previous = _previous_gap_10()
    for current_unit in (
            unit('甲公司', 'campus', expected=None, collected=0, status='failed', complete=False),
            unit('甲公司', 'campus', expected=None, collected=None, status='blocked', complete=False),
            # Numbers match but the round was not a clean complete success.
            unit('甲公司', 'campus', expected=20, collected=20, status='partial', complete=False),
    ):
        comparison = gap.build_report(status(current_unit), date='20260923',
                                      previous=previous)['comparison']
        assert comparison['resolved_gaps'] == []
        assert [(item['company'], item['previous_gap']) for item in comparison['unknown_gaps']] \
            == [('甲公司', 10)]


def test_previous_gap_is_resolved_only_by_a_reliable_complete_zero():
    comparison = gap.build_report(status(unit('甲公司', 'campus', expected=20, collected=20)),
                                  date='20260923', previous=_previous_gap_10())['comparison']
    assert comparison['resolved_gaps'] == [
        {'company': '甲公司', 'scope': 'campus', 'previous_gap': 10}]
    assert comparison['unknown_gaps'] == []


def test_previous_gap_missing_from_this_round_stays_unknown():
    comparison = gap.build_report(status(unit('乙公司', 'campus', expected=5, collected=5)),
                                  date='20260923', previous=_previous_gap_10())['comparison']
    assert comparison['resolved_gaps'] == []
    assert comparison['unknown_gaps'][0]['reason'] == 'not_in_this_round'


def test_known_gap_after_unknown_or_first_seen_zero_does_not_crash():
    previous = gap.build_report(status(
        unit('甲公司', 'campus', expected=None, collected=3, status='partial', complete=False)),
        date='20260922')
    comparison = gap.build_report(status(
        unit('甲公司', 'campus', expected=10, collected=4, status='partial', complete=False),
        unit('新公司', 'campus', expected=10, collected=10)),
        date='20260923', previous=previous)['comparison']
    assert [(item['company'], item['previous_gap'], item['first_seen'])
            for item in comparison['new_gaps']] == [('甲公司', None, False)]
    assert comparison['resolved_gaps'] == [] and comparison['wider_gaps'] == []


def test_pending_plan_adds_not_started_units_with_unknown_gap():
    payload = status(unit('甲公司', 'campus', expected=10, collected=10))
    payload['pending'] = ['乙公司/intern', '甲公司/intern']
    report = gap.build_report(payload, date='20260923', previous=_previous_gap_10())
    summary = report['summary']
    rows = by_key(report['units'])
    # A paused pending lists real targets, but it is not proof of the whole plan.
    assert summary['report_scope'] == 'incomplete' and summary['plan_source'] == 'pending'
    assert summary['plan_issue'] == 'no_target_list' and summary['plan_complete'] is False
    assert summary['units_planned'] is None and summary['units_known_planned'] == 3
    assert summary['units_total'] == 3
    assert summary['units_not_started'] == 2
    assert summary['units_gap_unknown'] == 2
    assert rows[('乙公司', 'intern')]['gap'] is None
    assert rows[('乙公司', 'intern')]['status'] == 'not_started'
    # Not started is neither a match, a gap, nor a "site gives no total" unit.
    assert summary['units_matched'] == 1 and summary['units_with_gap'] == 0
    assert summary['units_without_expected_total'] == 0 and summary['total_gap'] == 0
    # Only planned scopes appear: 乙公司 social was never planned, so it is not a gap.
    assert ('乙公司', 'social') not in rows and ('甲公司', 'social') not in rows


def test_explicit_plan_wins_and_not_started_previous_gap_is_unknown():
    payload = status(unit('乙公司', 'campus', expected=5, collected=5))
    payload['batch_plan'] = [['乙公司', 'campus']]
    report = gap.build_report(payload, date='20260923', previous=_previous_gap_10(),
                              plan=[('乙公司', 'campus'), ('甲公司', 'campus')])
    assert report['summary']['plan_source'] == 'argument'
    assert report['summary']['units_planned'] == 2
    unknown = report['comparison']['unknown_gaps']
    assert [(item['company'], item['reason']) for item in unknown] == [('甲公司', 'not_started')]
    assert report['comparison']['resolved_gaps'] == []


def test_without_a_plan_the_report_says_it_covers_results_only(tmp_path):
    payload = status(unit('甲公司', 'campus', expected=10, collected=10))
    outcome = gap.publish(payload, tmp_path / '20260923', previous=None)
    assert outcome['summary']['report_scope'] == 'results_only'
    assert outcome['summary']['units_planned'] is None
    assert outcome['summary']['units_not_started'] == 0
    markdown = (tmp_path / '20260923' / gap.REPORT_MD).read_text(encoding='utf-8')
    assert '仅已产出结果的单元' in markdown


# --- 9. review fixes: comparison noise, stale pending, out-of-plan results --- #

def test_unknown_gaps_only_track_a_previous_positive_gap():
    previous = gap.build_report(status(
        unit('零公司', 'campus', expected=5, collected=5),
        unit('未知公司', 'campus', expected=None, collected=3, status='partial', complete=False),
        unit('甲公司', 'campus', expected=20, collected=10, status='partial', complete=False),
        unit('收窄公司', 'campus', expected=20, collected=10, status='partial', complete=False)),
        date='20260922')
    current = gap.build_report(status(
        unit('零公司', 'campus', expected=None, collected=0, status='failed', complete=False),
        unit('未知公司', 'campus', expected=None, collected=0, status='failed', complete=False),
        unit('甲公司', 'campus', expected=None, collected=0, status='failed', complete=False),
        unit('收窄公司', 'campus', expected=20, collected=15, status='failed', complete=False)),
        date='20260923', previous=previous)
    comparison = current['comparison']
    assert [(item['company'], item['previous_gap']) for item in comparison['unknown_gaps']] \
        == [('甲公司', 10)]
    assert [item['company'] for item in comparison['narrowed_gaps']] == ['收窄公司']
    assert comparison['resolved_gaps'] == []
    # The old 0 / old unknown units are still visible as unknown in the summary.
    assert current['summary']['units_gap_unknown'] == 3


def _resumed_status(run_finished):
    # Resume added 丙公司 and died before pending was rewritten.
    payload = status(unit('甲公司', 'campus', expected=10, collected=10),
                     unit('乙公司', 'campus', expected=5, collected=5))
    payload['companies'] = ['甲公司', '乙公司', '丙公司']
    payload['pending'] = ['乙公司/intern']
    if run_finished is not None:
        payload['run_finished'] = run_finished
    return payload


@pytest.mark.parametrize('run_finished', [None, False, True])
def test_stale_pending_after_resume_added_a_company_is_not_a_full_plan(run_finished):
    report = gap.build_report(_resumed_status(run_finished), date='20260923')
    summary = report['summary']
    assert summary['report_scope'] == 'incomplete' and summary['plan_complete'] is False
    assert summary['plan_issue'] == 'targets_missing_from_plan'
    assert summary['targets_missing_from_plan'] == ['丙公司']
    assert summary['units_planned'] is None
    # No target is invented for 丙公司; the real pending unit is still shown.
    rows = by_key(report['units'])
    assert not any(company == '丙公司' for company, _ in rows)
    assert rows[('乙公司', 'intern')]['status'] == 'not_started'
    assert '分母未知' in gap.render_markdown(report)


def test_pending_is_a_plan_only_after_a_finished_run_covering_every_target():
    payload = status(unit('甲公司', 'campus', expected=10, collected=10),
                     unit('乙公司', 'intern', expected=5, collected=5))
    payload.update(companies=['甲公司', '乙公司'], pending=['乙公司/campus'], run_finished=False)
    summary = gap.build_report(payload, date='20260923')['summary']
    assert summary['report_scope'] == 'incomplete' and summary['plan_issue'] == 'run_not_finished'

    payload.update(pending=[], run_finished=True)
    summary = gap.build_report(payload, date='20260923')['summary']
    assert summary['report_scope'] == 'planned' and summary['plan_complete'] is True
    assert summary['units_planned'] == 2 and summary['units_out_of_plan'] == 0


def test_batch_plan_missing_a_target_company_is_incomplete():
    payload = status(unit('甲公司', 'campus', expected=10, collected=10))
    payload.update(companies=['甲公司', '乙公司'], batch_plan=[['甲公司', 'campus']])
    summary = gap.build_report(payload, date='20260923')['summary']
    assert summary['report_scope'] == 'incomplete'
    assert summary['targets_missing_from_plan'] == ['乙公司']


@pytest.mark.parametrize('field', ['plan', 'batch_plan'])
def test_empty_plan_with_real_results_is_out_of_plan(field):
    payload = status(unit('甲公司', 'campus', expected=10, collected=8,
                          status='partial', complete=False))
    kwargs = {}
    if field == 'plan':
        kwargs['plan'] = []
    else:
        payload['batch_plan'] = []
    report = gap.build_report(payload, date='20260923', **kwargs)
    summary = report['summary']
    assert summary['report_scope'] == 'out_of_plan' and summary['plan_complete'] is False
    assert summary['units_planned'] == 0 and summary['units_total'] == 1
    assert summary['units_out_of_plan'] == 1
    assert report['units_out_of_plan'] == [{'company': '甲公司', 'scope': 'campus'}]
    # The real result is kept and counted.
    assert summary['total_gap'] == 2
    assert '计划外结果 1 个' in gap.render_markdown(report)


def test_result_outside_a_real_plan_is_flagged_and_kept():
    payload = status(unit('甲公司', 'campus', expected=10, collected=10),
                     unit('外公司', 'campus', expected=4, collected=4))
    report = gap.build_report(payload, date='20260923', plan=[('甲公司', 'campus'),
                                                               ('甲公司', 'intern')])
    summary = report['summary']
    assert summary['report_scope'] == 'out_of_plan'
    assert summary['units_out_of_plan'] == 1 and summary['units_total'] == 3
    assert ('外公司', 'campus') in by_key(report['units'])


def test_real_full_plan_stays_planned():
    payload = status(unit('甲公司', 'campus', expected=10, collected=10))
    payload.update(companies=['甲公司', '乙公司'],
                   batch_plan=[['甲公司', 'campus'], ['乙公司', 'intern']])
    report = gap.build_report(payload, date='20260923')
    summary = report['summary']
    assert summary['report_scope'] == 'planned' and summary['plan_complete'] is True
    assert summary['units_planned'] == 2 and summary['units_not_started'] == 1
    assert summary['units_out_of_plan'] == 0 and summary['plan_issue'] is None
    assert '本轮计划 2 个单元' in gap.render_markdown(report)
