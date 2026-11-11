import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import pytest

from avatar.cancellation import CancellationToken, Cancelled
from avatar.mouth.tts import EdgeTTSEngine

OLD = b'previous-output'
PARTIAL = b'partial-output'
NEW = b'complete-output'


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('failure', ['error', 'cancel_partial', 'cancel_complete', 'empty', 'timeout'])
def test_failed_tts_preserves_old_target_or_leaves_new_target_absent(tmp_path, monkeypatch, existing, failure):
    target = tmp_path/'output.mp3'; token = CancellationToken(); during = []
    if existing: target.write_bytes(OLD)
    class Communicate:
        def __init__(self, *args, **kwargs): pass
        async def save(self, path):
            if failure == 'empty': return
            Path(path).write_bytes(PARTIAL)
            during.append(target.read_bytes() if target.exists() else None)
            if failure == 'error': raise OSError('fixture interrupted write')
            if failure == 'timeout': await asyncio.sleep(1)
            if failure == 'cancel_complete': Path(path).write_bytes(NEW)
            token.cancel()
            if failure == 'cancel_partial': await asyncio.sleep(.001)
    monkeypatch.setattr('avatar.mouth.tts.edge_tts.Communicate', Communicate)
    expected = {'error': OSError, 'cancel_partial': Cancelled, 'cancel_complete': Cancelled,
                'empty': ValueError, 'timeout': TimeoutError}[failure]
    with pytest.raises(expected):
        EdgeTTSEngine(timeout=.01).synthesize_cancellable('受控文本', str(target), cancel=token)
    if existing: assert target.read_bytes() == OLD
    else: assert not target.exists()
    assert all(content == (OLD if existing else None) for content in during)
    assert set(tmp_path.iterdir()) == ({target} if existing else set())


@pytest.mark.parametrize('existing', [False, True])
def test_success_is_published_only_when_complete_with_original_api_parameters(tmp_path, monkeypatch, existing):
    target = tmp_path/'output.mp3'; observed = []; calls = []
    if existing: target.write_bytes(OLD)
    class Communicate:
        def __init__(self, text, voice, **kwargs): calls.append((text, voice, kwargs))
        async def save(self, path):
            Path(path).write_bytes(PARTIAL)
            observed.append(target.read_bytes() if target.exists() else None)
            await asyncio.sleep(.001)
            Path(path).write_bytes(NEW)
    monkeypatch.setattr('avatar.mouth.tts.edge_tts.Communicate', Communicate)
    result = EdgeTTSEngine(voice='fixture-voice').synthesize('受控文本', str(target), '+4%', '-1Hz')
    assert result == str(target) and target.read_bytes() == NEW
    assert observed == [OLD if existing else None]
    assert calls == [('受控文本', 'fixture-voice', {'rate': '+4%', 'pitch': '-1Hz'})]
    assert set(tmp_path.iterdir()) == {target}


@pytest.mark.parametrize('existing', [False, True])
def test_pre_cancel_preserves_output_without_starting_component(tmp_path, monkeypatch, existing):
    target = tmp_path/'output.mp3'; token = CancellationToken(); token.cancel()
    if existing: target.write_bytes(OLD)
    class Never:
        def __init__(self, *args, **kwargs): pytest.fail('pre-cancelled synthesis started component')
    monkeypatch.setattr('avatar.mouth.tts.edge_tts.Communicate', Never)
    with pytest.raises(Cancelled):
        EdgeTTSEngine().synthesize_cancellable('受控文本', str(target), cancel=token)
    assert set(tmp_path.iterdir()) == ({target} if existing else set())
    if existing: assert target.read_bytes() == OLD


def test_late_cancelled_save_cannot_damage_another_calls_successful_output(tmp_path, monkeypatch):
    target = tmp_path/'output.mp3'; started = threading.Event(); published = threading.Event()
    token = CancellationToken()
    class Communicate:
        def __init__(self, text, *args, **kwargs): self.text = text
        async def save(self, path):
            if self.text == 'good':
                Path(path).write_bytes(NEW); return
            started.set()
            assert await asyncio.to_thread(published.wait, 2)
            Path(path).write_bytes(PARTIAL)
            token.cancel(); await asyncio.sleep(.001)
    monkeypatch.setattr('avatar.mouth.tts.edge_tts.Communicate', Communicate)
    engine = EdgeTTSEngine()
    def cancelled_save():
        with pytest.raises(Cancelled): engine.synthesize_cancellable('bad', str(target), cancel=token)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(cancelled_save)
        try:
            assert started.wait(2)
            assert engine.synthesize('good', str(target)) == str(target)
            assert target.read_bytes() == NEW
        finally: published.set()
        future.result(timeout=3)
    assert target.read_bytes() == NEW and set(tmp_path.iterdir()) == {target}


@pytest.mark.parametrize('phase', ['before', 'after'])
def test_checkpoint_runs_on_caller_thread_before_component_and_before_publish(tmp_path, monkeypatch, phase):
    target = tmp_path/'output.mp3'; target.write_bytes(OLD)
    caller = threading.get_ident(); revoked = phase == 'before'; calls = []
    class Communicate:
        def __init__(self, *args, **kwargs): calls.append('component')
        async def save(self, path):
            nonlocal revoked
            Path(path).write_bytes(NEW); revoked = True
    def check():
        assert threading.get_ident() == caller  # SQLite callbacks belong to this thread.
        if revoked: raise Cancelled('source revoked')
    monkeypatch.setattr('avatar.mouth.tts.edge_tts.Communicate', Communicate)
    with pytest.raises(Cancelled, match='source revoked'):
        EdgeTTSEngine().synthesize_cancellable('受控文本', str(target), checkpoint=check)
    assert calls == ([] if phase == 'before' else ['component'])
    assert target.read_bytes() == OLD and set(tmp_path.iterdir()) == {target}
