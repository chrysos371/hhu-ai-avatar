from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.receipt_capability_prompt import ReceiptCapabilityPromptAvatar
from avatar.lab.request_scope_capability_prompt import CurrentRequestCapabilityPromptAvatar
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('text,reply', [
    ('请原样回复朋友：“好的，我会自己发送。”只要正文。', '好的，我会自己发送。'),
    ('写一句小说台词：“需要我帮你提醒他一下吗？”', '“需要我帮你提醒他一下吗？”'),
    ('写一条周五交材料的消息，不补充谁必须提交。', '关于周五交材料一事，请您知悉。'),
])
def test_no_postprocessing_extra_model_calls_or_sql_actions(text, reply):
    engine = Recorder(reply)
    with closing(MemoryStore(':memory:')) as memory:
        bot = CurrentRequestCapabilityPromptAvatar(memory=memory, llm=engine)
        pieces = []
        result = bot.respond(text, on_delta=pieces.append)
        assert ''.join(pieces) == result['reply'] == memory.get_short_term()[-1]['content'] == reply
        assert len(engine.native) == len(engine.analysis) == 1
        assert not result['tool_calls'] and not result['action_receipts']['items']
        prompt = engine.native[-1][0]['content']
        assert prompt.count('可信元数据如下：\n') == 1
        data = json.loads(prompt.rsplit('可信元数据如下：\n', 1)[1])
        assert data['capability_evidence_version'] == 2 and data['response_contract_version'] == 4
        actual_user_id = memory._conn.execute("SELECT id FROM memory_messages WHERE role='user' ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert data['current_user_source']['message_id'] == actual_user_id == bot._current_message_id
        assert data['local_execution_evidence']['items'] == []
        assert bot.final_reply_reviewer is None


def test_inherited_real_receipts_remain_read_only_and_same_session():
    engine = Recorder('普通回复。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = CurrentRequestCapabilityPromptAvatar(memory=memory, llm=engine)
        created = bot.respond('提醒我明天下午3点去资料室')
        bot.respond('这个本地提醒的条件是什么？')
        conn = memory._conn
        before = conn.total_changes
        with memory.transaction():
            data = bot._source_capability_evidence('这个本地提醒的条件是什么？')
            assert conn.in_transaction and conn.total_changes == before
        assert data['response_contract_version'] == 4
        assert data['local_execution_evidence']['items'][0]['id'] == created['action_receipts']['items'][0]['id']
        assert not data['local_execution_evidence']['current_reminder_state_verified']


def test_independent_forget_after_compilation_prevents_reply(tmp_path, monkeypatch):
    engine = Recorder('must not dispatch')
    path = str(tmp_path / 'owned.db')
    with closing(MemoryStore(path)) as memory:
        fragment = memory.remember_user('名字', '请求范围来源实验名')
        bot = CurrentRequestCapabilityPromptAvatar(memory=memory, llm=engine)
        original = bot._system_prompt
        def changed(decision, text):
            prompt = original(decision, text)
            with closing(MemoryStore(path)) as writer:
                writer.forget(fragment)
            return prompt
        monkeypatch.setattr(bot, '_system_prompt', changed)
        with pytest.raises(Cancelled):
            bot.respond('我的名字是请求范围来源实验名。', cancel=CancellationToken())
        assert not engine.native
        assert not memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()


@pytest.mark.parametrize('factory,version', [(Avatar, None), (ReceiptCapabilityPromptAvatar, 3)])
def test_default_and_previous_candidate_do_not_install_v4(factory, version):
    engine = Recorder('普通回复。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = factory(memory=memory, llm=engine)
        bot.respond('聊聊今天。')
        prompt = engine.native[-1][0]['content']
        if version is None:
            assert 'response_contract_version' not in prompt
        else:
            data = json.loads(prompt.rsplit('可信元数据如下：\n', 1)[1])
            assert data['response_contract_version'] == version
        assert '当前请求范围与草稿忠实性' not in prompt


def test_v4_freeze_must_bind_its_candidate_protocols(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'scripts'))
    import evaluate_capability_pair as audit
    candidate = 'lab_source_capability_v4'
    names = audit.required_sources(candidate)
    frozen = {'candidate': candidate, 'execution_authorized': True, 'allowed_partition': 'development',
              'prospective_execution_authorized': False,
              'sha256': {name: sha256((root / name).read_bytes()).hexdigest() for name in names}}
    path = tmp_path / 'freeze.json'
    path.write_text(json.dumps(frozen))
    assert audit.verify_freeze(path, 'development', candidate) == frozen
    with pytest.raises(ValueError):
        audit.verify_freeze(path, 'prospective', candidate)
    del frozen['sha256']['evals/interaction/cycle-23/source-capability-candidate-v4.json']
    path.write_text(json.dumps(frozen))
    with pytest.raises(ValueError):
        audit.verify_freeze(path, 'development', candidate)
