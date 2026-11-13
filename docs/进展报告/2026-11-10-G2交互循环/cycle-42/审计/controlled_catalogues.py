"""Scripted interface controls of three actual source/SQLite catalogue branches.

No HTTP/SDK generation/native model/GPU. Expected labels affect scoring only.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from sample_catalogues import canonical, run_branch, sample_repetition

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'evals/interaction/cycle-42/source-catalogue-trial-protocol.json'
STATE='read_reminder_state'
POLICY='read_reminder_delivery_policy'
CLARIFY='clarify_reminder_reference'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Scripted:
    def __init__(self,mode):
        self.mode=mode;self.records=[];self.context={};self.callback=None

    def chat_tools(self,messages,*,tools,temperature,max_tokens):
        row={'context':dict(self.context),'messages':copy.deepcopy(messages),
             'tools':copy.deepcopy(tools),'result':None,'error':None}
        self.records.append(row)
        assert temperature==0 and max_tokens==256
        text=messages[-1]['content']
        names={t['function']['name'] for t in tools}
        by_name={t['function']['name']:t for t in tools}
        # This CPU fixture responds to text and advertised schemas, never gold.
        if self.mode=='plain':
            result={'role':'assistant','content':'我保证一定提醒你。'}
        elif self.mode=='error':
            row['error']='RuntimeError: scripted model failure'
            raise RuntimeError('scripted model failure')
        elif self.mode=='malformed':result={'role':'assistant','tool_calls':[17]}
        elif self.mode=='unavailable':result=self.call('send_mail',{})
        elif self.mode=='unbound':result=self.call(STATE,{'reminder_id':12345})
        elif self.mode=='extra':result=self.call(STATE,{'reminder_id':1,'authorized':True})
        elif self.mode=='policy-only':result=self.call(POLICY,{})
        elif self.mode=='clarify-only':result=self.call(CLARIFY,{})
        elif '改写' in text or '不要查询' in text:
            result={'role':'assistant','content':'普通文字，不读取提醒。'}
        elif '状态' in text or '还存在' in text or '具体编号' in text:
            if STATE in names:
                prop=by_name[STATE]['function']['parameters']['properties']['reminder_id']
                ident=prop.get('const',999 if '999' in text else 1 if '编号1' in text else 12345)
                result=self.call(STATE,{'reminder_id':ident})
            elif CLARIFY in names:result=self.call(CLARIFY,{})
            else:result={'role':'assistant','content':'请提供提醒编号。'}
        elif '到时间' in text or '短信' in text:
            if self.context.get('arm')=='full' and '到时间' in text:
                result=self.call(STATE,{'reminder_id':12345})
            else:result=self.call(POLICY,{})
        else:result={'role':'assistant','content':'普通文字。'}
        if self.callback:
            callback,self.callback=self.callback,None
            callback()
        row['result']=copy.deepcopy(result)
        return result

    def call(self,name,args):
        return {'role':'assistant','tool_calls':[{'id':f'call_scripted_{len(self.records)}',
            'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}


def reconstruct(directory,row):
    dump=directory/'state.sql'
    assert digest(dump)==row['SQL_dump_sha256']
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    try:
        conn.executescript(dump.read_text())
        for table,values in row['business_after'].items():
            assert [dict(r) for r in conn.execute('SELECT * FROM '+table+' ORDER BY id')]==values
        source=conn.execute('SELECT * FROM memory_messages WHERE id=?',(row['source_message_id'],)).fetchone()
        assert source and source['role']=='user' and source['session_id']==row['session_id']
        if not row['source_cancelled']:
            assert conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()[0]==row['source_revision']
            assert conn.execute('SELECT cursor FROM memory_web_speaker_state WHERE id=1').fetchone()[0]==source['id']
        assert row['business_unchanged']
        if not row['source_cancelled']:assert row['no_post_source_writes']
    finally:conn.close()


def run(mode):
    protocol=json.loads(PROTOCOL.read_text())
    out=BASE/'审计/工作目录/003-受控目录配对'/mode
    out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),BASE/'审计/sample_catalogues.py',PROTOCOL,
             ROOT/'src/avatar/lab/source_tool_catalogue.py',ROOT/'src/avatar/lab/trusted_local_read.py']
    before={str(p.relative_to(ROOT)):digest(p) for p in sources}
    model=Scripted(mode);context=lambda d:setattr(model,'context',dict(d))
    branches=[]
    if mode=='three-arm':
        batch=sample_repetition(model,protocol,protocol['development_cases'],1,out/'cases',on_context=context)
        scores={v:sum(r['arms'][v]['final_expected_task_outcome'] for r in batch['cases']) for v in protocol['arms']}
        assert scores=={'full':9,'eligible_bound':10,'eligible_complete':10},scores
        assert len(model.records)==22
        for row in batch['cases']:
            for variant,branch in row['arms'].items():branches.append((out/'cases'/row['case']/variant,branch))
        # Rule-skipped negative cases contribute no model calls and no SQL.
        assert sum(b['framework_skipped_model'] for _,b in branches)==8
        assert sum(b['status_business_SELECTs'] for _,b in branches)==6
    else:
        case=copy.deepcopy(protocol['development_cases'][2])
        variant='eligible_complete'
        if mode=='policy-only':
            case=copy.deepcopy(protocol['development_cases'][8]);variant='eligible_bound'
        if mode=='clarify-only':case=copy.deepcopy(protocol['development_cases'][0])
        if mode=='gold-poison':case.update(tool=POLICY,args={})
        def hook(session,catalogue,arm):
            def forget():
                fact=session.memory.remember('受控版本更新')
                session.memory.forget(fact)
            if mode=='source-before':forget()
            if mode=='source-after':model.callback=forget
        row=run_branch(model,protocol,case,1,variant,out/'case',on_context=context,before_model=hook)
        branches=[(out/'case',row)];scores=None
        if mode in ('source-before','source-after'):
            assert row['source_cancelled'] and row['reply'] is None and row['status_business_SELECTs']==0
            assert len(model.records)==(mode=='source-after')
        elif mode=='gold-poison':
            assert row['final_tool']==STATE and row['final_arguments']=={'reminder_id':1}
            assert not row['final_expected_task_outcome'] and row['status_business_SELECTs']==1
        elif mode=='policy-only':
            assert row['reply_origin']=='trusted_read_fixed' and not row['final_expected_task_outcome']
        elif mode=='clarify-only':
            assert row['reply_origin']=='verified_clarification' and not row['final_expected_task_outcome']
        else:
            assert row['status_business_SELECTs']==0 and row['reply_origin']!='trusted_read_fixed'
            assert not row['final_expected_task_outcome']
            if mode=='plain':
                assert row['proposal']['content']=='我保证一定提醒你。' and '保证' not in row['reply']
            if mode in ('unbound','extra'):assert row['result_kind']=='validation_failure'
            if mode in ('malformed','unavailable'):assert row['model_contract_error']
            if mode=='error':assert row['model_error']
    for directory,row in branches:reconstruct(directory,row)
    assert before=={str(p.relative_to(ROOT)):digest(p) for p in sources}
    result={'verified':True,'scope':'scripted interfaces/actual SQLite, no HTTP/SDK generation/native/GPU',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_sha256':before,'native_calls':0,'scripted_model_attempts':len(model.records),
        'lab_branch_outcomes':len(branches),'SQL_dumps_reconstructed':len(branches),
        'status_business_SELECTs':sum(b['status_business_SELECTs'] for _,b in branches),
        'arm_task_scores':scores,'model_records':model.records}
    (out/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(mode,'verified:',len(branches),'branches;',len(model.records),'scripted attempts')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('three-arm','policy-only','clarify-only','plain','error','malformed',
        'unavailable','unbound','extra','gold-poison','source-before','source-after'))
    run(parser.parse_args().mode)
