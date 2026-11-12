EXPRESSION_HINT = (
    '\nQQ表达约束（服从已有事实、角色和安全边界）：'
    '按当前请求和上下文选择回应方式，不凭个别情绪词给人下结论。'
    '要文案、改写、步骤时先给可直接使用的产物，缺失信息留占位；'
    '只想倾听时接住具体内容，不安排任务、不连续追问；'
    '用户明确不要建议时，不再给解决办法、休息安排或劝其别在意；只回应具体遭遇，不淡化感受。'
    '换话题不是告别，告别不是睡觉；仅在用户明确要睡觉或说晚安时回应晚安，不推测时间。'
    '吃饭、洗澡、出门按实际活动简短回应，不附加睡觉休息；明确告别不另开话题。'
    '问用户叫什么须回答用户姓名，不能用角色名字替代；无用户姓名记录就直说不确定。'
    '人设示例只作语气参考，不能逐字套用或带入时间、活动、关系。普通闲聊可以轻松，但不强行玩梗。'
    '不扮演群管理员，不推测未收到的群聊内容，不编造线下经历；'
    '自然表达，不宣读策略或情绪评分。需要解释或完成任务时允许超过三句话。\n'
)


def expression_context(text):
    """Small current-turn hints; never route tasks or safety into canned replies."""
    import re
    from ..brain.facts import _mask_quoted

    clean = _mask_quoted(text)
    hints = []
    # Formatting and current-turn instructions must win over an earlier output.
    if re.search(r'只(?:输出|给|要)|不要(?:解释|标点)|四字|字数|格式', clean):
        hints.append('最新一轮输出格式替代上一轮格式；重新完成当前请求，不复读上一份答案。')
    if re.search(r'只想.{0,6}(?:抱怨|吐槽|倾诉)|(?:不要|别|不想听).{0,4}(?:建议|办法)|先别教', clean):
        hints.append('本轮只倾听：具体承接用户原话，不给建议、不劝别在意、不复读上轮安慰。')
    if re.search(r'不聊.{0,8}了|换个.{0,5}话题', clean):
        hints.append('用户只结束旧话题，并未告别。停止旧话题，不劝去休息或睡觉。')
    if re.search(r'我叫什么|我.{0,6}(?:名字|爱喝什么|喜欢什么)|你知道我叫什么', clean):
        hints.append('本轮询问用户资料，不是角色资料。只能引用已确认记忆或用户当前原话；没有依据就回答不记得，禁止补全不存在的姓名或饮食偏好。')
    if re.search(r'其他不变|不要丢|再短|更短|缩短', clean):
        hints.append('改稿只压缩措辞，不删除仍有效的日期、上午下午等时段、时间和事项；除用户明确更正的字段外，其余事实必须保留。')
    task = re.search(r'帮.{0,5}(?:写|拟)|翻译|改写|台词|故事|小说|代码', clean)
    if not task and re.search(r'拜拜|再见|晚点再聊|回头聊|我先去|我去.{0,5}(?:吃饭|洗澡|食堂)', clean):
        hints.append('用户本轮离开：一句简短收尾，不提问、不挽留、不约定主动发消息；没有明确睡觉则不说晚安。')
    return ('\n本轮语境：' + ''.join(hints)) if hints else ''


def expression_history(text, history):
    """Drop stale assistant wording only for explicit fresh response instructions.

    User evidence stays intact. Edits referring to a prior draft keep that draft.
    """
    import re
    from ..brain.facts import _mask_quoted
    clean = _mask_quoted(text)
    if re.search(r'再|改成|改为|上一|刚才那|之前那|更短|缩短|其他不变|保留', clean):
        return history
    if re.search(r'主题(?:是|为)|只输出JSON[:：]', clean) and re.search(r'只(?:输出|给|要)|字数|格式', clean):
        return []  # A self-contained fresh output must not inherit old formatting instructions.
    fresh = bool(expression_context(text))
    return [m for m in history if m['role'] != 'assistant'] if fresh else history
