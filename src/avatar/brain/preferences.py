"""Shared conservative identity for explicit preference objects."""


def canonical_preference_object(value: str) -> str:
    """Normalize only the established consumption aliases; never guess meaning."""
    value = value.strip().rstrip('。！!')
    # Eating bitterness is an activity, not the object 苦. Keep unknowns exact.
    consumables = {'咖啡', '茶', '奶茶', '牛奶', '可乐', '水', '果汁',
                   '苹果', '香蕉', '米饭', '火锅', '辣椒', '巧克力'}
    if value[:1] in ('吃', '喝') and value[1:] in consumables:
        return value[1:]
    return value
