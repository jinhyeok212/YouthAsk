from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.chunking.manifest import (
    StagedOutputs,
    qrels_sidecar_paths,
    read_json,
    sha256_file,
    utc_now_iso,
    write_json,
)


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


def validate_document_qrels_rows(qrels: list[dict[str, Any]]) -> None:
    """청크를 만들기 전에 문서 qrels 형식 오류를 먼저 잡는다."""
    if not qrels:
        raise ValueError("문서 qrels가 0건입니다.")
    for row_number, qrel in enumerate(qrels, start=1):
        if not str(qrel.get("query_id") or "").strip():
            raise ValueError(f"{row_number}번째 qrels 행에 query_id가 없습니다.")


def map_chunk_qrels(
    qrels: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """근거가 있는 qrels만 chunk 정답 후보로 매핑하고, 나머지는 검수 대상으로 분리한다.

    파일을 읽거나 쓰지 않는다. 반환값: (mapped_rows, review_rows)
    """
    validate_document_qrels_rows(qrels)

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

    for qrel in qrels:
        query_id = str(qrel.get("query_id") or "").strip()
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

    return mapped_rows, review_rows


def qrels_status(mapped_rows: list[dict[str, Any]], review_rows: list[dict[str, Any]]) -> str:
    return "ready" if mapped_rows and not review_rows else "review_required"


def build_chunk_qrels(
    document_qrels_path: str | Path,
    chunks_path: str | Path,
    output_path: str | Path,
    review_required_path: str | Path | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """자동 매핑 결과(후보)를 파일로 저장하는 단독 실행용 함수.

    검수된 qrels를 덮어쓰지 않도록 output_path가 이미 있으면 중단한다.
    Runner 경로는 resolve_chunk_qrels()를 사용한다.
    """
    document_qrels_path = Path(document_qrels_path)
    chunks_path = Path(chunks_path)
    output_path = Path(output_path)
    review_required_path = (
        Path(review_required_path)
        if review_required_path is not None
        else output_path.with_name(f"{output_path.stem}_review_required.jsonl")
    )

    if not document_qrels_path.exists():
        raise ValueError(f"문서 qrels 파일이 없습니다: {document_qrels_path}")
    if not chunks_path.exists():
        raise ValueError(f"chunks.jsonl 파일이 없습니다: {chunks_path}")
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"qrels 파일이 이미 있습니다. 검수 결과 보호를 위해 덮어쓰지 않습니다: {output_path}"
        )

    qrels = _read_jsonl(document_qrels_path)
    mapped_rows, review_rows = map_chunk_qrels(qrels, _read_jsonl(chunks_path))

    _write_jsonl(output_path, mapped_rows)
    _write_jsonl(review_required_path, review_rows)

    return {
        "chunk_qrels_path": str(output_path),
        "review_required_path": str(review_required_path),
        "status": qrels_status(mapped_rows, review_rows),
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



def _qrels_meta(
    *,
    status: str,
    chunking_version: str,
    chunk_sha256: str,
    qrels_sha256: str,
    source_document_qrels_sha256: str | None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = {
        "status": status,
        "chunking_version": chunking_version,
        "chunk_sha256": chunk_sha256,
        "qrels_sha256": qrels_sha256,
        "source_document_qrels_sha256": source_document_qrels_sha256,
        "updated_at_utc": utc_now_iso(),
    }
    if previous:
        meta["previous_status"] = previous.get("status")
        meta["previous_qrels_sha256"] = previous.get("qrels_sha256")
    return meta


def resolve_chunk_qrels(
    *,
    chunk_qrels_path: Path,
    chunk_path: Path,
    chunks: list[dict[str, Any]],
    chunk_sha256: str,
    chunking_version: str,
    document_qrels_path: Path | None,
    allow_auto: bool,
    bootstrap_status: str,
    staged: StagedOutputs,
) -> dict[str, Any]:
    """확정 chunk qrels를 검증·재사용하거나, 없으면 자동 매핑 후보를 만든다.

    - 확정본(chunk_qrels_path)이 있으면 절대 쓰지 않는다. 검증만 한다.
      메타의 chunk_sha256/chunking_version이 현재 청크와 다르면 보존한 채 중단한다.
    - 확정본이 없고 allow_auto이면 근거 기반으로 매핑한다.
      전부 매핑되면 확정본을 만들고, 아니면 후보/검수 파일만 만들고 review_required를 반환한다.
    - 쓰기는 staged에 등록만 한다. 반영은 호출자가 검증을 마친 뒤 commit한다.
    """
    sidecars = qrels_sidecar_paths(chunk_qrels_path)
    meta_path = sidecars["meta"]
    result: dict[str, Any] = {
        "chunk_qrels_path": str(chunk_qrels_path),
        "candidates_path": str(sidecars["candidates"]),
        "review_required_path": str(sidecars["review_required"]),
        "meta_path": str(meta_path),
    }

    if chunk_qrels_path.exists():
        qrels_sha = sha256_file(chunk_qrels_path)
        meta = read_json(meta_path) if meta_path.exists() else None
        if meta is not None:
            if (
                meta.get("chunking_version") != chunking_version
                or meta.get("chunk_sha256") != chunk_sha256
            ):
                raise ValueError(
                    "검수된 chunk qrels가 다른 청크 기준으로 만들어졌습니다. "
                    "qrels 파일은 그대로 보존하고 중단합니다. "
                    "새 chunking.version/chunk_qrels_path를 사용하거나 qrels를 다시 검수하세요: "
                    f"qrels={chunk_qrels_path}, "
                    f"meta_version={meta.get('chunking_version')}, current_version={chunking_version}, "
                    f"meta_chunk_sha256={meta.get('chunk_sha256')}, current_chunk_sha256={chunk_sha256}"
                )

        rows = _read_jsonl(chunk_qrels_path)
        if not rows:
            raise ValueError(
                "확정 chunk qrels 파일이 비어 있습니다. 검수를 마친 정답 행을 넣거나, "
                f"자동 매핑 후보를 다시 만들려면 파일을 다른 곳으로 옮기세요: {chunk_qrels_path}"
            )
        validate_chunk_qrels(chunk_qrels_path, chunk_path)

        if meta is None:
            review_status = bootstrap_status
            write_json(
                staged.path_for(meta_path),
                _qrels_meta(
                    status=review_status,
                    chunking_version=chunking_version,
                    chunk_sha256=chunk_sha256,
                    qrels_sha256=qrels_sha,
                    source_document_qrels_sha256=None,
                ),
            )
        elif meta.get("qrels_sha256") != qrels_sha:
            # 자동 생성 이후 사람이 확정본을 수정한 경우
            review_status = "reviewed"
            write_json(
                staged.path_for(meta_path),
                _qrels_meta(
                    status=review_status,
                    chunking_version=chunking_version,
                    chunk_sha256=chunk_sha256,
                    qrels_sha256=qrels_sha,
                    source_document_qrels_sha256=meta.get("source_document_qrels_sha256"),
                    previous=meta,
                ),
            )
        else:
            review_status = str(meta.get("status"))

        return result | {
            "status": "ready",
            "review_status": review_status,
            "qrels_sha256": qrels_sha,
            "mapped_row_count": len(rows),
            "review_required_count": 0,
            "auto_generated": False,
        }

    if not allow_auto:
        raise FileNotFoundError(f"검수된 qrels_chunk.jsonl이 필요합니다: {chunk_qrels_path}")
    if document_qrels_path is None or not document_qrels_path.exists():
        raise ValueError(f"문서 qrels 파일이 없습니다: {document_qrels_path}")

    document_qrels = _read_jsonl(document_qrels_path)
    mapped_rows, review_rows = map_chunk_qrels(document_qrels, chunks)
    status = qrels_status(mapped_rows, review_rows)
    document_qrels_sha = sha256_file(document_qrels_path)

    _write_jsonl(staged.path_for(sidecars["candidates"]), mapped_rows)
    _write_jsonl(staged.path_for(sidecars["review_required"]), review_rows)

    review_status = "review_required"
    if status == "ready":
        confirmed_temp = staged.path_for(chunk_qrels_path)
        _write_jsonl(confirmed_temp, mapped_rows)
        validate_chunk_qrels(confirmed_temp, chunk_path)
        review_status = "auto_ready"
        write_json(
            staged.path_for(meta_path),
            _qrels_meta(
                status=review_status,
                chunking_version=chunking_version,
                chunk_sha256=chunk_sha256,
                qrels_sha256=sha256_file(confirmed_temp),
                source_document_qrels_sha256=document_qrels_sha,
            ),
        )

    return result | {
        "status": status,
        "review_status": review_status,
        "qrels_sha256": None,
        "mapped_row_count": len(mapped_rows),
        "review_required_count": len(review_rows),
        "auto_generated": True,
    }
