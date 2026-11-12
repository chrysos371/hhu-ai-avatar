"""Download a pinned public GGUF; publish only after full size/SHA verification."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import uuid
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]


def metadata(path, expected):
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=expected:raise ValueError('Model metadata identity changed')
    data=json.loads(raw)
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',data.get('repo_id',''))
            or not re.fullmatch(r'[0-9a-f]{40}',data.get('revision',''))
            or not re.fullmatch(r'[0-9a-f]{64}',data.get('lfs',{}).get('oid',''))
            or type(data.get('size')) is not int or data['size']<=0
            or data['size']!=data.get('lfs',{}).get('size')
            or Path(data.get('path','')).name!=data.get('path') or not data['path'].endswith('.gguf')):
        raise ValueError('Invalid pinned GGUF metadata')
    return data


def file_sha(path):
    value=sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):value.update(block)
    return value.hexdigest()


def verify_file(path,size,expected):
    if path.stat().st_size!=size:raise ValueError('Downloaded model size mismatch')
    actual=file_sha(path)
    if actual!=expected:raise ValueError('Downloaded model SHA mismatch')
    return actual


def publish_verified(partial,target,size,expected):
    actual=verify_file(partial,size,expected)
    os.link(partial,target)  # Exclusive publication; never replace an existing target.
    partial.unlink()
    return actual


def save(path,data):
    temporary=path.with_suffix(path.suffix+'.part');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');os.replace(temporary,path)


def run(args):
    data=metadata(args.metadata,args.expected_metadata_sha256)
    target_dir=args.target_dir.absolute()
    if not target_dir.resolve().is_relative_to((ROOT/'models').resolve()):raise ValueError('Use the project model directory')
    if args.report.exists():raise ValueError('Use a fresh report for each download attempt')
    target_dir.mkdir(parents=True,exist_ok=True);args.report.parent.mkdir(parents=True,exist_ok=True)
    target=target_dir/data['path'];partial=target.with_suffix(target.suffix+'.part');owner=target_dir/'download-owner.json'
    if partial.exists() and not owner.exists():raise ValueError('Unowned partial file; retained unchanged')
    ownership={'metadata_sha256':args.expected_metadata_sha256,'target':str(target),'expected_sha256':data['lfs']['oid']}
    if owner.exists():
        if json.loads(owner.read_text())!=ownership:raise ValueError('Different download owns this partial')
    else:
        with owner.open('x') as stream:json.dump(ownership,stream,indent=2);stream.write('\n')
    if shutil.disk_usage(target_dir).free<data['size']+1024**3:raise ValueError('Insufficient measured disk headroom')
    record={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'pid':os.getpid(),
            'metadata_sha256':args.expected_metadata_sha256,'metadata':data,'target':str(target),'partial':str(partial),
            'phase':'preparing','completed':False,'failure':None,'started_unix':time.time(),'curl_pid':None}
    save(args.report,record);process=None
    try:
        if target.exists():
            record['actual_sha256']=verify_file(target,data['size'],data['lfs']['oid']);record['already_present']=True
        else:
            url='https://huggingface.co/'+data['repo_id']+'/resolve/'+data['revision']+'/'+quote(data['path'])+'?download=true&nonce='+uuid.uuid4().hex
            command=['curl','--fail','--location','--proto','=https','--proto-redir','=https','--max-redirs','5',
                '--retry','3','--retry-delay','2','--connect-timeout','30','--continue-at','-', '--output',str(partial),url]
            record.update(curl_command=command,phase='downloading',resume_bytes=partial.stat().st_size if partial.exists() else 0)
            with args.report.with_suffix('.curl.log').open('x') as log:
                process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);record['curl_pid']=process.pid;save(args.report,record)
                print('Download started, owned curl PID',process.pid,'expected bytes',data['size'],flush=True)
                record['curl_exit']=process.wait()
            if record['curl_exit']!=0:raise RuntimeError('curl failed; owned partial retained: '+str(record['curl_exit']))
            record['phase']='verifying_full_file';save(args.report,record)
            record['actual_sha256']=publish_verified(partial,target,data['size'],data['lfs']['oid'])
        record.update(phase='completed',completed=True,actual_size=target.stat().st_size,finished_unix=time.time());save(args.report,record)
        print('Verified and published',target,record['actual_sha256'],flush=True)
    except BaseException as error:
        record.update(phase='failed',failure=repr(error),finished_unix=time.time());save(args.report,record);raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait();record['forced_cleanup']=True
            record['curl_exit']=process.returncode;save(args.report,record)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--metadata',required=True,type=Path);parser.add_argument('--expected-metadata-sha256',required=True)
    parser.add_argument('--target-dir',required=True,type=Path);parser.add_argument('--report',required=True,type=Path);options=parser.parse_args()
    def stop(signum,frame):raise KeyboardInterrupt('Owned download supervisor stopped')
    signal.signal(signal.SIGTERM,stop)
    run(options)
