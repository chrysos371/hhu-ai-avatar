"""Source-sum corruption, incomplete turns, erasure and real Web restart."""
from contextlib import closing
import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.source_calculation import CalculationReader
from avatar.cancellation import Cancelled, CancellationToken
from avatar.main import Avatar
from avatar.web import create_server, run_chat
from test_capability_prompt_lab import Recorder
from test_reminder_query_flow import seed, projection
from test_source_calculation import MATERIAL


def sources(memory):
    model = Recorder('93')
    bot = Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
    first = bot.respond('材料清单为纸板37张、卡纸28张。请只确认。')
    update = bot.respond('数量更新：卡纸改为46张，纸板不变。请只确认。')
    return bot, model, first, update


@pytest.mark.parametrize('fault',['wrong_pair','no_result','missing_dependency','redacted','incomplete_later_user'])
def test_invalid_or_incomplete_later_sources_do_not_resurrect_old_values(tmp_path,fault):
    with closing(MemoryStore(str(tmp_path/'sources.db'))) as memory:
        bot,model,first,update = sources(memory)
        aid=update['conversation']['assistant_message_id']
        with memory.transaction():
            if fault=='wrong_pair':
                update['conversation']['user_message_id']=first['conversation']['user_message_id']
                memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?',(json.dumps(update),aid))
            elif fault=='no_result': memory._conn.execute('DELETE FROM memory_chat_results WHERE message_id=?',(aid,))
            elif fault=='missing_dependency': memory._conn.execute('DELETE FROM memory_response_context WHERE message_id=?',(aid,))
            elif fault=='redacted': memory._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?",(update['conversation']['user_message_id'],))
            else:
                ident=memory.add_message('user','数量更新：卡纸改为99张，纸板不变。请只确认。',bot.session_id)
                bot.speaker_context_store.observe('数量更新：卡纸改为99张，纸板不变。请只确认。',memory.context_revision,ident)
        result=bot.respond(MATERIAL)
        if fault=='redacted':
            assert result['generation_mode']=='rules_speaker_scope'
            assert 'source_calculation' not in result
            bot.respond('回到现实')
            result=bot.respond(MATERIAL)
        assert result['reply']=='无法确认' and not result['source_calculation']['calculation_verified']


@pytest.mark.parametrize('change',['cancel','foreign_forget','source_rewrite'])
def test_real_late_mutation_never_emits_or_persists_calculated_answer(tmp_path,monkeypatch,change):
    with closing(MemoryStore(str(tmp_path/'late.db'))) as memory:
        bot,model,first,update=sources(memory)
        fid=memory.remember('有来源数量',source_message_id=update['conversation']['user_message_id'])
        token=CancellationToken();pieces=[];original=bot._analyze
        def changed(text):
            original(text)
            if change=='cancel':token.cancel()
            else:
                with closing(MemoryStore(memory.db_path)) as actor:
                    if change=='foreign_forget':actor.forget(fid)
                    else:
                        with actor.transaction():actor._conn.execute('UPDATE memory_messages SET content=? WHERE id=?',
                            ('数量更新：卡纸改为1张，纸板不变。请只确认。',update['conversation']['user_message_id']))
        monkeypatch.setattr(bot,'_analyze',changed)
        with pytest.raises(Cancelled):bot.respond(MATERIAL,cancel=token,on_delta=pieces.append)
        assert not pieces
        assert not memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant' AND content='83'").fetchone()


def test_readonly_calculation_does_not_claim_an_overdue_reminder(tmp_path):
    with closing(MemoryStore(str(tmp_path/'readonly.db'))) as memory:
        bot,model,first,update=sources(memory)
        seed(memory,due=True);before=projection(memory)
        result=bot.respond(MATERIAL)
        assert result['reply']=='83' and projection(memory)==before
        assert not result['action_receipts']['items'] and not result['due_reminders']


def test_actual_web_restart_and_recovered_calculation_cannot_trust_tampered_proof(tmp_path,monkeypatch):
    engines=[]
    def factory():
        engine=Recorder('普通回复');engines.append(engine);return engine
    monkeypatch.setattr('avatar.main.LLMEngine',factory)
    db=str(tmp_path/'restart.db')
    def make():return create_server(db,port=0,capability_contract_enabled=True,role_state_enabled=True)
    server=make()
    try:
        run_chat(server,'材料清单为纸板37张、卡纸28张。请只确认。')
        run_chat(server,'数量更新：卡纸改为46张，纸板不变。请只确认。')
    finally:server.server_close()
    server=make()
    try:
        result=run_chat(server,MATERIAL)
        assert result['reply']=='83' and result['source_calculation']['calculation_verified']
    finally:server.server_close()
    server=make()
    try:
        run_chat(server,'聊聊窗外。')
        assert any('rules_source_calculation' in m['content'] for m in engines[-1].native[-1] if m['role']=='assistant')
    finally:server.server_close()
    with closing(MemoryStore(db)) as memory:
        aid=result['conversation']['assistant_message_id'];result['source_calculation']['inputs'][0]['value']='999'
        with memory.transaction():memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?',(json.dumps(result),aid))
    server=make()
    try:
        run_chat(server,'换一个话题。')
        assert not any('rules_source_calculation' in m['content'] for m in engines[-1].native[-1] if m['role']=='assistant')
    finally:server.server_close()
