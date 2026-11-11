"""A new lab review must not outlive privacy deletion of its old source."""
import pytest

from avatar.brain.llm import LLMEngine
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar


@pytest.mark.parametrize('check', ['dependency', 'privacy'])
def test_trusted_review_source_outside_window_is_bound_to_committed_response(check):
    with controlled_provider(delay=.0001) as (_, url):
        engine = LLMEngine(base_url=url, api_key='fixture', model='fixture')
        bot = Avatar(db_path=':memory:', llm=engine)
        try:
            root = bot.memory.add_message('user', '帮我写一条含私密称呼的短信。', 'old-session')
            bot.final_reply_reviewer = lambda text, reply: (reply, {'source_message_ids': [root]})
            result = bot.respond('fixture-review')
            assistant = result['conversation']['assistant_message_id']
            if check == 'dependency':
                assert bot.memory._conn.execute("SELECT 1 FROM memory_response_context WHERE message_id=? AND source_type='message' AND source_id=?", (assistant, root)).fetchone()
            else:
                fact = bot.memory.remember('受控私密来源', source_message_id=root)
                bot.memory.forget(fact)
                assert bot.memory._conn.execute('SELECT content FROM memory_messages WHERE id=?', (assistant,)).fetchone()[0] == '[redacted]'
        finally: bot.memory.close(); engine.close()
