"""Opt-in evaluation wire adapter, never an executor or semantic validator.

GGUF raw XML and native stop remain in the provider trace. Structured OpenAI
messages are an explicit adapter result; this module never approves business
arguments, source authority, tool results or model claims.
"""
import json
import re


class ToolWireError(ValueError):
    pass


def request_tools(data, *, enabled=False):
    tools=data.get('tools')
    history=any(m.get('role')=='tool' or m.get('tool_calls') for m in data.get('messages',[]))
    if (tools or history) and not enabled:
        raise ToolWireError('tool evaluation not enabled')
    if tools is None or tools==[]:
        if history:
            raise ToolWireError('tool history requires current tool schemas')
        return None
    if not isinstance(tools,list) or not 1<=len(tools)<=8:
        raise ToolWireError('tools must be a bounded nonempty list')
    if data.get('stream') or data.get('response_format'):
        raise ToolWireError('tool mode requires nonstreaming without response_format')
    if data.get('tool_choice','auto')!='auto' or data.get('parallel_tool_calls',False) is not False:
        raise ToolWireError('only auto single tool selection is supported')
    names=set()
    for tool in tools:
        if not isinstance(tool,dict) or set(tool)!={'type','function'} or tool['type']!='function':
            raise ToolWireError('invalid function tool declaration')
        fn=tool['function']
        if not isinstance(fn,dict) or set(fn)-{'name','description','parameters','strict'}:
            raise ToolWireError('unsupported function declaration')
        name=fn.get('name');params=fn.get('parameters')
        if (not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',name)
                or name in names or not isinstance(params,dict) or params.get('type')!='object'):
            raise ToolWireError('invalid or duplicate function identity/schema')
        names.add(name)
    return tools


def adapt_completion(text, native_finish_reason, tools, identifier):
    """Return adapted message/finish; strict tool syntax is not intent approval."""
    if not isinstance(text,str):
        raise ToolWireError('native completion is not text')
    plain={'role':'assistant','content':text}
    if not tools:
        return plain,native_finish_reason
    if '<tool_call' not in text and '</tool_call' not in text:
        return plain,native_finish_reason
    match=re.fullmatch(r'\s*<tool_call>\s*(.*?)\s*</tool_call>\s*',text,re.S)
    if not match or native_finish_reason!='stop':
        raise ToolWireError('incomplete, multiple or mixed tool completion')
    def unique(pairs):
        result={}
        for key,item in pairs:
            if key in result:raise ToolWireError('duplicate tool JSON key')
            result[key]=item
        return result
    def constant(value):
        raise ToolWireError('nonfinite JSON constant')
    try:
        value=json.loads(match[1],object_pairs_hook=unique,parse_constant=constant)
    except (ValueError,TypeError) as error:
        raise ToolWireError('invalid tool JSON: '+str(error)) from error
    names={t['function']['name'] for t in tools}
    if (not isinstance(value,dict) or set(value)!={'name','arguments'}
            or not isinstance(value['name'],str) or value['name'] not in names
            or not isinstance(value['arguments'],dict)):
        raise ToolWireError('unknown tool or invalid call shape')
    message={'role':'assistant','content':None,'tool_calls':[{'id':'call_'+identifier,'type':'function',
        'function':{'name':value['name'],'arguments':json.dumps(value['arguments'],ensure_ascii=False,separators=(',',':'))}}]}
    return message,'tool_calls'


def template_messages(messages):
    """Normalize SDK's absent/null assistant tool content without editing wire.

    The embedded text-only Jinja template requires a string. Missing ordinary
    user/system/tool content remains an error rather than an invented message.
    """
    if not isinstance(messages,list) or not messages:
        raise ToolWireError('messages must be a nonempty list')
    result=[]
    for original in messages:
        if not isinstance(original,dict) or original.get('role') not in ('system','user','assistant','tool'):
            raise ToolWireError('unsupported template message role')
        message={'tool_calls':[],'reasoning_content':None}|original
        content=message.get('content')
        if content is None and message['role']=='assistant' and message.get('tool_calls'):
            content=''
        if not isinstance(content,str):
            raise ToolWireError('text content required except assistant tool calls')
        message['content']=content
        result.append(message)
    return result
