import pytest

from avatar.brain.tasks import TaskTracker


def test_clause_scoped_delete_and_keep_then_reinstate():
    tracker = TaskTracker()
    tracker.update('给老师写一封邮件，保留【姓名】和【课程】。')
    tracker.update('删掉【姓名】，保留【课程】。')
    assert tracker.current.required_literals == ['【课程】']
    assert tracker.current.forbidden_literals == ['【姓名】']
    assert tracker.inspect('【姓名】老师好。') == ['missing_literal:【课程】', 'forbidden_literal:【姓名】']
    tracker.update('再保留【姓名】，删除【课程】。')
    assert tracker.current.required_literals == ['【姓名】']
    assert tracker.current.forbidden_literals == ['【课程】']


def test_operations_without_comma_and_suffix_operation():
    t = TaskTracker()
    t.update('写一条消息，【编号】请保留。')
    assert t.current.required_literals == ['【编号】']
    t.update('删掉【编号】并保留【姓名】。')
    assert t.current.required_literals == ['【姓名】']
    assert t.current.forbidden_literals == ['【编号】']


def test_pronoun_revision_preserves_known_actor():
    t = TaskTracker()
    t.update('室友让我替他给物业写消息，保留【房号】。')
    t.update('润色这条消息，用他的第一人称。')
    assert t.current.perspective == '室友'


def test_explicit_placeholder_left_for_unknown_value_is_required():
    t = TaskTracker()
    t.update('起草姐姐的回复，房号留作【房号】，别替她编一个。')
    assert t.current.required_literals == ['【房号】']
    assert t.inspect('物业您好，请帮忙处理门禁卡。') == ['missing_literal:【房号】']


@pytest.mark.parametrize('text', ['写一条取消订单的消息。', '帮我写一封申请，说明取消报名。'])
def test_cancellation_as_deliverable_is_not_cancel_command(text):
    tracker = TaskTracker()
    tracker.update(text)
    assert tracker.current is not None


@pytest.mark.parametrize('text', ['取消。', '取消这个任务。', '不写了。', '先不写', '换个话题'])
def test_explicit_cancel_clears_contract(text):
    tracker = TaskTracker()
    tracker.update('写一条通知，保留【地点】。')
    tracker.update(text)
    assert tracker.current is None


@pytest.mark.parametrize('text', ['我只想倾诉。', '不要给我建议。', '听我说就好。'])
def test_listening_request_clears_previous_writing_contract(text):
    tracker = TaskTracker()
    tracker.update('写一条通知，保留【地点】。')
    tracker.update(text)
    assert tracker.current is None


@pytest.mark.parametrize('text', [
    '姐姐让我替她给物业写消息，她的门禁卡失效了。',
    '起草姐姐的回复，给物业，保留【房号】。',
])
def test_explicit_delegated_role_and_recipient(text):
    tracker = TaskTracker()
    tracker.update(text)
    assert tracker.current.perspective == '姐姐'
    assert tracker.current.recipient == '物业'
