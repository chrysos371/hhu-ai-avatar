"""Opt-in SDK/Web lifecycle integration; no model or human quality claim."""
from contextlib import closing

import pytest

from avatar.main import Avatar
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.web import create_server, run_chat
from avatar.web_state import automatic_emotion_snapshot


class Offline:
    available = False
    def close(self): pass


def test_sdk_reopen_preserves_role_but_not_last_user_observation(tmp_path):
    db = str(tmp_path/'sdk.db')
    first = Avatar(db_path=db, llm=Offline(), role_state_enabled=True, summary_enabled=False)
    try:
        first.respond('我很开心。')
        old = first.emotion.state.valence
    finally: first.memory.close()
    second = Avatar(db_path=db, llm=Offline(), role_state_enabled=True, summary_enabled=False)
    try:
        assert old*.98 < second.emotion.state.valence <= old
        assert second.emotion.user_state.valence == 0 and second.emotion._observation_text == ''
        result = second.respond('随便聊聊窗外。')
        assert result['valence'] > 0 and result['user_valence'] == 0
    finally: second.memory.close()


def test_optout_does_not_create_snapshot_table(tmp_path):
    bot = Avatar(db_path=str(tmp_path/'off.db'), llm=Offline(), role_state_enabled=False)
    try:
        bot.respond('我很开心。')
        assert bot.role_state_store is None
        assert not bot.memory._conn.execute("SELECT 1 FROM sqlite_master WHERE name='memory_role_state'").fetchone()
    finally: bot.memory.close()


@pytest.mark.parametrize('failure', ['cancel', 'tts'])
def test_unsuccessful_later_response_never_becomes_durable_completion(tmp_path, monkeypatch, failure):
    db = str(tmp_path/'failure.db')
    bot = Avatar(db_path=db, llm=Offline(), role_state_enabled=True, summary_enabled=False)
    try:
        bot.respond('我很开心。')
        old = tuple(bot.memory._conn.execute('SELECT * FROM memory_role_state').fetchone())
        if failure == 'cancel':
            token = CancellationToken()
            original = bot._fallback_reply
            def cancelled(*args, **kwargs):
                value = original(*args, **kwargs)
                token.cancel()
                return value
            monkeypatch.setattr(bot, '_fallback_reply', cancelled)
            with pytest.raises(Cancelled): bot.respond('我很难过。', cancel=token)
        else:
            class BrokenTTS:
                def synthesize(self, *args, **kwargs): raise RuntimeError('controlled TTS failure')
            bot.tts = BrokenTTS()
            with pytest.raises(RuntimeError): bot.respond('我很难过。', use_tts=True)
        assert tuple(bot.memory._conn.execute('SELECT * FROM memory_role_state').fetchone()) == old
    finally: bot.memory.close()
    reopened = Avatar(db_path=db, llm=Offline(), role_state_enabled=True)
    try: assert reopened.emotion.state.valence == reopened.emotion.user_state.valence == 0
    finally: reopened.memory.close()


def test_web_startup_state_and_chat_retain_role_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr('avatar.main.LLMEngine', Offline)
    db = str(tmp_path/'web.db')
    first = create_server(db, port=0, role_state_enabled=True)
    try:
        result = run_chat(first, '我很开心。')
        old = first.emotion.state.valence
    finally: first.server_close()
    second = create_server(db, port=0, role_state_enabled=True)
    try:
        with closing(MemoryStore(db)) as memory: state = automatic_emotion_snapshot(second, memory)
        assert old*.98 < state['automatic']['valence'] <= old
        assert state['user_observation']['valence'] == 0
        result = run_chat(second, '聊聊窗外。')
        assert result['valence'] > 0 and result['user_valence'] == 0
    finally: second.server_close()


def test_fictional_role_restores_only_verified_scope_and_exit_resets_old_scope(tmp_path):
    db = str(tmp_path/'fiction.db')
    first = Avatar(db_path=db, llm=Offline(), role_state_enabled=True, summary_enabled=False)
    try:
        first.respond('我来扮演一个虚构角色。')
        first.respond('我很开心。')
        old = first.emotion.state.valence
        assert old > .1
    finally: first.memory.close()
    second = Avatar(db_path=db, llm=Offline(), role_state_enabled=True, summary_enabled=False)
    try:
        assert second._restored_role_scope == 'fictional_character'
        assert old*.98 < second.emotion.state.valence <= old
        result = second.respond('回到现实')
        assert result['valence'] == result['arousal'] == 0
        assert result['speaker_attribution']['scope'] == 'current_user'
    finally: second.memory.close()


def test_corrupt_speaker_basis_cannot_restore_mood_even_with_valid_snapshot(tmp_path):
    db = str(tmp_path/'scope.db')
    first = Avatar(db_path=db, llm=Offline(), role_state_enabled=True)
    try:
        first.respond('我很开心。')
        with first.memory.transaction():
            first.memory._conn.execute("UPDATE memory_web_speaker_state SET source_ids_json='[true]'")
    finally: first.memory.close()
    second = Avatar(db_path=db, llm=Offline(), role_state_enabled=True)
    try: assert second.emotion.state.valence == 0 and second._restored_role_scope is None
    finally: second.memory.close()


@pytest.mark.parametrize('factory', [Avatar, create_server])
def test_role_flag_validation_precedes_any_database_write(tmp_path, factory):
    db = str(tmp_path/'invalid.db')
    with pytest.raises(ValueError, match='role_state_enabled'):
        factory(db_path=db, role_state_enabled=1)
    assert not (tmp_path/'invalid.db').exists()
