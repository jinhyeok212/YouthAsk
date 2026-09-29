from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _document_id(document: dict[str, Any]) -> str:
    return str(document.get("document_id") or document.get("doc_id") or "").strip()


def validate_chunks(
    documents_path: str | Path,
    chunks_path: str | Path,
    *,
    chunk_size: int,
    overlap: int,
) -> dict[str, Any]:
    """Validate chunk artifacts before embedding/indexing stages consume them."""
    documents_path = Path(documents_path)
    chunks_path = Path(chunks_path)

    if chunk_size <= 0:
        raise ValueError("chunk_size는 0보다 커야 합니다.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap은 0 이상이고 chunk_size보다 작아야 합니다.")
    if not documents_path.exists():
        raise ValueError(f"documents.jsonl 파일이 없습니다: {documents_path}")
    if not chunks_path.exists():
        raise ValueError(f"chunks.jsonl 파일이 없습니다: {chunks_path}")

    documents = _read_jsonl(documents_path)
    chunks = _read_jsonl(chunks_path)

    document_ids = [_document_id(document) for document in documents]
    valid_document_ids = {document_id for document_id in document_ids if document_id}
    if not valid_document_ids:
        raise ValueError("documents.jsonl에 유효한 document_id가 없습니다.")

    errors: list[str] = []
    chunk_ids: list[str] = []
    blank_chunk_count = 0
    missing_document_id_count = 0
    invalid_document_refs: list[str] = []
    invalid_char_length_count = 0
    over_size_count = 0

    for row_number, chunk in enumerate(chunks, start=1):
        chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
        document_id = str(chunk.get("document_id") or "").strip()
        text = str(chunk.get("text") or "")

        if not chunk_id:
            errors.append(f"{row_number}번째 chunk에 chunk_id가 없습니다.")
        else:
            chunk_ids.append(chunk_id)

        if not document_id:
            missing_document_id_count += 1
            errors.append(f"{row_number}번째 chunk에 document_id가 없습니다.")
        elif document_id not in valid_document_ids:
            invalid_document_refs.append(document_id)

        if not text.strip():
            blank_chunk_count += 1
            errors.append(f"{row_number}번째 chunk의 text가 비어 있습니다.")

        if "char_length" in chunk and int(chunk.get("char_length") or 0) != len(text):
            invalid_char_length_count += 1

        # Overlap can make source spans shorter, but emitted text should not exceed
        # the configured character chunk size for this simple character splitter.
        if len(text) > chunk_size:
            over_size_count += 1

    duplicate_chunk_ids = sorted(
        chunk_id for chunk_id, count in Counter(chunk_ids).items() if count > 1
    )
    chunk_document_ids = {str(chunk.get("document_id") or "").strip() for chunk in chunks}
    missing_chunk_document_ids = sorted(valid_document_ids - chunk_document_ids)

    if duplicate_chunk_ids:
        errors.append(f"중복 chunk_id가 존재합니다: {duplicate_chunk_ids[:5]}")
    if invalid_document_refs:
        errors.append(f"원본 문서에 없는 document_id가 chunk에 있습니다: {sorted(set(invalid_document_refs))[:5]}")
    if invalid_char_length_count:
        errors.append(f"char_length가 실제 text 길이와 다른 chunk가 {invalid_char_length_count}개 있습니다.")
    if over_size_count:
        errors.append(f"chunk_size보다 긴 chunk가 {over_size_count}개 있습니다.")
    if missing_chunk_document_ids:
        errors.append(f"chunk가 생성되지 않은 document_id가 있습니다: {missing_chunk_document_ids[:5]}")

    if errors:
        raise ValueError("청킹 검증 실패:\n- " + "\n- ".join(errors))

    return {
        "valid": True,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "duplicate_chunk_id_count": len(duplicate_chunk_ids),
        "blank_chunk_count": blank_chunk_count,
        "missing_document_id_count": missing_document_id_count,
        "missing_chunk_document_id_count": len(missing_chunk_document_ids),
    }

