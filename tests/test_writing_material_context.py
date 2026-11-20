"""Recorded real prompt inputs, not semantic quality from scripted outputs."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('reopen',[False,True])
def test_old_material_control_reaches_actual_prompt_outside_window_and_after_reopen(tmp_path,reopen):
    path=str(tmp_path/'materials.db')
    with closing(MemoryStore(path)) as memory:
        engine=Recorder('草稿。')
        bot=Avatar(memory=memory,llm=engine,capability_contract_enabled=True,summary_enabled=False)
        root=bot.respond('帮我写一条短信，正文说周三见。')['conversation']['user_message_id']
        control=bot.respond('改成周五见。')['conversation']['user_message_id']
        for _ in range(40):bot.respond('再短一点。')
        if not reopen:
            bot.respond('再自然一点。')
            system=engine.native[-1][0]['content']
    if reopen:
        with closing(MemoryStore(path)) as memory:
            engine=Recorder('草稿。')
            bot=Avatar(memory=memory,llm=engine,capability_contract_enabled=True,summary_enabled=False)
            bot.respond('再自然一点。')
            system=engine.native[-1][0]['content']
    assert '已核验写作来源原文' in system
    assert '改成周五见。' in system
    assert f'"source_message_id": {root}' in system and f'"source_message_id": {control}' in system
