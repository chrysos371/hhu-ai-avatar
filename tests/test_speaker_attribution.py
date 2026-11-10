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

@pytest.mark.parametrize('declaration',[
    '我扮演过小说角色。',
    '我扮演小说角色时会很紧张。',
    '比如，我来扮演小说角色。',
    '也许我来扮演小说角色。',
    '我想知道，我来扮演小说角色是否合适。',
    '如果讨论剧情。假如我来扮演小说角色。',
])
def test_past_general_or_hypothetical_role_discussion_is_not_a_declaration(declaration):
    bot=Avatar(db_path=':memory:',llm=Offline())
    try:
        bot.respond(declaration)
        bot.respond('我叫陈宁。')
        assert bot.memory.get_user_profile().get('名字')=='陈宁'
    finally:bot.memory.close()


def test_model_proposed_role_facts_are_rejected_even_with_literal_evidence():
    class Proposing:
        available=True
        def chat_analysis(self,messages,**kwargs):
            text=messages[-1]['content']
            facts=[]
            if '我叫林悦' in text:
                facts=[dict(type='名字',content='林悦',evidence='我叫林悦',subject='self',modality='asserted',temporal='current')]
            return json.dumps({'emotion':{'valence':0.1,'arousal':0.2},'facts':facts})
        def chat(self,*args,**kwargs):return '好的，继续故事。'
    bot=Avatar(db_path=':memory:',llm=Proposing())
    try:
        bot.respond('我来扮演小说角色。')
        result=bot.respond('我叫林悦。')
        assert result['analysis_mode']=='llm'
        assert bot.memory.get_user_profile()=={}
        assert result['speaker_attribution']['persistent_facts_allowed'] is False
    finally:bot.memory.close()


def test_external_source_erasure_clears_derived_speaker_context(tmp_path):
    path=str(tmp_path/'erase.db');bot=Avatar(db_path=path,llm=Offline())
    writer=MemoryStore(path)
    try:
        bot.respond('我喜欢骑车。')
        fragment=bot.list_memories()[0]['id']
        bot.respond('我来扮演小说角色。')
        bot.respond('我喜欢游泳。')
        writer.forget(fragment)
        bot.respond('现在不喜欢了。')
        assert bot.memory.get_user_profile()=={}
        result=bot.respond('我叫陈宁。')
        assert result['speaker_attribution']['scope']=='current_user'
        assert bot.memory.get_user_profile()=={'名字':'陈宁'}
    finally:writer.close();bot.memory.close()


def test_fictional_query_does_not_take_real_profile_shortcut():
    class Echo:
        available=True
        def chat_analysis(self,*args,**kwargs):return '{"emotion":{},"facts":[]}'
        def chat(self,*args,**kwargs):return '故事里你叫林悦。'
    bot=Avatar(db_path=':memory:',llm=Echo(),profile_grounding_enabled=True,subject_prompt_enabled=True)
    try:
        bot.respond('我叫陈宁。')
        bot.respond('我来扮演小说角色。')
        bot.respond('我叫林悦。')
        result=bot.respond('我叫什么名字？')
        assert result['generation_mode']=='llm'
        assert result['profile_grounding']['action'] is None
        assert bot.memory.get_user_profile()=={'名字':'陈宁'}
    finally:bot.memory.close()

@pytest.mark.parametrize('text',['现在不喜欢了。','我叫陈宁。'])
def test_erasure_during_analysis_cannot_repopulate_facts_from_stale_speaker_context(tmp_path,text):
    from avatar.cancellation import Cancelled
    path=str(tmp_path/'mid-analysis.db');bot=Avatar(db_path=path,llm=Offline())
    writer=MemoryStore(path)
    try:
        bot.respond('我喜欢骑车。')
        fragment=bot.list_memories()[0]['id']
        class Erasing:
            available=True
            def chat_analysis(self,*args,**kwargs):
                writer.forget(fragment)
                return '{"emotion":{},"facts":[]}'
            def chat(self,*args,**kwargs):raise AssertionError('must stop before reply generation')
        bot.llm=Erasing();bot._llm_available=True
        with pytest.raises(Cancelled):bot.respond(text)
        assert bot.memory.get_user_profile()=={}
        assert bot.list_memories()==[]
    finally:writer.close();bot.memory.close()
