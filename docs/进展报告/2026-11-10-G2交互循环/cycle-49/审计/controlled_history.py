"""CPU-only real SDK reference/error trials; fixed clock for gold-input control."""
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
from unittest.mock import patch

from sample_history import sample_trial, projection
from avatar.brain.reminder_queries import parse_query

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
WORK = BASE/'审计/工作目录/003-受控实模管线/v1'


class ScriptedEngine:
    def __init__(self,reply,kind='correct'):
        self.available = kind != 'unavailable'; self.reply,self.kind = reply,kind

    def chat_analysis(self,messages,**options):
        if self.kind == 'cognition_error': raise RuntimeError('controlled cognitive transport error')
        return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'

    def chat(self,messages,**options):
        if self.kind == 'generation_error': raise RuntimeError('controlled generation transport error')
        return '```json\n'+self.reply+'\n```' if self.kind == 'malformed_generation' else self.reply


def main():
    assert not WORK.exists(); WORK.mkdir(parents=True)
    cases = json.loads((ROOT/'evals/interaction/cycle-49/minimal-history-cases.json').read_text())['cases']
    assert all(parse_query(c['followup_text']) is None for c in cases)
    rows = []; contexts = []
    # Explicit CPU fixture only. Native runs use the actual wall clock. A fixed
    # clock makes the two independently executed gold controls' full model token
    # inputs identical, including observed_at inside every history envelope.
    with patch('time.time',return_value=1800000000.0):
        for case in cases:
            for arm in ('production_snapshot','C48_typed_control','minimal_observation'):
                folder = case['id']+'-'+arm
                receipt = sample_trial(ScriptedEngine(json.dumps(case['expected'],ensure_ascii=False)),
                    case,arm,1,WORK/folder,on_context=contexts.append)
                assert receipt['final_reply_score']['task_correct'] and receipt['model_modes_valid']
                assert len(receipt['actual_model_interface_calls']) == 2
                rows.append({'folder':folder,'kind':'scripted_expected_fixture','receipt':receipt})
        case = cases[0]
        for kind in ('malformed_generation','cognition_error','generation_error','unavailable'):
            receipt = sample_trial(ScriptedEngine(json.dumps(case['expected']),kind),case,
                'minimal_observation',1,WORK/kind,on_context=contexts.append)
            if kind == 'malformed_generation':
                assert not receipt['final_reply_score']['format_valid'] and receipt['model_modes_valid']
            else: assert not receipt['model_modes_valid']
            rows.append({'folder':kind,'kind':kind,'receipt':receipt})
        poisoned = copy.deepcopy(case); poisoned['expected']['observed_record_state'] = 'cancelled'
        receipt = sample_trial(ScriptedEngine(json.dumps(case['expected'],ensure_ascii=False)),poisoned,
            'production_snapshot',1,WORK/'post-execution-gold-poison',on_context=contexts.append)
        original = rows[0]['receipt']
        assert [c['messages'] for c in receipt['actual_model_interface_calls']] == [c['messages'] for c in original['actual_model_interface_calls']]
        assert [c['options'] for c in receipt['actual_model_interface_calls']] == [c['options'] for c in original['actual_model_interface_calls']]
        assert not receipt['final_reply_score']['task_correct'] and original['final_reply_score']['task_correct']
        rows.append({'folder':'post-execution-gold-poison','kind':'gold_poison_no_input_change','receipt':receipt})
    dumps = 0; queries = 0
    for row in rows:
        data = row['receipt']; queries += data['actual_query_turns']
        assert data['business_unchanged_by_query_and_ordinary'] and data['no_new_user_facts']
        assert data['query_model_calls'] == 0
        for observation in data['query_observations']:
            assert observation['result']['reminder_query']['observed_at'] == 1800000000.0
            source = observation['result']['reminder_query']['source_message_id']
            assert source == 2*observation['number']-1
            frame = json.loads(observation['model_context'][-1]['content'].split('\n',1)[1])
            assert ('typed_historical_evidence' in frame) is (data['arm']=='C48_typed_control')
            assert ('minimal_historical_observation' in frame) is (data['arm']=='minimal_observation')
        for name in data['dump_files']:
            with sqlite3.connect(':memory:') as conn:
                conn.row_factory = sqlite3.Row; conn.executescript((WORK/row['folder']/name).read_text())
                index = next((o for o in data['query_observations'] if o['dump_file']==name),None)
                expected = index['business_after'] if index else data['business_after_ordinary']
                assert projection(type('MemoryView',(),{'_conn':conn})()) == expected
                count = 2*index['number'] if index else 2*(data['actual_query_turns']+1)
                messages = [dict(r) for r in conn.execute('SELECT id,role,content FROM memory_messages ORDER BY id')]
                assert len(messages) == count
                assert messages[-1]['content'] == (index['result']['reply'] if index else data['ordinary_result']['reply'])
                assert conn.execute('SELECT count(*) FROM memory_fragments').fetchone()[0] == 0
            dumps += 1
    result = {'completed':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'scope':'CPU scripted expected references and errors, never native model scores',
        'CPU_fixed_time_fixture':1800000000.0,'native_uses_actual_wallclock':True,
        'actual_SDK_trials':len(rows),'actual_query_turns':queries,'actual_ordinary_turns':len(rows),
        'actual_SDK_turns':queries+len(rows),'scripted_model_interface_attempts':sum(len(r['receipt']['actual_model_interface_calls']) for r in rows),
        'native_calls':0,'SQL_dumps_reconstructed':dumps,'gold_poison_model_inputs_unchanged':True,
        'groups':[{'folder':r['folder'],'kind':r['kind'],'query_turns':r['receipt']['actual_query_turns'],
            'final_score':r['receipt']['final_reply_score'],'model_modes_valid':r['receipt']['model_modes_valid']} for r in rows]}
    assert len(rows)==59 and queries==77 and dumps==136 and result['scripted_model_interface_attempts']==116
    (WORK/'controlled-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C49 CPU:59 trials;77query+59ordinary=136 SDK turns/SQL;116 scripted attempts;gold inputs unchanged;0 native')


if __name__ == '__main__': main()
