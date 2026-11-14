"""Pre-native controlled SDK trials, failure paths and post-execution gold poison."""
import copy
import json
from pathlib import Path
import sqlite3
import subprocess

from sample_history import sample_trial, projection
from avatar.brain.reminder_queries import parse_query

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
WORK = BASE/'审计/工作目录/003-受控实模管线/v2'


class ScriptedEngine:
    def __init__(self,reply,kind='correct'):
        self.available = kind != 'unavailable'
        self.reply,self.kind = reply,kind

    def chat_analysis(self,messages,**options):
        if self.kind == 'cognition_error': raise RuntimeError('controlled cognitive transport error')
        return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'

    def chat(self,messages,**options):
        if self.kind == 'generation_error': raise RuntimeError('controlled generation transport error')
        return '```json\n'+self.reply+'\n```' if self.kind == 'malformed_generation' else self.reply


def main():
    assert not WORK.exists(); WORK.mkdir(parents=True)
    cases = json.loads((ROOT/'evals/interaction/cycle-47/native-history-cases.json').read_text())['cases']
    assert all(parse_query(case['followup_text']) is None for case in cases)
    rows = []; contexts = []
    for case in cases:
        for arm in ('authorized_raw_history','verified_snapshot_history'):
            # This body is deliberately scripted from registered labels. It is
            # a scoring/transport fixture, never counted as native quality.
            engine = ScriptedEngine(json.dumps(case['expected'],ensure_ascii=False))
            receipt = sample_trial(engine,case,arm,1,WORK/(case['id']+'-'+arm),on_context=contexts.append)
            assert receipt['final_reply_score']['task_correct'] and receipt['model_modes_valid']
            assert len(receipt['actual_model_interface_calls']) == 2
            rows.append({'folder':case['id']+'-'+arm,'kind':'scripted_expected_fixture','receipt':receipt})
    case = cases[0]
    for kind in ('malformed_generation','cognition_error','generation_error','unavailable'):
        engine = ScriptedEngine(json.dumps(case['expected'],ensure_ascii=False),kind)
        receipt = sample_trial(engine,case,'verified_snapshot_history',1,WORK/kind,on_context=contexts.append)
        if kind == 'malformed_generation':
            assert not receipt['final_reply_score']['format_valid'] and receipt['model_modes_valid']
        else: assert not receipt['model_modes_valid']
        rows.append({'folder':kind,'kind':kind,'receipt':receipt})
    poisoned = copy.deepcopy(case); poisoned['expected']['observed_record_state'] = 'cancelled'
    receipt = sample_trial(ScriptedEngine(json.dumps(case['expected'])),poisoned,
        'authorized_raw_history',1,WORK/'post-execution-gold-poison',on_context=contexts.append)
    original = next(row['receipt'] for row in rows if row['folder'] == case['id']+'-authorized_raw_history')
    assert receipt['query_text'] == original['query_text'] and receipt['followup_text'] == original['followup_text']
    assert [c['messages'] for c in receipt['actual_model_interface_calls']] == [c['messages'] for c in original['actual_model_interface_calls']]
    assert [c['options'] for c in receipt['actual_model_interface_calls']] == [c['options'] for c in original['actual_model_interface_calls']]
    assert not receipt['final_reply_score']['task_correct'] and original['final_reply_score']['task_correct']
    rows.append({'folder':'post-execution-gold-poison','kind':'gold_poison_no_input_change','receipt':receipt})
    reconstructed = 0
    for row in rows:
        data = row['receipt']; assert data['business_unchanged_by_query_and_ordinary'] and data['no_new_user_facts']
        for name,expected in [('after-query.sql',data['business_after_query']),('after-ordinary.sql',data['business_after_ordinary'])]:
            with sqlite3.connect(':memory:') as conn:
                conn.row_factory = sqlite3.Row; conn.executescript((WORK/row['folder']/name).read_text())
                assert projection(type('MemoryView',(),{'_conn':conn})()) == expected
                expected_messages = 2 if name == 'after-query.sql' else 4
                assert conn.execute('SELECT count(*) FROM memory_messages').fetchone()[0] == expected_messages
                assert conn.execute('SELECT count(*) FROM memory_fragments').fetchone()[0] == 0
            reconstructed += 1
    result = {'completed':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'scope':'scripted controlled reference outputs/failures; not native model task scores',
        'actual_SDK_trials':len(rows),'actual_SDK_turns':len(rows)*2,
        'scripted_model_interface_attempts':sum(len(r['receipt']['actual_model_interface_calls']) for r in rows),
        'native_calls':0,'SQL_dumps_reconstructed':reconstructed,'gold_poison_model_inputs_unchanged':True,
        'groups':[{'folder':r['folder'],'kind':r['kind'],'model_calls':len(r['receipt']['actual_model_interface_calls']),
            'final_score':r['receipt']['final_reply_score'],'model_modes_valid':r['receipt']['model_modes_valid']} for r in rows]}
    assert len(rows) == 21 and reconstructed == 42 and result['scripted_model_interface_attempts'] == 40
    (WORK/'controlled-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C47 controls:21 actual SDK trials/42 turns;40 scripted interface attempts;42 SQL;gold poison input unchanged;0 native')


if __name__ == '__main__':
    main()
