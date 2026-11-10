"""Real local model disconnect/iterator audit, separate from quality assertions."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time

from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken, Cancelled


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',type=Path,required=True)
    parser.add_argument('--trace',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,default=Path('evals/interaction/cycle-02/real-cancellation-protocol.json'))
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a new output file')
    path=args.protocol
    protocol=json.loads(path.read_text());provider=json.loads(args.provider.read_text())
    model_id=provider.get('model_id','qwen3-4b-q4_k_m')
    if protocol.get('allowed_models'):
        selected=next(row for row in protocol['allowed_models'] if row['model_id']==model_id)
        assert provider['model_revision']==selected['revision'] and provider['model_sha256']==selected['sha256']
    else:
        assert model_id=='qwen3-4b-q4_k_m'
    engine=LLMEngine(base_url=provider['url'],api_key='local-eval-only',model=model_id,timeout=180,max_retries=0)
    rows=[]
    report={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'protocol_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'protocol':protocol,'provider':provider,'rows':rows,'execution_status':'running'}
    def save():
        temp=args.output.with_suffix('.tmp')
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');temp.replace(args.output)
    with args.output.open('x') as target:json.dump(report,target,ensure_ascii=False,indent=2)
    try:
        for trial in range(protocol['trials']):
            prior=len(args.trace.read_text().splitlines())
            started=threading.Event();token=CancellationToken();outcome=[];parts=[]
            def callback(text):
                parts.append(text);started.set()
            def work():
                try:
                    engine.stream_chat([{'role':'user','content':protocol['prompt']}],
                        temperature=0,max_tokens=protocol['max_tokens'],cancel=token,on_delta=callback)
                    outcome.append('completed')
                except Cancelled:outcome.append('cancelled')
                except Exception as exc:outcome.append(type(exc).__name__);started.set()
            worker=threading.Thread(target=work)
            begin=time.perf_counter();worker.start()
            if not started.wait(180):
                token.cancel();worker.join(10);raise RuntimeError('No first delta')
            first=time.perf_counter()-begin
            begin=time.perf_counter();token.cancel();worker.join(10)
            elapsed=time.perf_counter()-begin
            deadline=time.monotonic()+10;trace=[]
            while time.monotonic()<deadline:
                trace=[json.loads(line) for line in args.trace.read_text().splitlines()[prior:]]
                if trace:break
                time.sleep(.02)
            begin=time.perf_counter()
            recovery=engine.chat([{'role':'user','content':protocol['recovery_prompt']}],temperature=0,
                max_tokens=protocol['recovery_max_tokens'])
            rows.append({'trial':trial,'first_delta_seconds':first,'cancel_join_seconds':elapsed,
                'outcome':outcome,'worker_alive':worker.is_alive(),'received_text':''.join(parts),
                'provider_trace':trace,'provider_iterator_closed':bool(trace) and trace[0]['outcome']=='client_disconnected',
                'recovery_reply':recovery,'recovery_seconds':time.perf_counter()-begin})
            save()
            print(trial,outcome,elapsed,repr(recovery),flush=True)
    finally:engine.close()
    p95=max(row['cancel_join_seconds'] for row in rows)  # N=5, nearest-rank p95 is max.
    report.update(execution_status='complete',local_cancel_p95_seconds=p95,
        all_provider_iterators_closed=all(row['provider_iterator_closed'] for row in rows),
        passes_gate=p95<.5 and all(row['outcome']==['cancelled'] and not row['worker_alive']
            and row['provider_iterator_closed'] and row['recovery_reply'].strip()=='2' for row in rows))
    save()
    print('passes_gate',report['passes_gate'],flush=True)


if __name__=='__main__':main()
