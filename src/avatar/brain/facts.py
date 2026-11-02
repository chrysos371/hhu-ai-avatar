"""保守的事实证据校验：模型只提出候选，原始输入决定能否写入。"""
from __future__ import annotations

import re
from typing import Iterator

from .preferences import canonical_preference_object


_HYPOTHETICAL = re.compile(r"假如|假设|如果|要是|倘若|假装|比如|例如|也许|可能|据说")
_QUOTED = re.compile(r"[\"'“”‘’「」『』]|(?:他说|她说|朋友说|我说)[：:]")
_PAST = re.compile(r"以前|曾经|过去|原来|之前")
_NAME = re.compile(r"(?:我叫|我的名字是|我的姓名是|以后叫我|请叫我|叫我)([^\s，,。！？!?；;：:]{1,10})")
_PREFERENCE = re.compile(r"我(?:现在|目前|已经)?(不再喜欢|不喜欢|不爱|讨厌|喜欢|爱)([^\s，,。！？!?；;：:]{1,30})")
_NAME_TYPES = {"名字", "姓名", "称呼"}
_PREFERENCE_TYPES = {"偏好", "爱好", "喜欢"}
_SELF_ASSERTION = re.compile(r"^我(?:是|在|住在|养了|考试|毕业|参加|获得|通过|失去|找到|换了)")


def _mask_quoted(text: str) -> str:
    """先屏蔽完整引用范围，再分句；未闭合引用一直屏蔽到输入末尾。"""
    pairs = {'“': '”', '‘': '’', '「': '」', '『': '』', '"': '"', "'": "'"}
    stack = []
    masked = []
    for character in text:
        if stack:
            masked.append(' ')
            if character == stack[-1]:
                stack.pop()
            elif character in pairs:
                stack.append(pairs[character])
        elif character in pairs:
            stack.append(pairs[character])
            masked.append(' ')
        else:
            masked.append(character)
    return ''.join(masked)


def _safe_sentences(text: str) -> Iterator[str]:
    for match in re.finditer(r"[^。！？!?；;\n]+[。！？!?；;]?", _mask_quoted(text)):
        sentence = match.group(0).strip()
        # Masking is for locating sentence boundaries only. A sentence touching
        # a quoted span is ambiguous; never persist the synthetic masked text.
        source = text[match.start():match.end()].strip()
        if (source != sentence
                or _HYPOTHETICAL.search(sentence) or _QUOTED.search(sentence)
                or re.search(r"是否|是不是|有没有|能不能", sentence)
                or re.search(r"什么|谁|哪(?:个|些|种|里|儿)|多少|怎么|如何", sentence)
                or re.search(r"[？?]|(?:吗|么|呢)[。！!；;]?$", sentence)):
            continue
        yield sentence


def _clauses(text: str) -> Iterator[str]:
    """保留条件/问句的完整句子作用域，不能靠截短证据绕开。"""
    for sentence in _safe_sentences(text):
        clauses = [clause.strip() for clause in re.split(r"[，,。！？!?；;]", sentence)]
        for clause in clauses:
            if clause:
                yield clause


def safe_context_source(text: str) -> bool:
    """Require the whole context source to pass the same quote/question guards.

    Returning only its safe sentences would silently change the meaning of a
    mixed conditional source. Prefer dropping an ambiguous source altogether.
    """
    return bool(text.strip()) and ''.join(_safe_sentences(text)) == text.strip()


def _explicit_fact(clause: str) -> dict | None:
    name = _NAME.fullmatch(clause)
    if name:
        value = name.group(1)
        if clause.startswith('我叫') and value.startswith(('你', '他', '她', '它', '您')):
            return None
        if value in {"什么", "谁", "我的名字", "名字", "姓名"}:
            return None
        return {"type": "名字", "content": value}
    preference = _PREFERENCE.fullmatch(clause)
    if preference and not _PAST.search(clause):
        verb, item = preference.groups()
        if item.endswith("了"):
            item = item[:-1]
        if not item or item in {"什么", "啥", "哪些", "的东西"}:
            return None
        return {"type": "偏好", "content": verb.replace('不再喜欢', '不喜欢') + item}
    return None


