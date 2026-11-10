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
