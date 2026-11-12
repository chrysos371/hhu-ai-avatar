"""Read GGUF metadata only: no tensor allocation, inference or CUDA context."""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
model=ROOT/'models/Qwen3-4B-Q4_K_M.gguf'
out=BASE/'审计/工作目录/001-工具调用调查'
assert not (out/'gguf-template.json').exists()
with model.open('rb') as f:
    def number(fmt):
        n=struct.calcsize(fmt);raw=f.read(n)
        if len(raw)!=n:raise ValueError('truncated GGUF metadata')
        return struct.unpack('<'+fmt,raw)[0]
    def string():
        n=number('Q')
        if n>16*1024*1024:raise ValueError('metadata string too large')
        raw=f.read(n)
        if len(raw)!=n:raise ValueError('truncated GGUF string')
        return raw.decode()
    def value(kind,keep=True):
        if kind==8:return string() if keep else f.seek(number('Q'),1)
        if kind==9:
            item,n=number('I'),number('Q')
            if n>10_000_000:raise ValueError('metadata array too large')
            for _ in range(n):value(item,False)
            return None
        formats={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
        return number(formats[kind])
    assert f.read(4)==b'GGUF'
    version=number('I');assert version==3
    tensors,count=number('Q'),number('Q');assert count<100_000
    selected={}
    for _ in range(count):
        name=string();kind=number('I');keep=name in ('tokenizer.chat_template','general.name')
        item=value(kind,keep)
        if keep:selected[name]=item
    end=f.tell()
template=selected['tokenizer.chat_template']
assert '<tool_call>' in template and 'tools' in template and 'tool_response' in template
(out/'embedded-chat-template.jinja').write_text(template)
record={'model':str(model),'gguf_version':version,'tensor_count':tensors,'metadata_count':count,
    'metadata_bytes_read_or_skipped':end,'general_name':selected['general.name'],
    'template_sha256':hashlib.sha256(template.encode()).hexdigest(),
    'tensor_allocation':False,'native_inference_calls':0,'GPU_context_created':False,
    'finding':'embedded template declares tools and XML tool_call/tool_response; generation quality and SDK adaptation untested'}
(out/'gguf-template.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record,ensure_ascii=False))
