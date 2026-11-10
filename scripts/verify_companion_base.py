"""Hash original model shards against the pinned official Hub LFS objects."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1] / 'training/companion/base-model.json')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    verified = {}
    for name, expected in manifest['sha256'].items():
        with (args.model / name).open('rb') as file:
            checksum = hashlib.sha256()
            for block in iter(lambda: file.read(8 * 1024 * 1024), b''):
                checksum.update(block)
        actual = checksum.hexdigest()
        if actual != expected:
            raise ValueError('SHA256 mismatch: ' + name)
        verified[name] = actual
        print('Verified ' + name, flush=True)
    result = dict(model_id=manifest['model_id'], revision=manifest['revision'],
                  source=manifest['source'], verified_weight_sha256=verified)
    (args.model / 'verified-revision.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
