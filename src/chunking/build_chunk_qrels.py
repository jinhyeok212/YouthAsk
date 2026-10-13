from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


SPAN_START_FIELDS = ("evidence_start_char", "answer_start_char", "start_char")
SPAN_END_FIELDS = ("evidence_end_char", "answer_end_char", "end_char")
TEXT_FIELDS = ("evidence_text", "answer_text", "ground_truth_text")


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


def _first_present(row: dict[str, Any], fields: tuple[str, ...]) -> Any:
    for field in fields:
        if row.get(field) is not None:
            return row[field]
    return None


def _span(row: dict[str, Any]) -> tuple[int, int] | None:
    start = _first_present(row, SPAN_START_FIELDS)
    end = _first_present(row, SPAN_END_FIELDS)
    if start is None or end is None:
        return None
    try:
        start_int = int(start)
        end_int = int(end)
    except (TypeError, ValueError):
        return None
    if start_int < 0 or end_int <= start_int:
        return None
    return start_int, end_int


def _evidence_text(row: dict[str, Any]) -> str:
    for field in TEXT_FIELDS:
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _overlaps(chunk: dict[str, Any], start: int, end: int) -> bool:
    chunk_start = int(chunk.get("start_char", -1))
    chunk_end = int(chunk.get("end_char", -1))
    return chunk_start < end and start < chunk_end


def build_chunk_qrels(
    document_qrels_path: str | Path,
    chunks_path: str | Path,
    output_path: str | Path,
    review_required_path: str | Path | None = None,
) -> dict[str, Any]:
    """근거가 있는 qrels만 chunk qrels로 확정하고, 불확실한 항목은 검수 대상으로 분리한다."""
    document_qrels_path = Path(document_qrels_path)
    chunks_path = Path(chunks_path)
    output_path = Path(output_path)
    review_required_path = (
        Path(review_required_path)
        if review_required_path is not None
        else output_path.with_name("qrels_chunk_review_required.jsonl")
    )

    if not document_qrels_path.exists():
        raise ValueError(f"문서 qrels 파일이 없습니다: {document_qrels_path}")
    if not chunks_path.exists():
        raise ValueError(f"chunks.jsonl 파일이 없습니다: {chunks_path}")

    qrels = _read_jsonl(document_qrels_path)
    chunks = _read_jsonl(chunks_path)

    chunks_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    chunk_by_id: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        document_id = str(chunk.get("document_id") or "").strip()
        if chunk_id and document_id:
            chunks_by_document[document_id].append(chunk)
            chunk_by_id[chunk_id] = chunk

    mapped_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for row_number, qrel in enumerate(qrels, start=1):
        query_id = str(qrel.get("query_id") or "").strip()
        if not query_id:
            raise ValueError(f"{row_number}번째 qrels 행에 query_id가 없습니다.")

        explicit_chunk_id = str(qrel.get("chunk_id") or "").strip()
        explicit_document_id = str(qrel.get("document_id") or "").strip()
        if explicit_chunk_id:
            chunk = chunk_by_id.get(explicit_chunk_id)
            if not chunk:
                review_rows.append(
                    {
                        "query_id": query_id,
                        "document_id": explicit_document_id,
                        "chunk_id": explicit_chunk_id,
                        "reason": "explicit_chunk_id_not_found",
                    }
                )
                continue
            document_id = explicit_document_id or str(chunk.get("document_id") or "").strip()
            pair = (query_id, explicit_chunk_id)
            if pair not in seen:
                mapped_rows.append(
                    {
                        "query_id": query_id,
                        "document_id": document_id,
                        "chunk_id": explicit_chunk_id,
                        "relevance": qrel.get("relevance", 1),
                        "mapping_method": "explicit_chunk_id",
                    }
                )
                seen.add(pair)
            continue

        document_ids = _positive_document_ids(qrel)
        if not document_ids:
            review_rows.append({"query_id": query_id, "reason": "no_positive_document_id"})
            continue

        evidence_span = _span(qrel)
        evidence_text = _evidence_text(qrel)
        mapped_any_for_query = False

        for document_id in document_ids:
            candidate_chunks = chunks_by_document.get(document_id, [])
            if not candidate_chunks:
                review_rows.append(
                    {
                        "query_id": query_id,
                        "document_id": document_id,
                        "reason": "document_has_no_chunks",
                    }
                )
                continue

            matched_chunks: list[dict[str, Any]] = []
            mapping_method = ""
            if evidence_span is not None:
                start, end = evidence_span
                matched_chunks = [chunk for chunk in candidate_chunks if _overlaps(chunk, start, end)]
                mapping_method = "evidence_span"
            elif evidence_text:
                matched_chunks = [
                    chunk for chunk in candidate_chunks if evidence_text in str(chunk.get("text") or "")
                ]
                mapping_method = "evidence_text"

            if not matched_chunks:
                review_rows.append(
                    {
                        "query_id": query_id,
                        "document_id": document_id,
                        "reason": (
                            "missing_evidence_for_chunk_mapping"
                            if evidence_span is None and not evidence_text
                            else "evidence_not_found_in_chunks"
                        ),
                    }
                )
                continue

            for chunk in matched_chunks:
                chunk_id = str(chunk["chunk_id"])
                pair = (query_id, chunk_id)
                if pair in seen:
                    continue
                mapped_rows.append(
                    {
                        "query_id": query_id,
                        "document_id": document_id,
                        "chunk_id": chunk_id,
                        "relevance": qrel.get("relevance", 1),
                        "mapping_method": mapping_method,
                    }
                )
                seen.add(pair)
                mapped_any_for_query = True

        if not mapped_any_for_query and not any(row.get("query_id") == query_id for row in review_rows):
            review_rows.append({"query_id": query_id, "reason": "unmapped"})

    _write_jsonl(output_path, mapped_rows)
    _write_jsonl(review_required_path, review_rows)

    status = "ready" if mapped_rows and not review_rows else "review_required"
    return {
        "chunk_qrels_path": str(output_path),
        "review_required_path": str(review_required_path),
        "status": status,
        "query_count": len({str(row.get("query_id") or "").strip() for row in qrels if row.get("query_id")}),
        "mapped_row_count": len(mapped_rows),
        "review_required_count": len(review_rows),
    }


