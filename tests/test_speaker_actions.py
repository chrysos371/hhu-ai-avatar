"""Character speech must not silently authorize real persistent actions."""
from avatar.main import Avatar
from avatar.brain.reminders import ReminderStore

class Offline: available=False

def test_character_cannot_create_real_reminder():
    bot=Avatar(db_path=':memory:',llm=Offline())
    try:
        bot.respond('我来扮演小说角色。')
        result=bot.respond('提醒我明天9点带伞。')
        assert bot.reminders.list()==[]
        assert result['reminder'] is None
        assert '退出角色' in result['reply']
    finally:bot.memory.close()


def test_character_cannot_cancel_real_reminder():
    bot=Avatar(db_path=':memory:',llm=Offline())
    try:
        reminder=bot.reminders.create('提醒我明天9点带伞。')
        original_status=bot.reminders.list()[0]['status']
        bot.respond('我来扮演小说角色。')
        bot.respond(f'取消提醒{reminder["id"]}')
        assert bot.reminders.list()[0]['status']==original_status
    finally:bot.memory.close()


def test_character_tool_flag_does_not_dispatch_web_agent():
    class Agent:
        calls=0
        def run(self,*args,**kwargs):
            self.calls+=1
            return {'reply':'已执行工具。','sources':[],'tool_calls':[]}
    agent=Agent();bot=Avatar(db_path=':memory:',llm=Offline(),web_agent=agent)
    try:
        bot.respond('我来扮演小说角色。')
        result=bot.respond('请帮我设置明天的提醒。',use_web=True)
        assert agent.calls==0
        assert result['tool_calls']==[]
        assert '退出角色' in result['reply']
    finally:bot.memory.close()


def test_real_user_can_resume_actions_after_explicit_exit():
    bot=Avatar(db_path=':memory:',llm=Offline())
    try:
        bot.respond('我来扮演小说角色。')
        bot.respond('回到现实。')
        result=bot.respond('提醒我明天9点带伞。')
        assert result['reminder'] is not None
        assert len(bot.reminders.list())==1
    finally:bot.memory.close()


def test_character_reminder_before_exit_in_same_message_is_not_real_authority():
    bot=Avatar(db_path=':memory:',llm=Offline())
    try:
        bot.respond('我来扮演小说角色。')
        result=bot.respond('提醒我明天9点带伞。回到现实。')
        assert bot.reminders.list()==[]
        assert result['speaker_attribution']['scope']=='current_user'
        assert result['speaker_tool_blocked'] is True
    finally:bot.memory.close()


def test_mixed_scope_tool_request_requires_a_separate_real_request():
    class Agent:
        calls=0
        def run(self,*args,**kwargs):
            self.calls+=1
            return {'reply':'执行了工具。','sources':[],'tool_calls':[]}
    agent=Agent();bot=Avatar(db_path=':memory:',llm=Offline(),web_agent=agent)
    try:
        bot.respond('我来扮演小说角色。')
        bot.respond('请帮我设置提醒。回到现实。',use_web=True)
        assert agent.calls==0
        bot.respond('请搜索明天的天气。',use_web=True)
        assert agent.calls==1
    finally:bot.memory.close()
