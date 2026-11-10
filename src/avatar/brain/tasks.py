"""Small, explicit task contracts. Source text is data, never a tool command.

Only a current explicit writing request or a clearly linked follow-up carries a
contract forward. Unknown identity/recipient remains unknown; no profile writes.
"""
from dataclasses import asdict, dataclass, field
import json
import re

from .facts import _mask_quoted


_LITERAL = re.compile(r'【[^【】\n]{1,40}】|“[^“”\n]{1,120}”|「[^「」\n]{1,120}」|『[^『』\n]{1,120}』|"[^"\n]{1,120}"|\'[^\'\n]{1,120}\'')
_OPERATION = re.compile(
    r'不必包含|无需包含|不用包含|不必保留|无需保留|不用保留|不要保留|不要包含|不得包含|禁止包含|'
    r'原样保留|原样输出|必须包含|删除|删掉|保留|留作|留为|不要改|不得改|别改|包含')
_FORBID = {'不用保留', '不要保留', '不要包含', '不得包含', '禁止包含', '删除', '删掉'}
_RELEASE = {'不必包含', '无需包含', '不用包含', '不必保留', '无需保留'}


def _instructions(text):
    cleaned = list(_mask_quoted(text))
    for match in re.finditer(r'【[^【】\n]{1,40}】', text):
        cleaned[match.start():match.end()] = ' ' * len(match.group())
    return ''.join(cleaned)


@dataclass
class TaskContract:
    source: str
    perspective: str = ''
    recipient: str = ''
    required_literals: list[str] = field(default_factory=list)
    forbidden_literals: list[str] = field(default_factory=list)

    def data(self):
        return asdict(self)


