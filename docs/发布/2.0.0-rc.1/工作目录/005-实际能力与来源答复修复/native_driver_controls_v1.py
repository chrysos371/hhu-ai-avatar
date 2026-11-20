"""Exercise all trial/SQL/recording paths against controlled HTTP, never a model."""
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('native_communication_control', HERE/'native_communication_v1.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
from avatar.lab.transport_fixture import controlled_provider
from avatar.cancellation import CancellationToken, Cancelled


def main():
    root = Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/native-driver-controls-v1')
    root.mkdir(parents=True, exist_ok=False)
    result = dict(completed_trials=0, completed_turns=0)
    with controlled_provider(delay=.001, reply_overrides={
        '我刚才自己给同学发了短信': '我已经替你发送短信。'}) as (_, url):
        driver.trials(url, root, result)
        assert result['completed_trials'] == 36 and result['completed_turns'] == 62
        base = driver.read(root/'trials/K01-baseline/turn-01.json')
        candidate = driver.read(root/'trials/K01-candidate/turn-01.json')
        assert base['result']['reply'] == '我已经替你发送短信。'
        assert candidate['result']['reply'] != base['result']['reply']
        assert candidate['result']['generation_mode'] == 'llm_capability_guarded'
        calls = candidate['native_call_numbers']
        assert driver.read(root/f'trials/K01-candidate/call-{calls[-1]:03d}-response.json')['response'] == base['result']['reply']
        negative = root/'negative-cancel'
        negative.mkdir()
        token = CancellationToken()
        token.cancel()
        engine = driver.RecordedLLM(url, negative, [0])
        try:
            try:
                engine.stream_chat([dict(role='user', content='不应实际请求')], cancel=token)
            except Cancelled:
                pass
            else:
                raise AssertionError('pre-cancel did not propagate')
            assert engine.errors
            assert driver.read(negative/'call-001-response.json')['error']
        finally:
            engine.close()
    result.update(passed=True, source_ref=subprocess.check_output(['git', 'rev-parse', 'HEAD'],
        cwd=driver.ROOT, text=True).strip(), source_sha256={str(p.relative_to(driver.ROOT)): driver.digest(p)
            for p in (Path(__file__), HERE/'native_communication_v1.py', HERE/'native-cases-v1.json')},
        scope='controlled HTTP recording/SQL/dispatch only; zero native GPU calls or semantic approval')
    driver.immutable(root/'result.json', result)
    driver.immutable(HERE/'native-driver-controls-v1.json', result)
    driver.immutable(HERE/'native-driver-controls-raw-v1.json', dict(root=str(root),
        sha256={str(p.relative_to(root)): driver.digest(p) for p in sorted(root.rglob('*')) if p.is_file()}))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
