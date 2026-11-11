"""Observe cleanup of an owned disposable browser helper after SIGTERM."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sources = [ROOT/'tests/helpers/serve_admin_e2e.py', Path(__file__).resolve(),
               ROOT/'evals/interaction/cycle-10/cleanup-protocol.json']
    report = {'phase': args.phase, 'scope': 'Owned disposable helper, no user DB opened',
              'sourceHead': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'sourceSha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sources},
              'pid': None, 'created': [], 'remaining': [], 'exitCode': None, 'failure': None, 'passed': False}
    with args.output.open('x') as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    temp = ROOT.parent/'runtime/tmp'
    before = set(temp.glob('admin-e2e-*'))
    proc = None
    started = time.monotonic()
    try:
        with socket.socket() as probe:
            probe.settimeout(.1)
            if probe.connect_ex(('127.0.0.1', 18765)) == 0:
                raise RuntimeError('Port18765 is in use; do not disturb another experiment')
        with args.output.with_suffix('.log').open('x') as log:
            proc = subprocess.Popen([sys.executable, str(ROOT/'tests/helpers/serve_admin_e2e.py')], cwd=ROOT,
                                    stdout=log, stderr=subprocess.STDOUT)
            report['pid'] = proc.pid
            ready = False
            for _ in range(200):
                if proc.poll() is not None:
                    raise RuntimeError('Helper exited before health became ready')
                try:
                    with urlopen('http://127.0.0.1:18765/healthz', timeout=1) as response:
                        ready = response.status == 200
                except OSError:
                    pass
                if ready:
                    break
                time.sleep(.05)
            if not ready:
                raise RuntimeError('Startup retry budget exhausted')
            report['created'] = sorted(str(p) for p in set(temp.glob('admin-e2e-*')) - before)
            proc.send_signal(signal.SIGTERM)
            report['exitCode'] = proc.wait()
    except Exception as error:
        report['failure'] = repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            report['exitCode'] = proc.wait()
        report['remaining'] = [p for p in report['created'] if Path(p).exists()]
        report['elapsedSeconds'] = time.monotonic() - started
        report['passed'] = report['failure'] is None and len(report['created']) == 1 and not report['remaining'] and report['exitCode'] == 0
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key: report[key] for key in ['phase', 'pid', 'exitCode', 'created', 'remaining', 'passed']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
