"""Actual SQLite source validation with controlled elapsed wall-clock tests."""
from contextlib import closing
import json

import pytest

from avatar.brain.emotion import EmotionEngine
from avatar.brain.memory import MemoryStore
from avatar.brain.role_state import RoleStateStore, encode, digest
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar


class Offline:
    available = False


@pytest.fixture
def saved(tmp_path):
    with closing(MemoryStore(str(tmp_path/'role.db'))) as memory:
        bot = Avatar(memory=memory, llm=Offline(), summary_enabled=False)
        bot.emotion = EmotionEngine(clock=lambda: 0)
        result = bot.respond('我很开心。')
        store = RoleStateStore(memory, wallclock=lambda: 1000)
        assert store.save(bot.emotion, source=result['conversation'], scope='current_user')
        yield memory, bot, store, result


def test_restore_only_role_with_elapsed_decay_and_fresh_monotonic_anchor(saved):
    memory, bot, store, result = saved
    original = bot.emotion.role_snapshot()
    store.wallclock = lambda: 1300
    clock = [17.0]
    engine = EmotionEngine(clock=lambda: clock[0])
    assert store.restore(engine)
    assert engine.state.valence == pytest.approx(original['valence']/2)
    assert engine.state.arousal == pytest.approx(original['arousal']/2)
    assert engine.energy == pytest.approx(.5+(original['energy']-.5)*2**(-300/21600))
    assert engine.user_state.valence == engine.user_state.arousal == 0
    assert not engine._has_observation and engine._observation_text == ''
    clock[0] += 300
    assert engine.state.valence == pytest.approx(original['valence']/4)
    payload = memory._conn.execute('SELECT payload FROM memory_role_state').fetchone()[0]
    assert '我很开心' not in payload and result['reply'] not in payload


@pytest.mark.parametrize('change', ['forget', 'correct'])
def test_external_revision_change_removes_derived_snapshot(saved, change):
    memory, bot, store, result = saved
    fragment = memory.remember('公开观测来源', source_message_id=result['conversation']['user_message_id'])
    with closing(MemoryStore(memory.db_path)) as writer:
        writer.forget(fragment) if change == 'forget' else writer.correct(fragment, '公开更正')
    assert not memory._conn.execute('SELECT 1 FROM memory_role_state').fetchone()
    assert not store.restore(EmotionEngine())


@pytest.mark.parametrize('fault', ['version', 'revision', 'scope', 'source_hash', 'bool_source_id',
    'nan', 'range', 'future', 'policy', 'hash', 'duplicate', 'missing_source'])
def test_corrupt_or_stale_snapshot_rejected_without_restoring_user(saved, fault):
    memory, bot, store, result = saved
    payload = memory._conn.execute('SELECT payload FROM memory_role_state').fetchone()[0]
    data = json.loads(payload)
    if fault == 'version': data['version'] = True
    elif fault == 'revision': data['source']['revision'] += 1
    elif fault == 'scope': data['scope'] = 'fictional_character'
    elif fault == 'source_hash': data['sources'][0]['sha256'] = 'wrong'
    elif fault == 'bool_source_id': data['sources'][0]['id'] = True
    elif fault == 'nan': data['role']['valence'] = float('nan')
    elif fault == 'range': data['role']['energy'] = 9
    elif fault == 'future': data['saved_at'] = 1001
    elif fault == 'policy': data['role']['half_life_seconds'] = 99
    elif fault == 'missing_source':
        memory._conn.execute('DELETE FROM memory_messages WHERE id=?', (result['conversation']['user_message_id'],))
        memory._conn.commit()
    payload = json.dumps(data, ensure_ascii=False)
    if fault == 'duplicate': payload = payload[:-1]+',"version":1}'
    with memory.transaction():
        memory._conn.execute('UPDATE memory_role_state SET payload=?,payload_sha256=?',
            (payload, 'wrong' if fault == 'hash' else digest(payload)))
    engine = EmotionEngine()
    assert not store.restore(engine)
    assert engine.state.valence == engine.user_state.valence == 0


def test_incomplete_later_turn_prevents_restore(saved):
    memory, bot, store, result = saved
    memory.add_message('user', '后来取消但已入库的消息。', 'later-session')
    assert not store.restore(EmotionEngine())


def test_restore_never_commits_callers_unrelated_write(saved):
    memory, bot, store, result = saved
    memory._conn.execute('CREATE TABLE rollback_witness(value TEXT)')
    memory._conn.execute("INSERT INTO rollback_witness VALUES ('rollback-marker')")
    assert memory._conn.in_transaction
    assert RoleStateStore(memory, wallclock=lambda: 1000).restore(EmotionEngine())
    assert memory._conn.in_transaction
    memory._conn.rollback()
    assert not memory._conn.execute('SELECT 1 FROM rollback_witness').fetchone()
    assert store.restore(EmotionEngine())


def test_cancel_during_save_rolls_back_snapshot_and_preserves_live_observation(saved):
    memory, bot, store, result = saved
    before = tuple(memory._conn.execute('SELECT * FROM memory_role_state').fetchone())
    token = CancellationToken()
    calls = [0]
    def checkpoint():
        calls[0] += 1
        if calls[0] == 2: token.cancel()
        token.checkpoint()
    with pytest.raises(Cancelled):
        store.save(bot.emotion, source=result['conversation'], scope='current_user', checkpoint=checkpoint)
    assert tuple(memory._conn.execute('SELECT * FROM memory_role_state').fetchone()) == before
    assert bot.emotion.user_state.valence > 0


def test_legacy_empty_store_and_scope_optout_remain_neutral(tmp_path):
    with closing(MemoryStore(str(tmp_path/'old.db'))) as memory:
        store = RoleStateStore(memory)
        engine = EmotionEngine()
        assert not store.restore(engine) and not store.restore(engine, scope='fictional_character')
        assert engine.energy == .5
