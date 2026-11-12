"""Audit-only conservative source-question route; never imported by production."""
import re

_PERSONAL_OR_ACTION=re.compile(
    r'我|咱|俺|本人|你|他|她|叫|喜欢|讨厌|住在|生日|今年|今天|明天|岁|'
    r'提醒|发送|发给|短信|打电话|联网|删除|忘掉|纠正|保存|记住|记下|设置|预约|购买|支付|执行|操作|'
    r'扮演|角色|现实|引用|转述|假如|如果|[“”‘’「」『』"\']|\b(?:I|my|me|we|our|you|he|she)\b',re.I)
_AFFECT=re.compile(r'情绪|情感|心情|难过|难受|伤心|委屈|害怕|焦虑|担心|沮丧|开心|高兴|愤怒|生气|紧张|不想听建议|只想说说|想缓一缓|自杀|轻生|自残')
_FORM=re.compile(r'^(?:请)?(?:根据|按照)(?:上文|前文|资料|记录|清单|表格|文本|预算)[，,][^。.！？!?；;\n\r]{1,150}[?？](?:请)?(?:只|仅)(?:回答|输出)[^。.！？!?;；\n\r]{1,60}[。.]?$')


def decide(text,*,history=(),scope='current_user',risk=None,rule_fact_candidates=()):
    from avatar.brain.emotion import EmotionEngine
    if scope!='current_user' or risk:return {'eligible':False,'reason':'scope_or_ongoing_boundary'}
    if not isinstance(text,str) or not 1<=len(text)<=200:return {'eligible':False,'reason':'text_type_or_bound'}
    if not _FORM.fullmatch(text):return {'eligible':False,'reason':'outside_explicit_single_source_question'}
    if _PERSONAL_OR_ACTION.search(text):return {'eligible':False,'reason':'personal_action_quote_or_control'}
    if _AFFECT.search(text) or EmotionEngine.infer(text)!=(0.0,0.0):return {'eligible':False,'reason':'current_affect'}
    if not isinstance(history,(list,tuple)) or len(history)>6:return {'eligible':False,'reason':'invalid_recent_history'}
    for message in history:
        if not isinstance(message,dict) or message.get('role') not in ('user','assistant') or not isinstance(message.get('content'),str):return {'eligible':False,'reason':'invalid_recent_message'}
        value=message['content']
        if _AFFECT.search(value) or EmotionEngine.infer(value)!=(0.0,0.0):return {'eligible':False,'reason':'recent_affect'}
    if not isinstance(rule_fact_candidates,(tuple,list)) or rule_fact_candidates:return {'eligible':False,'reason':'current_rule_fact'}
    return {'eligible':True,'reason':'explicit_neutral_source_question_no_current_rule_facts'}


def install(rows):
    """Delegate all ineligible calls; preserve actual fact/revision checkpoints."""
    from avatar.main import Avatar
    from avatar.brain.facts import rule_facts
    original=Avatar._analyze
    def analyze(self,text):
        recent=self.memory.get_short_term()
        if recent and recent[-1]=={'role':'user','content':text}:recent=recent[:-1]
        values={'history':recent[-6:],'scope':self.speaker_scope.scope,'risk':self.boundaries.risk}
        decision=decide(text,**values)
        if decision['eligible']:
            self._checkpoint_prompt_context()
            facts=rule_facts(self.speaker_scope.fact_text,context=self._fact_context(text))
            decision=decide(text,**values,rule_fact_candidates=facts)
        row={'input':text,'decision':decision,'history_role_count':len(recent[-6:]),'current_user_source_id':self._current_message_id,
             'scope':self.speaker_scope.scope,'revision':self.memory.context_revision,'delegates_original':not decision['eligible']}
        rows.append(row)
        if not decision['eligible']:return original(self,text)
        self._extract_facts(text)
        self.emotion.update(text)
        self.analysis_mode='lab_readonly_context_rules'
        self._checkpoint_prompt_context()
    Avatar._analyze=analyze
    return original
