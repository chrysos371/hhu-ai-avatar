"""Native-environment worker: actual Jinja/provider, scripted model and GPU probes."""
from contextlib import ExitStack
import importlib.metadata
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import serve_local_model_eval as provider


def main():
    group=Path(sys.argv[1]);temporary=Path(sys.argv[2]);enabled=sys.argv[3]=='enabled'
    raw='<tool_call>{"name":"read_reminder_state","arguments":{"reminder_id":1}}</tool_call>'
    completions=([('普通兼容。','stop')] if not enabled else [(raw,'stop'),('合成工具结果：本条记录已取消。','stop'),('准备查询。'+raw,'stop'),(raw,'length'),('普通兼容。','stop')])
    calls=[];models=[];servers=[];errors=[]
    model=temporary/'fixture.gguf';model.write_bytes(b'controlled fixture; not a real GGUF')
    metadata=temporary/'metadata.json';metadata.write_text(json.dumps({'path':model.name,'lfs':{'oid':provider.sha(model)}}))
    registry={'models':[{'model_id':'fixture','file':model.name,'sha256':provider.sha(model),'revision':'b'*40,'required_free_mib':16384}]}
    registry_path=ROOT/'evals/interaction/cycle-40/model-registry.json'
    class ScriptedModel:
        def __init__(self,**options):
            self.metadata={'tokenizer.chat_template':(BASE/'审计/工作目录/001-工具调用调查/embedded-chat-template.jinja').read_text(),'general.name':'SCRIPTED-NOT-NATIVE'}
            self.closed=False;models.append(self)
        def create_completion(self,**options):
            text,finish=completions[len(calls)];calls.append(options)
            return {'choices':[{'text':text,'finish_reason':finish}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
        def close(self):self.closed=True
    real_server=provider.ThreadingHTTPServer
    class CapturedServer(real_server):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);servers.append(self)
    def gpu_probe(command,**kwargs):
        assert command[0]=='nvidia-smi'
        return '0, GPU-CONTROLLED-NOT-REAL, 40000, 0\n' if 'index,uuid' in command[1] else str(__import__('os').getpid())+', 2048\n'
    argv=['serve_local_model_eval.py','--model',str(model),'--model-key','fixture','--metadata',str(metadata),'--ready',str(group/'ready.json'),'--trace',str(group/'provider-trace.jsonl')]
    if enabled:argv.append('--enable-tools')
    def child():
        try:provider.main()
        except BaseException as error:errors.append(repr(error))
    actual_version=importlib.metadata.version
    with ExitStack() as stack:
        stack.enter_context(patch.object(sys,'argv',argv))
        stack.enter_context(patch.object(provider,'load_registry',return_value=(registry,provider.sha(registry_path),registry_path)))
        stack.enter_context(patch.dict(sys.modules,{'llama_cpp':SimpleNamespace(Llama=ScriptedModel,LlamaGrammar=None,llama_supports_gpu_offload=lambda:True)}))
        stack.enter_context(patch.object(provider.subprocess,'check_output',side_effect=gpu_probe))
        stack.enter_context(patch.object(provider.signal,'signal',return_value=None))
        stack.enter_context(patch.object(provider,'ThreadingHTTPServer',CapturedServer))
        stack.enter_context(patch('importlib.metadata.version',side_effect=lambda name:'SCRIPTED' if name=='llama-cpp-python' else actual_version(name)))
        thread=threading.Thread(target=child);thread.start()
        try:
            while not (group/'stop').exists() and thread.is_alive():time.sleep(.01)
        finally:
            if servers:servers[0].shutdown()
            thread.join(10)
        assert not thread.is_alive() and not errors and all(m.closed for m in models),errors
    if enabled:assert '# Tools' in calls[0]['prompt'] and '<tool_response>' in calls[1]['prompt']
    else:assert '# Tools' not in calls[0]['prompt']
    (group/'worker-cleanup.json').write_text(json.dumps({'scripted_model_calls':len(calls),'native_or_GPU_calls':0,'all_models_servers_closed':True,'errors':errors,'worker_sha256':provider.sha(__file__),'actual_worker_prefix':sys.prefix},indent=2)+'\n')


if __name__=='__main__':main()
