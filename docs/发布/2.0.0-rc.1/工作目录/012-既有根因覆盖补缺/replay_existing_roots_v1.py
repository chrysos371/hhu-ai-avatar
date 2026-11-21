"""Known failure-text injection on current source, never native model evidence."""
from hashlib import sha256
import json
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE = Path(__file__).resolve().parent
RAW = Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/existing-root-replay-v1')
sys.path.insert(0, str(ROOT/'tests'))
from avatar.main import Avatar
from avatar.brain.memory import MemoryStore
from test_capability_prompt_lab import Recorder


class Replay(Recorder):
    def chat(self, messages, **kwargs):
        self.native.append(dict(messages=messages, response_format=kwargs.get('response_format')))
        return self.reply

    def stream_chat(self, messages, *, on_delta=None, cancel=None, **kwargs):
        if cancel:
            cancel.checkpoint()
        text = self.chat(messages, **kwargs)
        if on_delta:
            on_delta(text)
        return text


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    common = runpy.run_path(str(HERE.parent/'006-写作交付与严格格式/run_current_python.py'))
    before = common['snapshot']()
    before[str(Path(__file__).resolve().relative_to(ROOT))] = digest(Path(__file__))
    ref = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert subprocess.check_output(['git', 'show', ref+':'+str(Path(__file__).resolve().relative_to(ROOT))], cwd=ROOT) == Path(__file__).read_bytes()
    RAW.mkdir(parents=True, exist_ok=False)
    old = json.loads((ROOT/'evals/interaction/cycle-02/subject-ownership-dev16.json').read_text())
    scenarios = old['scenarios'] if 'scenarios' in old else old['cases']
    cases = [dict(id=c['id'], turns=c['turns'], injected=bad, issue='C02-016') for ident, bad in [
        ('negative_a', '哦，你喜欢爬山啊！那一起爬山吧，我陪你去。'),
        ('update_a', '我最近也想试试看，不过还没机会呢。'),
        ('quoted_b', '哦，那我们一起去打网球吧。')]
        for c in scenarios if c['id'] == ident]
    source = json.loads((ROOT/'evals/interaction/cycle-37/current-default-capability-protocol.json').read_text())
    scenarios = source['cases'] if 'cases' in source else source['scenarios']
    c = next(c for c in scenarios if c['id'] == 'c37_unaccepted_obligation')
    cases.append(dict(id=c['id'], turns=c['turns'], injected='我还没确定好时间，等我安排好再告诉你。', issue='C37-007'))
    results = []
    for case in cases:
        memory = MemoryStore(str(RAW/(case['id']+'.db')))
        engine = Replay(case['injected'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True, role_state_enabled=True)
        rows = []
        try:
            for index, text in enumerate(case['turns'], 1):
                engine.reply = case['injected'] if case['issue'] == 'C02-016' or index == len(case['turns']) else '我明白你的说法。'
                pieces = []
                result = bot.respond(text, on_delta=pieces.append)
                rows.append(dict(turn=index, user=text, result=result, visible=pieces,
                                 sql=[dict(row) for row in memory._conn.execute('SELECT * FROM memory_messages')]))
            results.append(dict(case=case, turns=rows, analysis=engine.analysis,
                                controlled_generation_requests=engine.native))
        finally:
            memory.close()
    stable = all(digest(ROOT/name) == value for name, value in before.items())
    report = dict(source_ref=ref, source_sha256=before, source_unchanged=stable, actual_native_calls=0,
                  scope='known bad model-text injection and original user sequences, not native rate/quality or blind evidence',
                  cases=results, raw=str(RAW))
    with (RAW/'result.json').open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    assert stable
    for row in results:
        print(row['case']['id'], [(r['result']['generation_mode'], r['result']['reply']) for r in row['turns']])


if __name__ == '__main__':
    main()
