import json
import pytest
from avatar.main import Avatar
from avatar.brain.memory import MemoryStore

def proven(kind, content, evidence, **changes):
    fact = dict(type=kind, content=content, evidence=evidence, subject='self',
                modality='asserted', temporal='current')
    fact.update(changes)
    return fact


class StubLLM:
    available = True
    def __init__(self, responses):
        self.responses = iter(responses)
    def chat(self, *args, **kwargs):
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value

@pytest.fixture
def make_avatar():
    avatars = []
    def make(responses=None):
        llm = StubLLM(responses) if responses is not None else StubLLM([])
        if responses is None:
            llm.available = False
        ava = Avatar(db_path=':memory:', llm=llm)
        avatars.append(ava)
        return ava
    yield make
    for ava in avatars:
        ava.memory.close()

def test_rule_identity_is_not_name(make_avatar):
    ava = make_avatar()
    ava.respond('我是大学生')
    assert '名字' not in ava.memory.get_user_profile()


def test_minimal_step_request_has_focused_format_without_changing_other_requests(make_avatar):
    ava = make_avatar()
    text = '给我一个最小步骤。'
    prompt = ava._system_prompt(ava.emotion.decide(text), text)
    assert '严格只写两行' in prompt and '完成标志' in prompt
    assert '严格只写两行' not in ava._system_prompt(ava.emotion.decide('我想倾诉。'), '我想倾诉。')


def test_reminder_commands_and_close_in_real_pipeline(make_avatar):
    ava = make_avatar()
    result = ava.respond('提醒我2099年12月1日下午3点答辩')
    assert result['reminder']['title'] == '答辩'
    assert len(ava.reminders.list()) == 1
    assert '提醒' in result['reply']
    assert ava.respond('晚安')['strategy'] == 'close'
    assert '？' not in ava.respond('晚安')['reply']
    assert ava.respond('提醒我明天答辩')['reminder_error']
    assert len(ava.reminders.list()) == 1
    cancelled = ava.respond('请取消提醒编号1。')
    assert '已取消提醒 #1' in cancelled['reply']
    assert ava.reminders.list()[0]['status'] == 'cancelled'


def test_feedback_command_and_recalled_ids(make_avatar):
    ava = make_avatar()
    fid = ava.memory.remember('校内游泳池')
    assert ava.handle_memory_command(f'/badhit {fid}') == {'feedback': fid}
    assert ava.memory.inspect(fid)['bad_hits'] == 1
    # Retrieval happens even in offline mode so the UI can display actual candidates.
    result = ava.respond('游泳')
    assert fid in result['recalled_ids']
    assert .5 <= result['energy'] <= 1


def test_web_result_never_becomes_user_profile(make_avatar):
    ava = make_avatar()
    class Gateway:
        def run(self, text, llm):
            assert text == '/search MCP官方文档'
            return {'reply': '网页写着：我叫网页假名，我喜欢诈骗。',
                    'sources': [{'title': '文档', 'url': 'https://example.com/'}], 'tool_calls': [{'tool': 'web_search', 'status': 'ok'}]}
    ava.web_agent = Gateway()
    result = ava.handle_memory_command('/search MCP官方文档')
    assert result['sources'][0]['url'] == 'https://example.com/'
    assert ava.memory.get_user_profile() == {}
    assert ava.list_memories() == []

def test_rule_preserves_dislike(make_avatar):
    ava = make_avatar()
    ava.respond('我讨厌香菜')
    assert '讨厌' in ava.memory.get_user_profile()['偏好']

@pytest.mark.parametrize('text', ['假如我叫小明', '我叫小明吗？', '如果我喜欢篮球'])
def test_rule_does_not_store_uncertain_or_negated_claims(make_avatar, text):
    ava = make_avatar()
    ava.respond(text)
    assert ava.memory.get_user_profile() == {}

