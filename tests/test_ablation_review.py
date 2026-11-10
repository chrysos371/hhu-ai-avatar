import csv
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('ablation_review', Path(__file__).resolve().parents[1]/'scripts/build_reliability_ablation_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def fixture_config(tmp_path, monkeypatch):
    monkeypatch.setattr(review, 'ROOT', tmp_path)
    cases = [dict(id=f'case-{i}',turns=['用户原话'],checks=['完整交付']) for i in range(4)]
    (tmp_path/'suite.json').write_text(json.dumps(dict(cases=cases)))
    for arm in ('before','after'):
        rows={c['id']:dict(turns=[dict(user='用户原话',reply=arm+'正文')]) for c in cases}
        (tmp_path/(arm+'.json')).write_text(json.dumps(rows))
    config=dict(suites=['suite.json'],arms=[dict(name=arm,inputs=[arm+'.json']) for arm in ('before','after')])
    path=tmp_path/'config.json'
    path.write_text(json.dumps(config))
    return path


def test_packet_has_balanced_positions_and_strict_blank_csv(tmp_path,monkeypatch):
    config=fixture_config(tmp_path,monkeypatch)
    out=tmp_path/'review'
    review.build(config,out)
    rows=list(csv.DictReader((out/'human-review.csv').open()))
    assert len(rows)==4
    assert all(None not in r and all(not v for k,v in r.items() if k!='case_id') for r in rows)
    keys=json.loads((out/'unblinding-key.json').read_text())
    assert sum(v['A']=='before' for v in keys.values())==2
    assert sum(v['B']=='before' for v in keys.values())==2
    with pytest.raises(ValueError,match='already exists'):
        review.build(config,out)


def test_reject_changed_user_turn_before_writing_packet(tmp_path,monkeypatch):
    config=fixture_config(tmp_path,monkeypatch)
    path=tmp_path/'after.json'
    rows=json.loads(path.read_text())
    rows['case-0']['turns'][0]['user']='different'
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='turns mismatch'):
        review.build(config,tmp_path/'review')
    assert not (tmp_path/'review').exists()
