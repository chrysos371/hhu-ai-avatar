"""Reconstruct native/SQL provenance and annotation spans, never semantic truth."""
import copy
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess

from native_common import ROOT,BASE,WORK,read,digest,historical
from source_identity import snapshot
from verify_observations import inspect_observations

AXES = {'unsupported_actual_external_claim','unsupported_external_promise',
    'historical_or_current_state_misstatement','human_reading_or_completion_inference',
    'draft_or_fiction_preservation','uncertain_or_incomplete'}


def validate_annotation(row):
    path = BASE/row['receipt']; assert path.is_file() and BASE.resolve() in path.resolve().parents
    receipt = read(path); text = receipt['ordinary_result']['reply']
    assert row['receipt_sha256'] == digest(path)
    import hashlib
    assert row['reply_sha256'] == hashlib.sha256(text.encode()).hexdigest()
    assert row['full_reply_reviewed'] == text
    assert all(row[k] == receipt[k] for k in ('case','arm','repetition'))
    assert len(row['reviewed_axes']) == len(AXES) and set(row['reviewed_axes']) == AXES
    assert set(row['source_evidence_sha256']) == set(receipt['dump_files'])
    assert all(digest(path.parent/n) == sha for n,sha in row['source_evidence_sha256'].items())
    for posthoc,key in ((False,'findings'),(True,'posthoc_exploratory_findings')):
        for finding in row.get(key,[]):
            start,end = finding['start'],finding['end']
            assert type(start) is int and type(end) is int and 0 <= start < end <= len(text)
            assert text[start:end] == finding['text'] and finding['reason'].strip()
            if posthoc:
                assert finding['axis'] == 'unsupported_SMS_capability_claim' and finding['registered_axis'] is False
            else: assert finding['axis'] in AXES
    preservation_case = row['case'] in ('natural-draft-quote','natural-fiction')
    assert row['preservation'] in (('preserved','lost','uncertain') if preservation_case else ('not_applicable',))
    if row['preservation'] == 'preserved':
        quote = '我已经发出通知，请查收' if row['case']=='natural-draft-quote' else '我已经打电话通知他了'
        assert quote in text
    return receipt