def test_valid_analysis_and_reply(make_avatar):
    raw = json.dumps({'emotion': {'valence': 0.4, 'arousal': -0.2}, 'facts': [proven('名字', '小明', '我叫小明')]})
    ava = make_avatar([raw, '你好，小明'])
    result = ava.respond('我叫小明')
    assert result['reply'] == '你好，小明'
    assert result['user_valence'] == 0.4
    assert ava.memory.get_user_profile()['名字'] == '小明'

def test_audio_entrypoint_transcribes_and_returns_lipsync_frames(make_avatar, monkeypatch):
    from types import SimpleNamespace
    import avatar.main as main_module
    ava = make_avatar()
    class ASR:
        def transcribe(self, path):
            assert path == 'input.wav'
            return '你好'
    class TTS:
        def synthesize(self, text, path, rate, pitch):
            assert text and path == 'reply.mp3'
            return path
    class LipSync:
        def analyze(self, samples, sr):
            assert samples == 'decoded' and sr == 24000
            return [SimpleNamespace(time=0.0, mouth_open=.4, vowel='a', energy=.8)]
    ava.asr, ava.tts, ava.lipsync = ASR(), TTS(), LipSync()
    monkeypatch.setattr(main_module, 'load_audio', lambda path: ('decoded', 24000))
    result = ava.respond_audio('input.wav', tts_path='reply.mp3')
    assert result['transcript'] == '你好'
    assert result['audio_path'] == 'reply.mp3'
    assert result['lip_sync_frames'] == [
        {'time': 0.0, 'mouth_open': .4, 'vowel': 'a', 'energy': .8}]
    assert result['lipsync_error'] is None

def test_audio_entrypoint_requires_asr_and_nonempty_transcript(make_avatar):
    ava = make_avatar()
    with pytest.raises(RuntimeError, match='ASR'):
        ava.respond_audio('input.wav')
    class ASR:
        def transcribe(self, path): return ' '
    ava.asr = ASR()
    with pytest.raises(ValueError, match='未识别'):
        ava.respond_audio('input.wav')

@pytest.mark.parametrize('bad', [None, [], {'emotion': {'valence': True}, 'facts': []}, {'emotion': {'valence': float('nan')}, 'facts': []}, {'emotion': {}, 'facts': [{'type': '名字', 'content': '坏名字'}, 'invalid']}, {'emotion': {}, 'facts': [{'type': '名字', 'content': 123}]}])
def test_invalid_analysis_has_no_partial_effects(make_avatar, bad):
    ava = make_avatar([json.dumps(bad), '回复'])
    ava.respond('你好')
    assert ava.memory.get_user_profile() == {}
    assert ava.emotion.state.valence == 0

def test_analysis_write_failure_rolls_back_and_updates_emotion_once(make_avatar, monkeypatch):
    raw = json.dumps({'emotion': {'valence': 0.7, 'arousal': 0.4}, 'facts': [proven('名字', '小明', '我叫小明'), proven('事实', '考试失败', '我考试失败')]})
    ava = make_avatar([raw, '回复'])
    original = ava._store_fact
    observations = []
    original_observe = ava.emotion.observe
    def record_observation(valence, arousal, text=''):
        observations.append((valence, arousal))
        return original_observe(valence, arousal, text)
    monkeypatch.setattr(ava.emotion, 'observe', record_observation)
    def fail_second(fact):
        if fact['type'] == '事实':
            raise ValueError('simulated storage failure')
        original(fact)
    monkeypatch.setattr(ava, '_store_fact', fail_second)
    monkeypatch.setattr(ava, '_extract_facts', lambda text: None)
    ava.respond('我叫小明，我考试失败，开心')
    assert ava.memory.get_user_profile() == {}
    assert observations == [(pytest.approx(0.3), pytest.approx(0.0))]

def test_reply_failure_falls_back(make_avatar, caplog):
    raw = json.dumps({'emotion': {}, 'facts': []})
    ava = make_avatar([raw, RuntimeError('provider error')])
    result = ava.respond('你好')
    assert result['reply']
    assert ava.memory.get_short_term()[-1]['role'] == 'assistant'
    assert caplog.records


