import hashlib
import json
from pathlib import Path
import pytest
from qiuzhao.collector import import_p1_candidates as I


def author_manifest(tmp_path):
    scope=tmp_path/'source'/'campus';scope.mkdir(parents=True)
    evidence=scope/'list.json';evidence.write_text('{"total":1}')
    raw={'jobs':[{'source_record_id':'a','job_title':'工程师','description_raw':'岗位职责及要求',
                   'recruitment_unit':'大疆','recruitment_type':'校园招聘','detail_url':'https://careers.dji.com/job/a',
                   'reviewed_at':'2026-09-12T10:00:00+00:00','evidence_path':str(evidence)}],
         'coverage':{'status':'success','complete':True,'detail_complete':True,'expected_total':1,'collected_jobs':1,
                     'source_url':'https://careers.dji.com/jobs','errors':[],'evidence':[str(evidence)],
                     'evidence_files':[str(evidence)],'scope_evidence':'official campus channel',
                     'scope_request':{'company':'大疆','scope':'campus','source_url':'https://careers.dji.com/jobs','params':{}}}}
    candidate=scope/'candidate.json';candidate.write_text(json.dumps(raw))
    manifest=tmp_path/'author.json';manifest.write_text(json.dumps({'rows':[{'company':'大疆','scope':'campus',
        'candidate':str(candidate),'sha256':I.P.sha(candidate)}]}))
    return manifest


def test_bundle_preserves_source_time_and_has_separate_import_receipt(tmp_path):
    manifest=author_manifest(tmp_path);bundle=tmp_path/'bundle'
    I.build([manifest],bundle)
    data=tmp_path/'data';data.mkdir();(data/'jobs.json').write_text('[]')
    assert I.import_bundle(bundle,data)['validated_scopes']==1
    receipt=I.import_bundle(bundle,data,True)
    rows=json.loads((data/'jobs.json').read_text())
    assert len(rows)==1 and rows[0]['reviewed_at']=='2026-09-12T10:00:00+00:00'
    assert receipt['finished'] and not (data/'p1-status.json').exists()
    previous=(data/'jobs.json').read_bytes()
    I.import_bundle(bundle,data,True)
    assert (data/'jobs.json').read_bytes()==previous


def test_tampered_evidence_and_path_escape_fail_before_publish(tmp_path):
    manifest=author_manifest(tmp_path);bundle=tmp_path/'bundle';I.build([manifest],bundle)
    data=tmp_path/'data';data.mkdir();(data/'jobs.json').write_text('[]')
    (bundle/'02/campus/list.json').write_text('tampered')
    with pytest.raises(ValueError,match='bundle hash mismatch'):I.import_bundle(bundle,data,True)
    assert (data/'jobs.json').read_text()=='[]'
    with pytest.raises(ValueError,match='escapes root'):I.safe_path(bundle,'../outside')
