"""detail_cache_reused is an observation, not a change in the advertised job.

p1_pipeline.merge_records counts ``updated`` as
``business_value(old) != business_value(incoming)``; these tests pin that contract.
"""
from __future__ import annotations

import copy

from qiuzhao.normalize import OBSERVATION_FIELDS, business_value


def job(**overrides):
    row = {'id': 'a', 'title': '算法工程师', 'status': 'open',
           'description_raw': '负责推荐算法', 'detail_checked_at': '2026-09-22T06:00:00',
           'detail_cache_reused': False}
    row.update(overrides)
    return row


def updated(old, new):
    return int(business_value(old) != business_value(new))


def test_cache_flag_flip_is_not_a_business_update_in_either_direction():
    fetched, reused = job(detail_cache_reused=False), job(detail_cache_reused=True)
    assert updated(fetched, reused) == 0
    assert updated(reused, fetched) == 0
    assert updated(job(), {k: v for k, v in job().items() if k != 'detail_cache_reused'}) == 0


def test_real_description_and_status_changes_still_count():
    old = job(detail_cache_reused=False)
    assert updated(old, job(detail_cache_reused=True, description_raw='负责搜索算法')) == 1
    assert updated(old, job(detail_cache_reused=True, status='expired')) == 1
    assert updated(old, job(title='高级算法工程师')) == 1


def test_observation_field_is_kept_on_the_row():
    row = job(detail_cache_reused=True)
    before = copy.deepcopy(row)
    business_value(row)
    assert row == before and row['detail_cache_reused'] is True
    assert 'detail_cache_reused' in OBSERVATION_FIELDS
