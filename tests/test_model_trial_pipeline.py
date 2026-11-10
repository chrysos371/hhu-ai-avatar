import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded)
    return loaded


def pipeline_fixture(tmp_path,monkeypatch,states):
    m=module('try_larger_base');root=tmp_path/'project';base=root/'data/style-lab/style-regression-20261110-01';base.mkdir(parents=True)
    (base/'manifest.json').write_text(json.dumps({'backend':{'files':{'source':'same'}}}))
    for name in ['results.json','checks.json']:(base/name).write_text('{}')
    monkeypatch.setattr(m,'ROOT',root)
    from avatar.lab import common
    values=iter(states);monkeypatch.setattr(common,'source_state',lambda:{'files':next(values)})
    out=root/'data/new-run';monkeypatch.setattr(sys,'argv',['pipeline','--output',str(out)])
    calls=[]
    monkeypatch.setattr(m.subprocess,'run',lambda argv,**kwargs:calls.append(argv))
    return m,out,calls


def test_source_mismatch_stops_before_download(tmp_path,monkeypatch):
    m,out,calls=pipeline_fixture(tmp_path,monkeypatch,[{'source':'changed'}])
    m.main()
    assert json.loads((out/'status.json').read_text())['stage']=='blocked'
    assert calls==[]


def test_source_changes_during_download_stops_before_gpu(tmp_path,monkeypatch):
    m,out,calls=pipeline_fixture(tmp_path,monkeypatch,[{'source':'same'},{'source':'changed'}])
    m.main()
    status=json.loads((out/'status.json').read_text())
    assert status['reason']=='backend_source_changed_while_downloading'
    assert len(calls)==1 and not any('evaluate' in c for c in calls)


@pytest.mark.parametrize("used,utilization", [(4000,90),(512,0),(0,40)])
def test_busy_gpu_is_not_taken_or_waited_for(tmp_path,monkeypatch,used,utilization):
    m,out,calls=pipeline_fixture(tmp_path,monkeypatch,[{'source':'same'},{'source':'same'}])
    from avatar.lab import runner
    monkeypatch.setattr(runner,'gpu_inventory',lambda:{0:{'used_mib':used,'free_mib':40000-used,'utilization':utilization}})
    m.main()
    status=json.loads((out/'status.json').read_text())
    assert status['reason']=='selected_gpu_busy_no_wait_or_takeover'
    assert len(calls)==1


def test_partial_range_resumes_and_whole_shard_hash_is_verified(tmp_path,monkeypatch):
    m=module('download_locked_ranges');monkeypatch.setattr(m,'WORKSPACE',tmp_path)
    content=b'01234567';entry={'name':'14b','status':'locked','repo':'Qwen/Qwen3-14B','revision':'fixed',
        'local_name':'Qwen3-14B','files':[{'path':'model.safetensors','bytes':8,'sha256':hashlib.sha256(content).hexdigest()}],'assets':[]}
    lock=tmp_path/'lock.json';lock.write_text(json.dumps({'models':[entry]}))
    part=tmp_path/'models/Qwen3-14B/.range-parts/model.safetensors';part.mkdir(parents=True)
    (part/'000000000000.tmp').write_bytes(content[:3])
    requests=[]
    class Response:
        status=206;headers={'Content-Range':'bytes 3-7/8'}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,_):
            if getattr(self,'sent',False):return b''
            self.sent=True;return content[3:]
    def open(request,timeout):requests.append(request.get_header('Range'));return Response()
    monkeypatch.setattr(m.urllib.request,'urlopen',open)
    from avatar.lab import runner
    monkeypatch.setattr(runner,'local_model',lambda e:None)
    monkeypatch.setattr(sys,'argv',['download','--lock',str(lock),'--model','14b','--workers','1'])
    m.main()
    assert requests==['bytes=3-7']
    assert (tmp_path/'models/Qwen3-14B/model.safetensors').read_bytes()==content
    assert json.loads((tmp_path/'models/Qwen3-14B/range-download-progress.json').read_text())['status']=='verified'
