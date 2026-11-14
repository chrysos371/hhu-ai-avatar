"""Post-retirement source-channel comparison; no new model/SDK/dump sampling."""
import copy
import json
from pathlib import Path
import sqlite3

from native_common import ROOT,BASE,WORK,read,digest
from avatar.brain.query_history import query_history_content
from avatar.lab.minimal_history_observation import minimal_query_history_content
from avatar.lab.typed_history_observation import typed_query_history_content


def main():
    output = BASE/'审计/工作目录/005-最小来源契约/source-contract.json'
    assert not output.exists(); output.parent.mkdir(exist_ok=True)
    for short in ('4b','14b'): assert read(WORK/(short+'-freeze-v1-retirement.json'))['retired']
    folder = BASE/'实验/4b-development-v1/repetition-1/active-neutral-minimal_observation'
    path = folder/'receipt.json'; receipt = read(path); observation = receipt['query_observations'][0]
    query = observation['result']; metadata = query['reminder_query']; reply = query['reply']
    source = {'text':observation['text'],'source_message_id':metadata['source_message_id'],
        'session_id':metadata['session_id'],'revision':metadata['revision'],
        'scope':'current_user','turn_tools_allowed':True}
    with sqlite3.connect(':memory:') as conn:
        conn.executescript((folder/'after-query-1.sql').read_text())
        assert conn.execute('SELECT notified_at IS NOT NULL FROM memory_reminders WHERE id=1').fetchone()[0] == 0
    altered = copy.deepcopy(metadata); altered['state']['service_claim_recorded'] = True
    old_before = json.loads(typed_query_history_content(reply,metadata,**source).split('\n',1)[1])
    old_after = json.loads(typed_query_history_content(reply,altered,**source).split('\n',1)[1])
    assert old_before['typed_historical_evidence']['record_observation']['service_claim_recorded'] is False
    assert old_after['typed_historical_evidence']['record_observation']['service_claim_recorded'] is True
    original = minimal_query_history_content(reply,metadata,**source)
    assert original == minimal_query_history_content(reply,altered,**source)
    keys = {'version','kind','reminder_id','source_message_id','status_at_observation','client_ack_recorded'}
    frames = 0
    for short in ('4b','14b'):
        for p in (BASE/'实验'/(short+'-development-v1')).glob('repetition-*/*/receipt.json'):
            data = read(p)
            if data['arm'] != 'minimal_observation': continue
            for item in data['query_observations']:
                payload = json.loads(item['model_context'][-1]['content'].split('\n',1)[1])
                assert set(payload['minimal_historical_observation']) == keys
                assert 'typed_historical_evidence' not in payload
                frames += 1
    assert frames == 144
    negatives = []
    for field,value in [('status','completed'),('client_ack_recorded',True),('title','forged')]:
        changed = copy.deepcopy(metadata); changed['state'][field] = value
        assert minimal_query_history_content(reply,changed,**source) == query_history_content(reply,changed,**source)
        negatives.append({'field':field,'minimal_projection_added':False})
    assert minimal_query_history_content(reply,metadata,**(source|{'source_message_id':2})) is None
    result = {'verified':True,'scope':'post-hoc comparison on existing actual query, plus all native minimal query frames',
        'probe_sha256':digest(Path(__file__)),'candidate_sha256':digest(ROOT/'src/avatar/lab/minimal_history_observation.py'),
        'receipt':str(path.relative_to(ROOT)),'receipt_sha256':digest(path),
        'SQL_sha256':digest(folder/'after-query-1.sql'),'SQL_service_claim_recorded':False,
        'C48_control_exposes_flipped_flag':True,'minimal_context_identical_after_bit_flip':True,
        'sampled_minimal_query_frames_without_unbound_claim_or_query_proves_fields':frames,
        'actual_minimal_field_names':sorted(keys),'reply_inconsistent_negative_controls':negatives,
        'forged_source_rejected':True,'new_SDK_turns':0,'new_native_calls':0,'new_SQL_dumps':0,
        'existing_SQL_reconstructed':1,
        'boundary':'omits this unnecessary unbound channel; original source/time/producer/privacy assumptions remain. Not a general authenticity or semantic-quality proof; default remains unactivated.'}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C49 source contract:144 native query frames minimal;claim flip invisible;3 text mismatches fall back/source forge rejected;0 new calls')


if __name__=='__main__': main()
