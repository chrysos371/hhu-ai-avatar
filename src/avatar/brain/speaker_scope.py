"""Explicit speaker attribution, independent of literary/safety routing.

Only clear user roleplay declarations change scope. This is a bounded session
control, not general coreference resolution. No fictional source is retained in
the three-turn factual context. Mixed turns admit only the last explicit real
segment; earlier segments are conservatively omitted.
"""
import re
from collections import deque

from .facts import _mask_quoted


_ENTRY = re.compile(
    r'^(?:(?:接下来|现在|从现在起)[，,\s]*)?'
    r'我(?:来|要|将|会)?(?:扮演|饰演)(?!过)(?:[^。！？!?；;，,\n]{0,40})(?:角色|人物)\s*$')
_EXIT = re.compile(r'^(?:回到现实|停止扮演|退出角色|不演了|结束角色扮演)(?:吧)?\s*$')
_REAL = re.compile(r'^现实中的(?=我)')


class SpeakerScope:
    def __init__(self):
        self.clear(None)

    def clear(self, revision):
        self.revision = revision
        self.scope = 'current_user'
        self.fact_text = ''
        self.allows_actions = True
        self.context = []
        self._real_context = deque(maxlen=3)
        self._real_sources = deque(maxlen=3)
        self._scope_source = None
        self.context_source_ids = []

    @property
    def allows_facts(self):
        return self.scope == 'current_user'

    @property
    def source_ids(self):
        return sorted({ident for ident in [self._scope_source, *self._real_sources]
                       if type(ident) is int and ident > 0})

    def observe(self, text: str, revision: int, source_id=None):
        if self.revision != revision:
            self.clear(revision)
        clean = _mask_quoted(text)
        start = 0 if self.allows_facts else len(text)
        # Conditions/questions govern the whole sentence, including comma tails.
        for sentence in re.finditer(r'[^。！？!?；;\n]+[。！？!?；;]?', clean):
            value = sentence.group()
            if re.search(r'如果|假如|假设|要是|倘若|比如|例如|也许|可能|是否|[？?]|(?:吗|么|呢)[。！!；;]?$', value):
                continue
            for clause in re.finditer(r'[^，,。！？!?；;\n]+', value):
                raw = clause.group()
                trimmed = raw.lstrip()
                offset = sentence.start() + clause.start() + len(raw) - len(trimmed)
                entry, exit_, real = _ENTRY.match(trimmed), _EXIT.match(trimmed), _REAL.match(trimmed)
                if entry:
                    self.scope = 'fictional_character'
                    self._real_context.clear()
                    self._real_sources.clear()
                    self._scope_source = source_id
                    start = len(text)
                elif exit_ or real:
                    self.scope = 'current_user'
                    self._real_context.clear()
                    self._real_sources.clear()
                    self._scope_source = source_id
                    start = offset + (exit_ or real).end()
        self.fact_text = text[start:].lstrip('，,。；; \n') if self.allows_facts else ''
        # A final real segment cannot retroactively authorize an earlier
        # character instruction. Require a separate wholly real turn.
        self.allows_actions = self.allows_facts and start == 0
        self.context = list(self._real_context)
        self.context_source_ids = [ident for ident in self._real_sources if type(ident) is int and ident > 0]
        if self.fact_text:
            self._real_context.append(self.fact_text)
            self._real_sources.append(source_id)

    def data(self):
        return {'scope': self.scope, 'persistent_facts_allowed': self.allows_facts,
                'turn_tools_allowed': self.allows_actions,
                'version': 1, 'general_coreference_verified': False}

    def prompt(self):
        if self.allows_facts:
            return ''
        if self.scope == 'unverified':
            return ('此前说话者语境无法核验；不要推断当前第一人称是真实用户，'
                    '不更新真人资料、不执行真实操作。请用户单独发送“回到现实”确认后再提出真实请求。\n')
        return ('说话者来源：用户明确在扮演虚构角色；当前第一人称是故事角色，'
                '不是真实用户画像，不要更新真人资料或用真人姓名替换角色姓名。'
                '没有明确退出前保持这一归属；现实安全判断仍按既有安全规则执行。\n')
