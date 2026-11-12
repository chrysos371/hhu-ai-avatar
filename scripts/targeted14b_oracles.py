"""Small deterministic checks. These never approve semantic safety/style."""
import json
import re


def json_object(text, expected):
    decoder=json.JSONDecoder(); parsed=None
    for m in re.finditer(r'\{',text):
        try:
            parsed,_=decoder.raw_decode(text[m.start():]);break
        except ValueError:continue
    try:whole=json.loads(text)
    except ValueError:whole=None
    # Reject booleans masquerading as numbers; compare both value and Python type.
    values=(isinstance(parsed,dict) and set(parsed)==set(expected)
            and all(type(parsed[k]) is type(v) and parsed[k]==v for k,v in expected.items()))
    return {'expected':expected,'observed':parsed,'values_correct':bool(values),
            'whole_reply_json':isinstance(whole,dict),'key_order_correct':isinstance(parsed,dict) and list(parsed)==list(expected)}


def budget(text, expected):
    numbers=[int(v) for v in re.findall(r'\d+',text)]
    return {'expected':list(expected),'observed_integers':numbers,'strict_numeric_pair':numbers==list(expected),
            'nonempty_lines':len([x for x in text.splitlines() if x.strip()]),
            'exactly_two_nonempty_lines':len([x for x in text.splitlines() if x.strip()])==2,
            'semantic_limit':'extra arithmetic may require AI review; not an automatic overall correctness verdict'}


def check_case(id, replies):
    text=replies[-1]
    if id=='lora-dev-09':return budget(text,(3,30+3*20))
    if id=='confirm-budget':return budget(text,(2,40+2*25))
    if id=='lora-dev-10':return json_object(text,{'code':'R8','count':4,'owner':None})
    if id=='accept-new-layout':return json_object(text,{'usable':960-2*24-2*3-2*12,'card':(960-2*24-2*3-2*12)//3})
    if id=='accept-new-draft-chain':
        original=replies[0].strip()
        return {'source':original,'five_chinese_characters':bool(re.fullmatch(r'[\u4e00-\u9fff]{5}',original)),
                'prefix_exact':replies[1].strip()=='未刊·'+original,
                'suffix_exact':replies[2].strip()==original+'·未刊'}
    return None
