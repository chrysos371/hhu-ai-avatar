"""Actual synthetic SDK/SQL source capture and scripted supervision, zero real models."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/004-纠错材料'
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
OUTPUT=ASSETS/'artifacts/c51/correction-data-v1'
PRIOR=BASE.parent/'cycle-50/审计'
sys.path.insert(0,str(PRIOR))
from sample_history import sample_trial
from verify_observations import inspect_observations
from avatar.lab import data
from avatar.lab.common import canonical,sha
from avatar.lab.runner import ReplyScopedModel,STYLE_HINT

FAMILIES=['external_email','external_SMS','external_phone','draft_quote','fiction_phone',
    'historical_active','historical_cancelled','record_completion','client_ACK',
    'due_not_observation','historical_missing']
TRAIN={
 'external_email':['替我把这件事发到电子信箱，回报寄件结果。','用电子邮件通知我这个事项，报告实际投递情况。','这条记录交给你寄电子邮件，做好后说明。','请执行邮件通知，不只是整理文字。'],
 'external_SMS':['用手机短消息通知我这个事项，说明发出没有。','直接向我的手机投递这件事的文字短信。','替我操作短信发送，再回报处理结果。','这条通知由你用短信发给我。'],
 'external_phone':['请替我拨号通知这件事，回报拨号结果。','你来完成电话通知，接着说明是否真的拨了。','直接拨电话告知我这条事项。','把这件事通过电话联系我，由你拨打。'],
 'draft_quote':['仅代写一行邮件正文，不要执行寄件：我已把邮件发出，请检查收件箱。','我会自行发送，只帮我拟正文，保留这句：我已把邮件发出，请检查收件箱。','做文字创作，不进行发送。正文照写：我已把邮件发出，请检查收件箱。','需要的是待发送草稿，内容为：我已把邮件发出，请检查收件箱。'],
 'fiction_phone':['给虚构人物林澈写一句台词：我已经拨通了电话，通知到位。','只是故事对白，让虚构角色说：我已经拨通了电话，通知到位。','创作一行舞台剧对白，人物说：我已经拨通了电话，通知到位。','给小说角色安排一句原话：我已经拨通了电话，通知到位。'],
 'historical_active':['只凭以前那份有效记录，能说眼下依然有效吗？','你先前拿到的有效状态可以保证此刻没有变吗？','请区分过去查到的有效记录和眼前能否确认的状态。','旧快照写着有效，现时结论也必定如此吗？'],
 'historical_cancelled':['先前那次显示取消，可否保证这一刻没有变化？','凭历史取消快照，能确定眼下仍取消吗？','请区分那次的取消状态和现在是否经过核实。','旧数据记为取消，可以直接充当实时结果吗？'],
 'record_completion':['这条数据库完成标记能不能证明本人真正执行完？','系统字段标为完成，就能证明人完成了工作吗？','请解释记录完成与本人实际做完有什么区别。','完成字段可以当作现实任务已做完的证据吗？'],
 'client_ACK':['记录有软件确认事件，可以证明当事人阅读了吗？','ACK这类客户端返回值能担保某个人读到了吗？','请分清客户端提交确认和本人已读这两件事。','软件登记的确认信号是否足以验证真人阅读？'],
 'due_not_observation':['记录中展示的提醒日期，是预定到期还是查询时间？','请区分提醒安排的时刻与记录的修改或观测时间。','所示日期能作为最近一次修改时间的依据吗？','你能说明提醒时刻这个字段究竟代表什么吗？'],
 'historical_missing':['过去未匹配到记录，能保证后来一直没有这条吗？','凭那次缺失快照，可以断定此时仍没有编号吗？','一次没有匹配的旧结果是否足以担保现在还不存在？','请分清当次未找到与当前是否再次核实存在。']}
DEV={
 'external_email':'麻烦你为这条事项执行电子邮件投递，告知是否已经成功寄送。',
 'external_SMS':'要你完成手机短消息通知，并告知实际发送结果。',
 'external_phone':'这件事由你执行拨打电话，回报有无拨出。',
 'draft_quote':'只拟一行尚未发送的文字，保留句子“我已把邮件发出，请检查收件箱。”由我以后自行寄件。',
 'fiction_phone':'请写纯虚构人物的一句发言：“我已经拨通了电话，通知到位。”这是小说创作。',
 'historical_active':'历史读取说有效，可以担保这一秒依然是同样的状态吗？',
 'historical_cancelled':'上次读出的取消标记，会自动等同于这一秒的真实状态吗？',
 'record_completion':'系统的完成属性能充当真实劳动已完成的凭证吗？',
 'client_ACK':'那份客户端ACK能构成本人确实阅读的凭证吗？',
 'due_not_observation':'提醒的安排时间是否就是记录刚刚更新的时间？',
 'historical_missing':'历史检索没有命中，能担保这一秒还是没有记录吗？'}
TARGET={
 'external_email':'我没有电子邮件发送接口，本回合没有寄出邮件。我可以提供邮件草稿，供你自行发送。',
 'external_SMS':'这套系统没有短信发送接口，本回合没有发出短信。我可以帮你整理文字稿。',
 'external_phone':'我没有拨号接口，因此没有替你打电话。可以为你准备通知时要说的话。',
 'draft_quote':'我已把邮件发出，请检查收件箱。',
 'fiction_phone':'林澈说：“我已经拨通了电话，通知到位。”',
 'historical_active':'当次读取的记录状态为有效；这是旧快照，没有本回合新的状态读取，不能确定此刻仍然有效。',
 'historical_cancelled':'那次读取时的记录状态为已取消；我没有本回合新的状态读取，不能保证现在仍是这个状态。',
 'record_completion':'数据库当时标记为已完成，但这不是本人做完事情的证明；没有实际行为证据，不能认定现实任务已经完成。',
 'client_ACK':'客户端返回确认，只说明软件登记了ACK，不足以证明某个人亲自阅读了内容。',
 'due_not_observation':'所示提醒时间是预定到期安排，不是查询发生或记录修改的时间；不能拿它当作最近更新时间。',
 'historical_missing':'那次读取没有找到这一编号；这是历史缺失结果，没有新的状态读取，不能保证现在仍不存在。'}


class Teacher:
    """Deliberately scripted CPU target, never a model-generated answer."""
    def __init__(self,target):self.target=target;self.calls=[]
    def generate(self,messages,kind,adapter):
        assert adapter is False
        reply='{"emotion":{"valence":0,"arousal":0},"facts":[]}' if kind=='analysis' else self.target
        self.calls.append({'kind':kind,'messages':json.loads(json.dumps(messages,ensure_ascii=False)),
            'adapter_enabled':adapter,'reply':reply})
        return {'reply':reply,'adapter_enabled':adapter,'seconds':0.0,'new_tokens':0,'truncated':False,'fixture':True}


def main():
    assert not OUTPUT.exists();OUTPUT.mkdir(parents=True)
    WORK.mkdir(exist_ok=True);summary_path=WORK/'data-preparation-v1.json';assert not summary_path.exists()
    protocol_path=ROOT/'evals/interaction/cycle-52/correction-transfer-protocol.json'
    protocol=json.loads(protocol_path.read_text());assert protocol['data']['train_samples']==176
    protected,hashes=data.evaluation_texts()
    eval_path='evals/interaction/cycle-52/correction-transfer-cases.json';assert eval_path in hashes
    bank=json.loads((ROOT/eval_path).read_text())['cases']
    assert len(bank)==22 and all(c[k] in protected for c in bank for k in ('query_text','followup_text'))
    old_sha=sha(ROOT/'src/avatar/lab/data.py')
    rows={'train':[],'dev':[]};groups=[];SQL_count=interface_count=0
    status={'historical_cancelled':'cancelled','record_completion':'completed',
        'external_phone':'completed','historical_missing':'missing'}
    with patch('time.time',return_value=protocol['evaluation']['controlled_query_clock_epoch']):
        for index,family in enumerate(FAMILIES):
            local=[];raw_hashes={};family_SQL=0
            for split,count,base in [('train',16,11000),('dev',4,21000)]:
                for i in range(count):
                    ident=base+index*100+i;sample_id=f'c51-{family}-{split}-{i:02}'
                    state=status.get(family,'active');ack=family=='client_ACK'
                    question=TRAIN[family][i%4] if split=='train' else DEV[family]
                    case={'id':sample_id,'group':family,'query_text':f'提醒编号{ident}现在是什么状态？',
                        'followup_text':question,'seed':{'record_id':ident,'title':f'合成校园事务-{split}-{index}-{i}',
                            'status_at_query':state,'client_ack_recorded':ack,'due_date':f'2097-05-{1+(index+i)%28:02}T10:00:00+08:00'},
                        'independent_actor_after_query':'create_record' if state=='missing' else 'set_completed' if state=='cancelled' else 'set_cancelled',
                        'repeat_query_after_actor':False,'oracle_observation':{'observed_record_state':state,'current_record_state':'unknown'},
                        'review_axes':['synthetic_source_correctness','scripted_target_not_native_quality']}
                    teacher=Teacher(TARGET[family]);engine=ReplyScopedModel(teacher,arm='style_prompt')
                    folder=OUTPUT/'raw'/sample_id
                    receipt=sample_trial(engine,case,'production_snapshot',1,folder,on_context=lambda _:None)
                    family_SQL+=inspect_observations(folder,receipt,case,'production_snapshot')
                    assert receipt['business_unchanged_by_query_and_ordinary'] and receipt['no_new_user_facts']
                    assert [c['kind'] for c in teacher.calls]==['analysis','reply']
                    assert receipt['ordinary_result']['reply']==TARGET[family] and receipt['model_modes_valid']
                    messages=teacher.calls[-1]['messages']+[{'role':'assistant','content':receipt['ordinary_result']['reply']}]
                    assert [m['role'] for m in messages]==['system','user','assistant','user','assistant']
                    assert messages[0]['content'].endswith(STYLE_HINT)
                    candidate=data.normalize_dialogue('c51-synthetic','train',sample_id,[m['content'] for m in messages[1:]])
                    accepted,rejected=data.screen_candidates([candidate],protected,
                        source_policy={'c51-synthetic':{'language':'zh','use':'experimental-sft'}})
                    if not accepted:
                        (folder/'screening-rejection.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2)+'\n')
                        raise ValueError('candidate rejected by actual source filter: '+sample_id+': '+str(rejected[0]['reasons']))
                    content=hashlib.sha256(canonical(messages).encode()).hexdigest()
                    row={'id':sample_id,'messages':messages,'provenance':{'source':'synthetic-actual-SDK-SQL-scripted-target',
                        'content_sha256':content,'family':family,'split':split,'human_reviewed':False,'semantic_quality':'not independently human reviewed'}}
                    rows[split].append(row);local.append(row['id'])
                    (folder/'case.json').write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
                    (folder/'scripted-backend-calls.json').write_text(json.dumps(teacher.calls,ensure_ascii=False,indent=2)+'\n')
                    raw_hashes.update({str(p.relative_to(OUTPUT)):sha(p) for p in folder.iterdir() if p.is_file()})
                    interface_count+=len(teacher.calls)
            assert len(local)==20 and family_SQL==40;SQL_count+=family_SQL
            group={'family':family,'samples':20,'train':16,'dev':4,'actual_CPU_SDK_turns':40,'SQL_dumps_reconstructed':40,
                'scripted_interfaces':40,'native_calls':0,'raw_output':str(OUTPUT),'raw_sha256':raw_hashes}
            group_path=WORK/(family+'-source-v1.json');assert not group_path.exists()
            group_path.write_text(json.dumps(group,ensure_ascii=False,indent=2)+'\n');groups.append(group_path.name)
            print(family,'closed20 CPU examples/40SQL;actual protected screening passed',flush=True)
    assert len(rows['train'])==176 and len(rows['dev'])==44 and SQL_count==interface_count==440
    assert len({r['id'] for values in rows.values() for r in values})==220
    assert not ({r['provenance']['content_sha256'] for r in rows['train']} & {r['provenance']['content_sha256'] for r in rows['dev']})
    assert data.evaluation_texts()[1]==hashes and sha(ROOT/'src/avatar/lab/data.py')==old_sha
    for split,name in [('train','sft.jsonl'),('dev','dev.jsonl')]:
        (OUTPUT/name).write_text(''.join(canonical(row)+'\n' for row in rows[split]))
    manifest={'purpose':'experimental-style-pilot','experiment_kind':'source-grounded-correction-pilot',
        'adapter_scope':'reply-only','human_reviewed':False,'samples':176,'dev_samples':44,
        'sft_sha256':sha(OUTPUT/'sft.jsonl'),'dev_sha256':sha(OUTPUT/'dev.jsonl'),
        'screening_code_sha256':old_sha,'protected_eval_hashes':hashes,'protocol_sha256':sha(protocol_path),
        'generator_sha256':sha(Path(__file__)),'source_query_helper_sha256':sha(PRIOR/'sample_history.py'),
        'source_independent_checker_sha256':sha(PRIOR/'verify_observations.py'),
        'source_teacher_is_scripted':True,'no_native_semantic_scores':True,'quality_approved':False}
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    result={'completed':True,'scope':'actual CPU SDK/SQL sources with scripted targets, not native quality or human approval',
        'output':str(OUTPUT),'train_samples':176,'dev_samples':44,'families':11,
        'actual_CPU_SDK_trials':220,'actual_CPU_SDK_turns':440,'SQL_dumps_reconstructed':440,
        'scripted_interfaces':440,'native_calls':0,'training_steps':0,'eval_protected_before_export':True,
        'protected_eval_hashes':hashes,'groups':groups,'manifest_sha256':sha(OUTPUT/'manifest.json'),
        'generator_sha256':sha(Path(__file__)),'protocol_sha256':sha(protocol_path)}
    summary_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C51 data:176train+44dev;220CPU SDK trials/440turns,SQL,scripted interfaces;0 native/training',flush=True)


if __name__=='__main__':main()
