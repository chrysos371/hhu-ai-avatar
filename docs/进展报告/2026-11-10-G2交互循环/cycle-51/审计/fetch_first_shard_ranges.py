"""Retrieve identical immutable bytes; publish only a verified shard under Hub's lock."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
import urllib.request
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/003-环境与基础权重'
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for value in iter(lambda:f.read(8*1024*1024),b''):h.update(value)
    return h.hexdigest()


def main():
    protocol=json.loads((WORK/'range-first-shard-protocol-v1.json').read_text())
    spec=json.loads((WORK/'preparation-protocol.json').read_text())['model']
    name=protocol['file'];expected=protocol['sha256'];total=protocol['bytes'];chunk=protocol['chunk_bytes']
    assert spec['sha256'][name]==expected
    upstream=json.loads((WORK/'model-v1/pinned-upstream-metadata.json').read_text())
    origin=next(f for f in upstream['siblings'] if f['rfilename']==name)
    assert upstream['sha']==spec['revision'] and origin['lfs']['sha256']==expected and origin['lfs']['size']==total
    cache=ASSETS/'cache/range-artifacts/c51'/expected;assert not cache.exists();cache.mkdir(parents=True)
    output=WORK/'range-first-shard-v1.json';assert not output.exists()
    url=f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{name}"
    report={'status':'running','scope':protocol['scope'],'source':url,'cache':str(cache),'chunks':[],
        'model_constructions':0,'training_steps':0,'existing_transfers_continue':True}
    def save():
        temporary=output.with_suffix('.part');temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');temporary.replace(output)
    def get(index):
        start=index*chunk;end=min(total,start+chunk)-1;events=[];path=cache/f'chunk-{index:04}.bin'
        for attempt in range(1,protocol['attempts_per_chunk']+1):
            began=time.perf_counter()
            try:
                partial=path.with_suffix('.part');offset=partial.stat().st_size if partial.exists() else 0
                assert 0<=offset<=end-start+1
                if offset<end-start+1:
                    request=urllib.request.Request(url,headers={'Range':f'bytes={start+offset}-{end}','User-Agent':'hhu-avatar-immutable-artifact/1.0'})
                    with urllib.request.urlopen(request,timeout=protocol['request_timeout_seconds']) as response:
                        assert response.status==206
                        assert response.headers.get('Content-Range')==f'bytes {start+offset}-{end}/{total}'
                        host=urlsplit(response.url).hostname
                        with partial.open('ab') as stream:
                            while partial.stat().st_size<end-start+1:
                                remaining=end-start+1-stream.tell()
                                block=response.read(min(protocol['stream_block_bytes'],remaining))
                                if not block:break
                                stream.write(block);stream.flush()
                        assert partial.stat().st_size==end-start+1
                else:host='previous verified-range partial response'
                os.replace(partial,path)
                events.append({'attempt':attempt,'status':206,'bytes':path.stat().st_size,'seconds':time.perf_counter()-began,'host':host})
                return {'index':index,'start':start,'end':end,'path':str(path),'sha256':sha(path),'events':events}
            except Exception as e:
                events.append({'attempt':attempt,'error':re.sub(r'https?://\S+','<url>',type(e).__name__+': '+str(e)),'seconds':time.perf_counter()-began})
        (cache/f'chunk-{index:04}-failure.json').write_text(json.dumps(events,ensure_ascii=False,indent=2)+'\n')
        raise RuntimeError('chunk '+str(index)+' exhausted its registered attempts; retained events')
    save();started=time.perf_counter()
    try:
        count=math.ceil(total/chunk)
        pool=ThreadPoolExecutor(max_workers=protocol['workers'])
        futures=[pool.submit(get,i) for i in range(count)]
        try:
            for future in as_completed(futures):
                report['chunks'].append(future.result());save()
                print('verified-range',len(report['chunks']),'/',count,flush=True)
        finally:
            for future in futures:future.cancel()
            pool.shutdown(wait=True,cancel_futures=True)
        records=sorted(report['chunks'],key=lambda r:r['index']);assert [r['index'] for r in records]==list(range(count))
        joined=cache/name
        with joined.open('xb') as out:
            for row in records:
                path=Path(row['path']);assert sha(path)==row['sha256']
                with path.open('rb') as stream:shutil.copyfileobj(stream,out)
        assert joined.stat().st_size==total and sha(joined)==expected
        from huggingface_hub._local_folder import get_local_download_paths,write_download_metadata
        from huggingface_hub.utils import WeakFileLock
        from filelock import Timeout
        target=ASSETS/'models'/spec['local_name'];paths=get_local_download_paths(target,name)
        published=False
        try:
            with WeakFileLock(paths.lock_path,timeout=0):
                if paths.file_path.exists():assert sha(paths.file_path)==expected
                else:
                    temporary=paths.file_path.with_suffix('.c51-verified-part')
                    shutil.copyfile(joined,temporary);assert sha(temporary)==expected
                    os.replace(temporary,paths.file_path)
                write_download_metadata(target,name,spec['revision'],expected)
                published=True
        except Timeout:
            report['publication_note']='Original downloader currently owns this exact Hub file lock; keep verified cache without interference.'
        report.update(status='complete',full_file_sha256=expected,bytes=total,verified_cache_file=str(joined),
            published_under_Hub_lock=published,seconds_including_transfer_and_proof=time.perf_counter()-started)
    except BaseException as e:
        report.update(status='failed',error=type(e).__name__+': '+str(e));save();raise
    save();print('C51 exact first shard SHA verified;published=',published,';original jobs retained',flush=True)


if __name__=='__main__':main()
