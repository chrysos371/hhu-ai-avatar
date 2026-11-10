"""Usage: python -m avatar.lab --help. No GPU or network use unless requested."""

import argparse
import json
from pathlib import Path
from .common import PROJECT, WORKSPACE, canonical, sha, write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("capture")
    c.add_argument(
        "--catalog", type=Path, default=PROJECT / "experiments/style/catalog.json"
    )
    c.add_argument("--limit", type=int, default=200)
    c.add_argument("--output", type=Path, required=True)
    c = sub.add_parser("rescreen")
    c.add_argument("--pool", type=Path, required=True)
    c.add_argument(
        "--catalog", type=Path, default=PROJECT / "experiments/style/catalog.json"
    )
    c.add_argument("--output", type=Path, required=True)
    c = sub.add_parser("export")
    c.add_argument("--pool", type=Path, required=True)
    c.add_argument("--output", type=Path, required=True)
    c.add_argument("--maximum", type=int, default=200)
    c = sub.add_parser("lock-models")
    c.add_argument(
        "--config", type=Path, default=PROJECT / "experiments/style/models.json"
    )
    c.add_argument("--output", type=Path, required=True)
    c = sub.add_parser("download-model")
    c.add_argument("--lock", type=Path, required=True)
    c.add_argument("--model", choices=["4b", "14b", "32b"], required=True)
    c = sub.add_parser("resources")
    c = sub.add_parser("preflight")
    c.add_argument("--data", type=Path, required=True)
    c.add_argument("--model-path", type=Path, default=WORKSPACE / "models/Qwen3-4B")
    c.add_argument(
        "--config", type=Path, default=PROJECT / "experiments/style/lora-config.json"
    )
    c.add_argument("--output", type=Path, required=True)
    for name in ("evaluate", "train", "verify-reload"):
        c = sub.add_parser(name)
        c.add_argument("--output", type=Path, required=True)
        c.add_argument("--lock", type=Path)
        c.add_argument("--model", choices=["4b", "14b", "32b"])
        c.add_argument("--gpus", type=int, nargs="+", default=[])
        if name == "evaluate":
            c.add_argument(
                "--suite",
                type=Path,
                default=PROJECT / "experiments/style/dev-suite.json",
            )
            c.add_argument("--adapter", type=Path)
            c.add_argument("--smoke", action="store_true")
            c.add_argument("--style", action="store_true")
            c.add_argument("--include-raw", action="store_true")
        else:
            c.add_argument("--data", type=Path, required=True)
            if name == "train":
                c.add_argument(
                    "--config",
                    type=Path,
                    default=PROJECT / "experiments/style/lora-config.json",
                )
    c = sub.add_parser("judge")
    c.add_argument("--run", type=Path, required=True)
    c.add_argument(
        "--suite", type=Path, default=PROJECT / "experiments/style/dev-suite.json"
    )
    c.add_argument("--judge-model", required=True)
    c.add_argument("--output", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("--runs", type=Path, nargs="+", required=True)
    c.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.command == "capture":
        from .data import capture

        result = capture(a.catalog, a.output, limit=a.limit)
        result = {
            k: result[k]
            for k in ("purpose", "captured", "accepted", "quarantined", "reasons")
        }
    elif a.command == "rescreen":
        from .data import rescreen

        result = rescreen(a.pool, a.output, a.catalog)
    elif a.command == "export":
        from .data import export_pilot

        result = export_pilot(a.pool, a.output, maximum=a.maximum)
    elif a.command == "lock-models":
        from .runner import lock_models

        result = lock_models(a.config, a.output)
    elif a.command == "download-model":
        from .runner import download_model

        result = download_model(a.lock, a.model)
    elif a.command == "resources":
        from .runner import gpu_inventory

        result = gpu_inventory()
    elif a.command == "preflight":
        from .training import preflight

        result = preflight(a.data, a.model_path, a.output, a.config)
    elif a.command == "evaluate":
        from .runner import evaluate

        evaluate(
            a.suite,
            a.output,
            lock_path=a.lock,
            model_name=a.model,
            gpus=a.gpus,
            adapter=a.adapter,
            smoke=a.smoke,
            style=a.style,
            include_raw=a.include_raw,
        )
        result = json.loads((a.output / "comparison.json").read_text())
    elif a.command in ("train", "verify-reload"):
        if not a.lock or not a.model:
            p.error("--lock and --model required")
        from .training import train, verify_reload

        result = (
            train(a.data, a.lock, a.model, a.config, a.output, gpus=a.gpus)
            if a.command == "train"
            else verify_reload(a.data, a.lock, a.model, a.output, gpus=a.gpus)
        )
    elif a.command == "judge":
        from .judge import judge_run

        result = judge_run(a.run, a.suite, a.output, a.judge_model)
    else:
        from .runner import compare_runs

        result = compare_runs(a.runs, a.output)
    print(canonical(result))


if __name__ == "__main__":
    main()
