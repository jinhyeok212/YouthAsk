from __future__ import annotations

from typing import Any

from src.chunking.build_chunk_qrels import build_chunk_qrels, validate_chunk_qrels
from src.chunking.generators import FIXED_STRATEGIES, generate_chunks
from src.chunking.manifest import (
    build_manifest,
    chunk_signature,
    default_chunk_paths,
    default_chunk_qrels_paths,
    guard_existing_outputs,
    project_path,
    read_jsonl,
    reusable_manifest,
    sha256_file,
    write_json,
    write_jsonl,
)
from src.chunking.validate_chunks import validate_chunks


def _strict_max_length(strategy: str) -> bool:
    return strategy.lower() in FIXED_STRATEGIES


def build_chunks(config: dict[str, Any], dataset_info: dict[str, Any]) -> dict[str, Any]:
    """Prepare chunks for the experiment runner.

    같은 입력 데이터와 같은 청킹 조건이면 기존 청크를 재사용하고,
    조건이 다르면 조건별 경로에 새 청크를 생성한다.
    """
    chunking = config["chunking"]
    version = str(chunking["version"])
    strategy = str(chunking["strategy"])
    size = int(chunking["size"])
    overlap = int(chunking["overlap"])
    unit = str(chunking.get("unit", "characters"))
    target_field = str(chunking["target_field"])

    document_path = project_path(dataset_info.get("document_path") or config["dataset"]["document_path"])
    document_qrels_path = project_path(config["evaluation"]["document_qrels_path"])
    chunk_path, manifest_path = default_chunk_paths(config)
    chunk_qrels_path, review_required_path = default_chunk_qrels_paths(config)
    signature = chunk_signature(config, dataset_info)

    reused = False
    if reusable_manifest(manifest_path, chunk_path, signature):
        reused = True
    else:
        guard_existing_outputs(manifest_path, chunk_path)
        documents = read_jsonl(document_path)
        chunks = generate_chunks(
            documents,
            version=version,
            strategy=strategy,
            size=size,
            overlap=overlap,
            unit=unit,
            target_field=target_field,
        )
        write_jsonl(chunk_path, chunks)

    validation = validate_chunks(
        document_path,
        chunk_path,
        chunk_size=size,
        overlap=overlap,
        strict_max_length=_strict_max_length(strategy),
    )
    qrels_result = build_chunk_qrels(
        document_qrels_path,
        chunk_path,
        chunk_qrels_path,
        review_required_path,
    )
    if qrels_result["mapped_row_count"] > 0:
        validate_chunk_qrels(chunk_qrels_path, chunk_path)

    manifest = build_manifest(
        config=config,
        dataset_info=dataset_info,
        signature=signature,
        document_path=document_path,
        chunk_path=chunk_path,
        chunk_count=validation["chunk_count"],
        validation=validation,
        qrels_result=qrels_result,
        reused=reused,
    )
    write_json(manifest_path, manifest)

    return {
        "chunk_path": str(chunk_path),
        "manifest_path": str(manifest_path),
        "chunk_count": validation["chunk_count"],
        "chunk_qrels_path": str(chunk_qrels_path),
        "chunk_qrels_status": qrels_result["status"],
        "chunk_qrels_review_required_path": str(review_required_path),
        "chunk_sha256": sha256_file(chunk_path),
        "dataset_sha256": dataset_info["sha256"],
    }

