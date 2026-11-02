"""Seeded local dialogue evaluation, isolated SQLite databases and raw evidence.

Example: python scripts/evaluate_backend.py --model qwen2.5:7b \
    --embedding-model bge-m3 --output /absolute/path/report.json
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from avatar.main import Avatar
from avatar.brain.embeddings import OllamaEmbeddingProvider
from avatar.brain.memory import MemoryStore


# Hand-labeled narrow extraction cases, separate from heterogeneous backend checks.
FACT_CASES = [
    dict(id='explicit-name-and-preference', user='我叫阿岚，我喜欢咖啡。',
         expected=[dict(type='名字', content='阿岚'), dict(type='偏好', content='喜欢咖啡')]),
    dict(id='explicit-negative', user='我现在不喜欢香菜。',
         expected=[dict(type='偏好', content='不喜欢香菜')]),
    dict(id='current-reversal', user='我喜欢咖啡，我现在不再喜欢咖啡。',
         expected=[dict(type='偏好', content='不喜欢咖啡')]),
    dict(id='hypothesis', user='假如我叫小红，我喜欢香菜。', expected=[]),
    dict(id='other-person', user='我朋友喜欢茶。', expected=[]),
    dict(id='quoted-topic-shift', user='我以前喜欢咖啡，朋友说“茶”，现在不喜欢了。', expected=[]),
    dict(id='inherited-subject-shift', user='我朋友以前喜欢茶，现在不喜欢了。',
         context=['我喜欢咖啡'], expected=[]),
]


def score_facts(expected, actual):
    """Exact type/content labels; raw candidates are not repaired by backend gates."""
    aliases = {'称呼': '名字', '姓名': '名字', '爱好': '偏好', '喜欢': '偏好'}

    def pairs(facts):
        return {(aliases.get(f['type'], f['type']), f['content'].replace('不再喜欢', '不喜欢'))
                for f in facts if isinstance(f, dict) and isinstance(f.get('type'), str)
                and isinstance(f.get('content'), str)}

    wanted, got = pairs(expected), pairs(actual or [])
    malformed = sum(not isinstance(f, dict) or not isinstance(f.get('type'), str)
                    or not isinstance(f.get('content'), str) for f in (actual or []))
    return dict(expected_facts=len(wanted), correct_facts=len(wanted & got),
                missing_facts=len(wanted - got), false_writes=len(got - wanted) + malformed,
                exact=actual is not None and wanted == got and not malformed,
                abstained=actual == [])


def summarize_facts(cases, key):
    scores = [case[key + '_score'] for case in cases]
    totals = {field: sum(score[field] for score in scores)
              for field in ('expected_facts', 'correct_facts', 'missing_facts', 'false_writes')}
    totals.update(exact_cases=sum(score['exact'] for score in scores),
                  accuracy=sum(score['exact'] for score in scores) / len(scores),
                  completeness=totals['correct_facts'] / totals['expected_facts'] if totals['expected_facts'] else None,
                  abstained_cases=sum(score['abstained'] for score in scores),
                  expected_abstention_successes=sum(case[key + '_score']['exact'] for case in cases if not case['expected_facts']),
                  abstention_false_writes=sum(case[key + '_score']['false_writes'] for case in cases if not case['expected_facts']))
    return totals


def score_answer(reply, expected, forbidden=(), abstention=False):
    """Transparent lexical labels only, not a general semantic answer judge."""
    hits = sum(any(token in reply for token in alternatives) for alternatives in expected)
    stale = [name for name in forbidden if name in reply]
    uncertainty = bool(re.search(r'不知道|不确定|不清楚|不记得|没有.{0,8}(?:名字|姓名|称呼)|无法确认|尚未记录', reply))
    false_history = bool(re.search(r'(?:从未|没(?:有)?|还没|未曾|并未).{0,8}(?:告诉|提供|说过|提过)', reply))
    correct = not stale and (uncertainty and not false_history if abstention else hits == len(expected))
    return dict(correct=bool(correct), expected_items=len(expected), matched_items=hits,
                stale_names=stale, uncertainty=uncertainty, false_history_claim=false_history,
                expected_abstention=abstention)


def summarize_latencies(turns):
    def median(rows):
        return statistics.median(row['seconds'] for row in rows) if rows else None

    extraction = [row for row in turns if row['scenario'].startswith('labeled-extraction/')]
    conversation = [row for row in turns if not row['scenario'].startswith('labeled-extraction/')]
    return dict(median_turn_seconds=median(turns), conversation_median_seconds=median(conversation),
                extraction_case_median_seconds=median(extraction),
                latency_note='Legacy median mixes all turns. Separate medians distinguish conversation (configured embeddings) from labeled extraction (embeddings disabled). Both include analysis and reply calls.')


class LocalChat:
    available = True

    def __init__(self, model, base_url, timeout):
        self.model, self.base_url, self.timeout = model, base_url.rstrip('/'), timeout
        self.calls = []

    def chat(self, messages, temperature=.8, max_tokens=768):
        started = time.perf_counter()
        record = dict(stage='analysis' if temperature == 0 else 'reply')
        try:
            payload = dict(model=self.model, messages=messages, temperature=temperature,
                           max_tokens=max_tokens, seed=42)
            request = urllib.request.Request(self.base_url + '/v1/chat/completions',
                data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
            choice = data['choices'][0]
            record.update(content=choice['message']['content'], finish_reason=choice.get('finish_reason'))
            return record['content']
        except Exception as error:
            record['error'] = type(error).__name__
            raise
        finally:
            record['seconds'] = round(time.perf_counter() - started, 3)
            self.calls.append(record)


def evaluate(model, embedding_model, base_url, output, timeout):
    llm = LocalChat(model, base_url, timeout)
    embedder = OllamaEmbeddingProvider(base_url, embedding_model, timeout) if embedding_model else None
    report = dict(model=model, embedding_model=embedding_model, seed=42, turns=[], checks={},
                  fact_cases=[], answer_cases=[])

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    started = time.perf_counter()
    llm.chat([{'role': 'user', 'content': '只回答一个字：好'}], temperature=0, max_tokens=8)
    report['chat_warmup_seconds'] = round(time.perf_counter() - started, 3)
    if embedder:
        started = time.perf_counter()
        embedder.embed('向量模型预热')
        report['embedding_warmup_seconds'] = round(time.perf_counter() - started, 3)
    llm.calls.clear()

    def turn(avatar, text, scenario):
        before, started = len(llm.calls), time.perf_counter()
        result = avatar.respond(text)
        calls = llm.calls[before:]
        raw_facts = None
        for call in calls:
            if call.get('stage') == 'analysis' and 'content' in call:
                try:
                    parsed = json.loads(Avatar._extract_json(call['content']))
                    if isinstance(parsed, dict) and isinstance(parsed.get('facts'), list):
                        raw_facts = parsed['facts']
                except (TypeError, ValueError):
                    pass
        memories = avatar.list_memories()
        admitted = []
        for memory in memories:
            sources = avatar.inspect_memory(memory['id'])['sources']
            if any(source['source_message_id'] == avatar._current_message_id for source in sources):
                kind, _, content = memory['content'].partition(': ')
                admitted.append(dict(type=kind, content=content))
        report['turns'].append(dict(scenario=scenario, user=text, result=result,
            profile=avatar.memory.get_user_profile(), memories=memories,
            raw_model_facts=raw_facts, admitted_facts=admitted,
            seconds=round(time.perf_counter() - started, 3), calls=calls))
        save()
        print(json.dumps(dict(model=model, turn=len(report['turns']), strategy=result['strategy'])), flush=True)
        return result

    def answer_case(result, scenario, expected, forbidden=(), abstention=False, prerequisite_met=True):
        score = score_answer(result['reply'], expected, forbidden, abstention)
        score['correct'] = score['correct'] and prerequisite_met
        report['answer_cases'].append(dict(scenario=scenario, reply=result['reply'],
            expected=expected, forbidden_names=list(forbidden), prerequisite_met=prerequisite_met, **score))
        return score

    with tempfile.TemporaryDirectory(prefix='avatar-eval-') as temp:
        db = str(Path(temp) / 'memory.db')
        avatar = Avatar(memory=MemoryStore(db, embedder=embedder), llm=llm, session_id='first')
        try:
            for text in ['我叫阿岚，我喜欢喝咖啡，我讨厌香菜。',
                         '我以前喜欢喝咖啡，现在已经不喜欢了。',
                         '以后叫我小岚。',
                         '假如我叫小红，而且喜欢香菜，你会怎么介绍我？',
                         '我实际叫什么？现在还喜欢喝咖啡吗？']:
                result = turn(avatar, text, 'memory-evolution')
            answer_case(result, 'current-recall', [['小岚'], ['咖啡'], ['不喜欢', '不爱', '不再喜欢']], ['阿岚', '小红'])
            profile = avatar.memory.get_user_profile()
            report['checks']['current_name'] = profile.get('名字') == '小岚'
            report['checks']['current_negative_preference'] = '不喜欢' in profile.get('偏好', '') and '咖啡' in profile.get('偏好', '')
            report['checks']['hypothesis_not_written'] = '小红' not in str(avatar.list_memories(include_history=True))
            report['checks']['historical_positive_excluded'] = not any(
                r['content'] in ('偏好: 喜欢喝咖啡', '偏好: 喜欢咖啡') for r in avatar.list_memories())
            name = next((r for r in avatar.list_memories() if r.get('profile_key') == '名字'), None)
            report['checks']['durable_source'] = bool(name and avatar.inspect_memory(name['id'])['sources'])
        finally:
            avatar.memory.close()

        avatar = Avatar(memory=MemoryStore(db, embedder=embedder), llm=llm, session_id='second')
        try:
            result = turn(avatar, '你还记得我的名字、现在的饮料偏好和不喜欢吃的东西吗？', 'cross-session')
            answer_case(result, 'cross-session', [['小岚'], ['咖啡'], ['香菜']], ['阿岚', '小红'])
            report['checks']['cross_session_name_intact'] = avatar.memory.get_user_profile().get('名字') == '小岚'
            for text in ['考试没过，我很难过，但暂时不想听建议。',
                         '别安慰我了，帮我分析一下怎么复习。',
                         '刚查到成绩改正了，我及格啦！',
                         '我特别生气，简直要崩溃！！']:
                result = turn(avatar, text, 'emotion-strategy')
                if '暂时不想听建议' in text:
                    report['checks']['listen_when_requested'] = result['strategy'] == 'listen'
                if '分析' in text:
                    report['checks']['practical_help_overrides_mood'] = result['strategy'] == 'advise'
                if '及格' in text:
                    report['checks']['celebrates_good_news'] = result['strategy'] == 'celebrate'
                if '特别生气' in text:
                    report['checks']['role_does_not_mirror_anger'] = result['valence'] >= 0 and result['strategy'] == 'empathize'
            name = next((r for r in avatar.list_memories() if r.get('profile_key') == '名字'), None)
            for check in ('manual_correction', 'forgotten_versions_removed', 'forgotten_context_cleared',
                          'forgotten_reply_has_no_stale_name', 'forgotten_reply_abstains'):
                report['checks'][check] = False
            if name:
                corrected = avatar.correct_memory(name['id'], '小舟')
                report['checks']['manual_correction'] = avatar.memory.get_user_profile().get('名字') == '小舟'
                avatar.forget_memory(corrected)
                report['checks']['forgotten_versions_removed'] = not any(r.get('profile_key') == '名字' for r in avatar.list_memories(include_history=True))
                report['checks']['forgotten_context_cleared'] = avatar.memory.get_short_term() == []
            result = turn(avatar, '你还知道我叫什么吗？不知道就直说。', 'after-forgetting')
            score = answer_case(result, 'after-forgetting', [], ['阿岚', '小岚', '小舟', '小红'],
                                abstention=True, prerequisite_met=bool(name))
            report['checks']['forgotten_reply_has_no_stale_name'] = bool(name) and not score['stale_names']
            report['checks']['forgotten_reply_abstains'] = score['correct']
        finally:
            avatar.memory.close()

        for case in FACT_CASES:
            avatar = Avatar(memory=MemoryStore(':memory:'), llm=llm, session_id=case['id'])
            try:
                for context in case.get('context', []):
                    avatar.memory.add_short_term('user', context)
                turn(avatar, case['user'], 'labeled-extraction/' + case['id'])
                observed = report['turns'][-1]
                raw, admitted = observed['raw_model_facts'], observed['admitted_facts']
                report['fact_cases'].append(dict(id=case['id'], user=case['user'],
                    context=case.get('context', []), label='positive' if case['expected'] else 'abstention',
                    expected_facts=case['expected'], raw_model_facts=raw, admitted_facts=admitted,
                    raw_model_score=score_facts(case['expected'], raw),
                    admitted_score=score_facts(case['expected'], admitted)))
            finally:
                avatar.memory.close()

        if embedder:
            store = MemoryStore(':memory:', embedder=embedder)
            try:
                cat = store.remember('我养了一只猫，名字叫团团')
                store.remember('我喜欢打篮球')
                store.remember('我每天坐地铁去上班')
                rows = store.recall('你还记得我的宠物吗？')
                report['semantic'] = [dict(content=r['content'], similarity=r.get('similarity')) for r in rows]
                report['checks']['semantic_paraphrase'] = bool(rows and rows[0]['id'] == cat)
                store.forget(cat)
                report['checks']['deleted_not_semantically_recalled'] = not any(r['id'] == cat for r in store.recall('宠物'))
            finally:
                store.close()

    report['summary'] = dict(passed=sum(report['checks'].values()), total=len(report['checks']),
        failed=[key for key, value in report['checks'].items() if not value],
        failed_model_calls=sum('error' in call for call in llm.calls),
        note='Small seeded system regression; not an independent model benchmark. No TTS or production DB.')
    report['summary'].update(summarize_latencies(report['turns']))
    cases = report['fact_cases']
    report['summary']['fact_extraction'] = dict(cases=len(cases),
        positive_cases=sum(bool(case['expected_facts']) for case in cases),
        abstention_cases=sum(not case['expected_facts'] for case in cases),
        raw_model=summarize_facts(cases, 'raw_model'), admitted=summarize_facts(cases, 'admitted'))
    answers = report['answer_cases']
    positives = [row for row in answers if not row['expected_abstention']]
    report['summary']['answers'] = dict(positive_cases=len(positives),
        accuracy=sum(row['correct'] for row in positives) / len(positives) if positives else None,
        completeness=sum(row['matched_items'] for row in positives) / sum(row['expected_items'] for row in positives) if positives else None,
        expected_abstention_cases=sum(row['expected_abstention'] for row in answers),
        expected_abstention_successes=sum(row['correct'] for row in answers if row['expected_abstention']),
        false_name_answers=sum(bool(row['stale_names']) for row in answers if row['expected_abstention']),
        note='Literal token groups and explicit uncertainty checks; inspect raw replies for meaning. Not a general model accuracy estimate.')
    report['summary']['system_checks'] = dict(passed=report['summary']['passed'], total=report['summary']['total'])
    save()
    markdown = [f'# Seeded backend evaluation: {model}', '',
        f"Backend checks: {report['summary']['passed']}/{report['summary']['total']}", '',
        'Fact extraction accuracy is exact labeled-case agreement; completeness is expected facts recovered.',
        'Raw model proposals and admitted facts are scored separately. Missing/invalid model JSON is not successful abstention.', '',
        '```json', json.dumps(report['summary'], ensure_ascii=False, indent=2), '```', '',
        'Answer metrics use literal token/uncertainty labels. These small scripted cases do not estimate generic model accuracy.',
        f'Raw replies, calls, labels, admitted facts and failures: {output.name}']
    output.with_suffix('.md').write_text('\n'.join(markdown) + '\n', encoding='utf-8')
    print(json.dumps(report['summary']), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='qwen2.5:7b')
    parser.add_argument('--embedding-model', default='')
    parser.add_argument('--base-url', default='http://localhost:11434')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.model, args.embedding_model, args.base_url, args.output, args.timeout)
