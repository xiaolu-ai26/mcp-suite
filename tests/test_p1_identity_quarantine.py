"""The static tupu360 identity quarantine (18 approved identities, 2026-09-24).

merge_records must hold back exactly the listed tupu360 candidates, leave every
existing row alone, and merge everything else as before. No network, no data dir.
"""
import copy
import hashlib
import json

import pytest

from qiuzhao.collector import p1_pipeline as p

LIST = json.loads(p.IDENTITY_QUARANTINE_PATH.read_text(encoding='utf-8'))
ENTRIES = LIST['entries']


def cid(company, scope, source_id):
    return 'p1-' + hashlib.sha256(f'{company}|{scope}|{source_id}'.encode()).hexdigest()[:24]


def tupu_row(company, scope, source_id, tenant):
    return {'source_record_id': source_id, 'job_title': 'T ' + source_id, 'description_raw': '岗位职责：测试。',
            'recruitment_unit': company, 'recruitment_type': p.SCOPES[scope],
            'detail_url': f'https://careersite.tupu360.com/{tenant}/position/detail?positionId={source_id}'
                          f'&recruitmentType=X&currentLang=zh_CN', 'status': 'open'}


def complete_result(company, scope, rows):
    payload = {'jobs': rows, 'coverage': {
        'status': 'success', 'complete': True, 'detail_complete': True, 'errors': [],
        'expected_total': len(rows), 'collected_jobs': len(rows), 'pages_scanned': 1,
        'source_url': 'https://careersite.tupu360.com/x/position/index', 'evidence': ['list.html'],
        'scope_evidence': 'official tupu360 careersite'}}
    return p.validate_result(payload, company, scope)


def unit(company, scope, tenant, extra_ids=()):
    listed = [e['source_record_id'] for e in ENTRIES if e['company'] == company and e['scope'] == scope]
    return complete_result(company, scope, [tupu_row(company, scope, sid, tenant)
                                            for sid in [*listed, *extra_ids]])


def test_the_list_is_the_approved_18_with_traceable_evidence():
    assert len(ENTRIES) == 18
    reasons = [e['reason'] for e in ENTRIES]
    assert reasons.count('same_posting_existing') == 11
    assert reasons.count('pending_cross_source_title_only') == 7
    assert {(e['company'], e['tenant']) for e in ENTRIES} == {('Intel', 'intel'), ('西门子中国', 'siemens')}
    assert len(p.load_identity_quarantine()) == 18
    for e in ENTRIES:
        assert e['candidate_id'] == cid(e['company'], e['scope'], e['source_record_id'])
        if e['reason'] == 'same_posting_existing':
            jr = e['evidence']['requisition_id']
            assert e['job_title'].startswith(jr)
            assert all(row['detail_url'].endswith('_' + jr) for row in e['evidence']['canonical_rows'])
        else:
            assert e['evidence']['title_match_rows']
    assert set(LIST['_provenance']['counts'].values()) == {11, 7}


def test_listed_identities_are_never_added_and_the_rest_merge_normally():
    results = [('Intel', 'campus', unit('Intel', 'campus', 'intel', ('free-c1', 'free-c2'))),
               ('Intel', 'intern', unit('Intel', 'intern', 'intel', ('free-i1',))),
               ('西门子中国', 'campus', unit('西门子中国', 'campus', 'siemens', ('free-s1',)))]
    before = copy.deepcopy(results)
    merged, changes = p.merge_records([], results)
    ids = {row['id'] for row in merged}
    assert not ids & {e['candidate_id'] for e in ENTRIES}
    assert ids == {cid('Intel', 'campus', 'free-c1'), cid('Intel', 'campus', 'free-c2'),
                   cid('Intel', 'intern', 'free-i1'), cid('西门子中国', 'campus', 'free-s1')}
    assert changes['added'] == 4 and changes['quarantined'] == 18
    trace = {q['candidate_id']: q for q in changes['quarantined_identities']}
    assert set(trace) == {e['candidate_id'] for e in ENTRIES}
    assert {q['reason'] for q in trace.values()} == p.IDENTITY_QUARANTINE_REASONS
    assert all(q['list'] == 'tupu360_identity_quarantine.json' for q in trace.values())
    # Unit results (expected/collected/complete, raw rows) are not rewritten by the merge.
    assert results == before
    assert results[0][2]['coverage']['collected_jobs'] == results[0][2]['coverage']['expected_total'] == 12


