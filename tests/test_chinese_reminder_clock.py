"""Bounded Chinese clock support without changing task text or fabricating writes."""
from contextlib import closing
from datetime import datetime
import pytest
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import CHINA, ReminderStore, parse_reminder
from test_web_api_v1 import api_v1
NOW = datetime(2026, 11, 1, 10, tzinfo=CHINA).timestamp()


@pytest.mark.parametrize('clock,hour,minute', [
    ('上午九点',9,0),('下午两点半',14,30),('二十三点五十九分',23,59),
    ('零点零五分',0,5),('〇九点',9,0),('十点十分',10,10),('十一点一分',11,1),
    ('中午十二点',12,0),('晚上八点三十五分',20,35),('九时二分',9,2),
    ('上午九点15分',9,15),('上午9点十五分',9,15),
])
def test_common_clock_fields_are_exact_and_digit_compatible(clock, hour, minute):
    parsed = parse_reminder('提醒我明天'+clock+'核对设备清单。', now=NOW)
    assert parsed == {'title':'核对设备清单','due_at':datetime(2026,11,2,hour,minute,tzinfo=CHINA).timestamp()}


@pytest.mark.parametrize('title',['三方会议','十项检查','五分钟呼吸练习','整理二十页材料'])
def test_chinese_title_prefix_is_never_swallowed_as_an_unmarked_minute(title):
    value = parse_reminder('提醒我明天九点'+title, now=NOW)
    assert value['title'] == title
    assert value['due_at'] == datetime(2026,11,2,9,0,tzinfo=CHINA).timestamp()


@pytest.mark.parametrize('body',[
    '二十四点开会','上午十三点开会','九点六十分开会','九九点开会','二三点开会','两十点开会',
    '一2点开会','九点二三分开会','九点半','九点十五分','九点','九点和后天十点开会',
])
def test_out_of_range_noncanonical_and_missing_tasks_are_rejected(body):
    with pytest.raises(ValueError):
        parse_reminder('提醒我明天'+body, now=NOW)


@pytest.mark.parametrize('body',['九点九十九分开会','九九点开会','九点十五分'])
def test_invalid_clock_never_creates_a_business_row(tmp_path, body):
    with closing(MemoryStore(str(tmp_path/'owned.db'))) as memory:
        store=ReminderStore(memory)
        with pytest.raises(ValueError):store.create('提醒我明天'+body,now=NOW)
        assert store.list()==[]


@pytest.mark.parametrize('prefix',['假如提醒我','他说“提醒我','不要提醒我'])
def test_new_clock_spellings_do_not_broaden_explicit_instruction_authority(prefix):
    assert parse_reminder(prefix+'明天上午九点开会', now=NOW) is None


def test_actual_http_chinese_clock_persists_business_and_source_bound_receipt(api_v1):
    request,server=api_v1
    code,body=request('/api/v1/chat',{'text':'提醒我明天上午九点核对设备清单。'})
    result=body['data'];assert code==200 and result['reminder_error'] is None
    assert result['reminder']['title']=='核对设备清单' and result['generation_mode']=='rules'
    assert '09:00' in result['reply'] and '程序运行并轮询' in result['reply']
    receipt=result['action_receipts']['items'];assert len(receipt)==1
    assert receipt[0]['action']=='reminder.created' and receipt[0]['source_message_id']==result['conversation']['user_message_id']
    with closing(MemoryStore(server.db_path)) as memory:
        rows=memory._conn.execute('SELECT * FROM memory_reminders').fetchall()
        assert len(rows)==1 and rows[0]['id']==receipt[0]['reminder_id']


def test_actual_http_invalid_clock_has_neither_business_nor_receipt_success(api_v1):
    request,server=api_v1
    result=request('/api/v1/chat',{'text':'提醒我明天九点九十九分开会。'})[1]['data']
    assert result['reminder'] is None and result['reminder_error'] and not result['action_receipts']['items']
    assert '已设置提醒' not in result['reply']
    with closing(MemoryStore(server.db_path)) as memory:
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_reminders').fetchone()[0]==0
