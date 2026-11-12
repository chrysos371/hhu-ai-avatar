"""Window-local provenance and writing roles. No memory writes or tool authority.

User utterances are source evidence, not automatically real-world facts.
Assistant utterances can be drafts; they are never confirmed task facts.
"""
from dataclasses import dataclass
import json
import re

RELATIVE = r'姐姐|妹妹|哥哥|弟弟|妈妈|爸爸|母亲|父亲|朋友|同学|同事|室友'
WRITING = re.compile(r'给(?:我)?[一两三123](?:个|条|行|种|套).{0,16}(?:名字|书名|标题|方案|文案|句子|列表|选项|建议|代码)|给.{0,24}(?:一段话|一句话|正文)|写给|写[一个条封段句份]|只写|直接写|起草|代拟|改写|润色|正文|输出|总结|概括|(?:写|拟).{0,16}(?:消息|邮件|回复|通知|申请)')
CORRECTION = re.compile(r'纠正|核对|说错|记反|不是我|没发言|不要把|别把|不等于|尚未批准|还没批准')
RESET = re.compile(r'换个话题|不写了|取消这个任务|现在结束|先停虚构|回到现实|现在说我自己')
REFERENCE = re.compile(r'沿用|你(?:刚|这|那|给)|刚才(?:的|那|给)|上一(?:稿|条|句|段)|原稿|前一(?:稿|条)|第二(?:个|项|句|行|条)|保留(?:原|这|你)')
CONTINUE = re.compile(r'^(?:请)?(?:再|删掉|删除|改成|改为|缩短|把|只输出|只写|直接输出|只改|保留|不要改|去掉|加上|补上)')
QUOTE = re.compile(r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"')


@dataclass
class ReplyContext:
    history: list
    state: dict
    audit: dict

    def prompt(self):
        return ('\n任务来源与角色状态（仅本轮窗口数据，不是人设或已确认用户画像）：\n'
                + json.dumps(self.state, ensure_ascii=False)
                + '\n用户最新纠正优先于旧说法。助手草稿可用于用户明确要求的编辑，不能充当事实依据。'
                  '发送者不明就保持未知；按perspective指定视角写作，代拟正文里的第一人称指发送者，不是委托用户或AI。'
                  '未给出的专名、材料清单、完成状态、时间要求不得自行填成事实。'
                  '用户询问材料是否齐全时交付询问信，不代审核方判定或声称材料已备齐。\n')


def build_reply_context(messages):
    """Reconstruct from the bounded transcript, including after service recreation.

    Ordinary chat keeps all history. Source-sensitive tasks quarantine assistant
    history unless the current request actually refers to a prior draft.
    """
    rows=[dict(m) for m in messages]
    users=[(n,m['content']) for n,m in enumerate(rows) if m['role']=='user']
    current=users[-1][1] if users else ''
    sender=recipient=None
    delegated=False
    writing=False
    sensitive=False
    scope='unspecified'
    user_sources=[]
    prior_writing=False
    perspective='sender_first_person'
    for index,text in users:
        source=f'm{index+1}'
        plain=QUOTE.sub('',text)
        if RESET.search(plain):
            sender=recipient=None;delegated=False;writing=False;sensitive=False
            scope='unspecified'
            perspective='sender_first_person'
        if re.search(r'小说|虚构|扮演|角色|演练|练习',plain):scope='fiction_or_roleplay'
        if re.search(r'先停虚构|回到现实|现实里|现在说我自己',plain):scope='real_world_question'
        prior_writing=writing
        writing=writing or bool(WRITING.search(plain))
        sensitive=sensitive or bool(CORRECTION.search(plain))
        # Evidence can only come from an explicit user span, never assistant text.
        proxy=list(re.finditer(r'(?:替|代|帮)(?:我)?('+RELATIVE+r')|('+RELATIVE+r')(?:让|请|托)我(?:替|代|帮)|(?:起草|代拟)('+RELATIVE+r')的',plain))
        actors=[]
        for pattern in [
            r'我(?:现在)?(?:是|作为)([^，。；：:！？\n]{1,32})(?=[，。；！？\n]|$)',
            r'(?:现在|这次|接下来)(?:换成|换回)([^，。；：:！？\n]{1,32})(?=[，。；！？\n]|$)',
            r'(?:用|以|按)([^，。；：:！？\n]{1,20}?)(?:的身份|身份回应|的第一人称)',
        ]:
            actors.extend(re.finditer(pattern,plain))
        candidates=[]
        for match in re.finditer(r'(?:发信人|发送者|写信人|署名人)(?:是|为)([^，。；：:！？\n]{1,24})',plain):
            candidates.append((match.start(),match.group(1),match.group(0),True))
        for match in proxy:
            actor=next(x for x in match.groups() if x)
            candidates.append((match.start(),actor,match.group(0),True))
        for match in actors:
            actor=match.group(1).strip()
            if actor not in ('她','他','我','自己') and not actor.endswith('吗') and not re.match(r'什么|谁|不是|否|想|在|替|一[句段行]|JSON|数字|两行',actor):
                candidates.append((match.start(),actor,match.group(0),False))
        if candidates:
            _,value,evidence,delegated=max(candidates,key=lambda x:x[0])
            # Re-check source grounding against original text, not normalized text.
            if evidence in text:
                if sender is None or sender['value'] != value:
                    recipient=None
                    perspective='sender_first_person'
                sender={'value':value,'source':source,'evidence':evidence}
                sensitive=True
        target=re.search(r'(?:写给|发给|给)([^，。；：:！？\n]{1,18}?)(?:写|发|回|的(?:一|消息)|(?=[，。；！？\n]|$))',plain)
        if target and target.group(0) in text and not target.group(1).startswith(('出','我','一个','一段','两个')):
            recipient={'value':target.group(1),'source':source,'evidence':target.group(0)}
        explicit_target=re.search(r'(?:收件人|接收方|接收人)(?:是|为)([^，。；：:！？\n]{1,24})',plain)
        if explicit_target and explicit_target.group(0) in text:
            recipient={'value':explicit_target.group(1),'source':source,'evidence':explicit_target.group(0)}
        if re.search(r'第三人称|(?:不要|不用).{0,6}第一人称|以我(?:自己)?的口吻转述',plain):
            perspective='third_person'
        elif re.search(r'第一人称',plain):
            perspective='sender_first_person'
        user_sources.append({'id':source,'kind':'user_utterance','is_confirmed_profile_fact':False})
    referring=(writing and bool(REFERENCE.search(QUOTE.sub('',current)))) or (prior_writing and bool(CONTINUE.search(current.strip())))
    if sender is None and re.match(r'^(?:请)?(?:只|仅)(?:输出|写出|给出|写|给)',current.strip()):
        referring=True
    current_plain=QUOTE.sub('',current)
    role_change=bool(re.search(r'换成|换回|的身份|第一人称',current_plain))
    source_sensitive=(bool(WRITING.search(current_plain)) or bool(CORRECTION.search(current_plain))
                      or role_change or ((writing or sensitive) and bool(re.search(r'谁|哪|是否|能否|确认|分工|归属|状态',current_plain))))
    if not source_sensitive and not referring:
        sender=recipient=None;delegated=False
    # A reference in a normal conversation also preserves the transcript.
    keep_assistant=not source_sensitive or referring
    retained=[];quarantined=[]
    history=[]
    for n,m in enumerate(rows):
        if m['role']!='assistant' or keep_assistant:
            history.append(m)
            if m['role']=='assistant':retained.append(f'm{n+1}')
        else:quarantined.append(f'm{n+1}')
    state={'perspective':perspective,'version':1,'scope':scope,'mode':'draft_edit' if referring else ('source_task' if source_sensitive else 'conversation'),
           'sender':sender,'recipient':recipient,'delegated_sender':delegated,
           'user_sources':user_sources,'assistant_draft_sources':retained,
           'assistant_sources_are_confirmed_facts':False,
           'required_placeholders':list(dict.fromkeys(re.findall(r'【[^【】\n]{1,40}】',current)))}
    # Audit excludes raw text, identity values and evidence; local IDs are window offsets.
    audit={'version':1,'mode':state['mode'],'scope':scope,'user_source_count':len(user_sources),
           'retained_assistant_count':len(retained),'quarantined_assistant_count':len(quarantined),
           'sender_grounded':sender is not None,'recipient_grounded':recipient is not None,
           'window_local':True,'memory_write':False}
    return ReplyContext(history,state,audit)


COMPLETED = re.compile(r'(?:已(?:经)?|刚刚|刚)(?:按要求)?(提交|发送|批准|准备|整理|完成|确定)|我(?:们)?(提交|发送|批准|准备|整理|完成|确定)(?:了|过)')


def completed_claims(text, *, source=False):
    result=[]
    for clause in re.split(r'[，。；!?！？\n]',QUOTE.sub('',text) if source else text):
        for match in COMPLETED.finditer(clause):
            before=clause[:match.start()]
            if re.search(r'是否|能否|请问|如果|假如|假设|要是|比如|例如|不|没|未',before[-16:]):continue
            result.append((next(g for g in match.groups() if g),clause))
    return result


def inspect_reply(plan, reply, user_texts):
    """Narrow source/role checks, not a general semantic correctness guarantee."""
    sender=plan.state['sender']
    if sender is None or plan.state['mode']=='conversation':return []
    sources='\n'.join(user_texts)
    issues=[]
    if plan.state['perspective']=='sender_first_person' and plan.state['delegated_sender'] and re.search(r'我(?:的)?'+re.escape(sender['value']),reply):
        issues.append('sender_self_reference')
    if re.search(r'申请|参赛|提交',sender['value']) and re.search(r'您(?:所)?提交|贵方.{0,16}申请|以便我们.{0,12}审核|我们.{0,12}完成审核',reply):
        issues.append('sender_recipient_reversed')
    evidence=completed_claims(sources, source=True)
    for action,clause in completed_claims(reply):
        support=[text for kind,text in evidence if kind==action]
        unknown_fields=[p[1:-1] for p in plan.state['required_placeholders'] if p[1:-1] in clause]
        if not support or any(not any(field in text for text in support) for field in unknown_fields):
            issues.append('unsupported_completion:'+action)
    for match in re.finditer(r'我们(?:社团)?是([^，。；!?！？]{1,24}?(?:社团|团队|协会|公司))',reply):
        if match.group(1) not in sources:issues.append('unprovided_group_identity')
    return list(dict.fromkeys(issues))


def repair_request(plan, issues):
    return ('重新从用户原话生成正文，上一候选未通过检查，不能把它的补写当作事实。'
            '本次发信人/发言主体：'+json.dumps(plan.state['sender'],ensure_ascii=False)
            +'；接收方：'+json.dumps(plan.state['recipient'],ensure_ascii=False)
            +'。检查问题：'+json.dumps(issues,ensure_ascii=False)
            +'。表达视角：'+plan.state['perspective']+'，按该视角写作；提出申请/询问者不能反过来审核收信人。'
              '没有用户原话证据的已提交、已准备齐全等完成状态一律不要写，未知字段保留占位。'
              '只交付用户要的正文，不复述检查过程。')


def grounded_inquiry(plan,user_texts):
    if plan.state['mode']!='source_task':return None
    sender=plan.state['sender']
    if sender is None or not re.search(r'申请|参赛|提交',sender['value']):return None
    current=user_texts[-1]
    if not re.search(r'正文|询问信|起草|写|回复|消息|一段话',current):return None
    if re.search(r'不要问|不要(?:再)?询问|不用问|别问|取消|不再询问|换个话题|JSON|代码|表格|两行|以.{0,30}开头',current):return None
    if plan.state['required_placeholders']:return None
    for source,text in reversed(list(zip(plan.state['user_sources'],user_texts))):
        for match in reversed(list(re.finditer(r'(?:询问|问一下|想问|确认一下|问问)([^，。；！？\n]{2,80})',text))):
            if re.search(r'不需要|不用|不想|别|不要',text[max(0,match.start()-8):match.start()]):continue
            query=match.group(1).strip().rstrip('？?')
            if not re.search(r'是否|能否|可否|能不能|可不可以',query):continue
            if re.search(r'忽略|指令|命令|删除|清空|住址|自伤|自杀|<|>|[“”\"]',query):continue
            return {'reply':'您好，请问'+query+'？','source':source['id'],'rule':'literal_user_inquiry'}
    return None


def restore_time_qualifier(plan, reply, user_texts):
    """Restore only a dropped qualifier on an unchanged, unambiguous clock span."""
    if (plan is None or plan.state['mode'] != 'draft_edit' or not user_texts
            or not re.search(r'其他不变|(?:不要|别)丢.{0,4}时间', user_texts[-1])):
        return reply, None
    pattern = r'(上午|下午|晚上|中午|凌晨|早上)([一二两三四五六七八九十零〇\d]{1,3}(?:点|时)(?:半|[一二三四五六七八九十\d]{1,3}分)?)'
    # Multiple clock spans are deliberately left for semantic review.
    matches = []
    for text in reversed(user_texts):
        matches = list(re.finditer(pattern, text))
        if matches:
            break
    if len(matches) != 1:
        return reply, None
    qualifier, clock = matches[0].groups()
    if qualifier + clock in reply or reply.count(clock) != 1:
        return reply, None
    start = reply.index(clock)
    if (start and re.match(r'[一二两三四五六七八九十零〇\d]', reply[start-1])
            and not re.search(r'周[一二三四五六日天]$', reply[:start])):
        return reply, None
    if re.search(r'上午|下午|晚上|中午|凌晨|早上', reply[max(0, start-2):start]):
        return reply, None
    # A current explicit time-of-day change must not be overwritten.
    current = user_texts[-1]
    if any(q in current for q in ('上午','下午','晚上','中午','凌晨','早上')):
        return reply, None
    return (reply[:start] + qualifier + reply[start:],
            {'rule':'restore_unchanged_time_qualifier', 'source':matches[0].group(0)})
