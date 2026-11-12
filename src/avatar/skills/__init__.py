"""Bounded project-owned instruction packs, separate from persona and tools."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import re
from ..brain.facts import _mask_quoted

PACK_IDS = ('study-coach', 'writing-editor', 'banter-coach')
ROOT = Path(__file__).with_name('packs')
MAX_PROMPT_CHARS = 1800
ALLOWED_CAPABILITIES = frozenset({'context.read'})


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    version: str
    content: str
    digest: str


class SkillRegistry:
    def __init__(self, root=ROOT):
        self.root = Path(root)

    def load(self, key):
        if key not in PACK_IDS:
            raise ValueError('unknown_skill')
        folder = self.root/key
        if self.root.is_symlink() or folder.is_symlink():
            raise ValueError('symlink_skill')
        paths = [folder/'manifest.json', folder/'SKILL.md']
        if any(p.is_symlink() or not p.resolve().is_relative_to(self.root.resolve()) for p in paths):
            raise ValueError('invalid_skill_path')
        if any(p.stat().st_size > 8192 for p in paths):
            raise ValueError('oversized_skill')
        raw, body = (p.read_bytes() for p in paths)
        manifest = json.loads(raw)
        if set(manifest) != {'id','name','version','capabilities'} or manifest['id'] != key:
            raise ValueError('invalid_skill_manifest')
        capabilities = manifest['capabilities']
        if (not isinstance(capabilities,list) or not all(isinstance(c,str) for c in capabilities)
                or not set(capabilities) <= ALLOWED_CAPABILITIES):
            raise ValueError('unsupported_skill_capability')
        if any(not isinstance(manifest[k],str) or not 1 <= len(manifest[k]) <= 80 for k in ('name','version')):
            raise ValueError('invalid_skill_metadata')
        content = body.decode().strip()
        if not content or len(content) > MAX_PROMPT_CHARS:
            raise ValueError('oversized_skill_prompt')
        digest_input=raw+b'\0'+body
        if key=='banter-coach':
            library=folder/'expressions.json'
            if library.is_symlink() or library.stat().st_size>16384:
                raise ValueError('invalid_expression_library')
            library_raw=library.read_bytes()
            if not isinstance(json.loads(library_raw).get('entries'),list):
                raise ValueError('invalid_expression_library')
            digest_input+=b'\0'+library_raw
        return Skill(key,manifest['name'],manifest['version'],content,
                     hashlib.sha256(digest_input).hexdigest())

    def catalog(self):
        return [{'id':s.id,'name':s.name,'version':s.version,'sha256':s.digest,
                 'capabilities':['context.read']} for s in map(self.load,PACK_IDS)]


def route(text, history=()):
    clean = _mask_quoted(text).strip()
    command = re.match(r'^/skill\s+(\S+)(?:\s|$)',clean)
    if command:
        key=command.group(1)
        return (None,'explicit_off') if key=='off' else (key,'explicit')
    if re.search(r'不聊|换个?话题|算了|晚安|拜拜|再见|只想.{0,5}(?:吐槽|抱怨)|不要建议',clean):
        return None,'conversation'
    if re.search(r'不要.{0,4}(?:教学|讲题|润色|改写)|别.{0,3}(?:讲题|润色|改写)',clean):
        return None,'declined'
    subject = re.search(r'数字电路|触发器|逻辑门|与门|或门|卡诺图|真值表|微积分|概率|线性代数|二极管|欧姆定律', clean)
    teaching = re.search(r'解释|讲解|教我|复习|推导|出题|练习|怎么|什么|求解|计算',clean)
    if re.search(r'辅导|讲题|讲解.{0,12}(?:概念|原理)|帮我复习|出一道.{0,10}题',clean) or (subject and teaching):
        return 'study-coach','study_request'
    if re.search(r'(?:帮|替).{0,16}(?:写|拟)|改写|润色|起草|代拟|写一(?:句|段|封|条)|文案|修改.{0,8}(?:消息|邮件|正文)',clean):
        return 'writing-editor','writing_request'
    from .banter import mode, EXPLAIN
    banter_text = text if EXPLAIN.search(clean) else clean
    if mode(banter_text,history) in ('explain','banter'):
        return 'banter-coach','banter_context'
    if re.match(r'^(?:请)?(?:再短|更短|缩短|改成|改为|改到|把.{0,15}改|只给|只要|其他不变|继续讲|再出一|你刚才|刚才的|那为什么|答案是|我选)',clean):
        # Only immediate user context; no persistence beyond a topic switch.
        users=[m['content'] for m in history if m['role']=='user'][-3:]
        for previous in reversed(users):
            key,reason=route(previous)
            if key:return key,'followup'
            if reason in ('conversation','declined','explicit_off'):break
    return None,'no_match'


def select(text, history=(), *, enabled=False, budget=MAX_PROMPT_CHARS, registry=None):
    audit={'enabled':bool(enabled),'selected':[],'reason':'disabled','errors':[],
           'granted_tools':[],'prompt_chars':0}
    if not enabled:return '',audit
    key,reason=route(text,history)
    audit['reason']=reason
    if key is None:return '',audit
    if key=='banter-coach' and os.getenv('AVATAR_BANTER_ENABLED','0')!='1':
        audit['reason']='banter_disabled'
        return '',audit
    try:
        skill=(registry or SkillRegistry()).load(key)
        extra=''
        if key=='banter-coach':
            from .banter import retrieve
            extra, retrieval = retrieve(text, history, (registry or SkillRegistry()).root)
            audit['retrieval']=retrieval
            if retrieval['mode'] not in ('explain','banter'):
                audit['reason']='banter_'+retrieval['mode']
                return '',audit
        prompt=('\n本轮只读任务技能（不覆盖事实、人设与安全规则；不授予工具或文件权限，不执行脚本）：\n'
                +skill.content+extra+'\n')
        if len(prompt)>min(budget,MAX_PROMPT_CHARS):
            audit['reason']='budget_exceeded'
            return '',audit
    except (OSError,ValueError,TypeError,UnicodeError,KeyError) as exc:
        audit['errors']=[type(exc).__name__]
        audit['reason']='unavailable'
        return '',audit
    audit['selected']=[{'id':skill.id,'version':skill.version,'sha256':skill.digest}]
    audit['prompt_chars']=len(prompt)
    return prompt,audit