def validate_chunk_qrels(chunk_qrels_path: str | Path, chunk_path: str | Path) -> None:
    chunks = _read_jsonl(Path(chunk_path))
    chunk_map = {str(row.get("chunk_id") or ""): row for row in chunks}
    seen_pairs: set[tuple[str, str]] = set()

    for row in _read_jsonl(Path(chunk_qrels_path)):
        query_id = str(row.get("query_id") or "").strip()
        chunk_id = str(row.get("chunk_id") or "").strip()
        document_id = str(row.get("document_id") or "").strip()
        relevance = row.get("relevance", 1)

        if not query_id:
            raise ValueError("Chunk qrels에 빈 query_id가 있습니다.")
        if not chunk_id:
            raise ValueError(f"Chunk qrels에 빈 chunk_id가 있습니다: query_id={query_id}")
        try:
            if float(relevance) <= 0:
                continue
        except (TypeError, ValueError) as e:
            raise ValueError(f"잘못된 relevance: query_id={query_id}, relevance={relevance}") from e

        pair = (query_id, chunk_id)
        if pair in seen_pairs:
            raise ValueError(f"중복 Chunk qrels: query_id={query_id}, chunk_id={chunk_id}")
        seen_pairs.add(pair)

        if chunk_id not in chunk_map:
            raise ValueError(f"존재하지 않는 정답 Chunk: query_id={query_id}, chunk_id={chunk_id}")
        actual_document_id = str(chunk_map[chunk_id].get("document_id") or "").strip()
        if document_id and actual_document_id != document_id:
            raise ValueError(
                "Chunk-document 불일치: "
                f"query_id={query_id}, chunk_id={chunk_id}, "
                f"qrels_document={document_id}, actual_document={actual_document_id}"
            )

