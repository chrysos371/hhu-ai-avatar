"""Frozen source-attribution regressions against the actual orchestrator."""
import json
from pathlib import Path
import pytest
from avatar.main import Avatar
from avatar.brain.memory import MemoryStore
from avatar.web import create_server, run_chat

SUITE=json.loads((Path(__file__).resolve().parents[1]/'evals/interaction/cycle-04/speaker-scope.json').read_text())
class Offline:
    available=False
    def close(self):pass

@pytest.mark.parametrize('case',SUITE['cases'],ids=lambda c:c['id'])
def test_explicit_speaker_scope(case):
    bot=Avatar(db_path=':memory:',llm=Offline())
    try:
        for turn in case['turns']:bot.respond(turn)
        assert bot.memory.get_user_profile()==case['profile']
        if 'facts' in case:assert len(bot.list_memories())==case['facts']
    finally:bot.memory.close()


def test_scope_survives_short_term_window_wrap():
    bot=Avatar(db_path=':memory:',llm=Offline())
    try:
        bot.respond('我来扮演小说角色。')
        for _ in range(24):bot.respond('继续聊剧情。')
        bot.respond('我叫林悦。')
        assert bot.memory.get_user_profile()=={}
    finally:bot.memory.close()


def test_web_keeps_speaker_scope_across_ephemeral_instances(tmp_path,monkeypatch):
    import avatar.main as module
    monkeypatch.setattr(module,'LLMEngine',Offline)
    path=str(tmp_path/'speaker.db');memory=MemoryStore(path);memory.close()
    server=create_server(path,port=0)
    try:
        run_chat(server,'我来扮演小说角色。',False)
        run_chat(server,'我叫林悦。',False)
        reader=MemoryStore(path)
        try:assert reader.get_user_profile()=={}
        finally:reader.close()
        run_chat(server,'回到现实，我叫陈宁。',False)
        reader=MemoryStore(path)
        try:assert reader.get_user_profile()=={'名字':'陈宁'}
        finally:reader.close()
    finally:server.server_close()
