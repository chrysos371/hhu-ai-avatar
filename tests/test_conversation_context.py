"""Completed-pair source validation, privacy and scope fences for Web recovery."""
from contextlib import contextmanager,closing
import json
import pytest
from avatar.brain.memory import MemoryStore
from avatar.brain.conversations import ConversationStore
from avatar.brain.speaker_context import SpeakerContextStore
from avatar.brain.conversation_context import ConversationContextStore
from avatar.cancellation import Cancelled


@pytest.fixture
def memory(tmp_path):
    with closing(MemoryStore(str(tmp_path/'context.db'))) as value:yield value


def completed(memory,text='场景A。',reply='收到场景A。',session='old-web',mode='llm',extra_sources=()):
    with memory.transaction():
        uid=memory.add_message('user',text,session)
        scope=SpeakerContextStore(memory).observe(text,memory.context_revision,uid)
        aid=memory.add_message('assistant',reply,session,context_ids=[],source_message_ids=[uid,*extra_sources])
        result={'reply':reply,'generation_mode':mode,'speaker_attribution':{'scope':scope.scope},
                'conversation':{'revision':memory.context_revision,'session_id':session,'user_message_id':uid,'assistant_message_id':aid}}
        ConversationStore(memory).record_result(result)
    return uid,aid,result


@contextmanager
def current(memory,text='请继续场景。'):
    with memory.transaction():
        uid=memory.add_message('user',text,'new-web')
        scope=SpeakerContextStore(memory).observe(text,memory.context_revision,uid)
        yield {'current_user_id':uid,'scope':scope.scope,'expected_revision':memory.context_revision}


def read(memory,options,**kwargs):return ConversationContextStore(memory).read(**options,**kwargs)
def ids(window):return window.source_ids


def test_complete_cross_session_sources_are_ordered_and_pure_read(memory):
    a=completed(memory);b=completed(memory,'场景B。','收到场景B。')
    with current(memory) as options:
        changes=memory._conn.total_changes;window=read(memory,options)
        assert ids(window)==(a[0],a[1],b[0],b[1]) and window.revision==memory.context_revision
        assert [(m.role,m.content) for m in window.messages]==[('user','场景A。'),('assistant','收到场景A。'),('user','场景B。'),('assistant','收到场景B。')]
        assert memory._conn.total_changes==changes and memory.get_short_term()==[]


@pytest.mark.parametrize('limit,count',[(0,0),(1,0),(2,2),(3,2),(4,4)])
def test_window_bound_keeps_complete_pairs_and_never_includes_current_source(memory,limit,count):
    completed(memory);b=completed(memory,'场景B。','收到B。')
    with current(memory) as options:
        window=read(memory,options,limit_messages=limit)
        assert len(window.messages)==count and options['current_user_id'] not in ids(window)
        if count==2:assert ids(window)==b[:2]


def test_read_requires_source_transaction_and_current_user_tail(memory):
    a=completed(memory)
    with pytest.raises(RuntimeError):ConversationContextStore(memory).read(current_user_id=a[0],scope='current_user',expected_revision=0)
    with memory.transaction():
        with pytest.raises(ValueError):ConversationContextStore(memory).read(current_user_id=a[0],scope='current_user',expected_revision=0)


def test_privacy_revision_drops_old_history_but_accepts_later_new_pair(memory):
    uid,aid,_=completed(memory,'私有标记A。','私有回复A。')
    fragment=memory.remember('私有标记A。',source_message_id=uid);memory.forget(fragment)
    b=completed(memory,'当前新场景。','新回复。')
    with current(memory) as options:
        assert ids(read(memory,options))==b[:2]
        with pytest.raises(Cancelled):read(memory,dict(options,expected_revision=options['expected_revision']-1))


@pytest.mark.parametrize('change',['json','duplicate_key','reply','session','user_id_bool','assistant_id','revision','scope','mode'])
def test_corrupt_or_wrong_bound_result_is_not_recovered(memory,change):
    uid,aid,result=completed(memory)
    if change=='json':body='{invalid'
    elif change=='duplicate_key':body='{"reply":"contradiction",'+json.dumps(result,ensure_ascii=False)[1:]
    else:
        if change=='reply':result['reply']='未存储的回复'
        elif change=='session':result['conversation']['session_id']='other-session'
        elif change=='user_id_bool':result['conversation']['user_message_id']=True
        elif change=='assistant_id':result['conversation']['assistant_message_id']=aid+100
        elif change=='revision':result['conversation']['revision']=10
        elif change=='scope':result['speaker_attribution']['scope']='fictional_character'
        else:result['generation_mode']='rules_service_error'
        body=json.dumps(result,ensure_ascii=False)
    memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?',(body,aid));memory._conn.commit()
    with current(memory) as options:assert read(memory,options).messages==()


def test_cancelled_orphan_gap_stops_older_history_and_new_suffix_can_recover(memory):
    completed(memory)
    with memory.transaction():
        orphan=memory.add_message('user','这条请求被取消。','old-web')
        SpeakerContextStore(memory).observe('这条请求被取消。',memory.context_revision,orphan)
    b=completed(memory,'取消后的新场景。','新场景已收到。')
    with current(memory) as options:assert ids(read(memory,options))==b[:2]


