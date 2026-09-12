import copy
import pytest
from qiuzhao.collector.p1_status_repair import repair_rows
UUID='7d6cd396-a45a-420d-a8c0-e2ad3261f0b9'

def test_only_exact_owned_identity_changes_and_dates_content_are_preserved():
    row={'id':'legacy-id','p1_company':'大疆','p1_scope':'social','source_record_id':UUID,'status':'unverified','description_raw':'original','reviewed_at':'yesterday','deadline':None}
    patch={'company':'大疆','scope':'social','source_record_id':UUID,'updates':{'status':'expired','source_is_active':False,'source_list_status_raw':'pause','status_note':'暂停'}}
    original=copy.deepcopy(row);result,changes=repair_rows([row], [patch])
    assert row==original and result[0]['status']=='expired' and result[0]['deadline'] is None
    assert result[0]['description_raw']=='original' and result[0]['reviewed_at']=='yesterday'
    assert len(changes)==1 and changes[0]['id']=='legacy-id'
    assert repair_rows(result,[patch])[1]==[]
    assert repair_rows([{**row,'p1_company':'其他'}],[patch])[1]==[]
    patch['updates']['description_raw']='forged'
    with pytest.raises(ValueError):repair_rows([row],[patch])


def test_response_must_show_same_id_and_official_status():
    from qiuzhao.collector.p1_status_repair import evidence_has_status
    response={'data':{'jobs':[{'id':UUID,'status':'pause'}]}}
    assert evidence_has_status(response,UUID,'pause')
    assert not evidence_has_status(response,UUID,'closed')
    assert not evidence_has_status(response,'other','pause')
