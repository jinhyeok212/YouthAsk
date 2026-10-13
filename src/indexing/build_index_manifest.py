"""Index manifest/signature helpers used to decide safe Chroma reuse."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


INDEX_AFFECTING_KEYS = (
    "index_version",
    "dataset_version",
    "preprocessing_version",
    "dataset_sha256",
    "chunking_version",
    "chunk_size",
    "chunk_overlap",
    "chunk_target_field",
    "chunk_sha256",
    "embedding_model",
    "embedding_revision",
    "embedding_dimension",
    "embedding_normalize",
    "distance_metric",
)


def build_index_signature(config: dict, chunk_info: dict) -> Dict[str, Any]:
    dataset = config["dataset"]
    chunking = config["chunking"]
    embedding = config["embedding"]
    index = config["index"]

    return {
        "index_version": index["version"],
        "dataset_version": dataset["version"],
        "preprocessing_version": dataset["preprocessing_version"],
        "dataset_sha256": chunk_info.get("dataset_sha256"),
        "chunking_version": chunking["version"],
        "chunk_size": int(chunking["size"]),
        "chunk_overlap": int(chunking["overlap"]),
        "chunk_target_field": chunking["target_field"],
        "chunk_sha256": chunk_info.get("chunk_sha256"),
        "chunk_count": int(chunk_info["chunk_count"]),
        "embedding_model": embedding["model"],
        "embedding_revision": embedding.get("revision"),
        "embedding_dimension": int(embedding["dimension"]),
        "embedding_normalize": bool(embedding["normalize"]),
        "distance_metric": index["distance_metric"],
    }


def build_index_manifest(
    config: dict,
    chunk_info: dict,
    *,
    index_count: int,
    build_time_seconds: float,
    reused: bool,
) -> Dict[str, Any]:
    index = config["index"]
    return {
        "manifest_schema_version": "2.0",
        "index_version": index["version"],
        "db_path": index["db_path"],
        "collection_name": index["collection_name"],
        "signature": build_index_signature(config, chunk_info),
        "index_count": int(index_count),
        "build_time_seconds": float(build_time_seconds),
        "reused": bool(reused),
    }


def manifest_matches(manifest: dict, config: dict, chunk_info: dict) -> bool:
    expected = build_index_signature(config, chunk_info)
    actual = manifest.get("signature", {})

    for key in INDEX_AFFECTING_KEYS:
        if actual.get(key) != expected.get(key):
            return False

    if actual.get("chunk_count") != expected.get("chunk_count"):
        return False

    return True


def load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
