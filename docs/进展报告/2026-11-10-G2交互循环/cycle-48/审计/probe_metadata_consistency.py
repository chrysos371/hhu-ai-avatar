"""Post-hoc historical metadata consistency probe, after both native retirements.

This tests deliberate metadata corruption at a pure helper, not a public API
exploit or the authenticity of the already verified native sampling inputs.
"""
import copy
import json
from pathlib import Path
import sqlite3

from native_common import ROOT,BASE,WORK,read,digest
from avatar.brain.query_history import query_history_content
from avatar.lab.typed_history_observation import typed_query_history_content


def main():
    output = BASE/'审计/工作目录/005-历史元数据一致性/metadata-probe.json'
    assert not output.exists(); output.parent.mkdir(exist_ok=True)
    for short in ('4b','14b'):
        assert read(WORK/(short+'-freeze-v1-retirement.json'))['retired']
    folder = BASE/'实验/4b-development-v1/repetition-1/active-neutral-typed_observation_history'
    receipt_path = folder/'receipt.json'; receipt = read(receipt_path)
    observation = receipt['query_observations'][0]; query = observation['result']
    metadata = query['reminder_query']; reply = query['reply']
    source = {'text':observation['text'],'source_message_id':metadata['source_message_id'],
        'session_id':metadata['session_id'],'revision':metadata['revision'],
        'scope':'current_user','turn_tools_allowed':True}
    with sqlite3.connect(':memory:') as conn:
        conn.executescript((folder/'after-query-1.sql').read_text())
        claimed = conn.execute('SELECT notified_at IS NOT NULL FROM memory_reminders WHERE id=1').fetchone()[0]
    assert claimed == 0 and metadata['state']['service_claim_recorded'] is False
    baseline = query_history_content(reply,metadata,**source)
    original = typed_query_history_content(reply,metadata,**source)
    before = json.loads(original.split('\n',1)[1])['typed_historical_evidence']['record_observation']
    assert before['service_claim_recorded'] is False
    flipped = copy.deepcopy(metadata); flipped['state']['service_claim_recorded'] = True
    assert query_history_content(reply,flipped,**source) == baseline
    changed = typed_query_history_content(reply,flipped,**source)
    after = json.loads(changed.split('\n',1)[1])['typed_historical_evidence']['record_observation']
    assert after == before|{'service_claim_recorded':True}
    negatives = []
    for field,value in [('client_ack_recorded',True),('status','completed'),('title','different title')]:
        mutated = copy.deepcopy(metadata); mutated['state'][field] = value
        value = typed_query_history_content(reply,mutated,**source)
        assert value == query_history_content(reply,mutated,**source)
        negatives.append({'field':field,'typed_projection_added':False})
    result = {'verified':True,'scope':'post-hoc deliberate pure-helper metadata corruption; no public-route exploit demonstrated',
        'probe_sha256':digest(Path(__file__)),'candidate_sha256':digest(ROOT/'src/avatar/lab/typed_history_observation.py'),
        'receipt':str(receipt_path.relative_to(ROOT)),'receipt_sha256':digest(receipt_path),
        'existing_SQL_sha256':digest(folder/'after-query-1.sql'),'SQL_service_claim_recorded':False,
        'unmodified_query_metadata':metadata,'public_reply_unchanged':reply,
        'before_projection':before,'after_single_flag_flip_projection':after,
        'production_envelope_unchanged_by_flip':True,'reply_bound_negative_controls':negatives,
        'source_binding_unchanged':True,'sampling_artifacts_modified':False,
        'new_SDK_turns':0,'new_native_calls':0,'new_SQL_dumps':0,'existing_SQL_dumps_reconstructed':1,
        'interpretation':'service claim is not narrated in the public reply; finite shape and canonical reply do not independently authenticate this metadata field. Actual SDK producer supplied correct metadata in the native runs. Production integration needs an explicit trusted-producer boundary or omission of unneeded unbound fields.'}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C48 post-hoc metadata:single claim flag passes projection while SQL false;3 text-bound mutations fall back;0 new native/SDK/dumps')


if __name__ == '__main__': main()