def test_existing_rows_are_not_rewritten_retired_or_retyped():
    same = next(e for e in ENTRIES if e['reason'] == 'same_posting_existing' and e['scope'] == 'campus')
    workday = dict(same['evidence']['canonical_rows'][0], p1_identity=same['evidence']['canonical_rows'][0]['id'],
                   job_title='Workday row', status='open')
    assert workday['recruitment_type'] == '社会招聘'
    # A row already stored under a listed tupu360 identity (e.g. published earlier).
    stored = {'id': same['candidate_id'], 'p1_identity': same['candidate_id'], 'p1_company': 'Intel',
              'p1_scope': 'campus', 'recruitment_type': '校园招聘', 'job_title': 'stored', 'status': 'open',
              'detail_url': same['detail_url'], 'description_raw': 'old text'}
    gone = {'id': cid('Intel', 'campus', 'gone'), 'p1_identity': cid('Intel', 'campus', 'gone'),
            'p1_company': 'Intel', 'p1_scope': 'campus', 'recruitment_type': '校园招聘', 'status': 'open',
            'detail_url': 'https://careersite.tupu360.com/intel/position/detail?positionId=gone'}
    previous = [copy.deepcopy(workday), copy.deepcopy(stored), copy.deepcopy(gone)]
    merged, changes = p.merge_records(previous, [('Intel', 'campus', unit('Intel', 'campus', 'intel'))])
    assert merged[0] == workday and merged[0]['recruitment_type'] == '社会招聘'
    assert merged[1] == stored                      # not overwritten, not retired
    assert merged[2]['status'] == 'removed'         # retirement still follows the full official list
    assert changes['removed'] == 1 and changes['added'] == 0 and changes['updated'] == 0


def test_a_row_that_does_not_match_every_identity_field_is_not_held_back():
    e = next(x for x in ENTRIES if x['company'] == 'Intel' and x['scope'] == 'campus')
    other_tenant = complete_result('Intel', 'campus', [tupu_row('Intel', 'campus', e['source_record_id'], 'intelcampus')])
    other_company = complete_result('英特尔（校招）', 'campus',
                                    [tupu_row('英特尔（校招）', 'campus', e['source_record_id'], 'intel')])
    other_scope = complete_result('Intel', 'social', [tupu_row('Intel', 'social', e['source_record_id'], 'intel')])
    merged, changes = p.merge_records([], [('Intel', 'campus', other_tenant), ('英特尔（校招）', 'campus', other_company),
                                           ('Intel', 'social', other_scope)])
    assert changes['added'] == 3 and 'quarantined' not in changes


def test_other_sources_never_read_the_list(monkeypatch, tmp_path):
    monkeypatch.setattr(p, 'IDENTITY_QUARANTINE_PATH', tmp_path / 'missing.json')
    e = next(x for x in ENTRIES if x['company'] == 'Intel')
    row = tupu_row('英特尔', 'campus', e['source_record_id'], 'intel')
    merged, changes = p.merge_records([], [('英特尔', 'campus', complete_result('英特尔', 'campus', [row]))])
    assert p.REGISTRY['英特尔'] != p.TUPU360_MODULE and changes['added'] == 1


@pytest.mark.parametrize('body', ['{}', '{"entries": [{"module": "x"}]}', 'not json'])
def test_a_broken_list_fails_the_tupu360_merge_loudly(monkeypatch, tmp_path, body):
    bad = tmp_path / 'q.json'
    bad.write_text(body, encoding='utf-8')
    monkeypatch.setattr(p, 'IDENTITY_QUARANTINE_PATH', bad)
    with pytest.raises(ValueError):
        p.merge_records([], [('Intel', 'campus', unit('Intel', 'campus', 'intel'))])


def test_a_tampered_candidate_id_is_rejected(monkeypatch, tmp_path):
    data = copy.deepcopy(LIST)
    data['entries'][0]['candidate_id'] = 'p1-000000000000000000000000'
    bad = tmp_path / 'q.json'
    bad.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='candidate_id'):
        p.load_identity_quarantine(bad)


def test_same_tenant_on_another_host_is_not_held_back():
    e = next(x for x in ENTRIES if x['company'] == 'Intel' and x['scope'] == 'campus')
    assert p._source_host(e['detail_url']) == 'careersite.tupu360.com'
    rows = []
    for host in ('evil.example.com', 'careersite.tupu360.com.evil.net', 'x.careersite.tupu360.com',
                 'careersite.tupu360.com:8443'):
        row = tupu_row('Intel', 'campus', e['source_record_id'], 'intel')
        row['detail_url'] = row['detail_url'].replace('careersite.tupu360.com', host)
        merged, changes = p.merge_records([], [('Intel', 'campus', complete_result('Intel', 'campus', [row]))])
        assert changes['added'] == 1 and 'quarantined' not in changes, host
    # Host case is normalized: the official host in upper case is still the same source.
    row = tupu_row('Intel', 'campus', e['source_record_id'], 'intel')
    row['detail_url'] = row['detail_url'].replace('careersite.tupu360.com', 'CareerSite.Tupu360.com')
    merged, changes = p.merge_records([], [('Intel', 'campus', complete_result('Intel', 'campus', [row]))])
    assert changes['added'] == 0 and changes['quarantined'] == 1
    trace = changes['quarantined_identities'][0]
    assert trace['host'] == 'careersite.tupu360.com' and trace['requisition_id'] == e['evidence']['requisition_id']
    assert trace['basis'] == e['evidence']['basis']


def test_an_entry_without_a_detail_url_is_rejected(tmp_path):
    data = copy.deepcopy(LIST)
    data['entries'][0].pop('detail_url')
    bad = tmp_path / 'q.json'
    bad.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='required key'):
        p.load_identity_quarantine(bad)
