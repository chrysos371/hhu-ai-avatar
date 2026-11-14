"""Download one pinned base and verify weights/config/index without tensor allocation."""
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import urllib.request

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
PREPARATION=BASE/'审计/工作目录/003-环境与基础权重'
WORK=PREPARATION/'model-v1'
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def header(path):
    with path.open('rb') as f:
        length=struct.unpack('<Q',f.read(8))[0];assert 0<length<64*1024*1024
        values=json.loads(f.read(length))
    tensors={k:v for k,v in values.items() if k!='__metadata__'};assert tensors
    widths={'BF16':2,'F16':2,'F32':4,'F64':8,'I64':8,'I32':4,'I16':2,'I8':1,'U8':1,'BOOL':1}
    intervals=[]
    for name,v in tensors.items():
        assert v['dtype'] in widths and all(type(n) is int and n>=0 for n in v['shape'])
        start,end=v['data_offsets'];assert type(start) is int and type(end) is int and 0<=start<=end
        assert end-start==math.prod(v['shape'])*widths[v['dtype']]
        intervals.append((start,end))
    intervals.sort();assert intervals[0][0]==0
    assert all(a[1]==b[0] for a,b in zip(intervals,intervals[1:]))
    assert 8+length+intervals[-1][1]==path.stat().st_size
    return tensors,intervals[-1][1]


def main():
    WORK.mkdir(exist_ok=False)
    protocol=json.loads((PREPARATION/'preparation-protocol.json').read_text());spec=protocol['model']
    target=ASSETS/'models'/spec['local_name'];assert not target.exists()
    output=WORK/'model-preparation.json'
    result={'status':'running','scope':'pinned download/hash/header only; no model allocation',
        'repo':spec['repo'],'revision':spec['revision'],'target':str(target),
        'model_constructions':0,'CUDA_allocation':False,'training_steps':0}
    write(output,result)
    try:
        url=f"https://huggingface.co/api/models/{spec['repo']}/revision/{spec['revision']}?blobs=true"
        with urllib.request.urlopen(url,timeout=60) as stream:metadata=json.load(stream)
        assert metadata['sha']==spec['revision'];write(WORK/'pinned-upstream-metadata.json',metadata)
        selected=[f for f in metadata['siblings'] if f['rfilename'].endswith(('.json','.safetensors','.txt','.jinja')) or f['rfilename'] in ('LICENSE','README.md')]
        assert all(Path(f['rfilename']).name==f['rfilename'] for f in selected)
        weights={f['rfilename']:f['lfs']['sha256'] for f in selected if f['rfilename'].endswith('.safetensors')}
        assert weights==spec['sha256']
        names=[f['rfilename'] for f in selected]
        assert {'config.json','tokenizer.json','tokenizer_config.json','model.safetensors.index.json'}<=set(names)
        os.environ['HF_HOME']=str(ASSETS/'cache/huggingface')
        os.environ['HF_HUB_CACHE']=str(ASSETS/'cache/huggingface/hub')
        os.environ['HF_XET_CACHE']=str(ASSETS/'cache/huggingface/xet')
        os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
        from huggingface_hub import snapshot_download
        snapshot_download(spec['repo'],revision=spec['revision'],local_dir=target,
            cache_dir=ASSETS/'cache/huggingface/hub',allow_patterns=names,max_workers=2,token=False)
        verified=[];tensors={};payload_bytes=0;dtypes=Counter()
        for f in selected:
            p=target/f['rfilename'];assert p.is_file();actual=sha(p)
            assert p.stat().st_size==f.get('lfs',{}).get('size',f.get('size'))
            if f.get('lfs'):assert actual==f['lfs']['sha256']
            else:
                raw=p.read_bytes();blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
                assert blob==f['blobId']
            verified.append({'path':f['rfilename'],'bytes':p.stat().st_size,'sha256':actual,'git_blob_sha1':f.get('blobId')})
            if p.suffix=='.safetensors':
                values,size=header(p);assert not (set(values)&set(tensors))
                payload_bytes+=size;dtypes.update(v['dtype'] for v in values.values())
                tensors.update({name:p.name for name in values})
        index=json.loads((target/'model.safetensors.index.json').read_text())
        assert index['weight_map']==tensors and index['metadata']['total_size']==payload_bytes
        assert set(index['weight_map'].values())==set(weights)
        entry={'name':'4b','repo':spec['repo'],'revision':spec['revision'],'local_name':spec['local_name'],
            'gpus':1,'status':'locked','license':metadata.get('cardData',{}).get('license'),
            'files':[r for r in verified if r['path'] in weights],
            'assets':[r for r in verified if r['path'] not in weights]}
        write(WORK/'models.lock.json',{'models':[entry],
            'generation':json.loads((ROOT/'experiments/style/models.json').read_text())['generation'],
            'scope':'C51 base preparation; assets include the actual shard index','default_activation_authorized':False})
        write(target/'verified-revision.json',{'model_id':spec['repo'],'revision':spec['revision'],
            'files_sha256':{r['path']:r['sha256'] for r in verified},'scope':'independently hashed pinned source, no tensor allocation'})
        result.update(status='complete',upstream_metadata_sha256=sha(WORK/'pinned-upstream-metadata.json'),
            files=verified,weight_shards=len(weights),tensor_count=len(tensors),tensor_dtypes=dict(dtypes),
            tensor_payload_bytes=payload_bytes,shard_index_verified=True,all_git_or_LFS_identities_verified=True)
    except BaseException as error:
        result.update(status='failed',error=type(error).__name__+': '+str(error));write(output,result);raise
    write(output,result)
    print('C51 pinned base ready:',len(verified),'files;',len(tensors),'tensor headers/index verified;0 model/CUDA allocation',flush=True)


if __name__=='__main__':main()
