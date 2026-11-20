"""Direct body container: no action labels, fact plans or model self-approval."""
import json

ARTIFACT_INSTRUCTION = ('只输出指定JSON容器中的稿件正文句子，不解释写作任务，不询问是否需要帮助。'
    '这不是动作计划或自评，不输出事实认证或执行字段。'
    '署名由框架按来源另行落款，sentences内不得再次生成署名。'
    '每个元素写一句实际正文，保留用户给定事实/修改和明确引文。'
    '现实请假未给的理由、日期、时长分别用【请假原因】、【请假时间】、【请假时长】，'
    '不要补个人原因/工作背景/一天等；已给事项不得替换成占位或医学理由。'
    '小说按当前创作要求交付对方台词，不能以要不要构思代替。')


def response_format(sentence_count=None):
    if sentence_count is not None and (type(sentence_count) is not int or not 1 <= sentence_count <= 10):
        raise ValueError('Unsupported writing sentence bound')
    return dict(type='json_schema', json_schema=dict(name='avatar_writing_artifact', strict=True,
        schema=dict(type='object', additionalProperties=False, required=['sentences'], properties=dict(
            sentences=dict(type='array', items=dict(type='string'),
                           minItems=sentence_count or 1, maxItems=sentence_count or 4)))))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate artifact field')
        result[key] = value
    return result


def decode(raw, sentence_count=None):
    response_format(sentence_count)
    if not isinstance(raw, str) or not 0 < len(raw) <= 8000:
        raise ValueError('Invalid artifact size')
    value = json.loads(raw, object_pairs_hook=_unique)
    if not isinstance(value, dict) or set(value) != {'sentences'}:
        raise ValueError('Unexpected artifact fields')
    sentences = value['sentences']
    if (not isinstance(sentences, list) or not 1 <= len(sentences) <= (sentence_count or 4)
            or sentence_count is not None and len(sentences) != sentence_count
            or any(not isinstance(s, str) or not s.strip() or len(s) > 2000 for s in sentences)):
        raise ValueError('Invalid artifact body')
    return ''.join(s.strip() for s in sentences)
