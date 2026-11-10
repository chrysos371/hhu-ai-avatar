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