def test_untracked_writer_does_not_authorize_model_history(memory):
    completed(memory);memory.add_message('user','未知写入来源。','legacy-cli')
    with current(memory) as options:
        assert options['scope']=='unverified' and read(memory,options).messages==()


def test_scope_control_pairs_are_included_as_fences_without_other_scope_history(memory):
    real=completed(memory,'真人场景R。','真人回复。')
    entry=completed(memory,'我来扮演一个虚构角色。','角色确认。',mode='rules_speaker_control')
    fiction=completed(memory,'角色场景F。','角色回复。')
    with current(memory,'角色继续。') as options:
        assert options['scope']=='fictional_character'
        assert ids(read(memory,options))==(*entry[:2],*fiction[:2])
    exit_pair=completed(memory,'回到现实。','真人确认。',mode='rules_speaker_control')
    after=completed(memory,'新的真人场景。','新的真人回复。')
    with current(memory) as options:
        assert options['scope']=='current_user' and ids(read(memory,options))==(*exit_pair[:2],*after[:2])


def test_no_missing_or_redacted_dependency_can_become_history(memory):
    uid,aid,_=completed(memory)
    memory._conn.execute('INSERT INTO memory_response_context VALUES (?,?,?)',(aid,'message',aid+100));memory._conn.commit()
    with current(memory) as options:assert read(memory,options).messages==()


def test_valid_historical_superseded_fragment_is_not_treated_as_erased(memory):
    uid,aid,_=completed(memory)
    fragment=memory.remember('历史偏好。',source_message_id=uid)
    memory._conn.execute('UPDATE memory_fragments SET status=? WHERE id=?',('superseded',fragment))
    memory._conn.execute('INSERT INTO memory_response_context VALUES (?,?,?)',(aid,'fragment',fragment));memory._conn.commit()
    with current(memory) as options:assert ids(read(memory,options))==(uid,aid)


def test_metadata_without_own_user_dependency_cannot_be_trusted(memory):
    uid,aid,_=completed(memory)
    memory._conn.execute('DELETE FROM memory_response_context WHERE message_id=?',(aid,));memory._conn.commit()
    with current(memory) as options:assert read(memory,options).messages==()


def test_redacted_ancestor_assistant_invalidates_derived_pair_without_skipping_it(memory):
    a=completed(memory);b=completed(memory,'后续场景。','后续回复。',extra_sources=[a[1]])
    memory._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?",(a[1],));memory._conn.commit()
    with current(memory) as options:assert read(memory,options).messages==()


def test_missing_fragment_or_self_dependency_is_not_verified_history(memory):
    uid,aid,_=completed(memory)
    memory._conn.execute('INSERT INTO memory_response_context VALUES (?,?,?)',(aid,'message',aid));memory._conn.commit()
    with current(memory) as options:assert read(memory,options).messages==()


def test_missing_fragment_dependency_is_not_verified_history(memory):
    uid,aid,_=completed(memory)
    memory._conn.execute('INSERT INTO memory_response_context VALUES (?,?,?)',(aid,'fragment',99999));memory._conn.commit()
    with current(memory) as options:assert read(memory,options).messages==()


@pytest.mark.parametrize('limit',[True,-1,201])
def test_unbounded_or_boolean_history_limits_rejected(memory,limit):
    completed(memory)
    with current(memory) as options:
        with pytest.raises(ValueError):read(memory,options,limit_messages=limit)


def test_unverified_control_journal_cannot_restore_otherwise_valid_results(memory):
    completed(memory)
    with current(memory) as options:
        memory._conn.execute('UPDATE memory_web_speaker_state SET cursor=cursor-1 WHERE id=1')
        assert read(memory,options).messages==()


@pytest.mark.parametrize('bad_content',[b'broken-content',''])
def test_malformed_old_content_outside_speaker_context_stops_older_pairs(memory,bad_content):
    first=completed(memory)
    remaining=[completed(memory,f'合法场景{i}。',f'合法回复{i}。') for i in range(3)]
    memory._conn.execute('UPDATE memory_messages SET content=? WHERE id=?',(bad_content,first[0]));memory._conn.commit()
    with current(memory) as options:
        assert options['scope']=='current_user'
        assert ids(read(memory,options))==tuple(value for pair in remaining for value in pair[:2])


def test_derived_reply_with_nontext_source_cannot_be_restored_even_outside_window(memory):
    first=completed(memory)
    for i in range(3):completed(memory,f'中间场景{i}。',f'中间回复{i}。')
    latest=completed(memory,'最新场景。','引用旧源的回复。',extra_sources=[first[0]])
    memory._conn.execute('UPDATE memory_messages SET content=? WHERE id=?',(b'broken-source',first[0]));memory._conn.commit()
    with current(memory) as options:assert read(memory,options,limit_messages=2).messages==()


@pytest.mark.parametrize('bad_content',[b'broken-fragment',''])
def test_broken_fragment_dependency_is_not_validated_merely_by_existence(memory,bad_content):
    uid,aid,_=completed(memory)
    fragment=memory.remember('有效的历史事实。',source_message_id=uid)
    memory._conn.execute('INSERT INTO memory_response_context VALUES (?,?,?)',(aid,'fragment',fragment))
    memory._conn.execute('UPDATE memory_fragments SET content=? WHERE id=?',(bad_content,fragment));memory._conn.commit()
    with current(memory) as options:assert read(memory,options).messages==()