def _temporal_preferences(text: str, context=None) -> list[dict]:
    """Resolve only a unique explicit object, never a guessed topic or another speaker."""
    reference = None
    if context and isinstance(context[-1], str):
        previous_text = context[-1]
        previous = [f for f in rule_facts(previous_text) if f['type'] == '偏好']
        trailing = [clause.strip() for clause in re.split(r'[，,。！？!?；;\n]', previous_text) if clause.strip()]
        safe_clauses = list(_clauses(previous_text))
        # The last clause must itself establish a safe, explicit self object.
        # A historical self fact earlier in the turn cannot outlive a new topic.
        final = _explicit_fact(trailing[-1]) if trailing and trailing[-1] in safe_clauses else None
        if len(previous) == 1 and final and final['type'] == '偏好':
            match = re.fullmatch(r'(不再喜欢|不喜欢|不爱|讨厌|喜欢|爱)(.+)', previous[0]['content'])
            if match:
                reference = match.group(2)
    results = []
    old_pattern = re.compile(r'我(?:以前|曾经|过去|原来|之前|现在|目前|已经)?(不再喜欢|不喜欢|不爱|讨厌|喜欢|爱)([^\s，,。！？!?；;：:]{1,30})')
    ellipsis = re.compile(r'(?:但是|不过|但|而)?(?:我)?(?:现在已经|现在|目前|已经|又)?(不再喜欢|不喜欢|不爱|讨厌|喜欢|爱)了?')
    repeated_object = re.compile(r'(?:但是|不过|但|而)?(?:现在已经|现在|目前|已经|又)(不再喜欢|不喜欢|不爱|讨厌|喜欢|爱)([^\s，,。！？!?；;：:]{1,30})')
    for sentence in _safe_sentences(text):
        objects = set()
        # A previous turn can only explain an ellipsis at this turn's start.
        # Skipped quoted/unsafe sentences must not silently preserve its topic.
        local_reference = reference if text.lstrip().startswith(sentence) else None
        reference = None
        for clause in re.split(r'[，,。！？!?；;]', sentence):
            clause = clause.strip()
            original = old_pattern.fullmatch(clause)
            if original and original.group(2).removesuffix('了'):
                obj = original.group(2).removesuffix('了')
                objects.add(canonical_preference_object(obj))
                local_reference = obj if len(objects) == 1 else None
                explicit = _explicit_fact(clause)
                if explicit:
                    results.append(dict(explicit, evidence=clause, subject='self',
                                        modality='asserted', temporal='current'))
                continue
            repeated = repeated_object.fullmatch(clause)
            if repeated and local_reference:
                obj = repeated.group(2).removesuffix('了')
                if (obj and canonical_preference_object(obj) == canonical_preference_object(local_reference)
                        and not re.search(r'和|或者|、|还是', obj)):
                    results.append(dict(type='偏好', content=repeated.group(1).replace('不再喜欢', '不喜欢') + obj,
                                        evidence=sentence if objects else clause, subject='self',
                                        modality='asserted', temporal='current'))
                    continue
            change = ellipsis.fullmatch(clause)
            if not change and clause:
                # Only an uninterrupted chain of explicit self preferences may
                # supply a reference. Unknown clauses can change subject/topic.
                local_reference = None
                objects.clear()
            if change and local_reference and not re.search(r'和|或者|、|还是', local_reference):
                verb = change.group(1).replace('不再喜欢', '不喜欢')
                # A same-sentence change needs its earlier object as evidence too.
                evidence = sentence if objects else clause
                results.append(dict(type='偏好', content=verb + local_reference,
                                    evidence=evidence, subject='self',
                                    modality='asserted', temporal='current'))
    # Source chronology, never candidate order, determines the current state of
    # each object. This applies symmetrically to every supported polarity.
    current = {}
    for fact in results:
        obj = re.fullmatch(r'(不再喜欢|不喜欢|不爱|讨厌|喜欢|爱)(.+)', fact['content']).group(2)
        current[canonical_preference_object(obj)] = fact
    return list(current.values())


def rule_facts(text: str, context=None) -> list[dict]:
    """无需模型的明确自述；与模型候选共享相同证据边界。"""
    facts = []
    for clause in _clauses(text):
        fact = _explicit_fact(clause)
        if fact and fact['type'] != '偏好':
            facts.append(dict(fact, evidence=clause, subject="self",
                              modality="asserted", temporal="current"))
    return facts + _temporal_preferences(text, context)


def supported_fact(text: str, candidate: dict, context=None) -> dict | None:
    """接受有原文依据的当前自述；拒绝无法验证的候选，不猜测。"""
    keys = ("type", "content", "evidence", "subject", "modality", "temporal")
    if (not isinstance(candidate, dict)
            or any(not isinstance(candidate.get(key), str) or not candidate[key].strip()
                   for key in keys)):
        return None
    if (candidate["subject"] != "self" or candidate["modality"] != "asserted"
            or candidate["temporal"] != "current"):
        return None
    evidence = candidate["evidence"]
    if evidence not in text:
        return None
    kind, content = candidate["type"].strip(), candidate["content"].strip()
    if kind in _PREFERENCE_TYPES:
        for resolved in _temporal_preferences(text, context):
            obj = re.fullmatch(r'(不再喜欢|不喜欢|不爱|讨厌|喜欢|爱)(.+)', resolved['content']).group(2)
            if content in (resolved['content'], obj) and resolved['evidence'] in evidence:
                return dict(candidate, type='偏好', content=resolved['content'])
        return None
    for clause in _clauses(text):
        # 必须覆盖完整自述；裸名称或谓语片段不能证明主体/语气。
        if clause not in evidence:
            continue
        explicit = _explicit_fact(clause)
        if explicit:
            kinds = _NAME_TYPES if explicit["type"] == "名字" else _PREFERENCE_TYPES
            if kind in kinds and content == explicit["content"]:
                return dict(candidate, type=explicit["type"], content=content)
        # 身份/事件暂只接受原文中的完整自述，避免模型补出原文没有的结论。
        elif (kind in {"身份", "事件", "事实"} and _SELF_ASSERTION.match(clause)
              and not _PAST.search(clause)
              and (content in (clause, clause[1:])
                   or (kind == "身份" and clause.startswith("我是")
                       and content == clause[2:]))):
            return dict(candidate, content=content)
    return None
