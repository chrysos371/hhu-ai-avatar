"""Re-read first native SSE and reject malformed synthetic fixtures; no new calls."""
from hashlib import sha256
import json
from pathlib import Path
from revision_sse import validate_result_delta
BASE=Path(__file__).resolve().parents[1]


def main():
    source=BASE/'实验/native-before-4b/evaluation.json';data=json.loads(source.read_text());rows=[]
    for index,turn in enumerate(data['cases'][0]['turns']):
        result=validate_result_delta(turn['result'],turn['events'])
        assert result['text_delivery']==('canonical_result_only' if index==2 else 'text_and_result')
        rows.append({'control':'retained_native_turn_'+str(index+1),'result':result,'passed':True})
    events=[{'event':'text','data':{'text':'确认现实。'}}];value=validate_result_delta({'generation_mode':'rules_speaker_control','reply':'确认现实。'},events)
    rows.append({'control':'synthetic_canonical_text_and_result','result':value,'passed':True})
    for name,result,events in (
        ('llm_without_text',{'generation_mode':'llm','reply':'AB-2738'},[]),
        ('partial_llm',{'generation_mode':'llm','reply':'AB-2738'},[{'event':'text','data':{'text':'AB-'}}]),
        ('unregistered_mode',{'generation_mode':'rules_unconfigured','reply':'确认。'},[]),
        ('malformed_text',{'generation_mode':'llm','reply':'AB-2738'},[{'event':'text','data':{'text':None}}])):
        try:validate_result_delta(result,events);raise AssertionError('Invalid SSE fixture accepted')
        except ValueError:pass
        rows.append({'control':name,'rejected':True,'passed':True})
    out=BASE/'审计/工作目录/001-自动情绪版本失效/sse-cpu-controls.json'
    with out.open('x') as stream:json.dump({'passed':True,'new_llm_or_gpu_calls':0,'new_app_or_http_calls':0,'retained_native_evidence_sha256':sha256(source.read_bytes()).hexdigest(),'controls':rows},stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('8 SSE audit CPU controls passed:3 retained native turns, canonical text fixture and4 invalid cases rejected; no new model/app/HTTP calls.')


if __name__=='__main__':main()
