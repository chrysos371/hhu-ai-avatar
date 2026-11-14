"""Seal committed C51 artifacts after final verification; never include the seal itself."""
import json
from pathlib import Path
import subprocess

from avatar.lab.common import sha
from collect_closeout import historical
from run_python_regression import ROOT, BASE


def main():
    output = BASE / "审计/证据清单.json"
    assert not output.exists()
    close = json.loads((BASE / "审计/收尾核验/closeout.json").read_text())
    assert close["verified"] and close["new_model_generations"] == 0 and close["training_steps"] == 0
    paths = sorted(p for p in BASE.rglob("*") if p.is_file() and p != output)
    relative = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert historical(head, relative) == relative, "commit all closed C51 artifacts before sealing"
    manifest = {str(p.relative_to(BASE)): relative[str(p.relative_to(ROOT))] for p in paths}
    with output.open("x") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    assert all(sha(BASE / name) == value for name, value in manifest.items())
    print("C51 sealed", len(manifest), "files;SHA", sha(output), ";committed source", head, ";overall goal remains active")


if __name__ == "__main__":
    main()
