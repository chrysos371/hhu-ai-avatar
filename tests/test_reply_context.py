import json
import pytest
from avatar.brain.reply_context import build_reply_context


def conversation(*texts):
    return [{'role':'user' if n%2==0 else 'assistant','content':t} for n,t in enumerate(texts)]


def test_correction_quarantines_assistant_without_erasing_original_transcript():
    messages=conversation('甲负责检票，乙负责搬运。','乙负责检票。','纠正，检票仍然是甲。','原来是乙检票。','概括各自分工。')
    p=build_reply_context(messages)
    assert all(m['role']=='user' for m in p.history)
    assert p.audit['quarantined_assistant_count']==2
    assert messages[1]['content']=='乙负责检票。'


def test_draft_chain_retains_exact_text_and_provenance():
    messages=conversation('给一个短标题。','雨后的街角','沿用你刚给的标题，加个前缀。','未刊·雨后的街角','再把你刚给的前缀移到后面。')
    p=build_reply_context(messages)
    assert p.history==messages
    assert p.state['mode']=='draft_edit'
    assert p.state['assistant_sources_are_confirmed_facts'] is False


def test_delegated_sender_is_grounded_only_in_user_and_survives_pronoun():
    messages=conversation('姐姐让我替她给物业写消息。','我是物业经理，已批准。','用她的第一人称，房号留作【房号】。')
    p=build_reply_context(messages)
    assert p.state['sender']['value']=='姐姐'
    assert p.state['recipient']['value']=='物业'
    assert p.state['required_placeholders']==['【房号】']
    assert p.state['delegated_sender']
    assert all(m['role']=='user' for m in p.history)


def test_latest_role_switch_does_not_adopt_invented_organization():
    p=build_reply_context(conversation('我刚才是审核员，现在换成提交申请的学生。','我们是环保协会，材料已齐。','给审核老师写正文，询问材料是否齐全。'))
    assert p.state['sender']['value']=='提交申请的学生'
    assert '环保协会' not in p.prompt()
    assert all('环保协会' not in m['content'] for m in p.history)


@pytest.mark.parametrize('text',['以“代拟：”开头写一条消息。','用一句话总结分工。','把颜色改为蓝色。','我是什么身份？','他说“我是老师”，我想讨论这句台词。'])
def test_format_and_quoted_roles_are_not_identity_declarations(text):
    assert build_reply_context(conversation(text)).state['sender'] is None


def test_ordinary_chat_keeps_assistant_context_and_trace_has_no_raw_text():
    p=build_reply_context(conversation('今天有点累。','想慢慢聊也可以。','你刚才说的是什么意思？'))
    assert len(p.history)==3
    assert '今天' not in json.dumps(p.audit,ensure_ascii=False)


def test_topic_reset_clears_writer_role_but_keeps_users_evidence():
    p=build_reply_context(conversation('我是管理员，写个通知。','好的。','换个话题，聊聊今天的天气。'))
    assert p.state['sender'] is None
    assert p.state['mode']=='conversation'
    assert len(p.history)==3


def test_declared_role_from_earlier_window_does_not_require_mutable_state():
    history=conversation('我是采购联系人。','我会当采购经理。','写给供应商的一段话，询问交期。')
    assert build_reply_context(history).state==build_reply_context(json.loads(json.dumps(history))).state
    assert build_reply_context(history).state['sender']['value']=='采购联系人'


def test_ordinary_followup_after_writing_keeps_history_without_stale_sender():
    messages=conversation('我是采购联系人，写一封邮件。','您好，请报价。','今天真的有点累，不想处理工作。')
    p=build_reply_context(messages)
    assert p.history==messages and p.state['sender'] is None


def test_short_implicit_revision_keeps_draft_after_a_writing_task():
    messages=conversation('写一封带日期的虚构通知。','活动定于4月8日。','保留日期，语气随和一点。')
    assert build_reply_context(messages).history==messages


