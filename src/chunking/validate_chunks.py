from __future__ import annotations

from src.common.io import read_jsonl


def validate_chunks(chunk_path: str, valid_document_ids: set[str]) -> int:
    """chunks.jsonl의 연결성/중복/순서를 검증하고 청크 수를 반환한다."""
    rows = read_jsonl(chunk_path)
    seen: set[str] = set()
    per_doc_last_index: dict[str, int] = {}

    for row in rows:
        cid = str(row.get("chunk_id", "")).strip()
        did = str(row.get("document_id", "")).strip()
        text = str(row.get("text", "")).strip()
        idx = row.get("chunk_index")

        if not cid or not did or not text:
            raise ValueError(f"빈 Chunk 필드가 있습니다: chunk_id={cid}, document_id={did}")
        if cid in seen:
            raise ValueError(f"중복 chunk_id가 존재합니다: {cid}")
        if did not in valid_document_ids:
            raise ValueError(f"존재하지 않는 document_id 참조: chunk_id={cid}, document_id={did}")
        if not isinstance(idx, int) or idx < 0:
            raise ValueError(f"잘못된 chunk_index: chunk_id={cid}, chunk_index={idx}")

        previous = per_doc_last_index.get(did, -1)
        if idx != previous + 1:
            raise ValueError(
                f"청크 순서 오류: document_id={did}, expected={previous + 1}, actual={idx}"
            )
        per_doc_last_index[did] = idx
        seen.add(cid)

    return len(rows)