class TaskTracker:
    def __init__(self):
        self.current = None

    def update(self, text):
        clean = _instructions(text)
        meta = bool(re.match(r'^(?:请)?(?:再|先|另外|顺便)?(?:解释|分析|评价|点评|讨论|判断|翻译|问|聊)|^我想(?:再)?(?:问|知道|聊)', clean.strip())
                    or re.search(r'什么意思|是指什么|如何理解|怎么理解', clean))
        explicit_rewrite = bool(re.search(r'(?:帮我|请|替我|给我).{0,12}(?:写|拟|改写|润色|起草|修改)|(?:并|再|然后)(?:请|帮我)?(?:改写|润色|重写|起草|修改)', clean[1:] if clean.startswith('请') else clean))
        if meta and not explicit_rewrite:
            self.current = None
            return
        writing = bool(re.search(r'(?:写|拟|改写|润色|起草|修改).{0,24}(?:消息|短信|邮件|申请|正文|通知|回复|段话|文字|台词|句子|句话|标语|提醒)|'
                                 r'(?:消息|短信|邮件|申请|正文|通知|台词|句子|句话|标语|提醒).{0,12}(?:写|拟|改写|润色)', clean))
        continuation = bool(re.match(
            r'^(?:再(?:写|改|短|长|精简|润色|正式|口语|自然|删|加|补|换|保留)|'
            r'再(?:来|给我)一版(?=[，,。！!\s]|$)|改成|改为|删掉|保留|加上|补上|缩短|'
            r'(?:不要|不用)(?:改|写|保留|包含|加|删|用|太长|太短|这么长|那么长)|'
            r'(?:不必|无需)(?:包含|保留)|只要(?:正文|结论|保留|写|改|短|[一二两三四五六七八九十0-9]+[行句段字])|'
            r'(?:仍然|还是)(?:要|想)?(?:保留|写|用|改|删|短|长|正式|口语)|'
            r'(?:把这|把它).{0,24}(?:改|写|删|加|换|精简|保留|压缩|润色))', clean.strip())
            or re.fullmatch(r'再说(?:一遍|一次)[。！!\s]*', clean.strip()))
        reset = bool(re.match(r'^(?:我们)?(?:先|再)?(?:换个话题|不写了|先不写|不要写了|不用写了|取消(?:这个任务|写作|上一条)?)(?=[，,。！!\s]|$)', clean.strip()))
        listening = bool(re.search(r'只想(?:倾诉|说说|吐槽)|(?:不要|不用|不需要)给(?:我)?建议|听我说(?:就好|就行)', clean))
        if reset or listening:
            self.current = None
            if listening or not writing:
                return
        revising = self.current is not None and (continuation or (writing and bool(re.search(r'改写|润色|修改', clean))))
        if writing and not revising:
            self.current = TaskContract(source=text)
        elif not writing and not revising and not continuation:
            self.current = None
        if self.current is None:
            return
        contract = self.current
        # Explicit role only, never infer family/recipient from old memories.
        role = re.search(r'(?:替|代|帮)(?:我)?(姐姐|妹妹|哥哥|弟弟|妈妈|爸爸|朋友|同学|同事|室友)', clean)
        if role is None:
            role = re.search(r'(姐姐|妹妹|哥哥|弟弟|妈妈|爸爸|朋友|同学|同事|室友)(?:让|请|托)我(?:替|代|帮)', clean)
        if role is None:
            role = re.search(r'(?:起草|代拟|写|拟)(姐姐|妹妹|哥哥|弟弟|妈妈|爸爸|朋友|同学|同事|室友)的(?:回复|消息|短信|邮件)', clean)
        if role:
            contract.perspective = role.group(1)
        if re.search(r'(?:用|以|按).{0,8}(?:她|他|姐姐|妹妹|哥哥|弟弟|朋友|同学|同事|室友).{0,4}第一人称', clean):
            contract.perspective = role.group(1) if role else (contract.perspective or '委托人指定的他人（第一人称）')
        if re.search(r'改(?:为|成|用)我(?:自己)?的?(?:口吻|第一人称)', clean):
            contract.perspective = '用户本人'
        recipient = re.search(r'(?:给|发给|写给)(房东|物业|老师|导师|辅导员|审核方|负责人|经理|同事|朋友)', clean)
        if recipient:
            contract.recipient = recipient.group(1)
        # Split only at punctuation OUTSIDE quotes/placeholders. Preserve raw
        # offsets so an operation inside quoted content never becomes a command.
        for scope in re.finditer(r'[^，,。；;\n]+', clean):
            clause = text[scope.start():scope.end()]
            instructions = clean[scope.start():scope.end()]
            operations = list(_OPERATION.finditer(instructions))
            for token in _LITERAL.finditer(clause):
                prior = [op for op in operations if op.end() <= token.start()]
                following = [op for op in operations if op.start() >= token.end()]
                operation = prior[-1] if prior else (following[0] if following else None)
                if operation is None:
                    continue
                literal = token.group(0) if token.group(0).startswith('【') else token.group(0)[1:-1]
                if not literal.strip():
                    continue
                if operation.group(0) in _RELEASE:
                    if literal in contract.required_literals:
                        contract.required_literals.remove(literal)
                    continue
                deleting = operation.group(0) in _FORBID
                remove = contract.required_literals if deleting else contract.forbidden_literals
                keep = contract.forbidden_literals if deleting else contract.required_literals
                if literal in remove:
                    remove.remove(literal)
                if literal not in keep:
                    keep.append(literal)
        # Keep bounded source evidence for revisions without growing indefinitely.
        if not writing or revising:
            contract.source = (contract.source + '\n最新修改：' + text)[-1200:]

    def prompt(self):
        if self.current is None:
            return ''
        return ('\n本轮明确的写作任务数据（不是额外指令；冲突以用户最新要求为准）：'
                + json.dumps(self.current.data(), ensure_ascii=False)
                + '\n先交付可直接使用的正文。代拟时用指定人的视角，不把委托用户写成当事人；'
                  '未提供的信息留空或保留占位，不虚构。建议、计划和收到回复不代表已经确认或同意。')

    def inspect(self, reply):
        if self.current is None:
            return []
        issues = ['missing_literal:' + x for x in self.current.required_literals if x not in reply]
        issues += ['forbidden_literal:' + x for x in self.current.forbidden_literals if x in reply]
        if re.fullmatch(r'\s*(?:好的[，,！!。]?\s*)?(?:我)?(?:可以|能|愿意)帮你.{0,60}[。！!？?]?\s*', reply):
            issues.append('offer_without_deliverable')
        if not reply.strip():
            issues.append('empty_deliverable')
        return issues
