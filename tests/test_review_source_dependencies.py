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


@pytest.mark.parametrize('invalid', ['bool', 'string', 'negative', 'future', 'missing', 'assistant', 'redacted', 'too_many', 'not_list'])
def test_invalid_review_sources_never_publish_or_commit_assistant(invalid):
    with controlled_provider(delay=.0001) as (_, url):
        engine = LLMEngine(base_url=url, api_key='fixture', model='fixture')
        bot = Avatar(db_path=':memory:', llm=engine)
        try:
            user = bot.memory.add_message('user', '受控来源', 'old')
            assistant = bot.memory.add_message('assistant', '旧回复', 'old')
            ids = {'bool': [True], 'string': [str(user)], 'negative': [-1], 'future': [99999],
                'missing': [assistant], 'assistant': [assistant], 'redacted': [user],
                'too_many': [user]*5, 'not_list': str(user)}[invalid]
            if invalid == 'missing':
                bot.memory._conn.execute('DELETE FROM memory_messages WHERE id=?', (assistant,)); bot.memory._conn.commit()
            if invalid == 'redacted':
                bot.memory._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?", (user,)); bot.memory._conn.commit()
            bot.final_reply_reviewer = lambda text, reply: (reply, {'source_message_ids': ids})
            pieces = []
            with pytest.raises(ValueError, match='source'):
                from avatar.cancellation import CancellationToken
                bot.respond('fixture-review', cancel=CancellationToken(), on_delta=pieces.append)
            assert not pieces
            assert bot.memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant' AND session_id=?", (bot.session_id,)).fetchone()[0] == 0
        finally: bot.memory.close(); engine.close()
