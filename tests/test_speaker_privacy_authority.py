from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from avatar.web import create_server, run_chat


class Offline:
    available = False
    def close(self): pass


@pytest.mark.parametrize('web', [False, True], ids=['avatar', 'web'])
@pytest.mark.parametrize('text', ['我叫角色林悦。', '提醒我明天9点带伞。'], ids=['profile', 'action'])
def test_unrelated_erasure_cannot_silently_grant_real_authority_to_an_active_role(tmp_path, monkeypatch, web, text):
    import avatar.main as module
    monkeypatch.setattr(module, 'LLMEngine', Offline)
    path = str(tmp_path/'privacy.db')
    actor = create_server(path, port=0) if web else Avatar(db_path=path, llm=Offline())
    respond = (lambda value: run_chat(actor, value)) if web else actor.respond
    try:
        respond('我叫原真人名。')
        respond('我来扮演小说角色。')
        with closing(MemoryStore(path)) as writer:
            fact = writer.list_memories()[0]['id']; writer.forget(fact)
        result = respond(text)
        with closing(MemoryStore(path)) as memory:
            profile = memory.get_user_profile()
            reminders = [dict(row) for row in memory._conn.execute('SELECT * FROM memory_reminders')]
            assert (profile, reminders) == ({}, [])
        assert result['speaker_attribution']['scope'] == 'unverified'
        respond('回到现实。')
        real = respond('我叫陈宁。')
        assert real['speaker_attribution']['scope'] == 'current_user'
        with closing(MemoryStore(path)) as memory: assert memory.get_user_profile() == {'名字': '陈宁'}
    finally:
        actor.server_close() if web else actor.memory.close()