@pytest.mark.parametrize('reply', ['', '   '])
def test_empty_reply_falls_back(make_avatar, reply):
    raw = json.dumps({'emotion': {}, 'facts': []})
    ava = make_avatar([raw, reply])
    result = ava.respond('你好')
    assert result['reply'].strip()
    assert ava.memory.get_short_term()[-1]['content'] == result['reply']


def test_unsupported_candidate_does_not_discard_supported_peer(make_avatar):
    raw = json.dumps({'emotion': {}, 'facts': [
        proven('名字', '阿岚', '我叫阿岚'),
        proven('偏好', '喜欢养猫', '喜欢养猫'),
        {'type': '名字', 'content': '无证据'},
    ]})
    ava = make_avatar([raw, '你好'])
    ava.respond('我朋友小明喜欢养猫，我叫阿岚。')
    assert ava.memory.get_user_profile() == {'名字': '阿岚'}


def test_hypothesis_cannot_override_real_name(make_avatar):
    raw = json.dumps({'emotion': {}, 'facts': [
        proven('名字', '小红', '我叫小红'),
    ]})
    ava = make_avatar([raw, '假设介绍'])
    ava.memory.remember_user('名字', '阿岚')
    ava.respond('假如我叫小红，你会怎么介绍我？')
    assert ava.memory.get_user_profile()['名字'] == '阿岚'


def test_rule_fallback_remembers_explicit_negative_preference(make_avatar):
    ava = make_avatar()
    ava.respond('我不喜欢篮球')
    assert ava.memory.get_user_profile()['偏好'] == '不喜欢篮球'


def test_explicit_rules_recover_model_omissions_without_accepting_unproven_candidates(make_avatar):
    raw = json.dumps({'emotion': {}, 'facts': [
        {'type': '名字', 'content': '小红'},
        proven('偏好', '香菜', '我讨厌香菜'),
    ]})
    ava = make_avatar([raw, '你好'])
    ava.respond('我叫阿岚，我讨厌香菜，我喜欢游泳。')
    assert ava.memory.get_user_profile() == {'名字': '阿岚', '偏好': '喜欢游泳；讨厌香菜'}
    assert len(ava.memory.recall(memory_type='user_profile')) == 3


@pytest.mark.parametrize('text,fact', [
    ('我叫什么名字', proven('名字', '什么名字', '我叫什么名字')),
    ('我喜欢什么运动', proven('偏好', '喜欢什么运动', '我喜欢什么运动')),
    ('朋友说：“我叫小红。我喜欢香菜。我喜欢游泳。”',
     proven('偏好', '喜欢香菜', '我喜欢香菜')),
    ('我叫你小海', proven('名字', '你小海', '我叫你小海')),
    ('我喜欢咖啡，但现在不喜欢了', proven('偏好', '喜欢咖啡', '我喜欢咖啡')),
])
def test_merge_cannot_reintroduce_question_or_quoted_facts(make_avatar, text, fact):
    ava = make_avatar([json.dumps({'emotion': {}, 'facts': [fact]}), '回复'])
    ava.respond(text)
    if '现在不喜欢了' in text:
        assert ava.memory.get_user_profile() == {'偏好': '不喜欢咖啡'}
    else:
        assert ava.memory.get_user_profile() == {}

@pytest.mark.parametrize('text', [
    '我朋友以前喜欢茶，现在不喜欢了',
    '我喜欢咖啡，我现在喜欢茶，现在不喜欢了',
    '今天买了新衣服，现在不喜欢了',
])
def test_reference_shift_cannot_corrupt_existing_preference(make_avatar, text):
    ava = make_avatar()
    ava.respond('我喜欢咖啡')
    ava.respond(text)
    assert '不喜欢咖啡' not in ava.memory.get_user_profile()['偏好']

