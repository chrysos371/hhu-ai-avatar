"""Seal committed C52 bytes after final closeout; no external generation."""
from pathlib import Path
import subprocess
import sys
HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1]
sys.path.insert(0, str(AUDIT))
from execution_common import ROOT, BASE, read, sha, write_new, require, historical


def main():
    target = AUDIT / "证据清单.json"
    require(not target.exists(), "C52 already sealed")
    close = read(HERE / "closeout.json")
    require(close["verified"] and close["actual_model_generations"] == 270
        and close["candidate_isolated"] and not close["default_model_changed"], "final closeout required")
    require(not subprocess.check_output(["git", "status", "--porcelain", "--", str(BASE)], cwd=ROOT), "commit all C52 files first")
    files = {str(p.relative_to(BASE)): sha(p) for p in sorted(BASE.rglob("*")) if p.is_file()}
    require(not any("__pycache__" in name for name in files), "bytecode must stay outside repository")
    names = {str((BASE / n).relative_to(ROOT)): v for n, v in files.items()}
    require(historical("HEAD", names) == names, "C52 file bytes not committed")
    write_new(target, files)
    require(all(sha(BASE / n) == v for n, v in files.items()), "C52 bytes changed while sealing")
    print("C52 sealed", len(files), "files;SHA", sha(target), ";270realgenerates;candidate remains isolated;goal active")


if __name__ == "__main__": main()
