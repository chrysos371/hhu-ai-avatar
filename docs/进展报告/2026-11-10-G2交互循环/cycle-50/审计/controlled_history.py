"""Actual SDK capture/source controls with scripted replies, zero native inference."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

from sample_history import sample_trial
from verify_observations import inspect_observations
from text_shape import text_shape

BASE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
WORK = BASE/'审计/工作目录/003-受控实模管线/v1'


class ScriptedEngine:
    def __init__(self, kind='normal'):
        self.kind = kind
        self.available = kind != 'unavailable'

    def chat_analysis(self, messages, **options):
        if self.kind == 'cognition_error': raise RuntimeError('controlled cognition failure')
        return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'

    def chat(self, messages, **options):
        if self.kind == 'generation_error': raise RuntimeError('controlled generation failure')
        return '' if self.kind == 'empty_generation' else '这是一条受控采集参考回复，不作为模型语义成绩。'


def main():
    assert not WORK.exists(); WORK.mkdir(parents=True)
    cases = json.loads((ROOT/'evals/interaction/cycle-50/natural-history-cases.json').read_text())['cases']
    arms = ['production_snapshot','C48_typed_control','minimal_observation']
    rows = []
    with patch('time.time', return_value=1800000000.0):
        for case in cases:
            for arm in arms:
                folder = case['id']+'-'+arm
                receipt = sample_trial(ScriptedEngine(),case,arm,1,WORK/folder,on_context=lambda _:None)
                rows.append((folder,'normal',case,receipt))
        case = cases[0]
        for kind in ('cognition_error','generation_error','unavailable','empty_generation'):
            receipt = sample_trial(ScriptedEngine(kind),case,arms[0],1,WORK/kind,on_context=lambda _:None)
            rows.append((kind,kind,case,receipt))
        poisoned = copy.deepcopy(case)
        poisoned['oracle_observation']['observed_record_state'] = 'cancelled'
        poisoned['review_axes'] = ['POISON_ONLY_NOT_A_MODEL_INPUT']
        receipt = sample_trial(ScriptedEngine(),poisoned,arms[0],1,WORK/'oracle-poison',on_context=lambda _:None)
        original = rows[0][3]
        assert [c['messages'] for c in receipt['actual_model_interface_calls']] == [c['messages'] for c in original['actual_model_interface_calls']]
        assert [c['options'] for c in receipt['actual_model_interface_calls']] == [c['options'] for c in original['actual_model_interface_calls']]
        assert receipt['oracle_observation_registered_after_execution'] != original['oracle_observation_registered_after_execution']
        rows.append(('oracle-poison','oracle_poison',poisoned,receipt))
    dumps = queries = attempts = 0
    for folder,kind,case,receipt in rows:
        dumps += inspect_observations(WORK/folder,receipt,case,receipt['arm'])
        queries += receipt['actual_query_turns']; attempts += len(receipt['actual_model_interface_calls'])
        assert receipt['business_unchanged_by_query_and_ordinary'] and receipt['no_new_user_facts']
        assert receipt['final_text_shape'] == text_shape(receipt['ordinary_result']['reply'])
        assert receipt['final_text_shape']['semantic_correctness'] is None and receipt['semantic_review_pending']
        assert all(o['result']['reminder_query']['observed_at'] == 1800000000.0 for o in receipt['query_observations'])
        if kind in ('normal','oracle_poison'):
            assert receipt['model_modes_valid']
            assert [c['role'] for c in receipt['actual_model_interface_calls']] == ['cognition','generation']
            assert all(c['error'] is None for c in receipt['actual_model_interface_calls'])
    assert len(rows) == 41 and queries == 47 and dumps == 88 and attempts == 80
    result = {'completed':True,'scope':'scripted CPU capture/oracle/source controls only; no semantic credit',
        'actual_SDK_trials':len(rows),'actual_query_turns':queries,'actual_ordinary_turns':len(rows),
        'actual_SDK_turns':queries+len(rows),'SQL_dumps_reconstructed':dumps,
        'scripted_interface_attempts':attempts,'native_calls':0,'CPU_fixed_time':1800000000.0,
        'native_uses_actual_wallclock':True,'oracle_and_review_axes_poison_model_inputs_identical':True,
        'groups':[{'folder':f,'kind':k,'case':c['id'],'arm':r['arm']} for f,k,c,r in rows]}
    (WORK/'controlled-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C50 CPU:41 trials;47query+41ordinary=88 SDK turns/SQL;80 scripted interfaces;oracle/rubric inputs unchanged;0 native')


if __name__ == '__main__': main()