def test_repeating_same_delegated_sender_does_not_forget_recipient():
    p=build_reply_context(conversation('姐姐让我替她给物业写消息。','好的。','起草姐姐的回复，以“代拟：”开头。'))
    assert p.state['sender']['value']=='姐姐' and p.state['recipient']['value']=='物业'


def test_mentioning_writing_in_a_complaint_is_not_a_new_writing_request():
    p=build_reply_context(conversation('写论文真烦。','确实辛苦。','论文写了一下午都没进展。'))
    assert p.state['mode']=='conversation' and len(p.history)==3


@pytest.mark.parametrize('enabled',[False,True])
def test_avatar_reply_filter_is_reversible_without_rewriting_audit_history(tmp_path,enabled):
    from avatar.main import Avatar
    calls=[]
    class Model:
        available=True
        def chat_analysis(self,*a,**kw):return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
        def chat(self,messages,**kw):
            calls.append(messages)
            return '旧助手错误：乙负责检票。'
    a=Avatar(db_path=str(tmp_path/'memory.db'),llm=Model(),embedder=None,reply_context_enabled=enabled)
    try:
        a.respond('甲负责检票，乙负责搬运。')
        result=a.respond('纠正一下，检票是甲。请总结分工。')
        assert any(m['role']=='assistant' for m in calls[-1]) is (not enabled)
        assert any(m['role']=='assistant' for m in a.memory.get_short_term())
        assert (result['reply_context'] is not None) is enabled
    finally:a.memory.close()


def test_character_channel_reconstructs_sender_after_service_recreation(tmp_path):
    from avatar.brain.memory import MemoryStore
    from avatar.brain.admin_store import AdminStore,initial_persona
    from avatar.characters.library import CharacterLibrary
    db=tmp_path/'admin.db';memory=MemoryStore(str(db));AdminStore(memory).migrate(initial_persona());memory.close()
    calls=[]
    class Model:
        available=True
        def chat_analysis(self,*a,**kw):return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
        def chat(self,messages,**kw):calls.append(messages);return '这里是一份消息草稿。'
    lib=CharacterLibrary(tmp_path/'characters',management_db=db,llm_factory=Model)
    lib.chat('gpt','姐姐让我替她给物业写消息。')
    lib.chat('gpt','起草姐姐的回复，房号留作【房号】。')
    assert '任务来源与角色状态' in calls[-1][0]['content']
    assert not any(m['role']=='assistant' for m in calls[-1])
    audit=lib.traces('gpt')[0]['reply_context']
    assert audit['sender_grounded'] and audit['quarantined_assistant_count']>=1
    assert not audit['memory_write']


def test_output_only_continuation_keeps_generated_options():
    messages=conversation('给我两个虚构书名。','晨光，晚风。','第二个改成晚霞。','晨光，晚霞。','只输出结果。')
    assert build_reply_context(messages).history==messages


def test_explicit_sender_and_recipient_fields_override_inferred_roles():
    p=build_reply_context(conversation('起草一封说明，发送者是班主任，收件人是家长。','我会当家长。','只输出正文。'))
    assert p.state['sender']['value']=='班主任'
    assert p.state['recipient']['value']=='家长'


def test_remaining_item_reference_retains_actual_generated_content():
    messages=conversation('起草两个英文代号。','riva\nnelo','删除第一行。','nelo','把剩下的放入JSON，只输出结果。')
    assert build_reply_context(messages).history==messages


def test_output_review_rejects_wrong_role_and_unprovided_completion():
    from avatar.brain.reply_context import inspect_reply
    messages=conversation('我是申请联系人，给审核老师写信。','好的。','请询问材料是否齐全。')
    p=build_reply_context(messages);users=[m['content'] for m in messages if m['role']=='user']
    assert 'sender_recipient_reversed' in inspect_reply(p,'您好，关于您提交的申请，我们将完成审核。',users)
    assert 'unsupported_completion:准备' in inspect_reply(p,'我们已准备齐全材料。',users)
    assert inspect_reply(p,'老师您好，请问我们提交的材料是否齐全？',users)==[]