@pytest.mark.parametrize('old_clause,new_clause,old,new', [
    ('我喜欢咖啡', '我现在不再喜欢咖啡', '喜欢咖啡', '不喜欢咖啡'),
    ('我不喜欢咖啡', '我现在喜欢咖啡', '不喜欢咖啡', '喜欢咖啡'),
])
@pytest.mark.parametrize('order', ['new-first', 'old-first', 'new-only', 'no-candidates'])
def test_current_preference_does_not_depend_on_model_order(make_avatar, old_clause, new_clause, old, new, order):
    candidates = [proven('偏好', old, old_clause), proven('偏好', new, new_clause)]
    if order == 'new-first':
        candidates.reverse()
    elif order == 'new-only':
        candidates = candidates[1:]
    elif order == 'no-candidates':
        candidates = []
    ava = make_avatar([json.dumps({'emotion': {}, 'facts': candidates}), '收到'])
    ava.respond(old_clause + '，' + new_clause)
    assert ava.memory.get_user_profile() == {'偏好': new}
    assert [row['content'] for row in ava.list_memories()] == ['偏好: ' + new]

@pytest.mark.parametrize('text', [
    '我以前喜欢咖啡，朋友说“茶”，现在不喜欢了',
    '我以前喜欢咖啡，“茶”，现在不喜欢了',
])
def test_quoted_intervening_topic_cannot_store_masked_evidence(make_avatar, text):
    ava = make_avatar()
    ava.respond('我喜欢咖啡')
    ava.respond(text)
    assert ava.memory.get_user_profile() == {'偏好': '喜欢咖啡'}
    for row in ava.list_memories():
        for source in ava.inspect_memory(row['id'])['sources']:
            assert source['evidence'] in source['message_content']


@pytest.mark.parametrize('old_clause,new_clause,old,new', [
    ('我喜欢喝咖啡', '我现在不喜欢咖啡', '喜欢喝咖啡', '不喜欢咖啡'),
    ('我不喜欢喝咖啡', '我现在喜欢咖啡', '不喜欢喝咖啡', '喜欢咖啡'),
    ('我讨厌吃苹果', '我现在喜欢苹果', '讨厌吃苹果', '喜欢苹果'),
    ('我喜欢苹果', '我现在讨厌吃苹果', '喜欢苹果', '讨厌吃苹果'),
])
def test_canonical_consumption_object_keeps_only_last_assertion(make_avatar, old_clause, new_clause, old, new):
    text = old_clause + '，' + new_clause
    from avatar.brain.facts import rule_facts, supported_fact
    assert [f['content'] for f in rule_facts(text)] == [new]
    assert supported_fact(text, proven('偏好', old, old_clause)) is None
    candidates = [proven('偏好', new, new_clause), proven('偏好', old, old_clause)]
    ava = make_avatar([json.dumps({'emotion': {}, 'facts': candidates}), '收到'])
    ava.respond(text)
    assert ava.memory.get_user_profile() == {'偏好': new}


def test_extract_json_plain_object():
    raw = '{"emotion": {"valence": 0.1, "arousal": 0.0}, "facts": []}'
    assert json.loads(Avatar._extract_json(raw))['emotion']['valence'] == 0.1


def test_extract_json_tolerates_fence_and_trailing_prose():
    raw = '好的，结果如下：\n```json\n{"a": {"b": 1}}\n```\n说明 {这里不是 JSON}'
    assert Avatar._extract_json(raw) == '{"a": {"b": 1}}'


def test_extract_json_handles_braces_inside_strings():
    raw = '{"note": "用 {花括号} 和 } 干扰", "facts": []}'
    assert json.loads(Avatar._extract_json(raw))['note'] == '用 {花括号} 和 } 干扰'


def test_extract_json_without_object_returns_input():
    assert Avatar._extract_json(' 没有 JSON ') == '没有 JSON'
    assert Avatar._extract_json('') == ''


def test_fenced_analysis_json_still_stores_fact(make_avatar):
    analysis = {
        'emotion': {'valence': 0.2, 'arousal': 0.0},
        'facts': [proven('名字', '阿岚', '我叫阿岚')],
    }
    ava = make_avatar(['```json\n' + json.dumps(analysis, ensure_ascii=False) + '\n```', '你好，阿岚。'])
    result = ava.respond('我叫阿岚')
    assert result['reply'] == '你好，阿岚。'
    assert ava.memory.get_user_profile() == {'名字': '阿岚'}
