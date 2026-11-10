"""Reproducible synthetic ASR and real TTS experiments; raw rows precede conclusions."""
from pathlib import Path
import argparse
import hashlib
from importlib.metadata import version
import json
import os
import platform
import statistics
import subprocess
import threading
import time
import unicodedata
import wave

import numpy as np

from avatar.ears.asr import FasterWhisperEngine
from avatar.mouth.tts import EdgeTTSEngine
from avatar.speech import SpeechService
from avatar.utils.audio import load_audio


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def wav(path, samples, sr):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, sr, 0, 'NONE', 'not compressed'))
        stream.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())


def normalized(text):
    return ''.join(c.lower() for c in unicodedata.normalize('NFKC', text) if c.isalnum())


def edits(a, b):
    previous = list(range(len(b) + 1))
    for i, char in enumerate(a, 1):
        row = [i]
        for j, other in enumerate(b, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j-1] + (char != other)))
        previous = row
    return previous[-1]


def prepare(folder):
    spec = json.loads(Path('evals/interaction/voice-corpus-v1.json').read_text())
    digest = sha('evals/interaction/voice-corpus-v1.json')
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / 'corpus.json'
    report = json.loads(manifest.read_text()) if manifest.exists() else {'spec_sha256': digest, 'spec': spec, 'rows': []}
    if report['spec_sha256'] != digest:
        raise ValueError('corpus specification changed; use a new output directory')
    rows = {row['id']: row for row in report['rows']}
    rng = np.random.default_rng(spec['seed'])
    for voice_index, voice in enumerate(spec['voices']):
        engine = EdgeTTSEngine(voice)
        for index, text in enumerate(spec['texts']):
            identifier = f'voice{voice_index}-text{index}'
            path = folder / (identifier + '.mp3')
            if identifier not in rows:
                start = time.perf_counter()
                engine.synthesize(text, str(path))
                samples, sr = load_audio(path)
                clean = folder / (identifier + '.wav')
                wav(clean, samples, sr)
                rows[identifier] = {'id': identifier, 'condition': 'clean', 'reference': text, 'voice': voice,
                    'path': str(clean), 'audio_sha256': sha(clean), 'duration_seconds': len(samples)/sr,
                    'generation_seconds': time.perf_counter()-start}
                report['rows'] = list(rows.values())
                save(manifest, report)
            clean = rows[identifier]
            samples, sr = load_audio(clean['path'])
            noise = rng.normal(size=len(samples))
            rms = float(np.sqrt(np.mean(samples**2)))
            noise *= rms / (10 ** (spec['noise_snr_db']/20)) / np.sqrt(np.mean(noise**2))
            noisy = folder / (identifier + '-noise.wav')
            wav(noisy, samples + noise, sr)
            rows[identifier+'-noise'] = clean | {'id': identifier+'-noise', 'condition': 'noise20db',
                'path': str(noisy), 'audio_sha256': sha(noisy), 'snr_db_before_quantization': float(20*np.log10(rms/np.sqrt(np.mean(noise**2))))}
    for duration in spec['silence_seconds']:
        path = folder / f'silence-{duration}.wav'
        wav(path, np.zeros(16000*duration), 16000)
        rows[f'silence-{duration}'] = {'id': f'silence-{duration}', 'condition': 'silence', 'reference': '',
            'path': str(path), 'audio_sha256': sha(path), 'duration_seconds': duration}
    report['rows'] = list(rows.values())
    report['complete'] = len(rows) == 27
    save(manifest, report)
    print(json.dumps({'rows': len(rows), 'complete': report['complete']}, ensure_ascii=False), flush=True)


def gpu_snapshot():
    data = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], text=True)
    return [dict(zip(('index', 'uuid', 'free_mib', 'utilization_percent'), [int(i), uid.strip(), int(free), int(util)]))
            for i, uid, free, util in (line.split(',') for line in data.splitlines())]


