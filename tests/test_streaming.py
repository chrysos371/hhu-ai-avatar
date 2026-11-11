import threading
import time

import pytest

from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar


def test_actual_sdk_stream_delivers_before_completion_and_closes():
    with controlled_provider(delay=0.02) as (_, url):
        engine = LLMEngine(base_url=url, api_key='local-fixture', model='fixture')
        deltas = []
        start = time.perf_counter()
        try:
            result = engine.stream_chat([{'role': 'user', 'content': 'hello'}],
                on_delta=lambda text: deltas.append((time.perf_counter() - start, text)))
            complete = time.perf_counter() - start
            assert ''.join(text for _, text in deltas) == result
            assert len(deltas) > 1 and deltas[0][0] < complete
        finally:
            engine.close()


@pytest.mark.parametrize('prompt', ['delay-headers', 'hello'])
def test_cancel_interrupts_actual_transport_including_pending_headers(prompt):
    with controlled_provider(delay=0.1) as (server, url):
        engine = LLMEngine(base_url=url, api_key='local-fixture', model='fixture')
        token, outcome = CancellationToken(), []
        def work():
            try:
                engine.stream_chat([{'role': 'user', 'content': prompt}], cancel=token)
            except Cancelled:
                outcome.append('cancelled')
        thread = threading.Thread(target=work)
        thread.start()
        assert server.started.wait(3)
        start = time.perf_counter()
        token.cancel()
        thread.join(2)
        try:
            assert outcome == ['cancelled']
            assert time.perf_counter() - start < 1
            assert server.disconnected.wait(2)
        finally:
            engine.close()


def test_cancelled_avatar_keeps_confirmed_input_but_no_partial_assistant():
    with controlled_provider(delay=0.02) as (_, url):
        engine = LLMEngine(base_url=url, api_key='local-fixture', model='fixture')
        avatar = Avatar(db_path=':memory:', llm=engine)
        token, pieces = CancellationToken(), []
        def delta(text):
            pieces.append(text)
            token.cancel()
        try:
            with pytest.raises(Cancelled):
                avatar.respond('我叫小林', cancel=token, on_delta=delta)
            assert pieces == ['第一句已经生成。']
            assert [row[0] for row in avatar.memory._conn.execute('SELECT role FROM memory_messages')] == ['user']
            assert avatar.memory.get_user_profile()['名字'] == '小林'
        finally:
            avatar.memory.close()
            engine.close()


def test_pre_cancelled_avatar_never_writes_input():
    token = CancellationToken()
    token.cancel()
    avatar = Avatar(db_path=':memory:')
    try:
        with pytest.raises(Cancelled):
            avatar.respond('我叫未发送', cancel=token)
        assert avatar.memory._conn.execute('SELECT COUNT(*) FROM memory_messages').fetchone()[0] == 0
    finally:
        avatar.memory.close()


def test_stream_has_total_deadline_even_when_chunks_beat_read_timeout():
    with controlled_provider(delay=0.02) as (server, url):
        engine = LLMEngine(base_url=url, api_key='local-fixture', model='fixture', timeout=0.15)
        start = time.perf_counter()
        try:
            with pytest.raises(TimeoutError):
                engine.stream_chat([{'role':'user','content':'fixture-long'}])
            assert time.perf_counter() - start < 0.5
            assert server.disconnected.wait(2)
        finally:
            engine.close()


@pytest.mark.parametrize('reply', ['"明天一起爬山。"', '没有句号的完整回复', '第一句。最后一段没有标点', '这句结束。🙂'])
@pytest.mark.parametrize('buffered', [False, True], ids=['sentences', 'buffered'])
def test_completed_avatar_stream_retains_unpunctuated_or_quoted_tail(reply, buffered):
    with controlled_provider(delay=.001, reply_overrides={'fixture-tail': reply}) as (_, url):
        engine = LLMEngine(base_url=url, api_key='local-fixture', model='fixture')
        bot = Avatar(db_path=':memory:', llm=engine, profile_grounding_enabled=buffered)
        pieces = []
        try:
            result = bot.respond('fixture-tail', cancel=CancellationToken(), on_delta=pieces.append)
            assert result['generation_mode'] == 'llm'
            assert result['reply'] == ''.join(pieces) == reply
            if buffered: assert pieces == [reply]
            assert bot.memory.get_short_term()[-1] == {'role': 'assistant', 'content': reply}
        finally:
            bot.memory.close(); engine.close()


def test_cancel_after_full_review_cannot_flush_a_late_quote_or_commit_assistant():
    reply = '"明天一起爬山。"'
    with controlled_provider(delay=.001, reply_overrides={'fixture-tail': reply}) as (_, url):
        engine = LLMEngine(base_url=url, api_key='local-fixture', model='fixture')
        bot = Avatar(db_path=':memory:', llm=engine); token = CancellationToken(); pieces = []
        review = bot.boundaries.review_output
        def cancel_final(text):
            if text == reply: token.cancel()
            return review(text)
        bot.boundaries.review_output = cancel_final
        try:
            with pytest.raises(Cancelled): bot.respond('fixture-tail', cancel=token, on_delta=pieces.append)
            assert ''.join(pieces) == reply[:-1]
            assert [r[0] for r in bot.memory._conn.execute('SELECT role FROM memory_messages')] == ['user']
        finally:
            bot.memory.close(); engine.close()


def test_erasure_after_full_review_blocks_tail_and_assistant_commit(tmp_path):
    from avatar.brain.memory import MemoryStore
    reply = '"明天一起爬山。"'
    with controlled_provider(delay=.001, reply_overrides={'fixture-tail': reply}) as (_, url):
        engine = LLMEngine(base_url=url, api_key='local-fixture', model='fixture')
        path = str(tmp_path/'tail-erase.db'); bot = Avatar(db_path=path, llm=engine)
        fact = bot.memory.remember_user('名字', '待删测试名'); writer = MemoryStore(path); pieces = []
        review = bot.boundaries.review_output
        def erase_final(text):
            if text == reply: writer.forget(fact)
            return review(text)
        bot.boundaries.review_output = erase_final
        try:
            with pytest.raises(Cancelled): bot.respond('fixture-tail', cancel=CancellationToken(), on_delta=pieces.append)
            assert ''.join(pieces) == reply[:-1]
            assert bot.memory.get_user_profile() == {}
            assert [r[0] for r in bot.memory._conn.execute('SELECT role FROM memory_messages')] == ['user']
        finally:
            writer.close(); bot.memory.close(); engine.close()


def test_whole_output_replacement_does_not_append_the_old_pending_tail():
    reply = '旧句子。旧的末尾片段'
    with controlled_provider(delay=.001, reply_overrides={'fixture-tail': reply}) as (_, url):
        engine = LLMEngine(base_url=url, api_key='local-fixture', model='fixture')
        bot = Avatar(db_path=':memory:', llm=engine); pieces = []
        review = bot.boundaries.review_output
        def replace_final(text):
            return ('最终已替换的文字。', 'controlled_whole_review') if text == reply else review(text)
        bot.boundaries.review_output = replace_final
        try:
            result = bot.respond('fixture-tail', cancel=CancellationToken(), on_delta=pieces.append)
            assert result['reply'] == '最终已替换的文字。'
            assert pieces == ['旧句子。']
            assert bot.memory.get_short_term()[-1]['content'] == result['reply']
        finally:
            bot.memory.close(); engine.close()
