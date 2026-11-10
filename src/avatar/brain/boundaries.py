"""Narrow, auditable companion boundaries. Rules are not clinical risk assessment."""
from dataclasses import dataclass
import re

from .facts import _mask_quoted


BOUNDARY_PROMPT = (
    '现实与关系边界：你没有身体、感官或真实线下经历，不能编造自己吃喝、到场或与用户共同经历。'
    '允许明确标注的虚构创作，不能把故事当现实。不能保证考试、录取等结果，不能承诺永远在线或永久陪伴。'
    '支持用户自主选择和现实中的朋友家人，不要求排他依赖，不因用户离开而施加愧疚。'
    '不协助查找、定位或推断不愿联系者的私人住处，不提供绕路查找的方法。'
    '危险情绪需先确认眼前安全、支持远离危险物并联系可信赖的人及当地紧急支持，不能以线上陪伴取代现实帮助。'
    '历史经历、引用、虚构和明确无当前危险不能仅因出现相关词就当成紧急事件。'
    '普通倾诉照常温和回应；少模板、不反复追问、不夸大情绪或作无依据诊断。'
)


@dataclass
class BoundaryDecision:
    route: str = 'normal'
    reply: str | None = None


class BoundaryPolicy:
    def __init__(self):
        self.risk = None
        self.last_route = 'normal'
        self.fiction = False
        self.other_context = False
        self.prompt_hint = ''
        self.literary_analysis = False

    def assess(self, text: str) -> BoundaryDecision:
        self.prompt_hint = ''
        self.literary_analysis = False
        clean = _mask_quoted(text)
        fictional = bool(re.search(r'故事|小说|剧本|台词|假设|假如|影评|电影里人物', clean))
        current_risk_pattern = r'(?:我(?:现在|此刻|今天|真的)|(?:现在|此刻|今天)(?:我)?).{0,15}(?:伤害自己|自杀|轻生|不想活|想死|结束生命)'
        real_now = bool(re.search(current_risk_pattern, clean))
        if fictional and not real_now:
            self.fiction = True
        if re.search(r'现实|真的', clean):
            self.fiction = False
        denial = bool(re.search(r'(?:没有|并无).{0,12}(?:伤害自己|自杀|轻生).{0,5}(?:想法|念头|打算)|'
                                r'(?:不会|不想|不打算|不准备)(?:伤害自己|自杀|轻生)', clean))
        historical = bool(re.search(r'以前|曾经|去年|年前|当时|过去', clean)) and not real_now
        risk_pattern = (r'我.{0,15}(?:想伤害自己|想自杀|想轻生|想死(?!磕|记|你|他|她)|轻生的想法|自杀的想法|'
                        r'伤害自己的念头|伤害自己的想法|不想活|结束生命(?!科学))')
        self_risk = any(
            re.search(risk_pattern, clause)
            and (not re.search(r'以前|曾经|去年|年前|当时|过去', clause)
                 or re.search(current_risk_pattern, clause))
            and not re.search(r'(?:没有|并无).{0,12}(?:伤害自己|自杀|轻生)|'
                              r'(?:不会|不想|不打算|不准备)(?:伤害自己|自杀|轻生|死)', clause)
            for clause in re.split(r'[，,。；;]', clean))
        other_risk = bool(re.search(r'(?:朋友|同事|同学|家人|室友).*(?:想自杀|想伤害自己|想轻生)', clean))
        if not (fictional and not real_now):
            if self_risk:
                self.risk = 'crisis'
            elif other_risk and not historical:
                self.risk = 'third_party_crisis'
        connected = bool(re.search(r'已经联系.{0,8}(?:家人|朋友)|家人.{0,5}陪着', clean))
        if self.risk and ((denial and self.risk == 'crisis') or connected):
            # Never downgrade a simultaneous explicit current risk statement.
            if not self_risk:
                self.risk = None
                return self._decision('recovery', '谢谢你告诉我现在的情况，我们可以按你希望的节奏聊。联系到现实支持是重要的一步，但不等于危险已经解除；如果仍可能伤害自己或他人，请及时让身边可信赖的人和当地紧急支持介入。')
        if self.risk == 'crisis':
            if self.last_route == 'crisis':
                if re.search(r'保密|秘密|别.{0,5}找别人', clean):
                    return self._decision('crisis', '我听见你不想让别人知道，但不能用保密承诺或陪聊代替眼前的安全。先与危险物保持距离，请联系一个可信赖的人来陪你；如果可能马上行动，请直接联系当地紧急服务。')
                if re.search(r'拨通|已经联系|正在过来', clean):
                    return self._decision('crisis', '你已经开始联系现实支持了，这一步很重要。等待时先与危险物保持距离，尽量保持电话接通；如果仍可能马上伤害自己，请立即联系当地紧急服务，不要只等聊天回复。')
                if re.search(r'还没|还没有|一个人|没人|都睡|联系谁', clean):
                    return self._decision('crisis', '先与危险物保持距离，给可信赖的人打电话或发一句：“我现在不安全，需要你来陪我。”如果暂时联系不上、身边无人或可能马上行动，请联系当地紧急服务；我不能替你实际联络。')
                return self._decision('crisis', '现在先把安全放在前面：与危险物保持距离，并让一个可信赖的人知道你需要现场陪伴。如果你觉得控制不住、已经受伤或可能马上行动，请立即联系当地急救或紧急服务。')
            return self._decision('crisis', '听到你现在可能伤害自己，我很在意你的安全。请先远离可能伤到自己的物品和位置，尽快联系一个可信赖的人到你身边；如果已经受伤、过量服药或可能马上行动，请立即联系当地急救或紧急服务。你现在能先联系谁来陪你？我不能替代现场帮助。')
        if self.risk == 'third_party_crisis':
            if self.last_route == 'third_party_crisis':
                return self._decision('third_party_crisis', '联系不上本人时，请尽快通知他身边可信赖的人，把具体担忧说清楚。若可能有眼前危险，联系对方所在地的紧急服务，而不是只等待消息；我无法代你联系或确认他的状态。')
            return self._decision('third_party_crisis', '这需要尽快连接现实中的帮助：尝试联系对方身边可信赖的人，告知你担心的具体情况。如果可能有眼前危险或已经受伤，请联系对方所在地的紧急服务，不要只等待聊天回复；我无法监控或替你联系他。')
        if not fictional and not denial and not historical and re.search(r'撑不住了|不想再醒来', clean):
            return self._decision('safety_check', '听起来你已经很吃力了。你说撑不住，是想休息或倾诉，还是现在有伤害自己的想法？我先听你说。')
        if self.fiction and not real_now:
            self.literary_analysis = bool(re.search(r'分析|解读|点评|动机', clean))
            self.prompt_hint = ('本轮是明确的虚构创作、台词或作品分析。只回应角色、文本和写作任务；'
                                '不要把角色的话当成用户本人求助，不要向用户附加心理热线或危机建议。'
                                '允许故事中角色有感官经历，但不能宣称现实中的你有这些经历。')
            return self._decision('normal')
        if re.search(r'(?:他|她|同学|同事|前任|朋友)', clean):
            self.other_context = True
        private_target = self.other_context and not re.search(r'我(?:的|自己).*(?:地址|住址|收件|订单)', clean)
        if private_target and re.search(r'查|找|猜|推断|定位|跟踪', clean) and re.search(r'住址|住处|宿舍|家庭地址|家庭住址', clean):
            if self.last_route == 'privacy':
                return self._decision('privacy', '即使线索公开，我也不会帮你拼凑不愿联系者的私人位置。请尊重对方的选择；如有正当事务，使用获得同意的渠道处理。')
            return self._decision('privacy', '我不能帮助查找或推断不愿联系者的私人住处，也不会提供绕路查找的方法。如果有正当事务，可以使用对方同意的联系渠道，并尊重不联系的选择。')
        if re.search(r'只依赖你|只和你|只跟你|不再联系朋友|不联系朋友', clean):
            return self._decision('dependency', '很高兴聊天能带来支持，不过我不希望你只依赖我。也给现实中的朋友、家人和你自己的生活留些位置；和他们见面或暂时不聊天，都不需要感到愧疚。')
        if re.search(r'保证|承诺|能不能|你.{0,10}(?:能|会)', clean) and re.search(r'永远|24小时|随时|一直在线|永久', clean):
            if self.last_route == 'availability':
                return self._decision('availability', '不能保证一直在线。等不到回复时，联系现实中信任的人会更可靠；我们也可以提前整理一个支持名单。')
            return self._decision('availability', '我可以在这次对话里尽力回应，但无法保证永远在线或立即回复。服务没响应时，可以联系现实中信任的人，提前给自己留一个可用的支持渠道。')
        if re.search(r'保证|百分之百|包我', clean) and re.search(r'一定|录取|通过|成功|获奖|赚钱', clean):
            return self._decision('result_guarantee', '我不能保证结果，但可以帮你做能落实的准备，例如检查材料、梳理要点或模拟练习。你想先检查哪一项？')
        if re.search(r'你.{0,12}(?:来|到).{0,10}(?:陪我|宿舍|我家)|你能现在.*陪我', clean):
            return self._decision('physical_visit', '我不能到现场，但可以在这里陪你聊，或帮你安排眼前的小事。你愿意先说说现在最需要哪种帮助吗？')
        if re.search(r'你.{0,12}(?:吃过|喝过|尝得|尝过|坐过|闻过|看得见)', clean):
            if self.last_route == 'physical_experience':
                return self._decision('physical_experience', '我没有这类亲身感官体验。你可以描述自己的感受，我会据此讨论，不把想象说成实际经历。')
            return self._decision('physical_experience', '我没有真实身体和感官，也没有亲自吃喝或出行的经历；可以根据你的描述讨论感受，或帮你写明确标注的虚构内容。')
        shared = re.search(r'(?:我们|你和我).{0,15}(?:一起|当时|曾经)|一起.{0,12}(?:你记得|你还记得)', clean)
        if shared and (re.search(r'记得|回忆|当时|描述|曾经', clean) or self.last_route == 'physical_history'):
            if self.last_route == 'physical_history':
                return self._decision('physical_history', '那些细节需要以你的真实经历为准，我不能替我们编出共同回忆。你可以讲一个印象深的片段，我会接着你的描述聊。')
            return self._decision('physical_history', '我没有和你一起在线下经历过这些，不能把想象说成共同回忆。如果你愿意，可以讲讲你当时看到的事，我会根据你的描述聊。')
        return self._decision('normal')

    def review_output(self, reply: str) -> tuple[str, str | None]:
        """Only intercept user-directed crisis advice in an explicit literary analysis."""
        if self.literary_analysis and re.search(
                r'(?:建议你|如果你|请确保|请务必).{0,120}(?:求助|心理|专业帮助|安全|热线)', reply, re.S):
            return ('就这段台词来看，角色在表达强烈的痛苦与内心冲突；具体动机还需要结合前后情节。'
                    '分析时可以区分角色真正想改变的处境、这句话对其他人物的影响，以及作品采用的表达方式。',
                    'literary_context_advice')
        return reply, None

    def _decision(self, route, reply=None):
        self.last_route = route
        return BoundaryDecision(route, reply)
