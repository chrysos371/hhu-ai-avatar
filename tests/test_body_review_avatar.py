import pytest

from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.body_review_avatar import ExplicitBodyReviewAvatar
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar

CLAIM = '那我们下次可以一起去爬山，享受大自然的风景。'


@pytest.fixture
def engine():
    with controlled_provider(delay=.001, reply_overrides={'fixture-body': CLAIM}) as (_, url):
        client = LLMEngine(base_url=url, api_key='local-fixture', model='fixture')
        try: yield client
        finally: client.close()


def test_default_avatar_stays_native_and_has_no_experimental_review(engine):
    bot = Avatar(db_path=':memory:', llm=engine); pieces = []
    try:
        result = bot.respond('fixture-body', cancel=CancellationToken(), on_delta=pieces.append)
        assert result['reply'] == ''.join(pieces) == CLAIM
        assert result['generation_mode'] == 'llm' and 'response_review' not in result
    finally: bot.memory.close()


def test_candidate_buffers_then_commits_only_corrected_text(engine):
    bot = ExplicitBodyReviewAvatar(db_path=':memory:', llm=engine); pieces = []
    try:
        result = bot.respond('fixture-body', cancel=CancellationToken(), on_delta=pieces.append)
        assert result['generation_mode'] == 'reviewed_response'
        assert pieces == [result['reply']] and CLAIM not in ''.join(pieces)
        assert result['response_review']['stream_buffered'] is True
        assert result['response_review']['general_semantics_verified'] is False
        assert bot.memory.get_short_term()[-1]['content'] == result['reply']
        assert bot.memory._conn.execute("SELECT content FROM memory_messages WHERE role='assistant'").fetchone()[0] == result['reply']
    finally: bot.memory.close()


@pytest.mark.parametrize('prompt', ['fixture-body 帮我给同学写一条短信。', 'fixture-body 写两句小说台词。'])
def test_candidate_derives_creative_exemption_from_real_input_not_fixture_labels(engine, prompt):
    bot = ExplicitBodyReviewAvatar(db_path=':memory:', llm=engine); pieces = []
    try:
        result = bot.respond(prompt, cancel=CancellationToken(), on_delta=pieces.append)
        assert result['reply'] == CLAIM and pieces == [CLAIM]
        assert result['generation_mode'] == 'llm' and result['response_review']['creative_exempt']
        assert result['task'] is None
    finally: bot.memory.close()


def test_candidate_keeps_role_scope_then_checks_a_later_real_turn(engine):
    bot = ExplicitBodyReviewAvatar(db_path=':memory:', llm=engine)
    try:
        bot.respond('我来扮演小说角色。')
        fictional = bot.respond('fixture-body', cancel=CancellationToken())
        assert fictional['reply'] == CLAIM and fictional['response_review']['creative_exempt']
        bot.respond('回到现实。')
        real = bot.respond('fixture-body', cancel=CancellationToken())
        assert real['reply'] != CLAIM and not real['response_review']['creative_exempt']
    finally: bot.memory.close()


def test_candidate_rebuilds_continued_writing_frame_from_current_sources(engine):
    bot = ExplicitBodyReviewAvatar(db_path=':memory:', llm=engine)
    try:
        bot.respond('fixture-body 帮我给同学写一条短信。', cancel=CancellationToken())
        result = bot.respond('再短一点。fixture-body', cancel=CancellationToken())
        assert result['reply'] == CLAIM and result['response_review']['creative_exempt']
    finally: bot.memory.close()


@pytest.mark.parametrize('interrupt', ['cancel', 'erase', 'error'])
def test_candidate_review_failure_never_releases_unchecked_text_or_assistant(engine, tmp_path, interrupt):
    path = str(tmp_path/'review.db'); bot = ExplicitBodyReviewAvatar(db_path=path, llm=engine)
    writer = MemoryStore(path); fact = bot.memory.remember_user('名字', '待删测试名')
    token, pieces = CancellationToken(), []; review = bot.final_reply_reviewer
    def interrupted(text, reply):
        result = review(text, reply)
        if interrupt == 'cancel': token.cancel()
        elif interrupt == 'erase': writer.forget(fact)
        else: raise ValueError('controlled reviewer failure')
        return result
    bot.final_reply_reviewer = interrupted
    try:
        with pytest.raises(ValueError if interrupt == 'error' else Cancelled):
            bot.respond('fixture-body', cancel=token, on_delta=pieces.append)
        assert pieces == []
        assert [row[0] for row in bot.memory._conn.execute('SELECT role FROM memory_messages')] == ['user']
    finally: writer.close(); bot.memory.close()
