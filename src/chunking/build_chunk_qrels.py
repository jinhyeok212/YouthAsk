from __future__ import annotations

from pathlib import Path

from src.common.io import read_jsonl


def validate_chunk_qrels(chunk_qrels_path: str, chunk_path: str) -> None:
    """검수된 row 기반 Chunk qrels가 실제 Chunk와 연결되는지 검증한다.

    같은 query_id가 여러 행에 등장하는 것은 정상이다.
    하나의 질문이 여러 Gold Chunk를 가질 수 있기 때문이다.

    중복으로 보는 것은 동일한 (query_id, chunk_id) 조합이 반복되는 경우다.
    """
    qrels_path = Path(chunk_qrels_path)
    if not qrels_path.exists():
        raise FileNotFoundError(
            f"검수된 qrels_chunk.jsonl이 필요합니다: {qrels_path}"
        )

    chunks = read_jsonl(chunk_path)
    chunk_map = {
        str(row["chunk_id"]): row
        for row in chunks
    }

    seen_pairs: set[tuple[str, str]] = set()

    for qrel in read_jsonl(qrels_path):
        query_id = str(qrel.get("query_id", "")).strip()
        chunk_id = str(qrel.get("chunk_id", "")).strip()
        document_id = str(qrel.get("document_id", "")).strip()
        relevance = qrel.get("relevance", 1)

        if not query_id:
            raise ValueError("Chunk qrels에 빈 query_id가 있습니다.")
        if not chunk_id:
            raise ValueError(
                f"Chunk qrels에 빈 chunk_id가 있습니다: query_id={query_id}"
            )

        try:
            if float(relevance) <= 0:
                continue
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"잘못된 relevance: query_id={query_id}, relevance={relevance}"
            ) from e

        pair = (query_id, chunk_id)
        if pair in seen_pairs:
            raise ValueError(
                "중복 Chunk qrels: "
                f"query_id={query_id}, chunk_id={chunk_id}"
            )
        seen_pairs.add(pair)

        if chunk_id not in chunk_map:
            raise ValueError(
                "존재하지 않는 정답 Chunk: "
                f"query_id={query_id}, chunk_id={chunk_id}"
            )

        if document_id:
            actual_document_id = str(
                chunk_map[chunk_id].get("document_id", "")
            ).strip()
            if actual_document_id != document_id:
                raise ValueError(
                    "Chunk-document 불일치: "
                    f"query_id={query_id}, chunk_id={chunk_id}, "
                    f"qrels_document={document_id}, "
                    f"actual_document={actual_document_id}"
                )
