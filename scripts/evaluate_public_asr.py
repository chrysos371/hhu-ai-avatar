"""Pinned, preregistered AISHELL-1 subset. Audio stays outside version control."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
import urllib.request
import wave

from evaluate_voice_interaction import sha, normalized, edits, save, gpu_snapshot
from avatar.ears.asr import FasterWhisperEngine

SPEC = Path('evals/interaction/cycle-02/aishell-selection.json')


def fetch(url, path):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                payload = response.read()
            temporary = path.with_suffix('.download')
            temporary.write_bytes(payload)
            temporary.replace(path)
            return
        except Exception:
            if attempt == 2:
                raise


def prepare(folder):
    spec = json.loads(SPEC.read_text())
    root = f"https://huggingface.co/datasets/{spec['dataset']}/resolve/{spec['revision']}/"
    ref = folder/'transcripts.txt'
    fetch(root+spec['referencePath'], ref)
    references = {}
    for line in ref.read_text().splitlines():
        identifier, text = line.split(maxsplit=1)
        references[identifier] = text.replace(' ', '')
    def one(source):
        path = folder/'audio'/Path(source).name
        fetch(root+source, path)
        with wave.open(str(path)) as audio:
            rate, count, channels = audio.getframerate(), audio.getnframes(), audio.getnchannels()
        assert channels == 1 and rate == 16000
        return {'id': path.stem, 'speaker': Path(source).parent.name,
            'source_path': source, 'path': str(path), 'reference': references[path.stem],
            'audio_sha256': sha(path), 'duration_seconds': count/rate, 'sample_rate': rate}
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, spec['samplePaths']))
    save(folder/'manifest.json', {'spec_sha256': sha(SPEC), 'spec': spec,
        'transcript_sha256': sha(ref), 'rows': rows})
    print('Prepared', len(rows), 'frozen public human utterances', flush=True)


def evaluate(folder, model, device, output):
    if output.exists():
        raise ValueError('Use a new output file; failures are evidence')
    manifest = json.loads((folder/'manifest.json').read_text())
    assert sha(SPEC) == manifest['spec_sha256']
    assert [r['source_path'] for r in manifest['rows']] == manifest['spec']['samplePaths']
    before = gpu_snapshot() if device == 'cuda' else []
    chosen = None
    if device == 'cuda':
        available = [r for r in before if r['free_mib'] >= 8192 and r['utilization_percent'] <= 85]
        if not available:
            raise RuntimeError('No GPU currently meets headroom gate')
        chosen = max(available, key=lambda r: (r['free_mib'], -r['utilization_percent']))
        os.environ['CUDA_VISIBLE_DEVICES'] = chosen['uuid']
    start = time.perf_counter()
    engine = FasterWhisperEngine(str(model), device=device)
    load = time.perf_counter()-start
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
        'source_head': subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'scope': manifest['spec']['scope'], 'device': device, 'gpu_before': before, 'chosen_gpu': chosen,
        'manifest_sha256': sha(folder/'manifest.json'), 'spec_sha256': sha(SPEC),
        'model_sha256': {p.name: sha(p) for p in model.iterdir() if p.is_file()},
        'configuration': {'beam_size':5,'language':'zh','temperature':0,'vad_filter':True,
            'condition_on_previous_text':False,'initial_prompt':'以下是普通话，请使用简体中文。',
            'compute_type':'int8_float16' if device=='cuda' else 'int8','cpu_threads':4},
        'load_seconds':load,'rows':[]}
    for item in manifest['rows']:
        assert sha(item['path']) == item['audio_sha256']
        row = dict(item)
        start = time.perf_counter()
        try:
            transcript = engine.transcribe(item['path'])
            reference, hypothesis = normalized(item['reference']), normalized(transcript)
            row.update(transcript=transcript,normalized_reference=reference,normalized_transcript=hypothesis,
                edit_distance=edits(reference,hypothesis),reference_characters=len(reference),error=None)
        except Exception as exc:
            row.update(transcript=None,error=type(exc).__name__)
        row['inference_seconds'] = time.perf_counter()-start
        report['rows'].append(row)
        save(output,report)
        print(item['id'],row['transcript'],row['error'],flush=True)
    good = [r for r in report['rows'] if r['error'] is None]
    reference_count = sum(r['reference_characters'] for r in good)
    cer = sum(r['edit_distance'] for r in good)/reference_count if reference_count else None
    report['summary'] = {'samples':len(report['rows']),'speakers':len(set(r['speaker'] for r in report['rows'])),
        'failed_samples':len(report['rows'])-len(good),'reference_characters':reference_count,
        'cer_on_successful_samples':cer,'all_samples_succeeded':len(good)==len(report['rows']),
        'passes_preregistered_gate':len(good)==len(report['rows']) and cer is not None and cer<=.2,
        'median_inference_seconds':statistics.median(r['inference_seconds'] for r in good) if good else None,
        'median_real_time_factor':statistics.median(r['inference_seconds']/r['duration_seconds'] for r in good) if good else None}
    report['gpu_after'] = gpu_snapshot() if device=='cuda' else []
    save(output,report)
    print(json.dumps(report['summary'],ensure_ascii=False),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['prepare','evaluate'])
    parser.add_argument('--folder',type=Path,default=Path('data/g2-cycle-02/aishell'))
    parser.add_argument('--model',type=Path,default=Path('models/faster-whisper-small'))
    parser.add_argument('--device',choices=['cpu','cuda'],default='cuda')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.mode=='prepare':prepare(args.folder)
    else:evaluate(args.folder,args.model,args.device,args.output)
