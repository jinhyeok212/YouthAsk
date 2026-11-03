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
    strict_max_length: bool = True,
    require_full_coverage: bool = True,
    coverage_target_field: str | None = None,
) -> dict[str, Any]:
    """Validate chunk artifacts before embedding/indexing stages consume them.

    require_full_coverage=False는 기존 검수 청크(reuse 모드)처럼 일부 문서만
    청크로 만든 산출물을 등록할 때 사용한다. main의 기존 검증 범위와 같다.
    coverage_target_field를 주면 원문(해당 필드)의 공백이 아닌 문자가 모두
    어떤 청크의 start_char~end_char 범위에 들어가는지 확인한다(본문 유실 방지).
    """
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
    invalid_order_count = 0
    per_doc_last_index: dict[str, int] = {}

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

        chunk_index = chunk.get("chunk_index")
        previous = per_doc_last_index.get(document_id, -1)
        if not isinstance(chunk_index, int) or chunk_index != previous + 1:
            invalid_order_count += 1
        else:
            per_doc_last_index[document_id] = chunk_index

        # fixed 전략은 최종 text 길이가 chunk_size 이하여야 한다.
        # section/C2 전략은 title prefix가 붙을 수 있어 최종 text가 size보다 길 수 있다.
        if strict_max_length and len(text) > chunk_size:
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
    if invalid_order_count:
        errors.append(f"document_id별 chunk_index 순서가 잘못된 chunk가 {invalid_order_count}개 있습니다.")
    if over_size_count:
        errors.append(f"chunk_size보다 긴 chunk가 {over_size_count}개 있습니다.")
    if missing_chunk_document_ids and require_full_coverage:
        errors.append(f"chunk가 생성되지 않은 document_id가 있습니다: {missing_chunk_document_ids[:5]}")

    uncovered_document_ids: list[str] = []
    if coverage_target_field:
        uncovered_document_ids = _uncovered_document_ids(documents, chunks, coverage_target_field)
        if uncovered_document_ids:
            errors.append(
                f"원문 {coverage_target_field}의 일부가 어떤 chunk에도 포함되지 않은 문서가 "
                f"{len(uncovered_document_ids)}개 있습니다: {uncovered_document_ids[:5]}"
            )

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
        "invalid_order_count": invalid_order_count,
        "uncovered_document_count": len(uncovered_document_ids),
    }


def _uncovered_document_ids(
    documents: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    target_field: str,
) -> list[str]:
    spans_by_document: dict[str, list[tuple[int, int]]] = {}
    for chunk in chunks:
        try:
            span = (int(chunk["start_char"]), int(chunk["end_char"]))
        except (KeyError, TypeError, ValueError):
            continue
        spans_by_document.setdefault(str(chunk.get("document_id") or "").strip(), []).append(span)

    uncovered: list[str] = []
    for document in documents:
        did = _document_id(document)
        text = str(document.get(target_field) or "")
        covered = [False] * len(text)
        for start, end in spans_by_document.get(did, []):
            for position in range(max(0, start), min(end, len(text))):
                covered[position] = True
        if any(not covered[i] and not char.isspace() for i, char in enumerate(text)):
            uncovered.append(did)
    return sorted(uncovered)

