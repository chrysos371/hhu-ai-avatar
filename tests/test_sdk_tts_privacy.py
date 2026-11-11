import asyncio
from contextlib import closing, contextmanager
import wave

import numpy as np
import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from avatar.mouth.tts import EdgeTTSEngine

PRIVATE = '待删语音实验名'


class Engine:
    available = True
    def chat_analysis(self, *args, **kwargs):
        return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
    def chat(self, *args, **kwargs): return PRIVATE+'你好。'


def silence(path):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0'*1600)


@pytest.mark.parametrize('when,use_tts', [('commit', False), ('commit', True),
                                        ('tts', True), ('metadata', False)])
@pytest.mark.parametrize('change', ['cancel', 'external_forget', 'same_instance_forget'])
def test_sdk_rechecks_original_turn_after_commit_tts_and_metadata(tmp_path, monkeypatch, when, use_tts, change):
    path = str(tmp_path/'sdk.db'); token = CancellationToken(); calls = []; decoded = []; changed = []
    def alter():
        if changed: return
        changed.append(True)
        if change == 'cancel': token.cancel()
        elif change == 'same_instance_forget': bot.forget_memory(fragment)
        else:
            with closing(MemoryStore(path)) as writer: writer.forget(fragment)
    class TTS:
        def synthesize(self, text, out_path, rate, pitch):
            calls.append(text)
            if when == 'tts': alter()
            silence(out_path); return out_path
    bot = Avatar(db_path=path, llm=Engine(), tts=TTS())
    fragment = bot.memory.remember_user('名字', PRIVATE)
    original_transaction = bot.memory.transaction; original_summary = bot.conversation_summary
    def assistant_committed():
        return not bot.memory._conn.in_transaction and bot.memory._conn.execute(
            "SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()
    @contextmanager
    def transaction():
        with original_transaction(): yield
        if when == 'commit' and assistant_committed(): alter()
    def summary():
        result = original_summary()
        if when == 'metadata' and assistant_committed(): alter()
        return result
    def load_audio(*args, **kwargs):
        decoded.append(True); return np.zeros(1600, dtype=np.float32), 16000
    monkeypatch.setattr(bot.memory, 'transaction', transaction)
    monkeypatch.setattr(bot, 'conversation_summary', summary)
    monkeypatch.setattr('avatar.main.load_audio', load_audio)
    try:
        with pytest.raises(Cancelled):
            bot.respond('我的名字是'+PRIVATE+'。', use_tts=use_tts,
                        tts_path=str(tmp_path/'reply.wav'), cancel=token)
        assert changed == [True]
        assert len(calls) == (1 if when == 'tts' else 0) and not decoded
        stored = list(bot.memory._conn.execute("SELECT content FROM memory_messages WHERE role='assistant'"))
        assert len(stored) == 1  # It committed before the scheduled change.
        if change != 'cancel': assert PRIVATE not in stored[0][0]
    finally:
        bot.memory.close()


def test_sdk_passes_original_token_to_native_cancellable_tts(tmp_path):
    token = CancellationToken(); calls = []
    class TTS:
        def synthesize(self, *args):
            calls.append('plain'); silence(args[1]); return args[1]
        def synthesize_cancellable(self, text, path, rate, pitch, *, cancel=None):
            calls.append(cancel); silence(path); return path
    bot = Avatar(db_path=':memory:', llm=Engine(), tts=TTS())
    try:
        result = bot.respond('普通话题。', use_tts=True, tts_path=str(tmp_path/'reply.wav'), cancel=token)
        assert calls == [token] and result['lip_sync_frames'] is not None
    finally:
        bot.memory.close()


def test_sdk_legacy_synthesize_only_engine_keeps_path_and_parameters(tmp_path):
    calls = []; path = str(tmp_path/'reply.wav')
    class TTS:
        def synthesize(self, text, out_path, rate, pitch):
            calls.append((text, out_path, rate, pitch)); silence(out_path); return out_path
    bot = Avatar(db_path=':memory:', llm=Engine(), tts=TTS())
    try:
        result = bot.respond('普通话题。', use_tts=True, tts_path=path, cancel=CancellationToken())
        assert len(calls) == 1 and calls[0][0] == result['reply'] and calls[0][1] == result['audio_path'] == path
        assert result['lip_sync_frames'] is not None and result['lipsync_error'] is None
    finally:
        bot.memory.close()


@pytest.mark.parametrize('stop', [False, True])
def test_sdk_edge_uses_turn_token_for_actual_async_save_lifecycle(tmp_path, monkeypatch, stop):
    token = CancellationToken(); started = []; finished = []; path = str(tmp_path/'reply.wav')
    class Communicate:
        def __init__(self, text, voice, **kwargs): assert text
        async def save(self, out_path):
            started.append(True)
            if stop: token.cancel()
            await asyncio.sleep(.01)
            silence(out_path); finished.append(True)
    monkeypatch.setattr('avatar.mouth.tts.edge_tts.Communicate', Communicate)
    bot = Avatar(db_path=':memory:', llm=Engine(), tts=EdgeTTSEngine())
    try:
        if stop:
            with pytest.raises(Cancelled): bot.respond('普通话题。', use_tts=True, tts_path=path, cancel=token)
            assert started == [True] and not finished and not (tmp_path/'reply.wav').exists()
        else:
            result = bot.respond('普通话题。', use_tts=True, tts_path=path, cancel=token)
            assert started == finished == [True] and result['audio_path'] == path
    finally:
        bot.memory.close()
