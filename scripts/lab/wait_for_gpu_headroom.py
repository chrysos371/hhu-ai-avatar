"""Read-only resource observation; never launches a model or changes admission."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import time

from avatar.gpu_resources import select_available_gpu

ROOT = Path(__file__).resolve().parents[2]


def wait(model_key, output):
    registry_path = ROOT/'evals/interaction/cycle-02/model-scale-protocol.json'
    registry = json.loads(registry_path.read_text())
    model = next(item for item in registry['models'] if item['model_id'] == model_key)
    identity = {'model_id': model_key, 'required_free_mib': model['required_free_mib'],
        'max_utilization': 20, 'interval_seconds': 10, 'required_consecutive_observations': 2,
        'source_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__).resolve(), ROOT/'src/avatar/gpu_resources.py', registry_path)},
        'scope': 'Two observations of same qualifying UUID; no reservation, allocation, process termination or experiment deadline; provider must recheck'}
    previous = None; consecutive = 0
    with output.open('x') as stream:
        stream.write(json.dumps(identity, ensure_ascii=False)+'\n'); stream.flush()
        while True:
            raw = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.free,utilization.gpu',
                                           '--format=csv,noheader,nounits'], text=True)
            inventory = []
            for line in raw.splitlines():
                index, uid, free, utilization = (part.strip() for part in line.split(','))
                inventory.append({'index': int(index), 'uuid': uid, 'free_mib': int(free),
                                  'utilization_percent': int(utilization)})
            row = {'utc': datetime.now(timezone.utc).isoformat(), 'inventory': inventory}
            try:
                chosen = select_available_gpu(inventory, required_free_mib=model['required_free_mib'],
                                              visible_mask=os.environ.get('CUDA_VISIBLE_DEVICES'))
                consecutive = consecutive+1 if previous == chosen['uuid'] else 1
                previous = chosen['uuid']; row['selected'] = chosen
            except RuntimeError as error:
                consecutive = 0; previous = None; row['unavailable'] = str(error)
            row['consecutive'] = consecutive; row['completed'] = consecutive >= 2
            stream.write(json.dumps(row, ensure_ascii=False)+'\n'); stream.flush()
            if row['completed']:
                print(json.dumps(row, ensure_ascii=False), flush=True); return
            time.sleep(10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-key', choices=['qwen3-4b-q4_k_m', 'qwen3-14b-q4_k_m'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); wait(args.model_key, args.output)
