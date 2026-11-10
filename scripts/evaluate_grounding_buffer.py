"""Measure the explicit first-visible latency cost of opt-in full-response review."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
import subprocess
import time

from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken
from avatar.config import config
from avatar.main import Avatar
from evaluate_real_interaction import save, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a fresh output path')
    spec_path = Path('evals/interaction/cycle-02/grounding-stream-protocol.json')
    spec = json.loads(spec_path.read_text())
    provider = json.loads(args.provider.read_text())
    config.embedding.model = ''
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'source_sha256': {str(p): sha(p) for p in [Path(__file__), Path('src/avatar/main.py'), Path('src/avatar/brain/profile_grounding.py')]},
              'protocol': spec, 'protocol_sha256': sha(spec_path), 'provider': provider, 'rows': []}
    engine = LLMEngine(base_url=provider['url'], api_key='local-eval-only',
                       model=provider['model_id'], timeout=180, max_retries=0)
    try:
        for index, text in enumerate(spec['prompts'] * spec['repetitions']):
            for mode in (['baseline', 'candidate'] if index % 2 == 0 else ['candidate', 'baseline']):
                avatar = Avatar(db_path=':memory:', llm=engine, fast_analysis=True,
                    subject_prompt_enabled=True, profile_grounding_enabled=mode == 'candidate')
                pieces = []
                started = time.perf_counter()
                try:
                    result = avatar.respond(text, cancel=CancellationToken(),
                        on_delta=lambda piece: pieces.append({'seconds': time.perf_counter()-started, 'text': piece}))
                    complete = time.perf_counter()-started
                    report['rows'].append({'pair': index, 'mode': mode, 'input': text,
                        'first_visible_seconds': pieces[0]['seconds'] if pieces else complete,
                        'complete_seconds': complete, 'delta_count': len(pieces), 'deltas': pieces,
                        'result': result})
                    save(args.output, report)
                    print(index, mode, report['rows'][-1]['first_visible_seconds'], complete, flush=True)
                finally:
                    avatar.memory.close()
    finally:
        engine.close()
    report['summary'] = {mode: {key: median(row[key] for row in report['rows'] if row['mode'] == mode)
        for key in ['first_visible_seconds', 'complete_seconds']} for mode in ['baseline', 'candidate']}
    report['valid'] = len(report['rows']) == 12 and all(row['result']['generation_mode'] == 'llm' for row in report['rows'])
    report['semantic_approved'] = False
    save(args.output, report)
    print(json.dumps(report['summary'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
