"""Controlled engineering checks, not evidence that a native planner is correct."""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.request

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.typed_capability_gate import (
    PLAN_RESPONSE_FORMAT, SourceSnapshot, TypedCapabilityGateAvatar, UserSource,
    checked_registry, parse_plan, render_unavailable,
)
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_web_api_v1 import api_v1

DRAFT = '我已经发到群里了。'
QUESTION = '替我发到项目群里。'


def plan(**updates):
    result = dict(route='unavailable_request', actor='assistant', channel='message',
                  source_message_id=1, evidence='发到项目群里')
    result.update(updates)
    return result


def ordinary():
    return dict(route='ordinary', actor='unknown', channel='none', source_message_id=0, evidence='')


def snapshot(text=QUESTION):
    return SourceSnapshot(0, 1, 'session', (UserSource(1, text),), 'current_user', True, False)


class Planner(Recorder):
    def __init__(self, choose=None):
        super().__init__(DRAFT)
        self.choose = choose
        self.plans = []
        self.during_plan = None

    def stream_chat(self, messages, *, response_format=None, **kwargs):
        if response_format is None:
            return super().stream_chat(messages, **kwargs)
        assert response_format == PLAN_RESPONSE_FORMAT and kwargs['on_delta'] is None
        payload = json.loads(messages[-1]['content'])
        self.plans.append(payload)
        if self.during_plan:
            self.during_plan()
        value = self.choose(payload) if self.choose else plan(source_message_id=payload['current_message_id'])
        if isinstance(value, BaseException):
            raise value
        return json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value


def test_schema_matches_preregistered_bytes_structure_and_factory_untouched():
    p = Path(__file__).resolve().parents[1] / 'evals/interaction/cycle-38/action-plan-response-format.json'
    assert PLAN_RESPONSE_FORMAT == json.loads(p.read_text())
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Planner())
        assert bot.final_reply_reviewer is None
        assert bot.respond(QUESTION)['reply'] == DRAFT
        assert not bot.llm.plans


@pytest.mark.parametrize('updates', [
    {'source_message_id': True}, {'source_message_id': '1'}, {'source_message_id': 999},
    {'source_message_id': -1}, {'actor': 'user'}, {'actor': 'system'},
    {'channel': 'none'}, {'channel': 'send_email'}, {'route': 'executed'},
    {'evidence': ''}, {'evidence': '群'}, {'evidence': '不存在的来源'},
    {'evidence': '发到项目群里', 'extra': 'ignored?'},
])
def test_bad_model_plan_rejected(updates):
    with pytest.raises(ValueError):
        parse_plan(json.dumps(plan(**updates)), snapshot())


@pytest.mark.parametrize('raw', ['[]', 'null', '{}', '```json\n{}\n```', 'x', '{"route":"ordinary","route":"unavailable_request"}', 'x'*8193])
def test_invalid_json_or_duplicate_keys_rejected(raw):
    with pytest.raises(ValueError):
        parse_plan(raw, snapshot())


@pytest.mark.parametrize('text', ['改写“发到项目群里”这句话。', '台词："发到项目群里"', '引号没闭合“发到项目群里'])
def test_quoted_citation_cannot_authorize_real_action(text):
    with pytest.raises(ValueError, match='quoted_action'):
        parse_plan(json.dumps(plan()), snapshot(text))


@pytest.mark.parametrize('scope,allowed', [('fictional_character', False), ('unverified', False), ('current_user', False)])
def test_runtime_scope_overrules_model_plan(scope, allowed):
    with pytest.raises(ValueError, match='restricted'):
        parse_plan(json.dumps(plan()), replace(snapshot(), scope=scope, tools_allowed=allowed))


def test_new_request_cannot_replay_old_request_but_status_can_cite_it():
    s = replace(snapshot(), current_id=3, sources=(UserSource(1, QUESTION), UserSource(3, '收到回复了吗？')))
    with pytest.raises(ValueError, match='current_source'):
        parse_plan(json.dumps(plan()), s)
    accepted = parse_plan(json.dumps(plan(route='unavailable_status')), s)
    assert '没有替你执行' in render_unavailable(accepted)


@pytest.mark.parametrize('names', [{'send_email'}, {'place_call'}, {'send_group'}, set()])
def test_changed_actual_registry_requires_revalidation(names):
    with pytest.raises(ValueError, match='inventory changed'):
        checked_registry(SimpleNamespace(names=names))


