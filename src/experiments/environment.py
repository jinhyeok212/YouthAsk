from __future__ import annotations

import importlib.metadata
import platform
import sys
from typing import Any


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def collect_environment_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "python": sys.version,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {
            name: _version(name)
            for name in (
                "PyYAML",
                "jsonschema",
                "numpy",
                "chromadb",
                "sentence-transformers",
                "torch",
                "transformers",
                "huggingface-hub",
                "tqdm",
            )
        },
    }

    try:
        import torch

        info["torch_runtime"] = {
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_device_name": (
                torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
            ),
            "mps_available": bool(
                hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
            ),
        }
    except Exception as exc:
        info["torch_runtime"] = {"error": f"{type(exc).__name__}: {exc}"}

    return info
