from __future__ import annotations

from pathlib import Path
from typing import Any

from src.chunking.build_chunk_qrels import resolve_chunk_qrels, validate_document_qrels_rows
from src.chunking.generators import chunk_id_scheme, generate_chunks, normalize_strategy
from src.chunking.manifest import (
    StagedOutputs,
    build_manifest,
    check_manifest,
    chunk_signature,
    configured_chunk_paths,
    generated_chunk_signature,
    guard_partial_outputs,
    project_path,
    read_json,
    read_jsonl,
    sha256_file,
    utc_now_iso,
    write_json,
    write_jsonl,
)
from src.chunking.validate_chunks import validate_chunks


CHUNKING_MODES = ("reuse", "generate")

# generate 모드 signature에만 있는 필드. reuse 모드는 이 필드를 빼고 비교한다.
_GENERATE_ONLY_SIGNATURE_FIELDS = ("mode", "chunk_id_scheme")


def chunking_mode(config: dict[str, Any]) -> str:
    mode = str(config["chunking"].get("mode", "reuse"))
    if mode not in CHUNKING_MODES:
        raise ValueError(f"지원하지 않는 chunking.mode입니다: {mode} (허용: {CHUNKING_MODES})")
    return mode


def _reuse_existing_chunks(
    config: dict[str, Any],
    dataset_info: dict[str, Any],
    *,
    document_path: Path,
    chunk_path: Path,
    manifest_path: Path,
    chunk_qrels_path: Path,
) -> dict[str, Any]:
    """검수된 기존 청크(C2 등)를 검증·등록한다. 청크를 생성하지 않는다."""
    chunking = config["chunking"]
    if not chunk_path.exists():
        raise FileNotFoundError(
            "검수된 chunks.jsonl이 필요합니다. reuse 모드는 qrels와의 ID 정합성을 "
            f"보호하기 위해 청크를 자동 생성하지 않습니다: {chunk_path}"
        )

    validation = validate_chunks(
        document_path,
        chunk_path,
        chunk_size=int(chunking["size"]),
        overlap=int(chunking["overlap"]),
        strict_max_length=False,
        require_full_coverage=False,
    )
    signature = chunk_signature(config, dataset_info)
    chunk_sha = sha256_file(chunk_path)

    staged = StagedOutputs()
    try:
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            old_signature = {
                key: value
                for key, value in manifest.get("signature", {}).items()
                if key not in _GENERATE_ONLY_SIGNATURE_FIELDS
            }
            if old_signature != signature:
                raise ValueError(
                    "기존 Chunk Manifest 설정과 현재 YAML이 다릅니다. 기존 chunks.jsonl을 "
                    "덮어쓰지 않습니다. 올바른 chunking.version/config를 사용하세요."
                )
            manifest_sha = manifest.get("chunk_sha256")
            if manifest_sha and manifest_sha != chunk_sha:
                raise ValueError(
                    "Chunk Manifest SHA256 불일치: "
                    f"manifest={manifest_sha}, actual={chunk_sha}"
                )
        else:
            write_json(
                staged.path_for(manifest_path),
                {
                    "signature": signature,
                    "chunk_path": str(chunk_path),
                    "chunk_count": validation["chunk_count"],
                    "chunk_sha256": chunk_sha,
                    "created_at_utc": utc_now_iso(),
                    "bootstrap_from_existing": True,
                },
            )

        qrels_result = resolve_chunk_qrels(
            chunk_qrels_path=chunk_qrels_path,
            chunk_path=chunk_path,
            chunks=read_jsonl(chunk_path),
            chunk_sha256=chunk_sha,
            chunking_version=str(chunking["version"]),
            document_qrels_path=None,
            allow_auto=False,
            bootstrap_status="legacy_bootstrap",
            staged=staged,
        )
        staged.commit()
    finally:
        staged.cleanup()

    return {
        "chunk_count": validation["chunk_count"],
        "chunk_sha256": chunk_sha,
        "chunks_reused": True,
        "qrels_result": qrels_result,
    }


