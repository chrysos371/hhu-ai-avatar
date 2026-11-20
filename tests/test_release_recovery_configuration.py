"""Release SDK recovery and the independent Web opt-out use actual databases."""
from contextlib import closing

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from avatar.web import create_server, run_chat
from test_capability_prompt_lab import Recorder


def test_release_sdk_restart_recovers_checked_delivery_instead_of_losing_context(tmp_path):
    db=str(tmp_path/'sdk.db')
    with closing(MemoryStore(db)) as memory:
        first=Avatar(memory=memory,llm=Recorder('不调用生成'),capability_contract_enabled=True,role_state_enabled=True)
        result=first.respond('原样输出这句话：“首轮保留的稿件正文。”')
    with closing(MemoryStore(db)) as memory:
        model=Recorder('现在聊聊窗外。')
        second=Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
        current=second.respond('现在聊聊窗外。')
        history=[m['content'] for m in model.native[-1] if m['role']=='assistant']
        assert any('历史写作交付' in s and result['reply'] in s for s in history)
        deps={r[0] for r in memory._conn.execute("SELECT source_id FROM memory_response_context "
            "WHERE message_id=? AND source_type='message'",(current['conversation']['assistant_message_id'],))}
        assert set(result['conversation'][k] for k in ('user_message_id','assistant_message_id'))<=deps


def test_web_context_opt_out_remains_effective_with_both_release_features(tmp_path,monkeypatch):
    engines=[]
    def factory():
        engine=Recorder('首轮的临时答复。');engines.append(engine);return engine
    monkeypatch.setattr('avatar.main.LLMEngine',factory)
    db=str(tmp_path/'optout.db')
    first=create_server(db,port=0,capability_contract_enabled=True,role_state_enabled=True,recover_context=False)
    try:run_chat(first,'首轮仅讨论山川。')
    finally:first.server_close()
    second=create_server(db,port=0,capability_contract_enabled=True,role_state_enabled=True,recover_context=False)
    try:
        run_chat(second,'现在聊聊窗外。')
        assert not any(m['role']=='assistant' and '首轮的临时答复' in m['content'] for m in engines[-1].native[-1])
    finally:second.server_close()


def test_profile_over_source_limit_refuses_instead_of_silently_disabling_guard():
    with closing(MemoryStore(':memory:')) as memory:
        for i in range(129):memory.remember_user('偏好',f'喜欢第{i}种运动')
        model=Recorder('你叫猜测名。')
        bot=Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
        result=bot.respond('我叫什么名字？')
        assert result['generation_mode']=='rules_profile_source_limit'
        assert '超过128条' in result['reply'] and '猜测名' not in result['reply']
        assert not model.native
