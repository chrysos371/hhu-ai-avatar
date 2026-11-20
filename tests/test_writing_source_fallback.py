"""A finite source-built artifact must disclose failed model repair and its scope."""
from contextlib import closing
import re

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from test_writing_delivery_contract import Replies


@pytest.mark.parametrize('count', [1,2,3])
def test_simple_unknown_leave_fields_render_from_sources_after_two_failed_calls(count):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies(['今天身体不适。', '因个人原因请假。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond(f'麻烦给导师写一封请假邮件，署名用【申请人】，改成{count}句话，只给正文。')
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert len(engine.native) == 2 and not result['writing_delivery']['repair_succeeded']
        fallback = result['writing_delivery']['source_fallback']
        assert fallback['used'] and fallback['semantic_verifier'] is False
        assert '【请假原因】' in result['reply'] and '【申请人】' == result['reply'].splitlines()[-1]
        assert len(re.findall(r'[。！？!?]+', result['reply'])) == count
        assert not result['writing_delivery']['final_issues']
        assert result['writing_delivery']['model_repair_issues']
        assert memory.get_short_term()[-1]['content'] == result['reply']
        assert not result['tool_calls'] and not result['action_receipts']['items']
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_action_receipts').fetchone()[0] == 0


def test_given_event_stays_verbatim_and_unprovided_duration_is_not_added():
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies(['明天请假一天。', '明天参加家里的活动，请假一天。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond('帮我写一条请假短信，我明天要参加家里的活动，只给正文。')
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert '我明天要参加家里的活动' in result['reply']
        assert '一天' not in result['reply'] and '个人原因' not in result['reply']


@pytest.mark.parametrize('request_text', [
    '帮我写一条请假短信，必须保留“不可丢失素材”。',
    '帮我替姐姐给老师写一封请假邮件。',
    '帮我写一条请假短信，明确说明尚未获批准。',
])
def test_unhandled_material_perspective_or_status_never_silently_dropped(request_text):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies(['今天身体不适。', '今天身体不适。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond(request_text)
        assert result['writing_requirements']['source_verified']
        assert result['generation_mode'] == 'rules_writing_validation'
        assert not result['writing_delivery']['source_fallback']['used']


@pytest.mark.parametrize('root,role', [('我已把邮件发给老师，接着写对方回复。','老师'),
    ('我刚把消息发给导师，随后写对方回复。','导师')])
def test_fictional_counterparty_author_and_receipt_do_not_become_real_execution(root, role):
    with closing(MemoryStore(':memory:')) as memory:
        bad = role + '您好，我已将邮件发送给您，希望您能尽快回复。'
        engine = Replies(['开始吧。', bad, bad])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        bot.respond('我来扮演小说角色。')
        result = bot.respond(root)
        assert result['writing_requirements']['author_role'] == role
        assert 'wrong_artifact_author' in result['writing_delivery']['initial_issues']
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert role + '您好' not in result['reply'] and '你好' in result['reply']
        assert not result['tool_calls'] and not result['action_receipts']['items']
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_action_receipts').fetchone()[0] == 0


@pytest.mark.parametrize('change', ['forget','cancel'])
def test_actual_source_change_after_fallback_construction_stops_publication(tmp_path, monkeypatch, change):
    from avatar.brain import writing_templates
    with closing(MemoryStore(str(tmp_path/'fallback.db'))) as memory:
        engine = Replies(['您好。因【请假原因】申请请假。', '今天身体不适。', '今天身体不适。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        root = bot.respond('帮我写一条请假短信，只给正文。')['conversation']['user_message_id']
        fragment = memory.remember('有来源的写作控制',source_message_id=root)
        token, pieces = CancellationToken(), []
        original = writing_templates.build_fallback
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            assert result is not None
            if change == 'cancel':
                token.cancel()
            else:
                with closing(MemoryStore(memory.db_path)) as writer:
                    writer.forget(fragment)
            return result
        monkeypatch.setattr(writing_templates,'build_fallback',changed)
        before = memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]
        with pytest.raises(Cancelled):
            bot.respond('再短一点。',cancel=token,on_delta=pieces.append)
        assert not pieces and len(engine.native) == 3
        assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == before


def test_release_signature_and_current_three_sentence_limit_survive_real_reopen(tmp_path):
    path = str(tmp_path/'restart.db')
    with closing(MemoryStore(path)) as memory:
        engine = Replies(['今天身体不适。']*6)
        bot = Avatar(memory=memory,llm=engine,capability_contract_enabled=True)
        bot.respond('帮我写一条请假短信，署名用【作者】，只给正文。')
        bot.respond('保留原意，改成三句话。')
        bot.respond('再短一点，不要署名。')
    with closing(MemoryStore(path)) as memory:
        engine = Replies(['今天身体不适。']*2)
        bot = Avatar(memory=memory,llm=engine,capability_contract_enabled=True)
        result = bot.respond('再自然一点。')
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert '【作者】' not in result['reply']
        assert len(re.findall(r'[。！？!?]+',result['reply'])) == 3
