"""Paired HTTP/SDK transport experiment; records whole-pipeline and isolated results."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import statistics
import threading
import time

from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=10)
    args = parser.parse_args()
    if args.output.exists() or args.repeats < 10:
        parser.error('output must be new and repeats must be at least 10')
    rows, cancellations = [], []
    with controlled_provider(delay=0.04) as (server, url):
        engine = LLMEngine(base_url=url, api_key='controlled-local', model='fixture')
        try:
            engine.chat([{'role': 'user', 'content': 'warmup'}])
            engine.stream_chat([{'role': 'user', 'content': 'warmup'}])
            for index in range(args.repeats):
                # Alternate A/B order; use the same provider, prompt, pacing and output.
                for mode in (['baseline', 'stream'] if index % 2 == 0 else ['stream', 'baseline']):
                    for scope in ('transport_only', 'whole_pipeline'):
                        first = []
                        avatar = Avatar(db_path=':memory:', llm=engine, fast_analysis=mode == 'stream') if scope == 'whole_pipeline' else None
                        start = time.perf_counter()
                        callback = lambda text: first.append(time.perf_counter() - start)
                        if avatar:
                            result = avatar.respond('请简短解释云为什么会移动。', **(
                                {'cancel': CancellationToken(), 'on_delta': callback} if mode == 'stream' else {}))['reply']
                            avatar.memory.close()
                        elif mode == 'stream':
                            result = engine.stream_chat([{'role': 'user', 'content': '请简短解释云为什么会移动。'}], on_delta=callback)
                        else:
                            result = engine.chat([{'role': 'user', 'content': '请简短解释云为什么会移动。'}])
                        complete = time.perf_counter() - start
                        rows.append({'repeat': index, 'mode': mode, 'scope': scope,
                            'first_visible_seconds': first[0] if first else complete,
                            'complete_seconds': complete, 'reply': result})
            for phase in ('delay-headers', 'streaming'):
                for index in range(args.repeats):
                    token, outcome = CancellationToken(), []
                    server.started.clear()
                    def work():
                        try:
                            engine.stream_chat([{'role': 'user', 'content': 'delay-headers' if phase == 'delay-headers' else 'hello'}], cancel=token)
                        except Cancelled:
                            outcome.append('cancelled')
                    worker = threading.Thread(target=work)
                    worker.start()
                    assert server.started.wait(5)
                    start = time.perf_counter()
                    token.cancel()
                    worker.join(5)
                    cancellations.append({'phase': phase, 'repeat': index,
                        'seconds': time.perf_counter() - start, 'cancelled': outcome == ['cancelled']})
        finally:
            engine.close()
    comparisons = {}
    for scope in ('transport_only', 'whole_pipeline'):
        medians = {mode: statistics.median(r['first_visible_seconds'] for r in rows if r['scope'] == scope and r['mode'] == mode)
                   for mode in ('baseline', 'stream')}
        comparisons[scope] = medians | {'ratio': medians['stream'] / medians['baseline'],
                                       'passes_50pct_gate': medians['stream'] <= 0.5 * medians['baseline']}
    samples = sorted(r['seconds'] for r in cancellations)
    p95 = samples[max(0, int(len(samples) * 0.95 + 0.9999) - 1)]
    report = {'kind': 'controlled_transport_not_model_quality', 'python': platform.python_version(),
        'provider_delay_per_4_char_chunk_seconds': 0.04, 'repeats': args.repeats,
        'candidate_policy': 'streaming plus conservative impersonal-knowledge analysis route; personal/emotional inputs unchanged',
        'comparisons': comparisons, 'cancellation_p95_seconds': p95,
        'cancellation_gate_passed': all(r['cancelled'] for r in cancellations) and p95 < 0.5,
        'rows': rows, 'cancellations': cancellations,
        'sources_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__), Path('src/avatar/main.py'), Path('src/avatar/brain/llm.py'), Path('src/avatar/lab/transport_fixture.py')]}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'cancellations', 'sources_sha256')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
