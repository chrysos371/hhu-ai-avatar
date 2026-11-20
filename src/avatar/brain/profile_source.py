"""Finite profile replies and hashes of the actual supporting fact rows.

Historical replay reconstructs the old projection from its dependencies; it
does not replace an old answer with today's profile or trust copied JSON data.
"""
from hashlib import sha256
import json

from ..cancellation import Cancelled
from .profile_grounding import lookup_profile, review_profile_reply, acknowledge_disclosure, _ordinary_preference


def fingerprint(value):
    return sha256(value.encode('utf-8')).hexdigest()


def projection(rows):
    values={}
    for row in rows:
        if ': ' not in row['content']: continue
        key,value=row['content'].split(': ',1)
        bucket=values.setdefault(key,[])
        if value not in bucket and (not bucket or key in ('偏好','爱好')):bucket.append(value)
    return {key:'；'.join(items) for key,items in values.items()}


def evidence(rows,action,reply):
    return dict(version=1,owner='current_user',action=action,
        sources=[dict(fragment_id=r['id'],content_sha256=fingerprint(r['content'])) for r in rows],
        reply_sha256=fingerprint(reply),general_semantic_verifier=False,
        scope='finite_profile_lookup_or_whole_copied_preference_replacement')


class ProfileReader:
    def __init__(self,memory):
        self.memory=memory
        self.rows=self._read()
        self.profile=projection(self.rows)

    def _read(self):
        return [dict(r) for r in self.memory._conn.execute("SELECT id,content FROM memory_fragments "
            "WHERE memory_type='user_profile' AND status='active' ORDER BY created_at DESC,id DESC LIMIT 129")]

    def ensure_current(self):
        if self._read()!=self.rows:raise Cancelled('supporting profile rows changed')

    def proof(self,action,reply):
        self.ensure_current()
        return evidence(self.rows,action,reply)


def verified_content(memory,result,*,user_id,assistant_id,text,scope,revision):
    from .release_history import content,canonical
    try:
        proof=result['profile_contract'];sources=proof['sources']
        if (scope!='current_user' or result['speaker_attribution'].get('turn_tools_allowed') is not True
                or type(sources) is not list or len(sources)>128):return None
        ids=[s['fragment_id'] for s in sources]
        if any(type(i) is not int or i<=0 for i in ids) or len(set(ids))!=len(ids):return None
        rows=[]
        for ident in ids:
            row=memory._conn.execute("SELECT id,content FROM memory_fragments WHERE id=? AND memory_type='user_profile'",(ident,)).fetchone()
            if row is None:return None
            rows.append(dict(row))
        profile=projection(rows)
        reply,action=lookup_profile(text,profile)
        if reply is None:
            reply,action=acknowledge_disclosure(text,profile)
        if reply is None and proof.get('action')=='copied_preference':
            for key in ('偏好','爱好'):
                for value in profile.get(key,'').split('；'):
                    if _ordinary_preference(value) and value.startswith('喜欢'):
                        checked,found=review_profile_reply(text,'我'+value+'。',profile)
                        if found=='copied_preference':reply,action=checked,found;break
                if reply is not None:break
        if (reply is None or reply!=result['reply']
                or canonical(proof)!=canonical(evidence(rows,action,reply))):return None
        deps={r[0] for r in memory._conn.execute("SELECT source_id FROM memory_response_context "
            "WHERE message_id=? AND source_type='fragment'",(assistant_id,))}
        if not set(ids)<=deps:return None
        return content(reply,mode='rules_profile_source',source_id=user_id)
    except (KeyError,TypeError,ValueError,OverflowError,RecursionError):return None