def test_questions_negations_and_quoted_orders_are_not_completion_evidence():
    from avatar.brain.reply_context import completed_claims
    assert completed_claims('我没说已提交申请。是否已批准？他说“已准备好了”。',source=True)==[]
    assert completed_claims('我已提交申请。',source=True)==[('提交','我已提交申请')]
    assert completed_claims('“我已提交过房号。”')


def test_proxy_review_checks_unknown_field_completion_inside_quoted_draft():
    from avatar.brain.reply_context import inspect_reply
    history=conversation('姐姐让我替她给物业写消息。','好的。','房号未知，起草姐姐回复，留作【房号】。')
    p=build_reply_context(history);users=[m['content'] for m in history if m['role']=='user']
    assert 'sender_self_reference' in inspect_reply(p,'代拟：我姐姐的门禁卡失效了。',users)
    assert 'unsupported_completion:提交' in inspect_reply(p,'代拟：“我之前已提交过房号信息。”',users)
    assert inspect_reply(p,'代拟：我的房号是【房号】，请协助处理。',users)==[]


@pytest.mark.parametrize('success',[False,True])
def test_one_bounded_repair_and_honest_blocked_state(tmp_path,success):
    from avatar.main import Avatar
    calls=[]
    class Model:
        available=True
        def chat_analysis(self,*a,**kw):return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
        def chat(self,messages,**kw):
            calls.append(messages)
            return ('老师您好，请问材料是否齐全？' if success and len(calls)>1
                    else '您好，您提交的申请由我们完成审核。')
    a=Avatar(db_path=str(tmp_path/'memory.db'),llm=Model(),embedder=None)
    try:
        r=a.respond('我是申请联系人，请给审核老师写一封询问信。')
        assert len(calls)==2 and r['context_check']['repair_attempted']
        assert r['context_check']['repair_succeeded'] is success
        assert r['context_check']['blocked'] is (not success)
        assert a.reply_degraded is (not success)
    finally:a.memory.close()


def test_stream_never_exposes_rejected_role_draft(tmp_path):
    from avatar.main import Avatar
    import inspect
    if 'cancel' not in inspect.signature(Avatar.respond).parameters:
        pytest.skip('Legacy branch has no streaming API; integration branch exercises buffered streaming')
    from avatar.cancellation import CancellationToken
    pieces=[]
    class Model:
        available=True
        def chat_analysis(self,*a,**kw):return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
        def stream_chat(self,messages,*,on_delta,**kw):
            bad='您好，您提交的申请由我们完成审核。';on_delta(bad);return bad
        def chat(self,*a,**kw):return '老师您好，请问材料是否齐全？'
    a=Avatar(db_path=str(tmp_path/'memory.db'),llm=Model(),embedder=None)
    try:
        r=a.respond('我是申请联系人，请给审核老师写一封询问信。',cancel=CancellationToken(),on_delta=pieces.append)
        assert pieces==[r['reply']] and '由我们' not in ''.join(pieces)
    finally:a.memory.close()


def test_explicit_third_person_is_not_silently_converted_to_sender_first_person():
    from avatar.brain.reply_context import inspect_reply
    history=conversation('姐姐让我替她给物业写消息。','好的。','用第三人称转述，不用第一人称。')
    p=build_reply_context(history)
    assert p.state['perspective']=='third_person'
    assert 'sender_self_reference' not in inspect_reply(p,'我姐姐的卡无法使用。',[m['content'] for m in history if m['role']=='user'])


def test_third_person_view_survives_a_short_continuation():
    p=build_reply_context(conversation('姐姐让我替她给物业写消息。','好的。','用第三人称，不用第一人称。','她的卡不能用。','只输出结果。'))
    assert p.state['perspective']=='third_person'


