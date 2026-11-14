"""Read both GGUF headers without allocating tensors or constructing a model."""
import json
import struct

from native_common import ROOT,WORK,WEIGHTS,REGISTRY,read,digest


def header(path):
    with path.open('rb') as stream:
        def number(fmt):
            size = struct.calcsize(fmt); raw = stream.read(size)
            if len(raw) != size: raise ValueError('truncated GGUF metadata')
            return struct.unpack('<'+fmt,raw)[0]
        def string():
            size = number('Q')
            if size > 16*1024*1024: raise ValueError('metadata string too large')
            raw = stream.read(size)
            if len(raw) != size: raise ValueError('truncated GGUF string')
            return raw.decode()
        def value(kind,keep=True):
            if kind == 8: return string() if keep else stream.seek(number('Q'),1)
            if kind == 9:
                item,size = number('I'),number('Q')
                if size > 10_000_000: raise ValueError('metadata array too large')
                for _ in range(size): value(item,False)
                return None
            return number({0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}[kind])
        assert stream.read(4) == b'GGUF'
        version = number('I'); assert version == 3
        tensors,count = number('Q'),number('Q'); assert count < 100_000
        selected = {}
        for _ in range(count):
            name = string(); kind = number('I')
            keep = name in ('tokenizer.chat_template','general.name')
            item = value(kind,keep)
            if keep: selected[name] = item
        return selected,version,tensors,count,stream.tell()


def main():
    weights = read(WEIGHTS)
    for spec in read(REGISTRY)['models']:
        short = '4b' if spec['model_id'] == 'qwen3-4b-q4_k_m' else '14b'
        template_path = WORK/(short+'-embedded-chat-template.jinja')
        metadata_path = WORK/(short+'-template-metadata.json')
        assert not template_path.exists() and not metadata_path.exists()
        weight = next(w for w in weights['models'] if w['model_id'] == spec['model_id'])
        path = ROOT/'models'/('qwen3-'+short+'-gguf')/spec['file']
        assert path.stat().st_size == weight['bytes'] and weight['sha256'] == spec['sha256']
        selected,version,tensors,count,end = header(path)
        template = selected['tokenizer.chat_template']; assert 'enable_thinking' in template
        template_path.write_text(template)
        record = {'model_id':spec['model_id'],'model_path':str(path),'gguf_version':version,
            'tensor_count':tensors,'metadata_count':count,'metadata_bytes_read_or_skipped':end,
            'general_name':selected['general.name'],'template_sha256':digest(template_path),
            'previous_weight_identity_receipt_sha256':digest(WEIGHTS),'tensor_allocation':False,
            'model_construction':False,'native_inference_calls':0,'GPU_context_created_by_header_parser':False}
        metadata_path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        print(short,'GGUF metadata/template read;0 tensor allocation/inference;template',record['template_sha256'])


if __name__ == '__main__':
    main()
