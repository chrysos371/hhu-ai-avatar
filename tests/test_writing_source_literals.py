"""Explicit source literals must survive the new artifact repair path."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_writing_delivery_contract import Replies


@pytest.mark.parametrize('text', ['帮我写一条短信，必须保留【代号】。', '帮我回复：必须保留【代号】。'])
def test_missing_literal_in_actual_source_requires_repair_even_without_legacy_task_flags(text):
    with closing(MemoryStore(':memory:')) as memory:
        engine=Replies(['普通正文。','请核对【代号】。'])
        bot=Avatar(memory=memory,llm=engine,capability_contract_enabled=True)
        result=bot.respond(text)
        assert result['reply']=='请核对【代号】。' and len(engine.native)==2
        assert 'missing_literal:【代号】' in result['writing_delivery']['initial_issues']
        assert result['writing_requirements']['required_literals']==['【代号】']


def test_forbidden_literal_and_current_release_are_source_constraints():
    with closing(MemoryStore(':memory:')) as memory:
        engine=Replies(['写着【旧称】。','请使用新称呼。','请核对【代号】。','自然一点的正文。'])
        bot=Avatar(memory=memory,llm=engine,capability_contract_enabled=True)
        result=bot.respond('帮我写一条短信，不要包含【旧称】。')
        assert result['reply']=='请使用新称呼。'
        assert 'forbidden_literal:【旧称】' in result['writing_delivery']['initial_issues']
        bot.respond('帮我写一条短信，必须保留【代号】。')
        result=bot.respond('再自然一点，不必保留【代号】。')
        assert result['reply']=='自然一点的正文。' and len(engine.native)==4
        assert not result['writing_requirements']['required_literals']


def test_actual_reopen_restores_old_literal_control_outside_short_window(tmp_path):
    path=str(tmp_path/'literal.db')
    with closing(MemoryStore(path)) as memory:
        bot=Avatar(memory=memory,llm=Replies(['保留【材料】。']*41),capability_contract_enabled=True)
        bot.respond('帮我写一条短信，必须保留【材料】。')
        for _ in range(40):bot.respond('再短一点。')
    with closing(MemoryStore(path)) as memory:
        engine=Replies(['普通正文。','保留【材料】。'])
        result=Avatar(memory=memory,llm=engine,capability_contract_enabled=True).respond('再自然一点。')
        assert result['reply']=='保留【材料】。' and len(engine.native)==2


def test_quoted_forbid_operation_is_artifact_data():
    with closing(MemoryStore(':memory:')) as memory:
        text='“不要包含【旧称】”'
        result=Avatar(memory=memory,llm=Replies([text]),capability_contract_enabled=True).respond(
            '帮我写一段说明，原样包含“不要包含【旧称】”。')
        assert result['reply']==text
        assert result['writing_requirements']['forbidden_literals']==[]
