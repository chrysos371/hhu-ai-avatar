import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled
from avatar.main import Avatar


def test_erasure_traces_transitive_replies_and_preserves_independent_tracked_reply():
    memory = MemoryStore(':memory:')
    try:
        user = memory.add_message('user','我叫小林','one')
        fid = memory.remember_user('名字','小林',source_message_id=user,evidence='我叫小林')
        first = memory.add_message('assistant','你好小林','one',context_ids=[fid],source_message_ids=[user])
        second = memory.add_message('assistant','小林，我们继续','two',context_ids=[],source_message_ids=[first])
        independent = memory.add_message('assistant','独立的无来源回应','three',context_ids=[],source_message_ids=[])
        legacy = memory.add_message('assistant','来源未追踪的旧回复','old')
        memory.forget(fid)
        rows = {row['id']:row['content'] for row in memory._conn.execute('SELECT id,content FROM memory_messages')}
        assert rows[user] == rows[first] == rows[second] == rows[legacy] == '[redacted]'
        assert rows[independent] == '独立的无来源回应'
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_response_context').fetchone()[0] == 0
    finally:
        memory.close()


def test_cross_session_recalled_profile_has_erasable_reply_lineage(tmp_path):
    path = str(tmp_path/'cross.db')
    first = Avatar(db_path=path, session_id='first')
    first._llm_available = False
    first.respond('我叫小林')
    fid = first.memory.list_memories()[0]['id']
    first.memory.close()
    class Model:
        available = True
        def chat_analysis(self,*args,**kwargs):
            return json.dumps({'emotion':{'valence':0,'arousal':0},'facts':[]})
        def chat(self,*args,**kwargs):
            return '你叫小林。'
    second = Avatar(db_path=path,session_id='second',llm=Model())
    try:
        assert second.respond('你记得我的名字吗')['reply'] == '你叫小林。'
        second.memory.forget(fid)
        assert not any('小林' in row[0] for row in second.memory._conn.execute('SELECT content FROM memory_messages'))
    finally:
        second.memory.close()


def test_reply_commit_rejects_external_erasure_during_generation(tmp_path):
    path = str(tmp_path/'race.db')
    setup = MemoryStore(path)
    fid = setup.remember_user('名字','旧名字')
    setup.close()
    class Model:
        available = True
        def chat_analysis(self,*args,**kwargs):
            return json.dumps({'emotion':{'valence':0,'arousal':0},'facts':[]})
        def chat(self,*args,**kwargs):
            external = MemoryStore(path)
            external.forget(fid)
            external.close()
            return '已经过时的旧名字。'
    avatar = Avatar(db_path=path,llm=Model())
    try:
        with pytest.raises(Cancelled):
            avatar.respond('你记得我的名字吗')
        assert avatar.memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == 0
        assert avatar.memory._conn.execute('SELECT COUNT(*) FROM memory_response_context').fetchone()[0] == 0
    finally:
        avatar.memory.close()


def test_reply_and_dependency_rows_roll_back_together():
    memory = MemoryStore(':memory:')
    try:
        source = memory.add_message('user','原文','one')
        with pytest.raises(RuntimeError):
            with memory.transaction():
                memory.add_message('assistant','待回滚','one',context_ids=[],source_message_ids=[source])
                raise RuntimeError('rollback')
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_response_context').fetchone()[0] == 0
        assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == 0
    finally:
        memory.close()


def test_summary_source_without_a_fact_erases_derived_reply():
    from avatar.brain.summaries import SummaryStore
    memory = MemoryStore(':memory:')
    try:
        source = memory.add_message('user','方案暗号霁月','one')
        response = memory.add_message('assistant','暗号是霁月','one',context_ids=[],source_message_ids=[source])
        memory._conn.execute('INSERT INTO memory_summary_items VALUES (?,?)',('one',source))
        memory._conn.commit()
        SummaryStore(memory).forget_source('one',source)
        assert memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',(response,)).fetchone()[0] == '[redacted]'
    finally:
        memory.close()
