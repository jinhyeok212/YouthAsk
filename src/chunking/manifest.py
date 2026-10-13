from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def chunk_signature(config: dict[str, Any], dataset_info: dict[str, Any]) -> dict[str, Any]:
    chunking = config["chunking"]
    dataset = config["dataset"]
    return {
        "dataset_version": dataset["version"],
        "preprocessing_version": dataset.get("preprocessing_version", ""),
        "dataset_sha256": dataset_info["sha256"],
        "chunking_version": chunking["version"],
        "strategy": chunking["strategy"],
        "size": int(chunking["size"]),
        "overlap": int(chunking["overlap"]),
        "unit": chunking.get("unit", "characters"),
        "target_field": chunking["target_field"],
    }


def default_chunk_paths(config: dict[str, Any]) -> tuple[Path, Path]:
    chunking_version = str(config["chunking"]["version"])
    configured = project_path(config["dataset"]["chunk_path"])

    if configured.parent.name == chunking_version:
        chunk_path = configured
    else:
        chunk_path = configured.parent / "chunks" / chunking_version / "chunks.jsonl"
    return chunk_path, chunk_path.with_name("chunk_manifest.json")


def default_chunk_qrels_paths(config: dict[str, Any]) -> tuple[Path, Path]:
    chunking_version = str(config["chunking"]["version"])
    configured = project_path(config["evaluation"]["chunk_qrels_path"])

    if configured.parent.name == chunking_version:
        qrels_path = configured
    else:
        qrels_path = configured.parent / "chunk_qrels" / chunking_version / "qrels_chunk.jsonl"
    return qrels_path, qrels_path.with_name("qrels_chunk_review_required.jsonl")


def reusable_manifest(manifest_path: Path, chunk_path: Path, signature: dict[str, Any]) -> bool:
    if not manifest_path.exists() or not chunk_path.exists():
        return False

    manifest = read_json(manifest_path)
    if manifest.get("signature") != signature:
        raise ValueError(
            "기존 Chunk Manifest 설정과 현재 YAML이 다릅니다. "
            "다른 조건의 청크를 같은 경로에 덮어쓰지 않습니다."
        )

    manifest_sha = manifest.get("chunk_sha256")
    actual_sha = sha256_file(chunk_path)
    if manifest_sha != actual_sha:
        raise ValueError(
            "Chunk Manifest SHA256 불일치: "
            f"manifest={manifest_sha}, actual={actual_sha}"
        )
    return True


def guard_existing_outputs(manifest_path: Path, chunk_path: Path) -> None:
    if chunk_path.exists() and not manifest_path.exists():
        raise ValueError(
            "기존 chunks.jsonl은 있지만 chunk_manifest.json이 없습니다. "
            "조건을 확인할 수 없어 덮어쓰지 않습니다."
        )


def build_manifest(
    *,
    config: dict[str, Any],
    dataset_info: dict[str, Any],
    signature: dict[str, Any],
    document_path: Path,
    chunk_path: Path,
    chunk_count: int,
    validation: dict[str, Any],
    qrels_result: dict[str, Any],
    reused: bool,
) -> dict[str, Any]:
    strategy = str(config["chunking"]["strategy"])
    size_meaning = (
        "section body split limit; final text may include title prefix"
        if strategy in {"section", "c2_section", "section_aware"}
        else "final chunk text character limit"
    )
    return {
        "signature": signature,
        "document_path": str(document_path),
        "document_sha256": sha256_file(document_path),
        "chunk_path": str(chunk_path),
        "chunk_count": chunk_count,
        "chunk_sha256": sha256_file(chunk_path),
        "created_at_utc": utc_now_iso(),
        "reused": reused,
        "generator": {
            "strategy": strategy,
            "size_meaning": size_meaning,
            "chunk_id_deterministic": True,
        },
        "validation": validation,
        "qrels": qrels_result,
        "dataset_info": dataset_info,
    }

