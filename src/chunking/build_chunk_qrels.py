from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _positive_document_ids(qrel: dict[str, Any]) -> list[str]:
    if qrel.get("ground_truth_document_ids") is not None:
        return [str(value).strip() for value in qrel.get("ground_truth_document_ids") or [] if str(value).strip()]

    if qrel.get("document_id") is None:
        return []

    relevance = int(qrel.get("relevance", 1) or 0)
    if relevance <= 0:
        return []
    return [str(qrel.get("document_id")).strip()]


def build_chunk_qrels(
    document_qrels_path: str | Path,
    chunks_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Convert document-level qrels into chunk-level qrels for retrieval evaluation."""
    document_qrels_path = Path(document_qrels_path)
    chunks_path = Path(chunks_path)
    output_path = Path(output_path)

    if not document_qrels_path.exists():
        raise ValueError(f"문서 qrels 파일이 없습니다: {document_qrels_path}")
    if not chunks_path.exists():
        raise ValueError(f"chunks.jsonl 파일이 없습니다: {chunks_path}")

    qrels = _read_jsonl(document_qrels_path)
    chunks = _read_jsonl(chunks_path)

    chunks_by_document: dict[str, list[str]] = defaultdict(list)
    all_chunk_ids: set[str] = set()
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
        document_id = str(chunk.get("document_id") or "").strip()
        if chunk_id and document_id:
            chunks_by_document[document_id].append(chunk_id)
            all_chunk_ids.add(chunk_id)

    docs_by_query: dict[str, list[str]] = defaultdict(list)
    seen_pairs: set[tuple[str, str]] = set()
    for row_number, qrel in enumerate(qrels, start=1):
        query_id = str(qrel.get("query_id") or "").strip()
        if not query_id:
            raise ValueError(f"{row_number}번째 qrels 행에 query_id가 없습니다.")

        for document_id in _positive_document_ids(qrel):
            pair = (query_id, document_id)
            if pair not in seen_pairs:
                docs_by_query[query_id].append(document_id)
                seen_pairs.add(pair)

    output_rows: list[dict[str, Any]] = []
    missing_documents: set[str] = set()
    for query_id, document_ids in docs_by_query.items():
        chunk_ids: list[str] = []
        for document_id in document_ids:
            mapped_chunk_ids = chunks_by_document.get(document_id, [])
            if not mapped_chunk_ids:
                missing_documents.add(document_id)
            chunk_ids.extend(mapped_chunk_ids)

        if not chunk_ids:
            raise ValueError(f"query_id={query_id}에 매핑된 정답 chunk가 없습니다.")

        unknown_chunk_ids = [chunk_id for chunk_id in chunk_ids if chunk_id not in all_chunk_ids]
        if unknown_chunk_ids:
            raise ValueError(f"존재하지 않는 chunk_id가 qrels_chunk에 포함됩니다: {unknown_chunk_ids[:5]}")

        output_rows.append(
            {
                "query_id": query_id,
                "ground_truth_document_ids": document_ids,
                "ground_truth_chunk_ids": chunk_ids,
            }
        )

    _write_jsonl(output_path, output_rows)
    return {
        "chunk_qrels_path": str(output_path),
        "query_count": len(docs_by_query),
        "mapped_query_count": len(output_rows),
        "missing_document_count": len(missing_documents),
        "missing_document_ids": sorted(missing_documents),
    }

