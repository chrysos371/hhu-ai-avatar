from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('stage', ['before_assembly', 'after_system', 'during_short_term'])
@pytest.mark.parametrize('writer_kind', ['external', 'same_instance'])
def test_observed_forget_never_dispatches_old_reply_prompt(tmp_path, monkeypatch, stage, writer_kind):
    path = str(tmp_path/'privacy.db'); engine = Recorder('must not dispatch')
    bot = Avatar(db_path=path, llm=engine)
    fragment = bot.memory.remember_user('名字', '待删请求名')
    original_messages = bot._messages; original_system = bot._system_prompt
    original_short = bot.memory.get_short_term; ready = False; done = False
    def forget():
        nonlocal done
        if done: return
        done = True
        if writer_kind == 'same_instance': bot.forget_memory(fragment)
        else:
            with closing(MemoryStore(path)) as writer: writer.forget(fragment)
    def messages(decision, text):
        if stage == 'before_assembly': forget()
        return original_messages(decision, text)
    def system(decision, text):
        nonlocal ready
        prompt = original_system(decision, text); ready = True
        if stage == 'after_system': forget()
        return prompt
    def short():
        if ready and stage == 'during_short_term': forget()
        return original_short()
    monkeypatch.setattr(bot, '_messages', messages)
    monkeypatch.setattr(bot, '_system_prompt', system)
    monkeypatch.setattr(bot.memory, 'get_short_term', short)
    try:
        with pytest.raises(Cancelled): bot.respond('我的名字是待删请求名。', cancel=CancellationToken())
        assert done and len(engine.analysis) == 1
        assert not engine.native
        assert not bot.memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()
    finally:
        bot.memory.close()


def test_cancel_during_system_compilation_stops_before_reply_method(monkeypatch):
    engine = Recorder('must not dispatch'); bot = Avatar(db_path=':memory:', llm=engine)
    token = CancellationToken(); original = bot._system_prompt
    def cancel_after(decision, text):
        prompt = original(decision, text); token.cancel(); return prompt
    monkeypatch.setattr(bot, '_system_prompt', cancel_after)
    try:
        with pytest.raises(Cancelled): bot.respond('普通话题。', cancel=token)
        assert len(engine.analysis) == 1 and not engine.native
    finally:
        bot.memory.close()


@pytest.mark.parametrize('change', ['external_forget', 'same_instance_forget', 'cancel'])
def test_analysis_dispatch_also_checks_immutable_turn_after_fact_context(tmp_path, monkeypatch, change):
    path = str(tmp_path/'analysis.db'); engine = Recorder('must not dispatch')
    bot = Avatar(db_path=path, llm=engine); token = CancellationToken()
    fragment = bot.memory.remember_user('名字', '待删分析名')
    original = bot._check_fact_context
    def change_after_check():
        original()
        if change == 'cancel': token.cancel()
        elif change == 'same_instance_forget': bot.forget_memory(fragment)
        else:
            with closing(MemoryStore(path)) as writer: writer.forget(fragment)
    monkeypatch.setattr(bot, '_check_fact_context', change_after_check)
    try:
        with pytest.raises(Cancelled): bot.respond('普通话题。', cancel=token)
        assert not engine.analysis and not engine.native
        assert not bot.memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()
    finally:
        bot.memory.close()
