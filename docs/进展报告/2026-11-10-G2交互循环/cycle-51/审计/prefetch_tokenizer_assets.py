"""Fetch small pinned assets while shard transfers run; shared Hub locks protect files."""
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/003-环境与基础权重'
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')


def main():
    output=WORK/'tokenizer-assets-v1.json';assert not output.exists()
    protocol=json.loads((WORK/'preparation-protocol.json').read_text());spec=protocol['model']
    metadata=json.loads((WORK/'model-v1/pinned-upstream-metadata.json').read_text())
    assert metadata['sha']==spec['revision']
    wanted={'config.json','generation_config.json','tokenizer.json','tokenizer_config.json',
        'merges.txt','vocab.json','model.safetensors.index.json'}
    selected=[f for f in metadata['siblings'] if f['rfilename'] in wanted];assert len(selected)==7
    os.environ['HF_HOME']=str(ASSETS/'cache/huggingface')
    os.environ['HF_HUB_CACHE']=str(ASSETS/'cache/huggingface/hub')
    os.environ['HF_XET_CACHE']=str(ASSETS/'cache/huggingface/xet')
    from huggingface_hub import hf_hub_download
    records=[]
    for row in selected:
        name=row['rfilename']
        path=Path(hf_hub_download(spec['repo'],filename=name,revision=spec['revision'],
            local_dir=ASSETS/'models'/spec['local_name'],cache_dir=ASSETS/'cache/huggingface/hub',
            token=False,etag_timeout=30))
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        assert len(raw)==row.get('lfs',{}).get('size',row.get('size'))
        if row.get('lfs'):assert sha==row['lfs']['sha256']
        else:assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==row['blobId']
        records.append({'path':str(path),'bytes':len(raw),'sha256':sha,'git_blob_sha1':row.get('blobId')})
        print(name,'pinned identity verified',flush=True)
    output.write_text(json.dumps({'verified':True,'scope':'small asset prefetch; does not claim base-shard completion or tokenizer execution',
        'revision':spec['revision'],'files':records,'model_constructions':0,'CUDA_allocation':False},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
