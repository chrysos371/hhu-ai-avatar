"""Install Linux direct-parent-death protection in a fresh interpreter, then exec.

No preexec_fn runs in a potentially threaded supervisor. Trusted payloads must
retain credentials and this signal; forked grandchildren are outside the scope.
"""
import argparse
import ctypes
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import sys


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def install_guard(parent_pid):
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Direct-parent-death guard requires Linux')
    if os.getppid() != parent_pid:
        raise RuntimeError('Supervisor parent changed before guard installation')
    libc=ctypes.CDLL(None,use_errno=True)
    libc.prctl.restype=ctypes.c_int
    if libc.prctl(1,signal.SIGKILL,0,0,0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(),'Cannot install parent-death SIGKILL')
    # If death preceded prctl, the kernel does not retroactively send it.
    if os.getppid() != parent_pid:
        raise RuntimeError('Supervisor parent changed while installing guard')
    actual=ctypes.c_int()
    if libc.prctl(2,ctypes.byref(actual),0,0,0) != 0 or actual.value != signal.SIGKILL:
        raise RuntimeError('Kernel parent-death signal verification failed')
    return actual.value


def execute(job,expected,parent_pid):
    signal_number=install_guard(parent_pid)
    path=job/'config.json'
    if digest(path) != expected:
        raise ValueError('Job config changed before protected exec')
    config=json.loads(path.read_text())
    if digest(Path(__file__).resolve()) != config['parent_death_guard_sha256']:
        raise ValueError('Parent-death guard source changed before exec')
    command=config['command']
    if not command or any(not isinstance(v,str) or not v or '\0' in v for v in command):
        raise ValueError('Protected payload requires explicit nonempty argv')
    fields=Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(') ',1)[1].split()
    receipt={'installed':True,'pid':os.getpid(),'start_ticks':int(fields[19]),
        'parent_pid':parent_pid,'kernel_parent_death_signal':signal_number,
        'config_sha256':expected,'guard_sha256':digest(Path(__file__).resolve()),
        'target_argv':command,'scope':'trusted direct child only;exec not yet acknowledged'}
    # This is immutable and complete before exec; the supervisor additionally
    # observes the final payload argv instead of claiming this transitional argv.
    with (job/'parent-death-guard.json').open('x') as stream:
        json.dump(receipt,stream,ensure_ascii=False,indent=2)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.execvpe(command[0],command,os.environ)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True)
    parser.add_argument('--config-sha256',required=True)
    parser.add_argument('--parent-pid',type=int,required=True)
    args=parser.parse_args()
    execute(args.job,args.config_sha256,args.parent_pid)
