"""Two-value arithmetic over authenticated user statements, never model text.

Finite complete grammars; unsupported changes fail closed. No eval inputs,
network, profile writes, reminder reads or external actions are involved.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
import re

from ..cancellation import Cancelled

_LABEL = r'[\u4e00-\u9fff]{1,12}?'
_NUMBER = r'[0-9]{1,32}(?:\.[0-9]{1,12})?'
_UNIT = r'张|个|件|份|升|元'
_MATERIAL = re.compile(r'材料清单为('+_LABEL+r')('+_NUMBER+r')('+_UNIT+r')、'
    r'('+_LABEL+r')('+_NUMBER+r')('+_UNIT+r')')
_BUDGET = re.compile(r'('+_LABEL+r')预算上限为('+_NUMBER+r')元[，,]'
    r'('+_LABEL+r')预算上限为('+_NUMBER+r')元')
_UPDATE = re.compile(r'(?:数量更新|更正|更新)[：:]('+_LABEL+r')(?:预算上限)?改为('
    +_NUMBER+r')('+_UNIT+r')[，,]('+_LABEL+r')不变')
_QUESTIONS = {
    'material': re.compile(r'(?:根据清单|根据记录|根据资料)[，,](?:更新后)?两种材料的数量合计是多少[？?]只回答数字[。.]?'),
    'budget': re.compile(r'(?:更正后|更新后)?两项预算上限合计是多少元[？?]只回答数字[；;]没有资料则回答无法确认[。.]?'),
}


def requested(text):
    if not isinstance(text,str) or not 0 < len(text) <= 200:
        return None
    return next((kind for kind,pattern in _QUESTIONS.items() if pattern.fullmatch(text.strip())), None)


@dataclass(frozen=True)
class Calculation:
    reply: str
    metadata: dict
    source_message_ids: tuple[int,...]


def compute(text, sources):
    kind = requested(text)
    if kind is None:
        return None
    values, ids, valid, reason = {}, [], False, 'no_authenticated_source_values'
    for ident, source, authenticated in sources:
        body = re.sub(r'[。.]请只确认[。.]?\s*$', '', source.strip())
        root = (_MATERIAL if kind == 'material' else _BUDGET).fullmatch(body)
        relevant = root is not None or ('材料清单' in source if kind == 'material' else '预算上限' in source)
        relevant = relevant or any(label in source for label in values)
        if not relevant:
            continue
        ids.append(ident)
        if authenticated is not True:
            valid, reason = False, 'unverified_material_source'; continue
        if root:
            fields = root.groups()
            if kind == 'budget': fields = fields[:2]+('元',)+fields[2:]+('元',)
            a,x,unit_a,b,y,unit_b = fields
            values = {a:(x,unit_a), b:(y,unit_b)}
            ids = [ident]
            valid = a != b and unit_a == unit_b
            reason = 'source_values' if valid else 'duplicate_label_or_unit_mismatch'
            continue
        update = _UPDATE.fullmatch(body)
        if update and valid:
            label,value,unit,unchanged = update.groups()
            if (label in values and unchanged in values and label != unchanged
                    and unit == values[label][1]):
                values[label] = (value,unit)
                continue
        valid, reason = False, 'unsupported_or_ambiguous_source_change'
    proof = dict(version=1, operation='sum_two_source_values', source_message_ids=ids,
        kind=kind, calculation_verified=valid, general_semantic_verifier=False,
        business_mutations=False, inputs=[], reason=reason)
    reply = '无法确认'
    if valid and len(values) == 2:
        with localcontext() as context:
            context.prec = 128
            total = sum((Decimal(value) for value,unit in values.values()), Decimal(0))
        reply = format(total, 'f')
        if '.' in reply: reply = reply.rstrip('0').rstrip('.')
        proof['inputs'] = [dict(label=label,value=value,unit=unit) for label,(value,unit) in values.items()]
        proof['reason'] = 'authenticated_two_value_decimal_sum'
    else: proof['calculation_verified'] = False
    return Calculation(reply, proof, tuple(ids))


def build(memory, *, text, user_id, revision):
    if requested(text) is None:
        return None
    from .conversation_context import ConversationContextStore
    reader = ConversationContextStore(memory)
    rows = memory._conn.execute('SELECT m.id,m.role,m.content,m.session_id,m.context_tracked,'
        'r.context_revision AS result_revision,r.result_json FROM memory_messages m '
        'LEFT JOIN memory_chat_results r ON r.message_id=m.id '
        'WHERE m.id<? ORDER BY m.id DESC LIMIT 128', (user_id,)).fetchall()
    sources = []
    for index in range(len(rows)-1,-1,-1):
        user = rows[index]
        assistant = rows[index-1] if index else None
        if user['role'] != 'user' or requested(user['content']) is not None:
            continue
        authenticated = False
        if assistant is not None and assistant['role'] == 'assistant':
            try: authenticated = reader._result(assistant,user,'current_user',revision) is not None
            except (TypeError,ValueError,OverflowError,RecursionError): pass
        sources.append((user['id'],user['content'],authenticated))
    return compute(text,sources)


class CalculationReader:
    def __init__(self,memory,*,text,user_id,session_id,revision):
        self.memory,self.text,self.user_id,self.session_id,self.revision=memory,text,user_id,session_id,revision
        self.result=self._read()

    def _read(self):
        conn=self.memory._conn;owned=not conn.in_transaction
        if owned:conn.execute('BEGIN')
        try:
            row=conn.execute('SELECT role,content,session_id FROM memory_messages WHERE id=?',(self.user_id,)).fetchone()
            latest=conn.execute("SELECT MAX(id) FROM memory_messages WHERE role='user'").fetchone()[0]
            if (self.memory.context_revision!=self.revision or not row or row['role']!='user'
                    or row['content']!=self.text or row['session_id']!=self.session_id or latest!=self.user_id):
                raise Cancelled('calculation source changed')
            return build(self.memory,text=self.text,user_id=self.user_id,revision=self.revision)
        finally:
            if owned:conn.rollback()

    def ensure_current(self):
        if self._read()!=self.result:raise Cancelled('calculation evidence changed')
