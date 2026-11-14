"""Scripted model baseline versus actual 0-model typed source/SQLite dispatch."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from sample_dispatch import run_branch,sample_repetition

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'evals/interaction/cycle-44/source-read-dispatch-trial-protocol.json'
STATE='read_reminder_state';POLICY='read_reminder_delivery_policy';CLARIFY='clarify_reminder_reference'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Scripted:
    def __init__(self,mode):self.mode=mode;self.records=[];self.context={}

    def chat_tools(self,messages,*,tools,temperature,max_tokens):
        row={'context':dict(self.context),'messages':copy.deepcopy(messages),'tools':copy.deepcopy(tools),
            'result':None,'error':None};self.records.append(row)
        assert self.context['arm']=='model_policy_grounded' and tools and temperature==0 and max_tokens==256
        if self.mode=='direct-no-model':raise AssertionError('direct arm must never invoke model')
        if self.mode=='model-error':
            row['error']='RuntimeError: scripted model failure';raise RuntimeError('scripted model failure')
        if self.mode=='model-plain':result={'role':'assistant','content':'我保证一定提醒你。'}
        elif self.mode=='model-unavailable':result=self.call('send_mail',{})
        elif self.mode=='model-unbound':result=self.call(STATE,{'reminder_id':12345})
        elif self.mode=='model-extra':result=self.call(POLICY,{'authorized':True})
        else:
            names={t['function']['name']:t for t in tools};text=messages[-1]['content']
            if STATE in names and '短信' not in text:
                ident=names[STATE]['function']['parameters']['properties']['reminder_id']['const']
                result=self.call(STATE,{'reminder_id':ident})
            elif POLICY in names:result=self.call(POLICY,{})
            elif CLARIFY in names:result=self.call(CLARIFY,{})
            else:raise AssertionError('unexpected fixture catalogue')
        row['result']=copy.deepcopy(result);return result

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
        assert row['business_unchanged']
        if not row['source_cancelled']:
            assert row['no_post_source_writes']
            assert conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()[0]==row['source_revision']
            assert conn.execute('SELECT cursor FROM memory_web_speaker_state WHERE id=1').fetchone()[0]==source['id']
    finally:conn.close()


def run(mode):
    p=json.loads(PROTOCOL.read_text());out=BASE/'审计/工作目录/003-受控直接路由'/mode
    out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),BASE/'审计/sample_dispatch.py',PROTOCOL,
        ROOT/'src/avatar/lab/source_read_dispatch.py',ROOT/'src/avatar/lab/policy_question_catalogue.py',
        ROOT/'src/avatar/lab/source_tool_catalogue.py',ROOT/'src/avatar/lab/trusted_local_read.py']
    before={str(path.relative_to(ROOT)):digest(path) for path in sources}
    model=Scripted(mode);context=lambda value:setattr(model,'context',dict(value));scores=None
    if mode=='paired':
        batch=sample_repetition(model,p,p['development_cases'],1,out/'cases',on_context=context)
        scores={v:sum(c['arms'][v]['final_expected_task_outcome'] for c in batch['cases']) for v in p['arms']}
        assert scores=={'model_policy_grounded':15,'source_dispatch':24},scores
        assert len(model.records)==20
        branches=[(out/'cases'/c['case']/v,b) for c in batch['cases'] for v,b in c['arms'].items()]
        assert sum(b['status_business_SELECTs'] for _,b in branches)==9
        assert sum(b['framework_skipped_model'] for _,b in branches)==11
        assert sum(b['direct_dispatch_without_model'] for _,b in branches)==17
        assert sum(c['arm_order'][0]=='model_policy_grounded' for c in batch['cases'])==12
    else:
        by_id={c['id']:c for c in p['development_cases']}
        ident='state-1' if mode in ('gold-poison','source-before','source-after-read','source-reentry','model-unbound') else 'policy-exit'
        if mode=='direct-no-model':ident='numbered-reference-channel'
        if mode=='intent-mixed':ident='mixed-numbered-targets'
        if mode=='noread-statement':ident='nonquery-runtime-note'
        case=copy.deepcopy(by_id[ident]);variant='model_policy_grounded' if mode.startswith('model-') else 'source_dispatch'
        if mode=='gold-poison':case.update(tool=POLICY,args={})
        def early(session,planning,arm):
            if mode=='source-before':session.memory.forget(session.memory.remember('临时版本事实'))
            if mode=='source-reentry':session.begin_turn('提醒编号1能通过短信送给我吗？')
        def late(session,result,arm):
            if mode=='source-after-read':session.memory.forget(session.memory.remember('读取后合法遗忘控制'))
        row=run_branch(model,p,case,1,variant,out/'case',on_context=context,before_execution=early,before_publication=late)
        branches=[(out/'case',row)]
        if mode.startswith('source-'):
            assert row['source_cancelled'] and row['reply'] is None and not row['model_used']
            assert row['status_business_SELECTs']==(mode=='source-after-read')
            assert len(model.records)==0
        elif mode=='gold-poison':
            assert row['final_tool']==STATE and row['final_arguments']=={'reminder_id':1}
            assert not row['final_expected_task_outcome'] and row['status_business_SELECTs']==1 and not model.records
        elif mode in ('direct-no-model','intent-mixed','noread-statement'):
            assert row['final_expected_task_outcome'] and not row['model_used'] and not model.records
            assert not row['status_business_SELECTs']
            if mode=='intent-mixed':assert row['result_kind']=='query_intent_clarification'
            if mode=='noread-statement':assert row['result_kind']=='no_read'
        else:
            assert not row['final_expected_task_outcome'] and not row['status_business_SELECTs']
            if mode=='model-plain':assert row['proposal']['content']=='我保证一定提醒你。' and '保证' not in row['reply']
            if mode=='model-error':assert row['model_error']
            if mode=='model-unavailable':assert row['model_contract_error']
            if mode in ('model-unbound','model-extra'):assert row['result_kind']=='validation_failure'
    for directory,row in branches:reconstruct(directory,row)
    assert before=={str(path.relative_to(ROOT)):digest(path) for path in sources}
    report={'verified':True,'scope':'scripted model interfaces and actual SQLite/source; no HTTP/SDK native generation',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_sha256':before,
        'native_calls':0,'scripted_model_attempts':len(model.records),'lab_branch_outcomes':len(branches),
        'SQL_dumps_reconstructed':len(branches),'status_business_SELECTs':sum(b['status_business_SELECTs'] for _,b in branches),
        'direct_without_model':sum(b['direct_dispatch_without_model'] for _,b in branches),
        'framework_skips':sum(b['framework_skipped_model'] for _,b in branches),
        'arm_task_scores':scores,'model_records':model.records}
    (out/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(mode,'verified:',len(branches),'branches;',len(model.records),'scripted attempts')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('paired','direct-no-model','intent-mixed','noread-statement','gold-poison',
        'source-before','source-after-read','source-reentry','model-plain','model-error','model-unavailable','model-unbound','model-extra'))
    run(parser.parse_args().mode)
