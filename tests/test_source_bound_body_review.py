import pytest

from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.source_bound_body_review import SourceBoundBodyReviewAvatar
from avatar.lab.transport_fixture import controlled_provider

CLAIM = '那我们下次可以一起去爬山，享受大自然的风景。'


@pytest.fixture
def engine():
    with controlled_provider(delay=.0001, reply_overrides={'fixture-source': CLAIM}) as (_, url):
        client = LLMEngine(base_url=url, api_key='fixture', model='fixture')
        try: yield client
        finally: client.close()


def response(bot, text):
    pieces = []
    result = bot.respond(text, cancel=CancellationToken(), on_delta=pieces.append)
    assert ''.join(pieces) == result['reply'] == bot.memory.get_short_term()[-1]['content']
    assert result['response_review']['general_semantics_verified'] is False
    return result


@pytest.mark.parametrize('prompt', ['替我回复朋友，原样写出“约你一起去爬山”。', '请原样写出“约你一起去爬山”。'])
def test_delegated_current_request_is_preserved_from_actual_input(engine, prompt):
    bot = SourceBoundBodyReviewAvatar(db_path=':memory:', llm=engine)
    try:
        result = response(bot, prompt+'fixture-source')
        assert result['reply'] == CLAIM and result['response_review']['creative_exempt']
    finally: bot.memory.close()


def test_root_survives_12_revisions_and_a_new_avatar_without_history_replay(engine, tmp_path):
    path = str(tmp_path/'root.db'); bot = SourceBoundBodyReviewAvatar(db_path=path, llm=engine)
    try:
        initial = response(bot, '帮我给同学写一条短信。fixture-source')
        root = initial['conversation']['user_message_id']
        for _ in range(12):
            result = response(bot, '再短一点。fixture-source')
            assert result['reply'] == CLAIM and result['response_review']['source_message_ids'] == [root]
        assert not any('写一条短信' in m['content'] for m in bot.memory.get_short_term())
    finally: bot.memory.close()
    bot = SourceBoundBodyReviewAvatar(db_path=path, llm=engine)
    try:
        result = response(bot, '再自然一点。fixture-source')
        assert result['reply'] == CLAIM and result['response_review']['composition_context']['root_id'] == root
        assistant = result['conversation']['assistant_message_id']
        assert bot.memory._conn.execute("SELECT 1 FROM memory_response_context WHERE message_id=? AND source_type='message' AND source_id=?", (assistant, root)).fetchone()
        fact = bot.memory.remember('受控根来源', source_message_id=root)
        bot.memory.forget(fact)
        assert bot.memory._conn.execute('SELECT content FROM memory_messages WHERE id=?', (assistant,)).fetchone()[0] == '[redacted]'
    finally: bot.memory.close()


def test_cancelled_user_root_is_purely_observed_and_next_revision_keeps_frame(engine):
    bot = SourceBoundBodyReviewAvatar(db_path=':memory:', llm=engine)
    token = CancellationToken(); analyze = bot._analyze
    def cancelled(text): analyze(text); token.cancel()
    bot._analyze = cancelled
    try:
        with pytest.raises(Cancelled): bot.respond('帮我给同学写一条短信。fixture-source', cancel=token)
        assert not bot.memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()
        bot._analyze = analyze
        assert response(bot, '再短一点。fixture-source')['reply'] == CLAIM
    finally: bot.memory.close()


def test_explicit_end_from_another_writer_revokes_creative_exemption(engine):
    bot = SourceBoundBodyReviewAvatar(db_path=':memory:', llm=engine)
    try:
        response(bot, '帮我给同学写一条短信。fixture-source')
        bot.memory.add_message('assistant', '不写了。', 'other')
        assert response(bot, '再短一点。fixture-source')['reply'] == CLAIM
        bot.memory.add_message('user', '不写了。', 'other')
        result = response(bot, 'fixture-source')
        assert result['reply'] != CLAIM and not result['response_review']['creative_exempt']
    finally: bot.memory.close()


@pytest.mark.parametrize('invalid', ['privacy', 'redacted', 'oversized', 'cursor'])
def test_unverified_composition_is_reported_as_deferred_not_creative_approval(engine, invalid):
    bot = SourceBoundBodyReviewAvatar(db_path=':memory:', llm=engine)
    try:
        result = response(bot, '帮我给同学写一条短信。fixture-source'); root = result['conversation']['user_message_id']
        if invalid == 'privacy':
            fact = bot.memory.remember('受控待删', source_message_id=root); bot.memory.forget(fact)
        elif invalid == 'redacted':
            bot.memory._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?", (root,)); bot.memory._conn.commit()
        elif invalid == 'oversized':
            for _ in range(65): bot.memory.add_message('user', '再短一点。', 'other')
        else:
            bot.memory._conn.execute('UPDATE lab_body_composition_state SET cursor=-1'); bot.memory._conn.commit()
        result = response(bot, '再短一点。fixture-source')
        review = result['response_review']
        assert review['review_deferred'] and not review['creative_exempt']
        assert review['composition_context']['frame'] == 'unverified' and not review['source_message_ids']
        # Deferred is a diagnostic limitation, not a quality pass: native text
        # remains visible, hence this experiment is still unfit for activation.
        assert result['reply'] == CLAIM
        bot.respond('不写了。')
        assert response(bot, 'fixture-source')['reply'] != CLAIM
    finally: bot.memory.close()


def test_quoted_request_does_not_install_writing_frame_and_role_exit_is_real(engine):
    bot = SourceBoundBodyReviewAvatar(db_path=':memory:', llm=engine)
    try:
        result = response(bot, '分析“替我回复朋友”这句话。fixture-source')
        assert result['reply'] != CLAIM
        bot.respond('我来扮演小说角色。')
        assert response(bot, 'fixture-source')['reply'] == CLAIM
        bot.respond('回到现实。')
        assert response(bot, 'fixture-source')['reply'] != CLAIM
    finally: bot.memory.close()
