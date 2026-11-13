"""Scripted two-service policy evidence controls with actual SQLite, no model."""
import argparse
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import hashlib

from sample_catalogues import run_branch, sample_repetition

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'evals/interaction/cycle-43/policy-question-trial-protocol.json'
STATE='read_reminder_state';POLICY='read_reminder_delivery_policy';CLARIFY='clarify_reminder_reference'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Scripted:
    def __init__(self,mode):
        self.mode=mode;self.records=[];self.context={};self.callback=None

    def chat_tools(self,messages,*,tools,temperature,max_tokens):
        assert tools and temperature==0 and max_tokens==256
        row={'context':dict(self.context),'messages':copy.deepcopy(messages),'tools':copy.deepcopy(tools),
            'result':None,'error':None};self.records.append(row)
        names={t['function']['name']:t for t in tools};text=messages[-1]['content']
        if self.mode=='error':
            row['error']='RuntimeError: scripted model failure'
            raise RuntimeError('scripted model failure')
        if self.mode=='plain':result={'role':'assistant','content':'我保证一定提醒你。'}
        elif self.mode=='policy-bypass':result=self.call(POLICY,{})
        elif self.mode=='unavailable':result=self.call('send_mail',{})
        elif self.mode=='bad-bound':result=self.call(STATE,{'reminder_id':12345})
        elif self.mode=='extra':result=self.call(POLICY,{'authorized':True})
        elif STATE in names and '短信' not in text:
            ident=names[STATE]['function']['parameters']['properties']['reminder_id']['const']
            result=self.call(STATE,{'reminder_id':ident})
        elif POLICY in names:result=self.call(POLICY,{})
        elif CLARIFY in names:result=self.call(CLARIFY,{})
        else:raise AssertionError('fixture received unexpected catalogue')
        if self.callback:
            callback,self.callback=self.callback,None;callback()
        row['result']=copy.deepcopy(result)
        return result

    def call(self,name,args):
        return {'role':'assistant','tool_calls':[{'id':f'call_scripted_{len(self.records)}','type':'function',
            'function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}


def reconstruct(directory,row):
    dump=directory/'state.sql';assert digest(dump)==row['SQL_dump_sha256']
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    try:
        conn.executescript(dump.read_text())
        for name,values in row['business_after'].items():
            assert [dict(r) for r in conn.execute('SELECT * FROM '+name+' ORDER BY id')]==values
        source=conn.execute('SELECT * FROM memory_messages WHERE id=?',(row['source_message_id'],)).fetchone()
        assert source and source['role']=='user' and source['session_id']==row['session_id']
        if not row['source_cancelled']:
            assert conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()[0]==row['source_revision']
            assert conn.execute('SELECT cursor FROM memory_web_speaker_state WHERE id=1').fetchone()[0]==source['id']
            assert row['no_post_source_writes']
        assert row['business_unchanged']
    finally:conn.close()


def run(mode):
    protocol=json.loads(PROTOCOL.read_text());out=BASE/'审计/工作目录/003-受控政策依据'/mode
    out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),BASE/'审计/sample_catalogues.py',PROTOCOL,
        ROOT/'src/avatar/lab/policy_question_catalogue.py',ROOT/'src/avatar/lab/source_tool_catalogue.py',
        ROOT/'src/avatar/lab/trusted_local_read.py']
    before={str(p.relative_to(ROOT)):digest(p) for p in sources}
    model=Scripted(mode);context=lambda d:setattr(model,'context',dict(d));scores=None
    if mode=='paired':
        batch=sample_repetition(model,protocol,protocol['development_cases'],1,out/'cases',on_context=context)
        scores={v:sum(c['arms'][v]['final_expected_task_outcome'] for c in batch['cases']) for v in protocol['arms']}
        assert scores=={'baseline_complete':12,'policy_grounded':16},scores
        assert len(model.records)==24
        branches=[(out/'cases'/c['case']/v,b) for c in batch['cases'] for v,b in c['arms'].items()]
        assert sum(b['framework_skipped_model'] for _,b in branches)==8
        assert sum(b['status_business_SELECTs'] for _,b in branches)==4
        # Balanced first positions; each service gets independent actual source/DB.
        assert sum(c['arm_order'][0]=='baseline_complete' for c in batch['cases'])==8
    else:
        case=copy.deepcopy(protocol['development_cases'][0])
        if mode in ('bad-bound','gold-poison'):case=copy.deepcopy(protocol['development_cases'][2])
        if mode=='policy-bypass':case=copy.deepcopy(protocol['development_cases'][8])
        if mode=='gold-poison':case.update(tool=POLICY,args={})
        def hook(session,catalogue,variant):
            def forget():session.memory.forget(session.memory.remember('临时版本事实'))
            if mode=='source-before':forget()
            if mode=='source-after':model.callback=forget
        row=run_branch(model,protocol,case,1,'policy_grounded',out/'case',on_context=context,before_model=hook)
        branches=[(out/'case',row)]
        if mode.startswith('source-'):
            assert row['source_cancelled'] and row['reply'] is None and not row['status_business_SELECTs']
            assert len(model.records)==(mode=='source-after')
        elif mode=='gold-poison':
            assert row['final_tool']==STATE and row['final_arguments']=={'reminder_id':1}
            assert not row['final_expected_task_outcome'] and row['status_business_SELECTs']==1
        elif mode=='policy-bypass':
            assert row['model_contract_error'] and not row['read_or_control_result'] and not row['status_business_SELECTs']
            # Fixed no-read can satisfy the broad task fallback but cannot erase
            # this invalid attempt from the strict preregistered primary gate.
            assert row['final_expected_task_outcome']
        else:
            assert not row['final_expected_task_outcome'] and not row['status_business_SELECTs']
            if mode=='plain':assert row['proposal']['content']=='我保证一定提醒你。' and '保证' not in row['reply']
            if mode=='error':assert row['model_error']
            if mode=='unavailable':assert row['model_contract_error']
            if mode in ('bad-bound','extra'):assert row['result_kind']=='validation_failure'
    for directory,row in branches:reconstruct(directory,row)
    assert before=={str(p.relative_to(ROOT)):digest(p) for p in sources}
    report={'verified':True,'scope':'scripted interface controls; actual SQLite/source; no HTTP/SDK generation/native/GPU',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_sha256':before,
        'native_calls':0,'scripted_model_attempts':len(model.records),'lab_branch_outcomes':len(branches),
        'SQL_dumps_reconstructed':len(branches),'status_business_SELECTs':sum(b['status_business_SELECTs'] for _,b in branches),
        'arm_task_scores':scores,'model_records':model.records}
    (out/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(mode,'verified:',len(branches),'branches;',len(model.records),'scripted attempts')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('paired','policy-bypass','plain','error','unavailable','bad-bound','extra',
        'gold-poison','source-before','source-after'))
    run(parser.parse_args().mode)
