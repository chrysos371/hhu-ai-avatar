"""Resumable public-Hub byte ranges; each completed shard must match the lock SHA256."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parent


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--lock',type=Path,required=True);p.add_argument('--model',choices=['14b','32b'],required=True);p.add_argument('--workers',type=int,default=24)
    args=p.parse_args()
    if not 1<=args.workers<=32:raise ValueError('workers must be 1..32')
    lock=json.loads(args.lock.read_text());entry=next(m for m in lock['models'] if m['name']==args.model)
    if entry['status']!='locked':raise ValueError('Unlocked model')
    target=WORKSPACE/'models'/entry['local_name']
    if not target.resolve().is_relative_to((WORKSPACE/'models').resolve()):raise ValueError('Model directory escape')
    target.mkdir(parents=True,exist_ok=True)
    parts=target/'.range-parts';parts.mkdir(exist_ok=True)
    base='https://huggingface.co/'+entry['repo']+'/resolve/'+entry['revision']+'/'
    def request(url,start=None,end=None,total=None):
        headers={'Accept-Encoding':'identity'}
        if start is not None:headers['Range']=f'bytes={start}-{end}'
        response=urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45)
        if start is not None and (response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{total}'):
            response.close();raise ValueError('Range response mismatch')
        return response
    jobs=[];chunk=64*1024*1024
    for item in entry['files']:
        final=target/item['path']
        if not final.resolve().is_relative_to(target.resolve()):raise ValueError('Path escape')
        if final.exists() and final.stat().st_size==item['bytes'] and sha(final)==item['sha256']:continue
        folder=parts/item['path'];folder.mkdir(exist_ok=True)
        for start in range(0,item['bytes'],chunk):
            end=min(item['bytes']-1,start+chunk-1);jobs.append((item,start,end,folder/f'{start:012d}.part'))
    def fetch(job):
        item,start,end,path=job
        if path.exists() and path.stat().st_size==end-start+1:return end-start+1
        temporary=path.with_suffix('.tmp')
        error=''
        for attempt in range(4):
            try:
                count=temporary.stat().st_size if temporary.exists() else 0
                if count>end-start+1:raise ValueError('Oversized partial range')
                if count==end-start+1:
                    temporary.replace(path);return count
                offset=start+count
                url=base+item['path']+f'?download=true&range={offset}-{end}'
                with request(url,offset,end,item['bytes']) as response, temporary.open('ab') as out:
                    while True:
                        block=response.read(1024*1024)
                        if not block:break
                        out.write(block);count+=len(block)
                if count!=end-start+1:raise ValueError('Range size mismatch')
                temporary.replace(path)
                return count
            except Exception as exc:
                error=type(exc).__name__;time.sleep(min(8,2**attempt))
        raise RuntimeError(f'{item["path"]}:{start} failed ({error})')
    done=0;completed=0;started=time.monotonic()
    state=target/'range-download-progress.json'
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(fetch,j) for j in jobs]
        for future in as_completed(futures):
            done+=future.result();completed+=1
            row={'status':'downloading','chunks_completed':completed,'chunks_total':len(jobs),'downloaded_gib':round(done/2**30,3),'elapsed_seconds':round(time.monotonic()-started,1)}
            state.write_text(json.dumps(row));print(json.dumps(row),flush=True)
    for item in entry['files']:
        final=target/item['path']
        if final.exists() and final.stat().st_size==item['bytes'] and sha(final)==item['sha256']:continue
        pending=final.with_suffix('.assembling')
        with pending.open('wb') as out:
            for part in sorted((parts/item['path']).glob('*.part')):
                with part.open('rb') as stream:
                    for block in iter(lambda:stream.read(4*1024*1024),b''):out.write(block)
        if pending.stat().st_size!=item['bytes'] or sha(pending)!=item['sha256']:raise ValueError('Shard hash mismatch: '+item['path'])
        pending.replace(final);print('Verified '+item['path'],flush=True)
    for item in entry['assets']:
        path=target/item['path']
        if not path.resolve().is_relative_to(target.resolve()):raise ValueError('Asset path escape')
        if path.exists() and path.stat().st_size==item['bytes']:continue
        with request(base+item['path']) as response:path.write_bytes(response.read())
    from avatar.lab.runner import local_model
    local_model(entry)
    (target/'style-lab-revision.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2))
    state.write_text(json.dumps({'status':'verified','model':entry['repo'],'revision':entry['revision']}))
    print('All weights and tokenizer/config verified against lock',flush=True)


if __name__=='__main__':main()
