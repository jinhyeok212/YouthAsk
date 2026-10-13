from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.experiments.config_validator import inspect_input_readiness, load_and_validate_config


PACKAGES = [
    "PyYAML",
    "jsonschema",
    "numpy",
    "chromadb",
    "sentence-transformers",
    "torch",
    "tqdm",
]


def version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Team environment doctor")
    parser.add_argument(
        "--config",
        default="configs/experiments/exp_full_kure_v4_team.yaml",
    )
    args = parser.parse_args()

    py = sys.version_info
    python_supported = (3, 10) <= (py.major, py.minor) < (3, 14)
    packages = {name: version(name) for name in PACKAGES}
    packages_ready = all(packages.values())

    config_error = None
    readiness = None
    try:
        config = load_and_validate_config(args.config)
        readiness = inspect_input_readiness(config)
    except Exception as exc:
        config_error = f"{type(exc).__name__}: {exc}"

    device = {"cuda_available": None, "mps_available": None}
    try:
        import torch

        device["cuda_available"] = bool(torch.cuda.is_available())
        device["mps_available"] = bool(
            hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        )
    except Exception:
        pass

    report = {
        "project_root": str(ROOT),
        "python": platform.python_version(),
        "python_supported": python_supported,
        "platform": platform.platform(),
        "packages": packages,
        "packages_ready": packages_ready,
        "device": device,
        "config_error": config_error,
        "input_readiness": readiness,
        "doctor_pass": bool(
            python_supported
            and packages_ready
            and config_error is None
            and readiness
            and readiness["input_files_ready"]
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not report["doctor_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
