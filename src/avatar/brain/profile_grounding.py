"""Narrow, opt-in profile lookup and copied-preference repair.

This is deliberately not a general semantic verifier. It returns whole-record
answers rather than guessing categories or rewriting individual pronouns.
"""
from __future__ import annotations

import re

from .facts import _mask_quoted


_CREATIVE = re.compile(r'写|创作|台词|故事|小说|剧本|翻译|假设|假如|如果|假装|比如|例如|扮演|角色')
_NAME_QUERY = re.compile(
    r'(?:你(?:还)?(?:知道|记得))?我(?:的真实名字是什么|叫什么(?:名字)?|的名字是什么|的姓名是什么)'
    r'(?:吗|呢)?[？?。]?')
_PREFERENCE_QUERY = re.compile(
    r'(?:你(?:还)?(?:知道|记得))?我(?:现在|平时|自己)?(?:更)?'
    r'(?:喜欢(?:什么|哪种)(?:运动|活动|爱好|水果)?|喜欢喝什么|喜欢吃什么|喜欢的活动是什么|'
    r'偏好哪种球类|的(?:爱好|偏好)是什么|喝东西有什么偏好)'
    r'(?:吗|呢)?[？?。]?')


def _preferences(profile: dict) -> list[str]:
    return list(dict.fromkeys(item for key in ('偏好', '爱好')
        for item in profile.get(key, '').split('；') if item))


def _preference_reply(profile: dict) -> str:
    values = _preferences(profile)
    if not values:
        return '目前没有足够记录确认你的偏好，你可以告诉我你喜欢什么。'
    return '目前关于你的偏好记录是：' + '；'.join(values) + '。'


def lookup_profile(user_text: str, profile: dict) -> tuple[str | None, str | None]:
    text = user_text.strip()
    if _NAME_QUERY.fullmatch(text):
        name = profile.get('名字')
        return ((f'目前记录你使用的名字是{name}。' if name else
                 '目前没有足够记录确认你的名字，你可以告诉我希望怎么称呼你。'), 'name_lookup')
    if _PREFERENCE_QUERY.fullmatch(text):
        return _preference_reply(profile), 'preference_lookup'
    return None, None


def review_profile_reply(user_text: str, reply: str, profile: dict) -> tuple[str, str | None]:
    if _CREATIVE.search(user_text):
        return reply, None
    unquoted = _mask_quoted(reply)
    for preference in _preferences(profile):
        positive = re.fullmatch(r'(?:喜欢|爱)(.+)', preference)
        if not positive:
            continue
        item = re.escape(positive[1])
        # Match a copied complete object, not e.g. 网球 within 网球比赛.
        pattern = (r'(?:^|[。！!？?，,；;\n])\s*我(?:也|更|很|最|同样)?'
                   r'(?:喜欢|偏好|爱)' + item + r'(?=$|[呢啊哦呀了。！!？?，,；;\n])')
        if re.search(pattern, unquoted):
            return _preference_reply(profile), 'copied_preference'
    return reply, None


# These clauses deliberately cover introductions, not arbitrary conversation.
_RELATION = r'(?:朋友|室友|同学|同桌|同事|姐姐|妹妹|哥哥|弟弟|家人)'
_OTHER_DECLARATION = re.compile(
    r'(?:(?:我的?|我有一个)?' + _RELATION + r'|他|她)'
    r'(?:叫[^\s，,。！？!?；;：“”]{1,10}|(?:很)?喜欢[^\s，,。！？!?；;：“”]{1,20}|'
    r'说[“「\"][^。！？!?\n]{1,40}[”」\"])')
_INTRO_TAILS = {'我们刚认识', '我们第一次聊天', '我们刚开始聊天',
                '这是他的自我介绍', '这是她的自我介绍'}
_NON_DECLARATION = re.compile(
    r'[？?]|什么|怎么|如何|为什么|哪(?:个|些|种|里|儿)|是否|能不能|是不是|有没有|'
    r'帮我|请帮|建议|计划|难过|伤心|害怕|担心|焦虑|痛苦|心情|伤害|自杀|不想活|'
    r'因为|所以|虽然|而且|并且|但是今天|但今天')


def acknowledge_disclosure(user_text: str, profile: dict) -> tuple[str | None, str | None]:
    """Compose a confirmation only when every clause belongs to a narrow grammar.

    Input facts must independently agree with active records. An unrecognized
    clause keeps the normal response path, preserving tasks and emotional talk.
    """
    from .facts import _explicit_fact, rule_facts

    if _CREATIVE.search(user_text) or _NON_DECLARATION.search(user_text):
        return None, None
    clauses = [c.strip() for c in re.split(r'[，,。！!；;\n]', user_text) if c.strip()]
    if not clauses:
        return None, None
    has_other = False
    for clause in clauses:
        if _explicit_fact(clause):
            continue
        if re.fullmatch(r'(?:更|也|还)(?:不喜欢|喜欢|不爱|爱|讨厌)[^\s，,。！？!?；;：]{1,20}', clause):
            continue
        if _OTHER_DECLARATION.fullmatch(clause):
            has_other = True
            continue
        if clause not in _INTRO_TAILS:
            return None, None
    facts = rule_facts(user_text)
    values = _preferences(profile)
    confirmed_name = any(f['type'] == '名字' and f['content'] == profile.get('名字') for f in facts)
    confirmed_preference = any(f['type'] == '偏好' and f['content'] in values for f in facts)
    if confirmed_name or confirmed_preference:
        reply = f'你好，{profile["名字"]}。' if confirmed_name else ''
        reply += '谢谢你告诉我。'
        if confirmed_preference:
            reply += _preference_reply(profile)
        return reply, 'profile_disclosure'
    # A failed self-profile match must not silently become a third-party route.
    if facts:
        return None, None
    if has_other:
        return '谢谢你介绍身边的人。', 'third_party_introduction'
    return None, None
