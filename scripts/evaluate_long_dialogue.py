"""40-turn scripted comparison. Uses temporary DBs; never the user's live memory."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import re
import statistics
import sys
import tempfile
import time


SCENARIO = [
    dict(id='name', text='我叫阿岚。'),
    dict(id='positive-preference', text='我喜欢喝咖啡。'),
    dict(id='negative-preference', text='我讨厌香菜。'),
    dict(id='project-anchor', text='这轮讨论的演示方案代号定为青岚，主题是河流水质预测。'),
    dict(id='constraints-anchor', text='这次方案的约束是预算上限500元，展示时长8分钟。'),
    dict(id='outline-anchor', text='这次汇报的顺序定为研究背景、方法、结果，先不要展开。'),
    dict(id='hypothesis', text='假如我叫小红又喜欢香菜，你会怎么介绍这个假设角色？'),
    dict(id='other-person', text='我朋友小王喜欢喝茶，这说的是他。'),
    dict(id='preference-reversal', text='我以前喜欢喝咖啡，现在不喜欢喝咖啡了。'),
    dict(id='rename', text='以后叫我小岚。'),
    dict(id='listen', text='考试没过，我很难过，但暂时不想听建议。', strategy='listen'),
    dict(id='advice', text='别安慰我了，帮我分析一下怎么复习。', strategy='advise'),
    dict(id='good-news', text='刚查到成绩改正了，我及格啦！', strategy='celebrate'),
    dict(id='anger', text='我特别生气，简直要崩溃！！', strategy='empathize'),
    dict(id='first-goodbye', text='晚安', strategy='close'),
    dict(id='return', text='我回来了，接着聊，先随便说两句。'),
    dict(id='filler-01', text='给我解释一下什么是云。'),
    dict(id='filler-02', text='一句话介绍彩虹为什么有颜色。'),
    dict(id='filler-03', text='什么是光合作用？简单说就好。'),
    dict(id='filler-04', text='太阳为什么看起来会升起？'),
    dict(id='filler-05', text='给我讲一个简短冷笑话。'),
    dict(id='filler-06', text='列举两种常见的树。'),
    dict(id='filler-07', text='一句话解释水蒸气和烟的区别。'),
    dict(id='filler-08', text='简单介绍一下月亮的阴晴圆缺。'),
    dict(id='filler-09', text='用一句话描述清晨的校园。'),
    dict(id='context-probe', text='回到前面那次方案：代号是什么，预算和展示时长各是多少？',
         expected=[['青岚'], ['500', '五百'], ['8分钟', '八分钟']]),
    dict(id='current-facts', text='我现在该怎么称呼？还喜欢喝咖啡吗？',
         expected=[['小岚'], ['咖啡'], ['不喜欢', '不再喜欢', '不爱']], forbidden=['阿岚', '小红']),
    dict(id='restart', action='restart', text='继续刚才的方案讨论。请复述我们定下的汇报顺序。',
         expected=[['研究背景'], ['方法'], ['结果']]),
    dict(id='correction', action='correct', text='确认一下，你现在应该怎么称呼我？',
         expected=[['小舟']], forbidden=['阿岚', '小岚', '小红']),
    dict(id='post-correction', text='先不展开方案，用一句话说说准备汇报要注意什么。'),
    dict(id='filler-10', text='简单解释一下降水和降雨有什么区别。'),
    dict(id='filler-11', text='一句话说明什么是河流流域。'),
    dict(id='forget', action='forget', text='你还记得我叫什么吗？不记得就直说。',
         expected=[], forbidden=['阿岚', '小岚', '小舟', '小红'], abstain=True),
    dict(id='post-forget-hypothesis', text='假如我叫小红，这只是假设，别当成我的名字。'),
    dict(id='post-forget-probe', text='现在还能确认我的真实名字吗？', expected=[],
         forbidden=['阿岚', '小岚', '小舟', '小红'], abstain=True),
    dict(id='closing-line', text='帮我给汇报写一句不夸张的结束语。'),
    dict(id='reminder', text='提醒我2099年12月1日下午3点答辩。'),
    dict(id='cancel-reminder', action='cancel', text='刚才的提醒已经通过管理命令取消了。'),
    dict(id='final-context', text='最后复述一下前面方案的主题、预算和时长，不要猜测我的名字。',
         expected=[['水质预测'], ['500', '五百'], ['8分钟', '八分钟']]),
    dict(id='final-goodbye', text='今天不聊了，拜拜', strategy='close'),
]


def score(reply, expected, forbidden=(), *, abstain=False):
    hits = [any(word in reply for word in alternatives) for alternatives in expected]
    stale = [word for word in forbidden if word in reply]
    uncertainty = bool(re.search(r'不记得|无法确认|不确定|不清楚|不知道|尚未记录', reply))
    false_history = bool(re.search(r'(?:从未|没(?:有)?|还没|未曾).{0,8}(?:告诉|提供|说过|提过)', reply))
    return dict(passed=not stale and (uncertainty and not false_history if abstain else all(hits)),
                hits=hits, stale=stale, uncertainty=uncertainty, false_history=false_history)


def evaluate(model, args, Avatar, MemoryStore, LocalChat, Provider):
    class TracedChat(LocalChat):
        def chat(self, messages, *positional, **kwargs):
            before = len(self.calls)
            try:
                return super().chat(messages, *positional, **kwargs)
            finally:
                if len(self.calls) > before:
                    self.calls[-1]['prompt_messages'] = messages
    llm = TracedChat(model, args.base_url, args.timeout)
    embedder = Provider(args.base_url, args.embedding_model, args.timeout) if args.embedding_model else None
    report = dict(model=model, summary_mode=args.summary_mode, source_root=str(args.source_root),
                  main_sha256=hashlib.sha256((args.source_root / 'avatar/main.py').read_bytes()).hexdigest(),
                  seed=42, turns=[], actions=[], backend_checks={}, answer_checks=[], completed=False)
    report['source_sha256'] = args.source_sha256
    report['scenario_sha256'] = hashlib.sha256(json.dumps(SCENARIO, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    out = args.output_dir / (re.sub(r'[^a-zA-Z0-9._-]', '_', model) + '-' + args.summary_mode + '.json')
    def save():
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    started = time.perf_counter()
    llm.chat([dict(role='user', content='只回答一个字：好')], temperature=0, max_tokens=8)
    report['warmup_seconds'] = round(time.perf_counter() - started, 3)
    llm.calls.clear()
    with tempfile.TemporaryDirectory(prefix='long-eval-', dir=args.temp_root) as temp:
        path = str(Path(temp) / 'memory.db')
        def make():
            kwargs = dict(memory=MemoryStore(path, embedder=embedder), llm=llm, session_id='continuous')
            if 'summary_enabled' in inspect.signature(Avatar).parameters:
                kwargs['summary_enabled'] = args.summary_mode == 'on'
            elif args.summary_mode == 'on':
                raise ValueError('source does not implement summaries')
            return Avatar(**kwargs)
        avatar = make()
        try:
            for number, case in enumerate(SCENARIO, 1):
                action = case.get('action')
                if action == 'restart':
                    avatar.memory.close()
                    avatar = make()
                    report['actions'].append(dict(turn=number, action=action))
                if action in ('correct', 'forget'):
                    row = next((r for r in avatar.list_memories() if r.get('profile_key') == '名字'), None)
                    report['backend_checks'][action + '_prerequisite'] = row is not None
                    if row:
                        if action == 'correct':
                            avatar.correct_memory(row['id'], '小舟')
                            report['backend_checks']['correct_current_name'] = avatar.memory.get_user_profile().get('名字') == '小舟'
                        else:
                            avatar.forget_memory(row['id'])
                            report['backend_checks']['forgotten_chain_absent'] = not any(
                                r.get('profile_key') == '名字' for r in avatar.list_memories(include_history=True))
                            report['backend_checks']['forgotten_short_term_empty'] = avatar.memory.get_short_term() == []
                    report['actions'].append(dict(turn=number, action=action, found=bool(row)))
                if action == 'cancel':
                    rows = avatar.reminders.list()
                    for row in rows:
                        avatar.reminders.set_status(row['id'], 'cancelled')
                    report['backend_checks']['reminder_created_and_cancelled'] = bool(rows) and all(
                        r['status'] == 'cancelled' for r in avatar.reminders.list())
                before, started = len(llm.calls), time.perf_counter()
                result = avatar.respond(case['text'])
                elapsed = round(time.perf_counter() - started, 3)
                observed = dict(number=number, id=case['id'], user=case['text'], result=result,
                                seconds=elapsed, calls=llm.calls[before:], profile=avatar.memory.get_user_profile())
                if 'expected' in case:
                    rating = score(result['reply'], case['expected'], case.get('forbidden', []), abstain=case.get('abstain', False))
                    report['answer_checks'].append(dict(id=case['id'], **rating))
                if 'strategy' in case:
                    report['backend_checks']['strategy/' + case['id']] = result['strategy'] == case['strategy']
                if case['id'] == 'current-facts':
                    profile = avatar.memory.get_user_profile()
                    report['backend_checks']['current_name'] = profile.get('名字') == '小岚'
                    report['backend_checks']['preference_reversal'] = '不喜欢' in profile.get('偏好', '') and '咖啡' in profile.get('偏好', '')
                    report['backend_checks']['hypothesis_not_stored'] = '小红' not in str(avatar.list_memories(include_history=True))
                    report['backend_checks']['other_person_not_profile'] = '茶' not in profile.get('偏好', '')
                report['turns'].append(observed)
                save()
                print(json.dumps(dict(model=model, summary=args.summary_mode, turn=number, scenario=case['id'], seconds=elapsed)), flush=True)
        finally:
            avatar.memory.close()
    report['completed'] = True
    report['statistics'] = dict(turns=len(report['turns']),
        median_seconds=statistics.median(r['seconds'] for r in report['turns']),
        backend_passed=sum(report['backend_checks'].values()), backend_total=len(report['backend_checks']),
        answers_passed=sum(r['passed'] for r in report['answer_checks']), answers_total=len(report['answer_checks']),
        model_call_errors=sum('error' in c for r in report['turns'] for c in r['calls']),
        note='固定脚本与关键词评分；不是开放域独立基准。40用户回合不含管理操作；每轮包含认知分析与生成。')
    save()
    print(json.dumps(dict(model=model, statistics=report['statistics']), ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+', required=True)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1] / 'src')
    parser.add_argument('--summary-mode', choices=['on', 'off'], required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--temp-root', type=Path, required=True)
    parser.add_argument('--base-url', default='http://localhost:11434')
    parser.add_argument('--embedding-model', default='bge-m3')
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    args.source_root = args.source_root.resolve()
    args.source_sha256 = {name: hashlib.sha256((args.source_root / name).read_bytes()).hexdigest()
                          if (args.source_root / name).exists() else None
                          for name in ('avatar/main.py', 'avatar/brain/memory.py', 'avatar/brain/facts.py', 'avatar/brain/summaries.py')}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.temp_root.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.source_root))
    from avatar.main import Avatar
    from avatar.brain.memory import MemoryStore
    from avatar.brain.embeddings import OllamaEmbeddingProvider
    from evaluate_backend import LocalChat
    for model in args.models:
        evaluate(model, args, Avatar, MemoryStore, LocalChat, OllamaEmbeddingProvider)


if __name__ == '__main__':
    main()
