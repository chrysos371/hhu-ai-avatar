"""Owned HTTP/SQLite recording and early-stop controls; zero native inference."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('release_writing_native_control', HERE/'native_communication_v14.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
from avatar.lab.transport_fixture import controlled_provider
from avatar.cancellation import CancellationToken, Cancelled


def synthetic(messages, response, form):
    schema = form.get('json_schema', {}).get('schema') if isinstance(form, dict) else None
    return dict(outcome='completed', finish_reason='stop', messages=messages, response=response,
        response_format=form, response_format_sha256=driver.canonical(form),
        response_schema_sha256=driver.canonical(schema), grammar_enabled=form is not None, stream=True)


def main():
    root = Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/native-writing-driver-controls-v14')
    root.mkdir(parents=True, exist_ok=False)
    result = dict(completed_trials=0, completed_turns=0, actual_native_generate_calls=0)
    def controlled(number, messages, response, form):
        row = synthetic(messages, response, form)
        driver.validate_native_record(row, messages, response, form)
        return dict(trace_source='controlled_http_synthetic_integrity_fields_not_native', request_number=number)
    driver.native_record = controlled
    with controlled_provider(delay=.001) as (_, url):
        driver.trials(url, root, result)
        assert result['completed_trials'] == 136 and result['completed_turns'] == 258
        negative = root/'negative'; negative.mkdir()
        token = CancellationToken(); token.cancel()
        engine = driver.RecordedLLM(url, negative, [0])
        try:
            try: engine.stream_chat([dict(role='user', content='不应发请求')], cancel=token)
            except Cancelled: pass
            else: raise AssertionError('pre-cancel did not propagate')
            assert not engine.calls and engine.budget[0] == 0 and not list(negative.glob('call-*'))
            def truncated(number, messages, response, form):
                row = synthetic(messages, response, form); row['finish_reason'] = 'length'
                driver.validate_native_record(row, messages, response, form)
            driver.native_record = truncated
            try: engine.stream_chat([dict(role='user', content='只执行一次截断控制')])
            except driver.NativeProtocolStop: pass
            else: raise AssertionError('truncation did not stop')
            assert engine.budget[0] == 1 and engine.calls == [1] and len(engine.errors) == 1
            assert driver.read(negative/'call-001-response.json')['error']
        finally:
            engine.close()
    # Every integrity dimension must independently stop, rather than falling
    # into Avatar's ordinary model-unavailable/reply-error fallback.
    messages = [dict(role='user', content='来源')]; response = '正文'
    form = dict(type='json_schema', json_schema=dict(schema=dict(type='object')))
    sample = synthetic(messages, response, form)
    rejected = []
    for key, bad in [('finish_reason','length'), ('finish_reason',None), ('outcome','client_disconnected'),
            ('messages',[]), ('response','不同原文'), ('response_format',None),
            ('response_format_sha256','bad'), ('response_schema_sha256','bad'),
            ('grammar_enabled',False), ('stream',False)]:
        row = copy.deepcopy(sample); row[key] = bad
        try: driver.validate_native_record(row, messages, response, form)
        except driver.NativeProtocolStop: rejected.append(dict(field=key, value=bad))
        else: raise AssertionError('invalid integrity field accepted: '+key)
    result.update(passed=True, integrity_negative_controls=rejected,
        source_ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=driver.ROOT,text=True).strip(),
        source_sha256={str(p.relative_to(driver.ROOT)):driver.digest(p) for p in
            (Path(__file__), HERE/'native_communication_v14.py', HERE/'native-cases-v14.json')},
        scope='actual controlled HTTP/SQLite/delta/final/recording; synthetic native integrity fields only; no model/semantic approval')
    driver.immutable(root/'result.json',result)
    driver.immutable(HERE/'native-driver-controls-v14.json',result)
    driver.immutable(HERE/'native-driver-controls-raw-v14.json',dict(root=str(root),
        sha256={str(p.relative_to(root)):driver.digest(p) for p in sorted(root.rglob('*')) if p.is_file()}))
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','integrity_negative_controls')},ensure_ascii=False))


if __name__ == '__main__': main()