def test_buffered_output_source_dependencies_no_action_or_receipt_writes():
    model = Planner()
    with closing(MemoryStore(':memory:')) as memory:
        bot = TypedCapabilityGateAvatar(memory=memory, llm=model, summary_enabled=False)
        pieces = []
        result = bot.respond(QUESTION, cancel=CancellationToken(), on_delta=pieces.append)
        assert result['generation_mode'] == 'reviewed_response'
        assert result['reply'] == ''.join(pieces) != DRAFT
        assert '无法替你执行' in result['reply']
        review = result['response_review']
        assert review['original_draft'] == DRAFT and review['fixed_renderer_used']
        assert review['native_model_improvement_claim'] is False
        assert len(model.native) == len(model.plans) == 1
        assert len(model.analysis) == 1 and not result['tool_calls'] and not result['action_receipts']['items']
        assert memory._conn.execute('SELECT count(*) FROM memory_reminders').fetchone()[0] == 0
        assert memory._conn.execute('SELECT count(*) FROM memory_action_receipts').fetchone()[0] == 0
        stored = memory._conn.execute('SELECT content FROM memory_messages WHERE id=?', (result['conversation']['assistant_message_id'],)).fetchone()[0]
        assert stored == result['reply']
        assert not memory._conn.in_transaction
        before = memory._conn.total_changes
        with memory.transaction():
            bot._snapshot(QUESTION)
            assert memory._conn.in_transaction and memory._conn.total_changes == before


@pytest.mark.parametrize('choice', [lambda p: ordinary(), lambda p: {}, lambda p: 'invalid', lambda p: RuntimeError('controlled-plan-failure')])
def test_ordinary_and_rejected_plans_keep_original_and_disclose_no_guard_claim(choice):
    model = Planner(choice)
    with closing(MemoryStore(':memory:')) as memory:
        bot = TypedCapabilityGateAvatar(memory=memory, llm=model)
        result = bot.respond(QUESTION)
        assert result['reply'] == DRAFT and result['generation_mode'] == 'llm'
        review = result['response_review']
        assert not review['fixed_renderer_used']
        assert bool(review['plan_error']) == (review['plan'] is None)


@pytest.mark.parametrize('mutation', ['cancel', 'revision', 'content', 'session', 'role'])
def test_change_during_planning_never_publishes_or_commits_assistant(mutation):
    model = Planner()
    with closing(MemoryStore(':memory:')) as memory:
        bot = TypedCapabilityGateAvatar(memory=memory, llm=model)
        token, pieces = CancellationToken(), []
        def changed():
            assert not memory._conn.in_transaction
            if mutation == 'cancel':
                token.cancel()
            elif mutation == 'revision':
                memory._conn.execute('UPDATE memory_context_revision SET revision=revision+1')
            else:
                field = {'content': 'content', 'session': 'session_id', 'role': 'role'}[mutation]
                memory._conn.execute('UPDATE memory_messages SET '+field+'=? WHERE id=?', ('changed', bot._current_message_id))
            memory._conn.commit()
        model.during_plan = changed
        with pytest.raises(Cancelled):
            bot.respond(QUESTION, cancel=token, on_delta=pieces.append)
        assert not pieces
        assert memory._conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == 0


def test_local_reminder_and_role_rules_do_not_invoke_planner_or_replay():
    model = Planner()
    with closing(MemoryStore(':memory:')) as memory:
        bot = TypedCapabilityGateAvatar(memory=memory, llm=model)
        result = bot.respond('提醒我明天上午九点，整理记录。')
        assert result['reminder'] and len(result['action_receipts']['items']) == 1
        bot.respond('我现在扮演小说里的角色。')
        blocked = bot.respond('提醒我明天下午三点，追赶星舰。')
        bot.respond('回到现实。')
        assert blocked['speaker_tool_blocked'] and len(bot.reminders.list()) == 1
        assert not model.plans


def test_real_http_sse_buffers_candidate_with_no_external_execution(api_v1, monkeypatch):
    import avatar.main as module
    request, server = api_v1
    model = Planner()
    class Candidate(TypedCapabilityGateAvatar):
        def __init__(self, *args, **kwargs):
            kwargs['llm'] = model
            super().__init__(*args, **kwargs)
    monkeypatch.setattr(module, 'Avatar', Candidate)
    ident = 'typed-gate-controlled-http-0001'
    assert request('/api/v1/turns', {'request_id': ident, 'text': QUESTION})[0] == 202
    req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1/turns/{ident}/events', headers={'X-Avatar-Token': server.token})
    with urllib.request.urlopen(req, timeout=10) as response:
        raw = response.read().decode()
    frames = [json.loads(line[6:]) for block in raw.split('\n\n') if 'event: result\n' in block
              for line in block.splitlines() if line.startswith('data: ')]
    assert len(frames) == 1
    result = frames[0]
    assert result['generation_mode'] == 'reviewed_response' and result['reply'] != DRAFT
    assert result['response_review']['original_draft'] == DRAFT and result['response_review']['fixed_renderer_used']
    assert not result['tool_calls'] and not result['action_receipts']['items']
    text_frames = [json.loads(line[6:])['text'] for block in raw.split('\n\n') if 'event: text\n' in block
                   for line in block.splitlines() if line.startswith('data: ')]
    assert ''.join(text_frames) == result['reply']
