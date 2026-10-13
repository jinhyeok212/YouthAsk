from __future__ import annotations

from pathlib import Path

from src.chunking.build_chunk_qrels import validate_chunk_qrels
from src.common.io import load_json, read_jsonl, sha256_file, utc_now_iso, write_json


def _chunk_signature(config: dict, dataset_info: dict) -> dict:
    c = config["chunking"]
    return {
        "dataset_version": config["dataset"]["version"],
        "preprocessing_version": config["dataset"]["preprocessing_version"],
        "dataset_sha256": dataset_info["sha256"],
        "chunking_version": c["version"],
        "strategy": c["strategy"],
        "size": int(c["size"]),
        "overlap": int(c["overlap"]),
        "unit": c["unit"],
        "target_field": c["target_field"],
    }


def _validate_existing_chunks(chunk_path: Path, document_ids: set[str]) -> int:
    rows = read_jsonl(chunk_path)
    if not rows:
        raise ValueError("chunks.jsonl이 비어 있습니다.")

    seen: set[str] = set()
    per_doc_last_index: dict[str, int] = {}

    for row in rows:
        cid = str(row.get("chunk_id", "")).strip()
        did = str(row.get("document_id", "")).strip()
        text = str(row.get("text", "")).strip()
        idx = row.get("chunk_index")

        if not cid or not did or not text:
            raise ValueError(
                f"빈 Chunk 필드가 있습니다: chunk_id={cid}, document_id={did}"
            )
        if cid in seen:
            raise ValueError(f"중복 chunk_id가 존재합니다: {cid}")
        if did not in document_ids:
            raise ValueError(
                f"존재하지 않는 document_id를 참조합니다: chunk_id={cid}, document_id={did}"
            )
        if not isinstance(idx, int) or idx < 0:
            raise ValueError(
                f"잘못된 chunk_index: chunk_id={cid}, chunk_index={idx}"
            )

        previous = per_doc_last_index.get(did, -1)
        if idx != previous + 1:
            raise ValueError(
                f"청크 순서 오류: document_id={did}, expected={previous + 1}, actual={idx}"
            )

        per_doc_last_index[did] = idx
        seen.add(cid)

    return len(rows)


def build_chunks(config: dict, dataset_info: dict) -> dict:
    """Validate and register the team's pre-built C2 chunks.

    Team-ready v4 deliberately does NOT auto-create chunks. The evaluated
    qrels_chunk.jsonl is tied to deterministic C2 chunk IDs, so generating a
    different fallback chunk-ID convention inside the experiment runner would
    silently invalidate the evaluation set.
    """
    c = config["chunking"]
    chunk_path = Path(c["chunk_path"])
    manifest_path = Path(c["manifest_path"])

    if not chunk_path.exists():
        raise FileNotFoundError(
            "검수된 chunks.jsonl이 필요합니다. Team Ready Runner는 qrels와의 ID 정합성을 "
            f"보호하기 위해 청크를 자동 생성하지 않습니다: {chunk_path}"
        )

    documents = read_jsonl(dataset_info["document_path"])
    document_ids = {str(d["document_id"]) for d in documents}
    current_sig = _chunk_signature(config, dataset_info)
    count = _validate_existing_chunks(chunk_path, document_ids)
    actual_sha = sha256_file(chunk_path)

    if manifest_path.exists():
        old = load_json(manifest_path)
        old_sig = old.get("signature", {})
        if old_sig != current_sig:
            raise ValueError(
                "기존 Chunk Manifest 설정과 현재 YAML이 다릅니다. 기존 chunks.jsonl을 "
                "덮어쓰지 않습니다. 올바른 chunking.version/config를 사용하세요."
            )
        manifest_sha = old.get("chunk_sha256")
        if manifest_sha and manifest_sha != actual_sha:
            raise ValueError(
                "Chunk Manifest SHA256 불일치: "
                f"manifest={manifest_sha}, actual={actual_sha}"
            )
    else:
        write_json(
            manifest_path,
            {
                "signature": current_sig,
                "chunk_path": str(chunk_path),
                "chunk_count": count,
                "chunk_sha256": actual_sha,
                "created_at_utc": utc_now_iso(),
                "bootstrap_from_existing": True,
            },
        )

    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    if not qrels_path.exists():
        raise FileNotFoundError(
            f"검수된 qrels_chunk.jsonl이 필요합니다: {qrels_path}"
        )

    validate_chunk_qrels(
        chunk_qrels_path=str(qrels_path),
        chunk_path=str(chunk_path),
    )

    return {
        "chunk_path": str(chunk_path),
        "manifest_path": str(manifest_path),
        "chunk_count": count,
        "chunk_qrels_path": str(qrels_path),
        "chunk_sha256": actual_sha,
        "dataset_sha256": dataset_info["sha256"],
    }
