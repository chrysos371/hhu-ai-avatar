"""Post-run independent message/format/raw-output alignment, zero new inference."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/native-communication-v6')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return None if value is None else hashlib.sha256(json.dumps(value, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def main():
    manifest = json.loads((HERE/'native-raw-manifest-v6.json').read_text())
    assert {n: digest(Path(manifest['root'])/n) for n in manifest['sha256']} == manifest['sha256']
    requests = sorted(RAW.glob('trials/*/call-*-request.json'), key=lambda p: int(p.name.split('-')[1]))
    lines = (RAW/'trace.jsonl').read_bytes().splitlines(keepends=True)
    result = json.loads((HERE/'native-result-v6.json').read_text())
    count = result['actual_generate_calls']
    assert type(count) is int and 0 < count <= 260
    assert result['engineering_passed'] and result['actual_worker_wait_code'] == 0
    assert result['completed_trials'] == 62 and result['completed_turns'] == 104
    assert len(requests) == len(lines) == count == result['actual_client_native_calls']
    rows, offset = [], 0
    for number, (request, line) in enumerate(zip(requests, lines), 1):
        assert int(request.name.split('-')[1]) == number
        client = json.loads(request.read_text())
        response = request.with_name(request.name.replace('-request', '-response'))
        completed = json.loads(response.read_text())
        native = json.loads(line)
        assert native['outcome'] == 'completed' and completed['error'] is None
        assert client['messages'] == native['messages']
        assert completed['response'] == native['response']
        form = client['response_format']
        schema = form.get('json_schema', {}).get('schema') if isinstance(form, dict) else None
        assert native['response_format'] == form
        assert native['response_format_sha256'] == canonical(form)
        assert native['response_schema_sha256'] == canonical(schema)
        assert native['grammar_enabled'] is (form is not None)
        assert native['stream'] and native['finish_reason'] == 'stop'
        rows.append(dict(number=number, native_id=native['id'], trace_byte_offset=offset,
            trace_line_sha256=hashlib.sha256(line).hexdigest(), phase_from_client=client['phase'],
            request_path=str(request), request_sha256=digest(request), response_sha256=digest(response),
            provider_recorded_wire_sha256=native['request_body_sha256'],
            response_format_sha256=native['response_format_sha256'],
            response_schema_sha256=native['response_schema_sha256']))
        offset += len(line)
    assert {n: digest(Path(manifest['root'])/n) for n in manifest['sha256']} == manifest['sha256']
    report = dict(passed=True, actual_generate_calls=count, new_generate_calls=0,
        source_sha256=digest(Path(__file__)), raw_manifest_sha256=digest(HERE/'native-raw-manifest-v6.json'),
        scope='post-run exact logical messages/format/schema/native raw-output alignment; '
            'wire hash is provider-recorded, not independently reconstructed client wire bytes; no content approval',
        rows=rows)
    with (HERE/'native-alignment-v6.json').open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(count, 'exact native/client message, format/schema and raw-response matches; zero new inference')


if __name__ == '__main__':
    main()