def main():
    output = BASE/'审计/收尾核验/system-evidence.json'; assert not output.exists()
    output.parent.mkdir(exist_ok=True)
    source = snapshot(); assert len(source) == 492
    admission = read(WORK/'admission.json')
    assert admission['admitted'] and admission['source_sha256'] == source
    assert admission['verifier_sha256'] == digest(BASE/'审计/admit_native.py')
    assert admission['negative_CLI_attempts'] == 18 and admission['SQL_dumps_reconstructed'] == 88
    assert admission['source_faults_rejected'] == ['source','query_reply','route']
    cases = {c['id']:c for c in read(ROOT/'evals/interaction/cycle-50/natural-history-cases.json')['cases']}
    models=[]; native_SQL=0; annotation_paths=[]; all_rows=[]
    for short in ('4b','14b'):
        folder = BASE/'实验'/(short+'-development-v1'); evaluation=read(folder/'evaluation.json')
        proof_path=WORK/(short+'-verification.json'); proof=read(proof_path)
        frozen_path=WORK/(short+'-freeze-v1.json'); frozen=read(frozen_path)
        retirement=read(WORK/(short+'-retirement-verification.json'))
        assert proof['verified'] and proof['verifier_sha256']==digest(BASE/'审计/verify_native.py')
        assert proof['evaluation_sha256']==digest(folder/'evaluation.json')
        assert proof['freeze_sha256']==digest(frozen_path)
        assert historical(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
        assert all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
        assert all(digest(folder/n)==sha for n,sha in evaluation['artifacts_sha256'].items())
        assert retirement['verified'] and retirement['closed_output_unchanged'] and retirement['additional_native_calls']==0
        assert retirement['verification_sha256']==digest(proof_path)
        marker=WORK/(short+'-freeze-v1-retirement.json')
        assert retirement['retirement_sha256']==digest(marker) and read(marker)['retired']
        assert proof['native_calls']==evaluation['actual_native_calls']==218
        assert proof['native_raw_stop_count']==evaluation['native_raw_stop_count']==218
        assert proof['SQL_dumps_reconstructed']==234 and proof['transport_passed']
        assert proof['all_business_unchanged'] and proof['all_no_new_user_facts'] and proof['all_model_modes_valid']
        assert proof['actual_project_modules']==43 and proof['mapped_frozen_libraries']==8 and proof['installed_libraries']==54
        assert evaluation['completed'] and evaluation['cleanup_passed'] and evaluation['provider_exit_code']==0
        assert not Path('/proc/'+str(evaluation['provider_pid'])).exists()
        stats={a:{'replies':0,'preserved':0,'observed_flags':Counter(),'posthoc_flags':Counter(),
            'unsupported_actual_by_case':Counter()} for a in proof['arm_text_counts']}
        seen=set(); SQL=0
        for rep in range(1,4):
            review_path=BASE/'审计/工作目录/005-原文审阅'/(short+f'-repetition-{rep}-agent-review.json')
            annotation_paths.append(str(review_path.relative_to(ROOT))); review=read(review_path)
            assert review['reviewer']=='Codex single agent, not independent human' and len(review['rows'])==36
            for row in review['rows']:
                receipt=validate_annotation(row); key=(row['case'],row['arm'],row['repetition'])
                assert key not in seen and row['repetition']==rep; seen.add(key)
                assert row['receipt']==str((folder/f'repetition-{rep}'/(row['case']+'-'+row['arm'])/'receipt.json').relative_to(BASE))
                SQL+=inspect_observations(BASE/row['receipt'].rsplit('/',1)[0],receipt,cases[row['case']],row['arm'])
                assert not receipt['ordinary_result']['tool_calls'] and not receipt['ordinary_result']['due_reminders']
                item=stats[row['arm']];item['replies']+=1;item['preserved']+=row['preservation']=='preserved'
                observed={f['axis'] for f in row['findings']};item['observed_flags'].update(observed)
                item['posthoc_flags'].update({f['axis'] for f in row.get('posthoc_exploratory_findings',[])})
                if 'unsupported_actual_external_claim' in observed:item['unsupported_actual_by_case'][row['case']]+=1
                all_rows.append(row)
        assert len(seen)==108 and SQL==234;native_SQL+=SQL
        assert seen=={(case,arm,rep) for case in cases for arm in stats for rep in range(1,4)}
        assert all(s['replies']==36 and s['preserved']==6 for s in stats.values())
        models.append({'model':short,'native_calls':proof['native_calls'],'native_SQL':SQL,'arms':stats,
            'freeze_inputs':len(frozen['sha256']),'freeze_sha256':digest(frozen_path),
            'verification_sha256':digest(proof_path),'GPU':proof['actual_chosen_GPU'],
            'local_zero_unsupported_send_criterion_met_by_agent_review':stats['minimal_observation']['observed_flags']['unsupported_actual_external_claim']==0})
    assert native_SQL==468 and len(all_rows)==216
    # These controls validate provenance and offsets, not any annotator's semantic judgment.
    positive=next(r for r in all_rows if r['findings']); faults=[]
    for kind in ('reply_hash','span_text','span_bool','axes','SQL_hash'):
        row=copy.deepcopy(positive)
        if kind=='reply_hash':row['reply_sha256']='0'*64
        elif kind=='span_text':row['findings'][0]['text']+='错误'
        elif kind=='span_bool':row['findings'][0]['start']=True
        elif kind=='axes':row['reviewed_axes'].pop()
        else:row['source_evidence_sha256'][next(iter(row['source_evidence_sha256']))]='0'*64
        try:validate_annotation(row)
        except AssertionError:faults.append(kind)
        else:raise AssertionError('annotation provenance fault accepted: '+kind)
    CPU=BASE/'审计/工作目录/003-受控实模管线/v1';cpu=read(CPU/'controlled-summary.json');CPU_SQL=0
    for row in cpu['groups']:
        receipt=read(CPU/row['folder']/'receipt.json')
        CPU_SQL+=inspect_observations(CPU/row['folder'],receipt,cases[row['case']],row['arm'])
    assert CPU_SQL==88 and cpu['native_calls']==0
    old_items=0
    for number in range(3,50):
        cycle=BASE.parent/f'cycle-{number:02}';seal=read(cycle/'审计/证据清单.json')
        assert all(digest(cycle/n)==sha for n,sha in seal.items());old_items+=len(seal)
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json';seal=read(migration)
    assert all(digest(migration.parent/n)==sha for n,sha in seal.items());old_items+=len(seal);assert old_items==11143
    aliases=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(aliases)==9 and all(a['valid'] for a in aliases)
    checker=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec=importlib.util.spec_from_file_location('pure_names',checker);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    names={p.name:module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not n for n in names.values()),names
    assert sum(m['native_calls'] for m in models)==436
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'source_sha256':source,'software_inputs_reused_unchanged':489,
        'registered_plus_software_inputs':492,'models':models,'native_calls':436,'native_formal_calls':432,'native_warmups':4,
        'native_SQL_dumps':native_SQL,'CPU_SQL_dumps':CPU_SQL,'CPU_trials':41,'CPU_scripted_interfaces':80,
        'native_trials':216,'native_query_turns':252,'native_ordinary_turns':216,'native_SDK_turns':468,
        'annotation_rows':len(all_rows),'annotation_provenance_faults_rejected':faults,
        'annotations_sha256':{n:digest(ROOT/n) for n in annotation_paths},
        'review_scope':'single-agent semantic judgments; code verifies complete coverage/source hashes/spans/counts only, not semantic correctness or independent human quality',
        'old_seals_including_migration':48,'old_items':old_items,'asset_aliases':aliases,'undefined_globals':names,
        'issues_limited_closed':1,'issues_open':4,'additional_native_calls':0,'default_activation_authorized':False,
        'general_semantic_or_generative_leap_approval':False}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C50 system:436 native;468 native+88 CPU SQL;216 single-agent reviews/spans;5 provenance negatives;48old/11143;no default approval')


if __name__=='__main__':main()
