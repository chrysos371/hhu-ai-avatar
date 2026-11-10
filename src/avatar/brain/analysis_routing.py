"""Conservative, inspectable fast route for impersonal factual questions only."""
import re

from .emotion import EmotionEngine


def impersonal_knowledge_question(text):
    if not 1 <= len(text) <= 200:
        return False
    if not re.match(r'^(?:请)?(?:简短)?(?:解释|说明|介绍)|^什么是', text.strip()):
        return False
    if re.search(r'我|咱|俺|本人|你|他|她|朋友|同事|家人|室友|同学|关系|拒绝|失去|分手|情绪|情感|陪伴|记忆|记得|自杀|轻生|自残', text):
        return False
    if EmotionEngine.infer(text) != (0.0, 0.0):
        return False
    return bool(re.search(r'云|雨|大气|水循环|光合作用|重力|电流|Python|排序|算法|数据结构|二进制|加法|乘法|积分|矩阵', text))
