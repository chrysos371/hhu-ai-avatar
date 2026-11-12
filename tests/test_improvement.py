import fcntl
import json
from pathlib import Path
import pytest
from avatar.lab.improvement import Store, signals, summary, run, report, exclusive


def test_dedup_keeps_repeat_evidence_but_not_duplicate_import(tmp_path):
    store=Store(tmp_path)
    rows=[{'case':'return','turn':1,'user':'我去吃饭','reply':'晚安'},
          {'case':'return','turn':2,'user':'回来啦','reply':'晚安'}]
    assert store.ingest(rows,'a')==2
    assert store.ingest(rows,'a')==0
    assert store.ingest(rows,'b')==2
    data=summary(tmp_path)
    assert len(data['issues'])==2
    assert sum(x['occurrences'] for x in data['issues'])==4
    assert data['automatic_release'] is False
    store.close()


def test_readonly_summary_does_not_initialize_state(tmp_path):
    root=tmp_path/'absent'
    assert not summary(root)['available']
    assert not root.exists()


def test_negative_and_format_controls():
    assert 'unexpected_goodnight' not in signals('晚饭后我要睡觉，晚安','晚安')
    assert 'invalid_json' not in signals('只输出JSON', '{"a":1}')
    assert 'invalid_json' in signals('只输出JSON', '```json\n{}\n```')
    assert 'title_format' in signals('只给四字标题','标题：海边读书')
    assert signals('只给四字标题','海边读书')==[]
    assert 'possible_unwanted_advice' in signals('先别教我怎么办','你可以先休息')


def test_budget_rotation_and_isolation(tmp_path):
    roots=[]
    class Fake:
        def __init__(self,path):roots.append(path)
        def chat(self,*args):return {'reply':'收到','trace':{'generation_mode':'llm','reply_degraded':False}}
    first=run(tmp_path,max_turns=3,daily_turns=6,chat_factory=Fake)
    second=run(tmp_path,max_turns=3,daily_turns=6,chat_factory=Fake)
    third=run(tmp_path,max_turns=3,daily_turns=6,chat_factory=Fake)
    assert first['turns']==second['turns']==3
    assert third['status']=='skipped_budget'
    assert len(set(roots))==2
    assert all(p.is_relative_to(tmp_path/'runs') for p in roots)
    assert (tmp_path/'latest.json').exists()
    assert len(summary(tmp_path)['runs'])==2


def test_error_counts_against_budget_and_stops_calls(tmp_path):
    class Broken:
        def __init__(self,path):pass
        def chat(self,*args):raise RuntimeError('sensitive failure detail')
    result=run(tmp_path,max_turns=6,daily_turns=6,chat_factory=Broken)
    assert result['turns']==1 and result['status']=='completed_with_errors'
    evidence=next((tmp_path/'runs').glob('*/turns.jsonl')).read_text()
    assert 'RuntimeError' in evidence and 'sensitive failure detail' not in evidence
    assert summary(tmp_path)['runs'][0]['turns']==1


def test_worker_lock_blocks_concurrent_run(tmp_path):
    with exclusive(tmp_path):
        with pytest.raises(BlockingIOError):
            run(tmp_path,chat_factory=lambda p:None)


def test_physical_invitation_is_a_signal_with_a_fiction_control():
    assert 'possible_physical_invitation' in signals('我爱喝茶','我们下次可以一起喝茶。')
    assert 'possible_physical_invitation' not in signals('写个一起喝茶的故事','我们下次可以一起喝茶。')


def test_interrupted_worker_recovers_saved_evidence_and_keeps_budget(tmp_path):
    store=Store(tmp_path)
    import time
    from datetime import datetime
    day=datetime.now().astimezone().strftime('%Y-%m-%d')
    store.db.execute("INSERT INTO runs VALUES('crashed',?,?,NULL,'running',3,'{}')",(day,time.time()))
    store.db.commit();store.close()
    folder=tmp_path/'runs/crashed';folder.mkdir(parents=True)
    row={'case':'old','turn':1,'user':'我去洗澡','reply':'晚安'}
    (folder/'turns.jsonl').write_text(json.dumps(row)+'\n{"partial":')
    result=run(tmp_path,max_turns=3,daily_turns=3,chat_factory=lambda p:None)
    assert result['status']=='skipped_budget'
    data=summary(tmp_path)
    assert data['runs'][0]['status']=='interrupted'
    assert data['issues'][0]['category']=='unexpected_goodnight'


def test_synthetic_suite_cannot_request_external_tools(tmp_path, monkeypatch):
    import avatar.lab.improvement as patrol
    suite=tmp_path/'suite.json'
    suite.write_text(json.dumps({'cases':[{'id':'external','turns':['帮我联网搜索南京天气']}]}))
    monkeypatch.setattr(patrol,'SUITE',suite)
    with pytest.raises(ValueError,match='tool requests'):
        run(tmp_path/'state',chat_factory=lambda p:None)