def evaluate_asr(corpus, model, device, gpu, output):
    if output.exists():
        raise ValueError('output already exists')
    report = json.loads((corpus / 'corpus.json').read_text())
    assert report.get('complete') and len(report['rows']) == 27
    before = gpu_snapshot() if device == 'cuda' else []
    chosen = None
    if device == 'cuda':
        candidates = [row for row in before if row['free_mib'] >= 8192 and row['utilization_percent'] <= 85]
        if gpu is not None:
            candidates = [row for row in candidates if row['index'] == gpu]
        if not candidates:
            raise RuntimeError('no GPU meets the declared headroom gate')
        chosen = max(candidates, key=lambda row: (row['free_mib'], -row['utilization_percent']))
        os.environ['CUDA_VISIBLE_DEVICES'] = chosen['uuid']
    start = time.perf_counter()
    engine = FasterWhisperEngine(str(model), device=device, cpu_threads=4)
    load_seconds = time.perf_counter() - start
    peak, stop = [], threading.Event()
    def monitor():
        while not stop.is_set():
            data = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'], text=True)
            for line in data.splitlines():
                pid, used = line.split(',')
                if int(pid) == os.getpid():
                    peak.append(int(used))
            stop.wait(0.2)
    monitor_thread = threading.Thread(target=monitor, daemon=True) if device == 'cuda' else None
    if monitor_thread:
        monitor_thread.start()
    rows = []
    try:
        for item in report['rows']:
            assert sha(item['path']) == item['audio_sha256']
            start = time.perf_counter()
            transcript = engine.transcribe(item['path'])
            elapsed = time.perf_counter() - start
            ref, hyp = normalized(item['reference']), normalized(transcript)
            rows.append(item | {'transcript': transcript, 'normalized_reference': ref, 'normalized_transcript': hyp,
                'edit_distance': edits(ref, hyp), 'reference_characters': len(ref),
                'inference_seconds': elapsed, 'real_time_factor': elapsed/item['duration_seconds']})
            print(item['id'], repr(transcript), round(elapsed, 3), flush=True)
    finally:
        stop.set()
        if monitor_thread:
            monitor_thread.join()
    summary = {}
    for condition in ('clean', 'noise20db', 'silence'):
        selected = [row for row in rows if row['condition'] == condition]
        reference_characters = sum(row['reference_characters'] for row in selected)
        summary[condition] = {'samples': len(selected), 'cer': sum(row['edit_distance'] for row in selected)/reference_characters if reference_characters else None,
            'nonempty_transcripts': sum(bool(row['normalized_transcript']) for row in selected),
            'median_inference_seconds': statistics.median(row['inference_seconds'] for row in selected),
            'median_real_time_factor': statistics.median(row['real_time_factor'] for row in selected)}
    result = {'scope': report['spec']['scope'], 'device': device, 'chosen_gpu': chosen,
        'gpu_before': before, 'gpu_after': gpu_snapshot() if device == 'cuda' else [],
        'peak_process_gpu_mib_sampled': max(peak) if peak else None, 'gpu_sample_count': len(peak),
        'python': platform.python_version(), 'packages': {name: version(name) for name in ['faster-whisper', 'ctranslate2', 'onnxruntime']},
        'corpus_sha256': sha(corpus/'corpus.json'), 'model_files_sha256': {p.name: sha(p) for p in model.iterdir() if p.is_file()},
        'load_seconds': load_seconds, 'configuration': {'language': 'zh', 'beam_size': 5, 'vad_filter': True,
            'condition_on_previous_text': False, 'compute_type': 'int8_float16' if device == 'cuda' else 'int8', 'cpu_threads': 4},
        'normalization': 'Unicode NFKC, lowercase, keep alphanumeric; no traditional-to-simplified conversion',
        'summary': summary, 'clean_cer_gate_passed': summary['clean']['cer'] <= 0.2,
        'silence_gate_passed': summary['silence']['nonempty_transcripts'] == 0, 'rows': rows}
    save(output, result)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def split_text(text):
    parts, pending = [], ''
    for char in text:
        pending += char
        if len(pending) >= 160 or len(pending) >= 32 and char in '。！？!?\n':
            if pending.strip(): parts.append(pending.strip())
            pending = ''
    if pending.strip(): parts.append(pending.strip())
    return parts


def evaluate_tts(output):
    if output.exists():
        raise ValueError('output already exists')
    text = Path('evals/interaction/long-reply-v1.txt').read_text().strip()
    parts = split_text(text)
    rows = []
    service = SpeechService()
    for repeat in range(3):
        for mode in (['whole', 'first_segment'] if repeat % 2 == 0 else ['first_segment', 'whole']):
            spoken = text if mode == 'whole' else parts[0]
            start = time.perf_counter()
            result = service.synthesize({'text': spoken})
            seconds = time.perf_counter() - start
            audio, content_type = service.read(result['audio_id'])
            rows.append({'repeat': repeat, 'mode': mode, 'seconds': seconds, 'text': spoken,
                'audio_bytes': len(audio), 'audio_sha256': hashlib.sha256(audio).hexdigest(), 'duration': result['duration'],
                'frames': len(result['frames']), 'warning': result['warning'], 'content_type': content_type})
            print(mode, round(seconds, 3), flush=True)
    medians = {mode: statistics.median(row['seconds'] for row in rows if row['mode'] == mode) for mode in ('whole', 'first_segment')}
    save(output, {'scope': 'three paired real Edge-TTS calls; network conditions not controlled',
        'input_sha256': sha('evals/interaction/long-reply-v1.txt'), 'segments': parts,
        'medians_seconds': medians, 'first_audio_ratio': medians['first_segment']/medians['whole'],
        'passes_70pct_gate': medians['first_segment'] <= 0.7*medians['whole'], 'rows': rows})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'asr', 'tts'])
    parser.add_argument('--corpus', type=Path, default=Path('data/g2-cycle-01/voice-corpus'))
    parser.add_argument('--model', type=Path, default=Path('models/faster-whisper-small'))
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--gpu-index', type=int)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare': prepare(args.corpus)
    elif args.mode == 'asr': evaluate_asr(args.corpus, args.model, args.device, args.gpu_index, args.output)
    else: evaluate_tts(args.output)


if __name__ == '__main__': main()
