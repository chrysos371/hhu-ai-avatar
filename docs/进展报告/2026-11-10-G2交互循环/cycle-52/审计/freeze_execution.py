"""Freeze all four stages only after C51 closes; no model or GPU construction."""
import argparse
import subprocess

from execution_common import (ROOT, WORK, RUN, DATA, STAGES, TOKENIZATION,
    protocol_check, preparation_check, required_inputs, historical, sha, write_new, require)


def main(seal):
    protocol_check()
    preparation_check(seal)
    require(not RUN.exists(), "C52 real output already exists; do not repeat")
    path = WORK / "freeze-v1.json"
    require(not path.exists(), "C52 freeze already exists")
    names = required_inputs()
    hashes = {name: sha(ROOT / name) for name in names}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(historical(head, names) == hashes, "commit all C52 execution inputs first")
    write_new(path, {"source_ref": head, "sha256": hashes, "run_root": str(RUN),
        "stages": list(STAGES), "c51_seal_sha256": seal,
        "external_data_sha256": {name: sha(DATA.parent / name)
            for name in ("sft.jsonl", "dev.jsonl", "manifest.json")},
        "training_config_sha256": sha(TOKENIZATION / "training-config-v1.json"),
        "scope": "single prospective four-stage BF16 developmental experiment; failed stages retained without retries",
        "default_activation_authorized": False, "model_constructions": 0, "training_steps": 0})
    print("C52 four-stage execution frozen", head, "inputs", len(hashes), "SHA", sha(path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c51-seal-sha256", required=True)
    main(parser.parse_args().c51_seal_sha256)