def _generate_or_reuse_generated_chunks(
    config: dict[str, Any],
    dataset_info: dict[str, Any],
    *,
    document_path: Path,
    chunk_path: Path,
    manifest_path: Path,
    chunk_qrels_path: Path,
) -> dict[str, Any]:
    """조건별 청크를 생성한다. 같은 조건의 산출물이 있으면 재사용한다.

    결과는 임시 파일에 먼저 쓰고 검증이 끝난 뒤 반영한다(manifest가 마지막).
    """
    chunking = config["chunking"]
    version = str(chunking["version"])
    strategy = normalize_strategy(str(chunking["strategy"]))
    size = int(chunking["size"])
    overlap = int(chunking["overlap"])

    if version.startswith("c2_"):
        raise ValueError(
            "generate 모드에서는 c2_ 로 시작하는 chunking.version을 쓸 수 없습니다. "
            "기존 C2 청크는 생성 규칙이 달라(chunk_id/section 체계) mode: reuse로만 사용합니다: "
            f"{version}"
        )

    scheme = chunk_id_scheme(strategy)
    signature = generated_chunk_signature(config, dataset_info, scheme)
    document_qrels_path = project_path(config["evaluation"]["document_qrels_path"])
    guard_partial_outputs(manifest_path, chunk_path)

    staged = StagedOutputs()
    try:
        reused = manifest_path.exists()
        if reused:
            check_manifest(manifest_path, chunk_path, signature)
            chunk_file = chunk_path
            chunks = read_jsonl(chunk_path)
        else:
            # 출력 파일을 쓰기 전에 검증 가능한 입력부터 확인한다.
            if not chunk_qrels_path.exists():
                if not document_qrels_path.exists():
                    raise ValueError(f"문서 qrels 파일이 없습니다: {document_qrels_path}")
                validate_document_qrels_rows(read_jsonl(document_qrels_path))
            chunks = generate_chunks(
                read_jsonl(document_path),
                version=version,
                strategy=strategy,
                size=size,
                overlap=overlap,
                unit=str(chunking.get("unit", "characters")),
                target_field=str(chunking["target_field"]),
            )
            chunk_file = staged.path_for(chunk_path)
            write_jsonl(chunk_file, chunks)

        validation = validate_chunks(
            document_path,
            chunk_file,
            chunk_size=size,
            overlap=overlap,
            strict_max_length=strategy == "fixed",
        )
        chunk_sha = sha256_file(chunk_file)

        qrels_result = resolve_chunk_qrels(
            chunk_qrels_path=chunk_qrels_path,
            chunk_path=chunk_file,
            chunks=chunks,
            chunk_sha256=chunk_sha,
            chunking_version=version,
            document_qrels_path=document_qrels_path,
            allow_auto=True,
            bootstrap_status="reviewed",
            staged=staged,
        )

        if not reused:
            write_json(
                staged.path_for(manifest_path),
                build_manifest(
                    config=config,
                    dataset_info=dataset_info,
                    signature=signature,
                    document_path=document_path,
                    chunk_path=chunk_path,
                    chunk_sha256=chunk_sha,
                    chunk_count=validation["chunk_count"],
                    validation=validation,
                    scheme=scheme,
                ),
            )
        staged.commit()
    finally:
        staged.cleanup()

    return {
        "chunk_count": validation["chunk_count"],
        "chunk_sha256": chunk_sha,
        "chunks_reused": reused,
        "qrels_result": qrels_result,
    }


def build_chunks(config: dict[str, Any], dataset_info: dict[str, Any]) -> dict[str, Any]:
    """Prepare chunks and chunk qrels for the experiment runner.

    경로는 YAML 계약(chunking.chunk_path, chunking.manifest_path,
    evaluation.chunk_qrels_path)을 그대로 쓴다. 반환 경로는 config 경로와 같다.

    - mode: reuse (기본) — 검수된 기존 청크/qrels를 검증·등록한다.
    - mode: generate — 조건별 청크를 생성하고 근거 기반 qrels 후보를 만든다.
      근거가 부족하면 chunk_qrels_status=review_required를 반환한다.
    """
    mode = chunking_mode(config)
    document_path = project_path(dataset_info.get("document_path") or config["dataset"]["document_path"])
    chunk_path, manifest_path, chunk_qrels_path = configured_chunk_paths(config)

    prepare = _reuse_existing_chunks if mode == "reuse" else _generate_or_reuse_generated_chunks
    prepared = prepare(
        config,
        dataset_info,
        document_path=document_path,
        chunk_path=chunk_path,
        manifest_path=manifest_path,
        chunk_qrels_path=chunk_qrels_path,
    )
    qrels_result = prepared["qrels_result"]

    return {
        "chunk_path": str(chunk_path),
        "manifest_path": str(manifest_path),
        "chunk_count": prepared["chunk_count"],
        "chunk_qrels_path": str(chunk_qrels_path),
        "chunk_qrels_status": qrels_result["status"],
        "chunk_qrels_review_status": qrels_result["review_status"],
        "chunk_qrels_candidates_path": qrels_result["candidates_path"],
        "chunk_qrels_review_required_path": qrels_result["review_required_path"],
        "chunk_qrels_meta_path": qrels_result["meta_path"],
        "chunk_qrels_mapped_row_count": qrels_result["mapped_row_count"],
        "chunk_qrels_review_required_count": qrels_result["review_required_count"],
        "chunk_sha256": prepared["chunk_sha256"],
        "dataset_sha256": dataset_info["sha256"],
        "chunking_mode": mode,
        "chunks_reused": prepared["chunks_reused"],
    }
