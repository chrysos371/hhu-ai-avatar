"""Preregistered actual human file endpoint information-loss check."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import wave

from avatar.ears.asr import FasterWhisperEngine
from avatar.gpu_resources import select_available_gpu
from evaluate_voice_interaction import sha, normalized, edits, save, gpu_snapshot


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','evaluate'])
    parser.add_argument('--folder',type=Path,default=Path('data/g2-cycle-02/human-endpoint'))
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    protocol=Path('evals/interaction/cycle-02/human-endpoint-protocol.json')
    if args.mode=='prepare':
        source=json.loads(Path('data/g2-cycle-02/aishell/manifest.json').read_text())
        args.folder.mkdir(parents=True,exist_ok=False);rows=[]
        for row in source['rows']:
            assert sha(row['path'])==row['audio_sha256']
            augmented=args.folder/(row['id']+'-full.wav');cropped=args.folder/(row['id']+'-auto.wav')
            with wave.open(row['path']) as audio:
                assert audio.getnchannels()==1 and audio.getsampwidth()==2 and audio.getframerate()==16000
                frames=audio.readframes(audio.getnframes())
            with wave.open(str(augmented),'wb') as audio:
                audio.setparams((1,2,16000,0,'NONE','not compressed'));audio.writeframes(frames+b'\0'*(16000*10*2))
            rows.append(row|{'augmented_path':str(augmented),'cropped_path':str(cropped),'augmented_sha256':sha(augmented)})
        save(args.folder/'input.json',{'protocol_sha256':sha(protocol),'source_manifest_sha256':sha('data/g2-cycle-02/aishell/manifest.json'),'rows':rows})
        return
    if args.output.exists():raise ValueError('Use a new result path')
    manifest=json.loads((args.folder/'endpoint-manifest.json').read_text())
    assert manifest['protocol_sha256']==sha(protocol)
    snapshot=gpu_snapshot()
    chosen=select_available_gpu(snapshot,required_free_mib=8192,
        visible_mask=os.environ.get('CUDA_VISIBLE_DEVICES'))
    os.environ['CUDA_VISIBLE_DEVICES']=chosen['uuid']
    engine=FasterWhisperEngine('models/faster-whisper-small',device='cuda')
    report={'protocol_sha256':sha(protocol),'protocol':json.loads(protocol.read_text()),
        'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'source_sha256':{str(p):sha(p) for p in [Path(__file__),Path('scripts/endpoint_human_audio.mjs'),Path('frontend/src/features/chat/endpointing.ts')]},
        'gpu_before':snapshot,'chosen_gpu':chosen,'rows':[]}
    for index,item in enumerate(manifest['rows']):
        assert sha(item['augmented_path'])==item['augmented_sha256']
        row=dict(item);ref=normalized(item['reference']);row['reference_characters']=len(ref)
        for mode in (['full','auto'] if index%2==0 else ['auto','full']):
            start=time.perf_counter()
            transcript='' if mode=='auto' and item['endpoint_reason']!='pause' else engine.transcribe(item['augmented_path'] if mode=='full' else item['cropped_path'])
            row[mode]={'transcript':transcript,'edit_distance':edits(ref,normalized(transcript)),'seconds':time.perf_counter()-start}
        report['rows'].append(row);save(args.output,report)
        print(item['id'],item['endpoint_reason'],row['full']['edit_distance'],row['auto']['edit_distance'],flush=True)
    count=sum(row['reference_characters'] for row in report['rows'])
    cer={mode:sum(row[mode]['edit_distance'] for row in report['rows'])/count for mode in ['full','auto']}
    increased=[row['id'] for row in report['rows'] if row['auto']['edit_distance']>row['full']['edit_distance']]
    report['summary']={'samples':len(report['rows']),'reference_characters':count,'cer':cer,
        'non_pause_ids':[row['id'] for row in report['rows'] if row['endpoint_reason']!='pause'],
        'increased_error_ids':increased,'passes_gate':not increased and cer['auto']<=cer['full'] and all(row['endpoint_reason']=='pause' for row in report['rows'])}
    save(args.output,report);print(json.dumps(report['summary'],ensure_ascii=False),flush=True)


if __name__=='__main__':main()