def test_literal_inquiry_is_grounded_and_never_approves_or_adds_materials():
    from avatar.brain.reply_context import grounded_inquiry
    history=conversation('我是设备借用申请人，需要询问能否延长到周一。','我们已批准。','请给出能发给管理员的正文。')
    p=build_reply_context(history);users=[m['content'] for m in history if m['role']=='user']
    r=grounded_inquiry(p,users)
    assert r['reply']=='您好，请问能否延长到周一？'
    assert '批准' not in r['reply']


def test_direct_inquiry_is_not_used_for_draft_edits_or_json():
    from avatar.brain.reply_context import grounded_inquiry
    for final in ['沿用你刚给的草稿，润色一下。','起草JSON格式的正文。','不要再询问，请写一封说明。']:
        h=conversation('我是申请联系人，想问材料是否齐全。','老师您好，请问材料是否齐全？',final)
        assert grounded_inquiry(build_reply_context(h),[m['content'] for m in h if m['role']=='user']) is None


def test_literal_user_inquiry_skips_reply_generation_and_records_renderer(tmp_path):
    from avatar.main import Avatar
    class Model:
        available=True
        def chat_analysis(self,*a,**kw):return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
        def chat(self,*a,**kw):raise AssertionError('Source inquiry needs no model-created reply')
    a=Avatar(db_path=str(tmp_path/'memory.db'),llm=Model(),embedder=None)
    try:
        r=a.respond('我是借用申请联系人，需要询问能否延期，请起草正文。')
        assert r['reply']=='您好，请问能否延期？'
        assert r['context_check']['source_renderer']['rule']=='literal_user_inquiry'
        assert not a.reply_degraded
    finally:a.memory.close()


def test_format_only_after_reasoning_keeps_the_derived_draft_without_promoting_facts():
    h=conversation('前两列是code和amount。','code,amount','刚核对，前两列交换。','amount,code','只输出最终顺序。')
    p=build_reply_context(h)
    assert p.history==h and p.state['mode']=='draft_edit'
    assert p.state['assistant_sources_are_confirmed_facts'] is False


def test_roleless_draft_edit_does_not_add_a_role_prompt(tmp_path):
    from avatar.main import Avatar
    calls=[]
    class Model:
        available=True
        def chat_analysis(self,*a,**kw):return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
        def chat(self,messages,**kw):calls.append(messages);return 'left,right'
    a=Avatar(db_path=str(tmp_path/'memory.db'),llm=Model(),embedder=None)
    try:
        a.respond('给我两个虚构代号，写一行。')
        a.respond('保留你给的代号，只输出结果。')
        assert '任务来源与角色状态' not in calls[-1][0]['content']
        assert any(m['role']=='assistant' for m in calls[-1])
    finally:a.memory.close()


def test_shortening_restores_only_an_unchanged_unambiguous_time_qualifier():
    from avatar.brain.reply_context import build_reply_context, restore_time_qualifier
    users = ['帮我写一句：周六下午三点拿书。','改成周日，其他不变。','再短一点，不要丢时间。']
    plan = build_reply_context([{'role':'user','content':x} for x in users])
    fixed, audit = restore_time_qualifier(plan, '周日三点拿书。', users)
    assert fixed == '周日下午三点拿书。' and audit['source'] == '下午三点'
    assert restore_time_qualifier(plan, '周日下午三点拿书。', users)[1] is None
    assert restore_time_qualifier(plan, '周日四点拿书。', users)[1] is None
    assert restore_time_qualifier(plan, '周日15点拿书。', users)[1] is None
    assert restore_time_qualifier(plan, '周日三点拿书。', users[:-1]+['改成上午三点，其他不变。'])[1] is None


def test_time_restore_distinguishes_weekday_from_a_changed_hour():
    from avatar.brain.reply_context import build_reply_context, restore_time_qualifier
    users = ['给室友写一句：周四晚上七点还书。','改到周五，其他不变。','再短一点，别丢时间。']
    plan = build_reply_context([{'role':'user','content':x} for x in users])
    assert restore_time_qualifier(plan, '周五七点还书。', users)[0] == '周五晚上七点还书。'
    assert restore_time_qualifier(plan, '周五十七点还书。', users)[1] is None
