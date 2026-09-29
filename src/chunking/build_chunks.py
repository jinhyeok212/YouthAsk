from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from src.chunking.build_chunk_qrels import build_chunk_qrels
from src.chunking.validate_chunks import validate_chunks


ROOT = Path(__file__).resolve().parents[2]
TEXT_FIELD_CANDIDATES = ("retrieval_text", "content", "text")


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_id(document: dict[str, Any]) -> str:
    return str(document.get("document_id") or document.get("doc_id") or "").strip()


def _document_text(document: dict[str, Any]) -> tuple[str, str]:
    for field_name in TEXT_FIELD_CANDIDATES:
        value = document.get(field_name)
        if isinstance(value, str) and value.strip():
            return value, field_name
    return "", ""


def _scalar(value: Any) -> str | int | float | bool:
    if isinstance(value, bool | int | float | str):
        return value
    if value is None:
        return ""
    return str(value)


def _chunk_spans(text_length: int, chunk_size: int, overlap: int) -> list[tuple[int, int]]:
    if text_length <= 0:
        return []
    if chunk_size <= 0:
        raise ValueError("chunking.size는 0보다 커야 합니다.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunking.overlap은 0 이상이고 chunking.size보다 작아야 합니다.")

    spans: list[tuple[int, int]] = []
    step = chunk_size - overlap
    start = 0
    while start < text_length:
        end = min(start + chunk_size, text_length)
        spans.append((start, end))
        if end >= text_length:
            break
        start += step
    return spans


def _chunk_metadata(
    document: dict[str, Any],
    *,
    version: str,
    chunk_size: int,
    overlap: int,
    source_text_field: str,
) -> dict[str, str | int | float | bool]:
    # Chroma metadata는 list/dict를 직접 받지 못하는 경우가 있어 scalar만 유지한다.
    metadata: dict[str, str | int | float | bool] = {
        "chunking_version": version,
        "chunk_size": chunk_size,
        "overlap": overlap,
        "source_text_field": source_text_field,
        "title": _scalar(document.get("title", "")),
        "category": _scalar(document.get("category", "")),
        "source": _scalar(document.get("source", "")),
        "url": _scalar(document.get("url", "")),
    }

    for key, value in (document.get("metadata") or {}).items():
        if key not in metadata:
            metadata[key] = _scalar(value)
    return metadata


def _build_document_chunks(
    document: dict[str, Any],
    *,
    version: str,
    chunk_size: int,
    overlap: int,
) -> list[dict[str, Any]]:
    document_id = _document_id(document)
    if not document_id:
        raise ValueError("document_id가 없는 문서가 있습니다.")

    text, source_text_field = _document_text(document)
    if not text.strip():
        raise ValueError(f"document_id={document_id} 문서에 청킹할 본문이 없습니다.")

    chunks: list[dict[str, Any]] = []
    spans = _chunk_spans(len(text), chunk_size, overlap)
    for chunk_index, (start_char, end_char) in enumerate(spans):
        chunk_text = text[start_char:end_char]
        chunk_id = f"{document_id}__chunk_{chunk_index:03d}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "text": chunk_text,
                "chunk_index": chunk_index,
                "start_char": start_char,
                "end_char": end_char,
                "char_length": len(chunk_text),
                "chunking_version": version,
                "metadata": _chunk_metadata(
                    document,
                    version=version,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    source_text_field=source_text_field,
                ),
            }
        )
    return chunks


def _manifest(
    *,
    config: dict[str, Any],
    dataset_info: dict[str, Any],
    documents_path: Path,
    chunks_path: Path,
    chunk_qrels_path: Path,
    validation: dict[str, Any],
    qrels_result: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    chunk_lengths = [int(chunk["char_length"]) for chunk in chunks]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment_id": config.get("experiment_id", ""),
        "chunking": {
            "version": config["chunking"]["version"],
            "size": config["chunking"]["size"],
            "overlap": config["chunking"]["overlap"],
            "unit": config["chunking"].get("unit", "characters"),
            "chunk_id_pattern": "{document_id}__chunk_{chunk_index:03d}",
            "text_field": "text",
            "input_text_field_priority": list(TEXT_FIELD_CANDIDATES),
        },
        "input": {
            "document_path": str(documents_path),
            "document_sha256": _sha256_file(documents_path),
            "dataset_info": dataset_info,
        },
        "output": {
            "chunk_path": str(chunks_path),
            "chunk_qrels_path": str(chunk_qrels_path),
        },
        "counts": {
            "document_count": validation["document_count"],
            "chunk_count": validation["chunk_count"],
            "chunk_length_min": min(chunk_lengths) if chunk_lengths else 0,
            "chunk_length_avg": round(mean(chunk_lengths), 3) if chunk_lengths else 0,
            "chunk_length_max": max(chunk_lengths) if chunk_lengths else 0,
        },
        "validation": validation,
        "qrels": qrels_result,
    }


def build_chunks(config: dict[str, Any], dataset_info: dict[str, Any]) -> dict[str, Any]:
    """Runner entrypoint for the chunking stage.

    The function follows the experiment contract:
    it creates chunks, validates them, builds chunk qrels, writes a manifest,
    and returns ChunkInfo for the next pipeline stage.
    """
    chunking = config["chunking"]
    version = str(chunking["version"])
    chunk_size = int(chunking["size"])
    overlap = int(chunking["overlap"])
    unit = str(chunking.get("unit", "characters"))
    if unit not in {"characters", "character", "chars"}:
        raise ValueError(f"지원하지 않는 chunking.unit입니다: {unit}")

    document_path_value = dataset_info.get("document_path") or config["dataset"]["document_path"]
    documents_path = _project_path(document_path_value)
    chunks_path = _project_path(config["dataset"]["chunk_path"])
    chunk_manifest_path = chunks_path.with_name("chunk_manifest.json")
    document_qrels_path = _project_path(config["evaluation"]["document_qrels_path"])
    chunk_qrels_path = _project_path(config["evaluation"]["chunk_qrels_path"])

    documents = _read_jsonl(documents_path)
    chunks: list[dict[str, Any]] = []
    for document in documents:
        chunks.extend(
            _build_document_chunks(
                document,
                version=version,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )

    _write_jsonl(chunks_path, chunks)
    validation = validate_chunks(
        documents_path,
        chunks_path,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    qrels_result = build_chunk_qrels(document_qrels_path, chunks_path, chunk_qrels_path)
    manifest = _manifest(
        config=config,
        dataset_info=dataset_info,
        documents_path=documents_path,
        chunks_path=chunks_path,
        chunk_qrels_path=chunk_qrels_path,
        validation=validation,
        qrels_result=qrels_result,
        chunks=chunks,
    )
    _write_json(chunk_manifest_path, manifest)

    return {
        "chunk_path": str(chunks_path),
        "manifest_path": str(chunk_manifest_path),
        "chunk_count": len(chunks),
        "chunk_qrels_path": str(chunk_qrels_path),
    }

