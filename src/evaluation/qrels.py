from __future__ import annotations

from src.common.io import read_jsonl


def load_row_qrels(path: str, id_field: str) -> dict[str, set[str]]:
    """Row 기반 qrels를 ``query_id -> 정답 ID 집합``으로 변환한다.

    실제 프로젝트 qrels는 한 질문에 정답이 여러 개면 같은 query_id를
    여러 행에 기록한다. 따라서 query_id 중복 자체는 정상이고,
    동일한 (query_id, 정답 ID) 조합만 중복으로 간주한다.

    예:
        {"query_id": "q1", "chunk_id": "c1", "relevance": 1}
        {"query_id": "q1", "chunk_id": "c2", "relevance": 1}

    반환:
        {"q1": {"c1", "c2"}}
    """
    mapping: dict[str, set[str]] = {}
    seen_pairs: set[tuple[str, str]] = set()

    for row in read_jsonl(path):
        query_id = str(row.get("query_id", "")).strip()
        item_id = str(row.get(id_field, "")).strip()
        relevance = row.get("relevance", 1)

        if not query_id:
            raise ValueError(f"빈 query_id: {path}")
        if not item_id:
            raise ValueError(
                f"빈 {id_field}: path={path}, query_id={query_id}"
            )

        try:
            is_relevant = float(relevance) > 0
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"잘못된 relevance: path={path}, query_id={query_id}, relevance={relevance}"
            ) from e

        if not is_relevant:
            continue

        pair = (query_id, item_id)
        if pair in seen_pairs:
            raise ValueError(
                "중복 qrels 조합: "
                f"query_id={query_id}, {id_field}={item_id}"
            )
        seen_pairs.add(pair)

        mapping.setdefault(query_id, set()).add(item_id)

    if not mapping:
        raise ValueError(f"유효한 qrels가 없습니다: {path}")

    return mapping


def load_document_qrels(path: str) -> dict[str, set[str]]:
    """Document qrels를 query_id -> document_id 집합으로 읽는다."""
    return load_row_qrels(path, "document_id")


def load_chunk_qrels(path: str) -> dict[str, set[str]]:
    """Chunk qrels를 query_id -> chunk_id 집합으로 읽는다."""
    return load_row_qrels(path, "chunk_id")
