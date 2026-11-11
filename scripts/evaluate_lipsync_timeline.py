"""Measure actual frame metadata against integer PCM sample offsets."""
import argparse
from datetime import datetime,timezone
import itertools
import json
from pathlib import Path
import subprocess
import time
import wave
import numpy as np
from avatar.face.lipsync import LipSyncEngine
from avatar.main import Avatar
from avatar.brain.memory import MemoryStore
from evaluate_analytic_lipsync import legacy
from evaluate_real_interaction import save,sha

SPEC=Path('evals/audio/cycle-07/timeline-protocol.json')


def run(arm,output):
    if output.exists():raise FileExistsError(output)
    spec=json.loads(SPEC.read_text())
    module,engine_sha=legacy(spec['baseline_revision']) if arm=='baseline' else (None,sha('src/avatar/face/lipsync.py'))
    engine_class=module.LipSyncEngine if module else LipSyncEngine
    cases=[{'sample_rate':sr,'hop_ms':hop,'duration_seconds':spec['duration_seconds']}
        for sr,hop in itertools.product(spec['sample_rates'],spec['hop_ms'])]+[spec['prolonged']]
    report={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'created_utc':datetime.now(timezone.utc).isoformat(),'spec':spec,'protocol_sha256':sha(SPEC),
        'engine_sha256':engine_sha,'audio_utils_sha256':sha('src/avatar/utils/audio.py'),'script_sha256':sha(__file__),
        'arm':arm,'rows':[],'execution_complete':False,'sample_clock_gate_passed':False,'physical_sync_approved':False}
    save(output,report);started=time.perf_counter()
    for item in cases:
        sr=item['sample_rate'];samples=np.zeros(int(sr*item['duration_seconds']),dtype=np.float32)
        frames=engine_class(hop_ms=item['hop_ms']).analyze(samples,sr)
        hop=int(sr*item['hop_ms']/1000);window=int(sr*spec['frame_ms']/1000)
        expected_count=1+(len(samples)-window)//hop
        errors=[frame.time*sr-index*hop for index,frame in enumerate(frames)]
        maximum=max(abs(value) for value in errors)
        within=frames[-1].time*sr+window<=len(samples)+1e-6
        row=item|{'count':len(frames),'expected_count':expected_count,'hop_samples':hop,'frame_samples':window,
            'first_time':frames[0].time,'last_time':frames[-1].time,
            'expected_last_time':(len(frames)-1)*hop/sr,'max_error_samples':maximum,'max_error_ms':maximum/sr*1000,
            'last_window_within_audio':within,'all_zero_outputs':all(frame.mouth_open==0 and frame.energy==0 and frame.vowel=='' for frame in frames),
            'sample_clock_passed':maximum<=spec['gates']['max_absolute_error_samples'] and within and len(frames)==expected_count}
        report['rows'].append(row);save(output,report)
        print(arm,sr,item['hop_ms'],item['duration_seconds'],row['max_error_ms'],row['sample_clock_passed'],flush=True)
    class Offline:
        available=False
    class LocalWave:
        def synthesize(self,text,path,rate,pitch):
            samples=.1*np.sin(2*np.pi*300*np.arange(44100)/22050)
            with wave.open(path,'wb') as target:
                target.setparams((1,2,22050,0,'NONE','not compressed'))
                target.writeframes((samples*32767).astype('<i2').tobytes())
            return path
    audio_path=output.with_suffix('.wav')
    if audio_path.exists():raise FileExistsError(audio_path)
    memory=MemoryStore(':memory:');bot=Avatar(memory=memory,llm=Offline(),tts=LocalWave())
    bot.lipsync=engine_class()
    try:
        result=bot.respond('读一段测试。',use_tts=True,tts_path=str(audio_path))
        if result['lipsync_error'] is not None:raise AssertionError('Actual file TTS analysis failed')
        frames=result['lip_sync_frames'];error=max(abs(row['time']*22050-index*220) for index,row in enumerate(frames))
        report['file_api']={'scope':'Actual Avatar.respond with injected local WAV; no remote model/TTS',
            'audio_sha256':sha(audio_path),'sample_rate':22050,'sample_count':44100,
            'frames':frames,'max_error_samples':error,'max_error_ms':error/22050*1000,'passed':error<=1e-6}
    finally:memory.close()
    report.update(execution_complete=True,sample_clock_gate_passed=all(row['sample_clock_passed'] for row in report['rows']) and report['file_api']['passed'],seconds=time.perf_counter()-started)
    save(output,report)
    print(json.dumps({'passed':report['sample_clock_gate_passed'],'cases':len(report['rows']),'max_error_ms':max(row['max_error_ms'] for row in report['rows'])}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['baseline','candidate'],required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();run(args.arm,args.output)
