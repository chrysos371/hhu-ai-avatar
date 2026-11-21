"""Finite current-contract suite list; every child actual exit is retained."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE = Path(__file__).resolve().parent
RAW = Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/browser-final-batch-v2')
STAGES = ['base', 'playback', 'history-audit', 'external-erase', 'history-restore',
          'notification', 'navigation', 'reminder-privacy', 'receipts'] + [
              'reminder-'+case+'-recovery' for case in
              ('normal-claim', 'response-drop-after-commit', 'navigation-before-response', 'ack-response-drop-after-commit')]


def main():
    path = HERE/'browser-final-batch-v2-result.json'
    assert not path.exists()
    RAW.mkdir(parents=True, exist_ok=False)
    ref = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    name = str(Path(__file__).resolve().relative_to(ROOT))
    assert subprocess.check_output(['git', 'show', ref+':'+name], cwd=ROOT) == Path(__file__).read_bytes()
    result = dict(source_ref=ref, driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  stages=[], whole_stage_wallclock_cutoff=None, passed=False)
    for stage in STAGES:
        started = time.monotonic()
        label = 'browser-'+stage+'-v4'
        with (RAW/(stage+'.log')).open('x') as stream:
            child = subprocess.run([sys.executable, '-B', str(HERE/'run_browser_suite_v4.py'),
                                    '--suite', stage, '--label', label], cwd=ROOT,
                                   stdout=stream, stderr=subprocess.STDOUT)
        result['stages'].append(dict(suite=stage, label=label, actual_returncode=child.returncode,
                                     seconds=time.monotonic()-started))
        (RAW/'progress.json').write_text(json.dumps(result, indent=2)+'\n')
        print(stage, 'actual exit', child.returncode, flush=True)
    result['passed'] = len(result['stages']) == 13 and all(row['actual_returncode'] == 0 for row in result['stages'])
    with path.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    assert result['passed'], 'all original failed evidence retained'


if __name__ == '__main__':
    main()
