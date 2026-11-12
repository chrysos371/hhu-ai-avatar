"""Scripted model-interface controls of actual source/SQLite/read-repair branches.

No HTTP, SDK generation, llama model or GPU is used by this controller.
"""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from sample_reads import sample_repetition, sample_case

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'evals/interaction/cycle-41/source-checked-read-repair-protocol.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Scripted:
    def __init__(self, protocol, mode):
        self.protocol, self.mode = protocol, mode
        self.records = []
        self.context = {}
        self.callback = None
        self.by_text = {c['text']: c for c in protocol['development_cases']}

    def chat_tools(self, messages, *, tools, temperature, max_tokens):
        row = {'context': dict(self.context), 'messages': copy.deepcopy(messages),
               'tools': copy.deepcopy(tools), 'temperature': temperature,
               'max_tokens': max_tokens, 'result': None, 'error': None}
        self.records.append(row)
        assert tools == self.protocol['tools'] and temperature == 0 and max_tokens == 256
        repair = any(m['role'] == 'tool' for m in messages)
        question = next(m['content'] for m in messages if m['role'] == 'user')
        case = self.by_text[question]
        if repair:
            error = json.loads(next(m['content'] for m in reversed(messages) if m['role'] == 'tool'))
            assert set(error) == {'ok', 'error'} and error['ok'] is False
            assert error['error']['code'] == 'unbound_reminder_id'
            assert all(word not in canonical(error) for word in ['policy-exit', 'read_reminder_delivery_policy', '12345'])
            if self.mode == 'error':
                row['error'] = 'RuntimeError: scripted selection failure'
                raise RuntimeError('scripted selection failure')
            if self.mode == 'plain':
                result = {'role': 'assistant', 'content': '我保证一定提醒你。'}
            elif self.mode == 'repeat':
                result = self.call('read_reminder_state', {'reminder_id': 12345})
            else:
                result = self.call('read_reminder_delivery_policy', {})
        elif self.mode == 'malformed':
            result = self.call('read_reminder_state', {'reminder_id': 1})
            result['tool_calls'][0]['id'] = ''
        elif case['id'] == 'policy-exit':
            result = self.call('read_reminder_state', {'reminder_id': 12345})
        elif case['tool']:
            result = self.call(case['tool'], case['args'])
        else:
            result = {'role': 'assistant', 'content': '受控普通文字，未读取提醒。'}
        if self.callback:
            callback, self.callback = self.callback, None
            callback()
        row['result'] = copy.deepcopy(result)
        return result

    def call(self, name, args):
        return {'role': 'assistant', 'tool_calls': [{'id': f'call_scripted_{len(self.records)}',
            'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def verify_sql(case_root, row):
    counts = {}
    for mode, branch in row['branches'].items():
        dump = case_root/(mode+'.sql')
        assert digest(dump) == branch['SQL_dump_sha256']
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(dump.read_text())
            for table, values in branch['business_after'].items():
                assert [dict(r) for r in conn.execute('SELECT * FROM '+table+' ORDER BY id')] == values
            source = conn.execute('SELECT * FROM memory_messages WHERE id=?', (branch['source_message_id'],)).fetchone()
            assert source and source['role'] == 'user' and source['session_id'] == branch['session_id']
            if not branch['source_cancelled']:
                revision = conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()[0]
                assert revision == branch['source_revision']
                assert conn.execute('SELECT cursor FROM memory_web_speaker_state WHERE id=1').fetchone()[0] == source['id']
            assert branch['business_unchanged']
            counts[mode] = branch['business_status_SELECTs']
        finally:
            conn.close()
    return counts


def run(mode):
    protocol = json.loads(PROTOCOL.read_text())
    out = BASE/'审计/工作目录/003-受控读取配对'/mode
    out.mkdir(parents=True, exist_ok=False)
    source_files = [ROOT/'src/avatar/lab/trusted_local_read.py', Path(__file__),
                    BASE/'审计/sample_reads.py', PROTOCOL]
    before = {str(p.relative_to(ROOT)): digest(p) for p in source_files}
    model = Scripted(protocol, mode)
    context = lambda data: setattr(model, 'context', dict(data))
    if mode in ('repair', 'repeat', 'plain', 'error'):
        batch = sample_repetition(model, protocol, protocol['development_cases'], 1, out/'cases', on_context=context)
        rows = batch['cases']
        assert len(rows) == 8 and len(model.records) == 9
        gate_score = sum(r['branches']['gate_only']['final_exact_expected_route'] for r in rows)
        repair_score = sum(r['branches']['single_repair']['final_exact_expected_route'] for r in rows)
        assert gate_score == 7 and repair_score == (8 if mode == 'repair' else 7)
        problem = rows[0]
        assert problem['branches']['gate_only']['first_read']['result']['error']['code'] == 'unbound_reminder_id'
        if mode == 'plain':
            assert problem['branches']['single_repair']['retry_proposal']['content'] == '我保证一定提醒你。'
            assert '保证' not in problem['branches']['single_repair']['reply']
        if mode == 'error':
            assert problem['branches']['single_repair']['retry_error'].startswith('RuntimeError:')
        for row in rows:
            for branch in row['branches'].values():
                assert branch['no_post_source_writes']
    else:
        case = copy.deepcopy(protocol['development_cases'][2])
        if mode == 'gold-poison':
            case.update(tool='read_reminder_delivery_policy', args={})
        def privacy(branches):
            def forget():
                for branch in branches.values():
                    memory = branch['memory']
                    fact = memory.remember('受控隐私版本事实')
                    memory.forget(fact)
            if mode == 'source-after':
                model.callback = forget
            elif mode == 'source-before':
                forget()
        row = sample_case(model, protocol, case, 1, out/'case', on_context=context, before_initial=privacy)
        rows = [row];gate_score = repair_score = None
        if mode.startswith('source-'):
            assert row['case_source_denied']
            assert row['initial_model_calls'] == (1 if mode == 'source-after' else 0)
            assert all(b['reply'] is None and b['source_cancelled'] and not b['business_status_SELECTs']
                       for b in row['branches'].values())
        elif mode == 'gold-poison':
            assert len(model.records) == 1
            assert all(b['final_tool'] == 'read_reminder_state' and b['final_arguments'] == {'reminder_id': 1}
                       and not b['final_exact_expected_route'] for b in row['branches'].values())
        else:
            assert mode == 'malformed' and len(model.records) == 1
            assert all(b['reply_origin'] == 'malformed_proposal' and not b['business_status_SELECTs']
                       for b in row['branches'].values())
    reconstructions = []
    for row in rows:
        directory = out/'cases'/row['case'] if len(rows) == 8 else out/'case'
        reconstructions.append({'case': row['case'], 'status_SELECTs': verify_sql(directory, row)})
    assert before == {str(p.relative_to(ROOT)): digest(p) for p in source_files}
    result = {'verified': True, 'scope': 'scripted model-interface controls with actual in-memory SQLite and source/renderer; no HTTP/SDK native generation',
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_sha256': before, 'native_or_GPU_calls': 0, 'scripted_model_attempts': len(model.records),
        'scripted_model_exceptions': sum(r['error'] is not None for r in model.records),
        'lab_branch_outcomes': len(rows)*2, 'gold_only_used_for_scoring': True,
        'SQL_dumps_reconstructed': len(rows)*2, 'SQL_checks': reconstructions,
        'gate_only_expected': gate_score, 'single_repair_expected': repair_score, 'model_records': model.records}
    (out/'evaluation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(mode+': controlled proof passed;scripted attempts='+str(len(model.records))+
          ';lab outcomes='+str(len(rows)*2)+';0native/GPU')


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('repair', 'repeat', 'plain', 'error', 'source-before', 'source-after', 'gold-poison', 'malformed'):
        raise ValueError('Select one fresh controlled scenario')
    run(sys.argv[1])
