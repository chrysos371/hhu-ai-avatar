"""Companion pilot runner. No teacher calls or real user databases by default."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def load_suite(path):
    suite = json.loads(Path(path).read_text(encoding='utf-8'))
    ids = set()
    for case in suite['cases']:
        if case['id'] in ids or case['category'] not in {'memory', 'emotion', 'boundary'}:
            raise ValueError('Duplicate id or invalid category')
        ids.add(case['id'])
        if not case['turns'] or not all(isinstance(t, str) and t.strip() for t in case['turns']):
            raise ValueError('Non-empty user turns required')
        if not case['checks'] or not case['forbidden']:
            raise ValueError('Review criteria required')
        if case.get('before_last_action') not in (None, 'forget_name'):
            raise ValueError('Unknown action')
    return suite


class TracedModel:
    available = True

    def __init__(self, model, base_url, key, timeout, smoke=False, temperature_override=None):
        from openai import OpenAI
        self.smoke = smoke
        self.model = model
        self.calls = []
        self.temperature_override = temperature_override
        self.client = None if smoke else OpenAI(base_url=base_url, api_key=key,
                                               timeout=timeout, max_retries=0)

    def chat(self, messages, temperature=0, max_tokens=512, response_format=None):
        requested_temperature = temperature
        if self.temperature_override is not None:
            temperature = self.temperature_override
        row = dict(messages=json.loads(json.dumps(messages)), temperature=temperature,
                   requested_temperature=requested_temperature, max_tokens=max_tokens)
        self.calls.append(row)
        if response_format is not None:
            row['response_format'] = response_format
        start = time.perf_counter()
        try:
            if self.smoke:
                reply = ('{"emotion":{"valence":0,"arousal":0},"facts":[]}'
                         if '事实提取器' in messages[0]['content'] else '离线冒烟占位回复。')
            else:
                options = {'response_format': response_format} if response_format is not None else {}
                response = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=temperature,
                    max_tokens=max_tokens, **options)
                row['response'] = response.model_dump(mode='json')
                row['finish_reason'] = response.choices[0].finish_reason
                row['truncated'] = row['finish_reason'] == 'length'
                reply = response.choices[0].message.content
                if not isinstance(reply, str) or not reply.strip():
                    raise ValueError('Empty model reply')
            row['reply'] = reply
            return reply
        except Exception as exc:
            # Exception text may contain credentials/headers: retain type only.
            row['error'] = type(exc).__name__
            raise
        finally:
            row['seconds'] = round(time.perf_counter() - start, 4)

    def chat_analysis(self, messages, temperature=0):
        from avatar.brain.analysis_protocol import ANALYSIS_RESPONSE_FORMAT
        return self.chat(messages, temperature=temperature, response_format=ANALYSIS_RESPONSE_FORMAT)


class FallbackTrace(logging.Handler):
    """Capture fixed Avatar fallback messages without changing production behavior."""
    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        if record.msg in ('认知分析失败，回退规则分析', '模型回复失败，使用规则回复'):
            self.events.append(str(record.msg))


def run(suite, mode, llm, temp_root=None, on_case=None, boundary_mode='enabled'):
    from avatar.main import Avatar
    reports = []
    for case in suite['cases']:
        item = dict(id=case['id'], category=case['category'], checks=case['checks'],
                    forbidden=case['forbidden'], turns=[], status='completed', backend_checks={})
        reports.append(item)
        if mode == 'model' and case.get('before_last_action'):
            item['status'] = 'not_applicable'
            if on_case:
                on_case(reports)
            continue
        with tempfile.TemporaryDirectory(prefix='companion-', dir=temp_root) as tmp:
            avatar = Avatar(db_path=str(Path(tmp) / 'memory.db'), llm=llm) if mode != 'model' else None
            if avatar and boundary_mode == 'disabled':
                # Evaluation-only ablation: keep all other backend behavior identical.
                from avatar.brain.boundaries import BoundaryDecision, BOUNDARY_PROMPT
                class PassThrough:
                    def assess(self, text):
                        return BoundaryDecision()
                avatar.boundaries = PassThrough()
                original_prompt = avatar._system_prompt
                avatar._system_prompt = lambda *a, **k: original_prompt(*a, **k).replace(BOUNDARY_PROMPT + '\n', '')
            messages = [dict(role='system', content='你是小海，一个温柔又有点好奇心的AI伙伴。请自然、简短地回应用户。')]
            try:
                for index, text in enumerate(case['turns']):
                    if index == len(case['turns']) - 1 and case.get('before_last_action') == 'forget_name':
                        names = [r for r in avatar.list_memories() if r.get('profile_key') == '名字']
                        item['backend_checks']['forget_prerequisite'] = bool(names)
                        for row in names:
                            avatar.forget_memory(row['id'])
                        item['backend_checks']['name_versions_removed'] = not any(
                            r.get('profile_key') == '名字' for r in avatar.list_memories(include_history=True))
                        item['backend_checks']['short_term_cleared'] = not avatar.memory.get_short_term()
                    before = len(llm.calls)
                    start = time.perf_counter()
                    turn = dict(number=index + 1, user=text)
                    fallback_trace = FallbackTrace()
                    avatar_logger = logging.getLogger('avatar.main')
                    avatar_logger.addHandler(fallback_trace)
                    try:
                        if avatar:
                            turn['result'] = avatar.respond(text)
                            turn['memories'] = [avatar.inspect_memory(r['id']) for r in avatar.list_memories()]
                            turn['reminders'] = avatar.reminders.list()
                        else:
                            messages.append(dict(role='user', content=text))
                            reply = llm.chat(messages)
                            messages.append(dict(role='assistant', content=reply))
                            turn['result'] = dict(reply=reply)
                    except Exception as exc:
                        turn['error'] = type(exc).__name__
                        item['status'] = 'error'
                    finally:
                        avatar_logger.removeHandler(fallback_trace)
                    turn['fallback_events'] = fallback_trace.events
                    turn['seconds'] = round(time.perf_counter() - start, 4)
                    turn['calls'] = llm.calls[before:]
                    if 'expected_routes' in case and avatar:
                        turn['expected_boundary_route'] = case['expected_routes'][index]
                        turn['boundary_route_match'] = (turn.get('result', {}).get('boundary', {}).get('route')
                                                        == turn['expected_boundary_route'])
                    turn['truncated'] = any(c.get('truncated', False) for c in turn['calls'])
                    turn['degraded'] = avatar is not None and (bool(fallback_trace.events) or
                                                             any('error' in c for c in turn['calls']))
                    if turn['degraded']:
                        item['status'] = 'error'
                    item['turns'].append(turn)
                    if 'error' in turn:
                        break
            finally:
                if avatar:
                    avatar.memory.close()
        if on_case:
            on_case(reports)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, default=ROOT / 'evals/companion/pilot.json')
    parser.add_argument('--mode', choices=['smoke', 'model', 'avatar'], required=True)
    parser.add_argument('--model')
    parser.add_argument('--case-ids', nargs='+', help='Explicit subset; unknown/duplicate IDs are rejected')
    parser.add_argument('--base-url', default='http://localhost:11434/v1')
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--temperature-override', type=float,
                        help='Force all model calls to this temperature for controlled comparisons')
    parser.add_argument('--boundary-mode', choices=['enabled', 'disabled'], default='enabled',
                        help='Evaluation-only ablation; disabled removes new boundary prompt and routes')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.mode != 'smoke' and not args.model:
        parser.error('--model required for real evaluation')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    if args.temperature_override is not None and not 0 <= args.temperature_override <= 2:
        parser.error('--temperature-override must be in 0..2')
    from urllib.parse import urlsplit
    endpoint = urlsplit(args.base_url)
    if endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        parser.error('Credentials and query parameters must not appear in --base-url')
    suite = load_suite(args.suite)
    if args.case_ids:
        known = {case['id'] for case in suite['cases']}
        if len(set(args.case_ids)) != len(args.case_ids) or set(args.case_ids) - known:
            parser.error('Unknown or duplicate case IDs')
        suite['cases'] = [case for case in suite['cases'] if case['id'] in args.case_ids]
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error('Output directory must be empty')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    llm = TracedModel(args.model, args.base_url, os.getenv('COMPANION_EVAL_API_KEY', 'ollama'),
                      args.timeout, smoke=args.mode == 'smoke',
                      temperature_override=args.temperature_override)
    report = dict(mode=args.mode, model=args.model, base_url=args.base_url, suite_version=suite['version'],
                  suite_sha256=hashlib.sha256(args.suite.read_bytes()).hexdigest(),
                  python=platform.python_version(), openai=importlib.metadata.version('openai'),
                  source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [Path(__file__), *sorted((ROOT / 'src/avatar').rglob('*.py'))]},
                  selected_case_ids=[case['id'] for case in suite['cases']], completed=False,
                  temperature_override=args.temperature_override,
                  boundary_mode=args.boundary_mode,
                  note='Smoke is infrastructure-only; human ratings pending. No quality aggregate.')
    def checkpoint(cases):
        report['cases'] = cases
        (args.output_dir / 'report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(dict(case=cases[-1]['id'], status=cases[-1]['status'],
                              finished=len(cases), total=len(suite['cases']))), flush=True)
    report['cases'] = run(suite, args.mode, llm, args.output_dir, checkpoint, args.boundary_mode)
    report['completed'] = True
    report['call_errors'] = sum('error' in c for c in llm.calls)
    report['case_errors'] = sum(c['status'] == 'error' for c in report['cases'])
    (args.output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['case_id', 'status', 'reviewer', 'memory', 'emotion', 'boundary', 'tool_honesty',
              'naturalness', 'hard_failure', 'evidence_turns', 'reason']
    with (args.output_dir / 'review.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for case in report['cases']:
            writer.writerow(dict(case_id=case['id'], status=case['status']))
    print(json.dumps(dict(cases=len(report['cases']), call_errors=report['call_errors'],
                          case_errors=report['case_errors'], output=str(args.output_dir)), ensure_ascii=False))
    return int(bool(report['case_errors']))


if __name__ == '__main__':
    raise SystemExit(main())
