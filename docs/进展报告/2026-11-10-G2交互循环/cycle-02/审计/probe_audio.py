"""Isolated signal/decoder probes. Run from repository root with core audio extras."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch
import wave

import numpy as np
from avatar.speech import SpeechService
import avatar.speech as speech


def alias_probe():
    rows=[]
    for source_sr,frequency in [(48000,2000),(48000,14000),(24000,2000),(24000,10000)]:
        samples=.1*np.sin(2*np.pi*frequency*np.arange(source_sr)/source_sr)
        captured=[]
        class Tone:
            def synthesize(self,text,path,*args):
                with wave.open(path,'wb') as stream:
                    stream.setparams((1,2,source_sr,0,'NONE','not compressed'))
                    stream.writeframes((samples*32767).astype('<i2').tobytes())
        def analyze(values,sr,**kwargs):
            captured.append((values.copy(),sr));return []
        with patch.object(speech.LipSyncEngine,'analyze',side_effect=analyze):
            SpeechService(Tone()).synthesize({'text':'probe'})
        output,sr=captured[0]
        # Ignore filter boundaries; compare same central region RMS.
        source_rms=float(np.sqrt(np.mean(samples[source_sr//10:-source_sr//10]**2)))
        output_rms=float(np.sqrt(np.mean(output[sr//10:-sr//10]**2)))
        rows.append({'source_sr':source_sr,'frequency_hz':frequency,'target_sr':sr,
            'source_rms':source_rms,'output_rms':output_rms,
            'gain_db':float(20*np.log10(max(output_rms,1e-12)/source_rms)),
            'kind':'passband' if frequency==2000 else 'above_target_nyquist'})
    return rows


def decode_probe():
    with tempfile.TemporaryDirectory(prefix='avatar-decoder-probe-') as folder:
        path=Path(folder)/'long.mp3'
        import soundfile as sf
        sf.write(str(path),np.zeros(16000*300,dtype=np.float32),16000,format='MP3',
            bitrate_mode='CONSTANT',compression_level=.99)
        # Observe actual decoded allocation via soundfile, without modifying payload.
        original=sf.read;calls=[]
        def observe(*args,**kwargs):
            output=original(*args,**kwargs)
            calls.append({'decoded_frames':len(output[0]),'decoded_numpy_bytes':output[0].nbytes})
            return output
        class Recorded:
            def synthesize(self,text,target,*args):Path(target).write_bytes(path.read_bytes())
        started=time.perf_counter();error=None
        with patch.object(sf,'read',side_effect=observe):
            try:SpeechService(Recorded()).synthesize({'text':'long decoder probe'})
            except Exception as exc:error=getattr(exc,'code',type(exc).__name__)
        return {'input_bytes':path.stat().st_size,'duration_seconds':300,'decoder_reads':calls,
            'error':error,'elapsed_seconds':time.perf_counter()-started}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'aliasing':alias_probe(),'decoder':decode_probe()}
    with args.output.open('x') as target:json.dump(result,target,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
