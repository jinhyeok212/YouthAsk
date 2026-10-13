"""평가 질문 전체를 KURE-v1 + 기존 Chroma Index로 검색하는 Batch Retriever."""

from __future__ import annotations

import time

from src.common.io import read_jsonl
from src.indexing.kure_adapter import KUREAdapter


def _distance_to_similarity(distance: float, metric: str) -> float | None:
    # 프로젝트에서는 원본 distance를 반드시 보존한다.
    # cosine/ip만 사람이 보기 쉬운 파생 similarity를 함께 기록한다.
    if metric in {"cosine", "ip"}:
        return 1.0 - float(distance)
    return None


def run_batch_retrieval(config: dict, index_info: dict, embedder=None) -> list[dict]:
    """전체 평가 질문을 순서대로 검색하고 공통 Contract 형식으로 반환한다."""
    import chromadb

    questions = read_jsonl(config["evaluation"]["questions_path"])
    if not questions:
        raise ValueError("평가 질문이 비어 있습니다.")

    seen: set[str] = set()
    for q in questions:
        qid = str(q.get("query_id", "")).strip()
        query = str(q.get("query", "")).strip()
        if not qid or not query:
            raise ValueError(f"빈 평가 질문: query_id={qid}")
        if qid in seen:
            raise ValueError(f"중복 query_id: {qid}")
        seen.add(qid)

    client = chromadb.PersistentClient(path=index_info["db_path"])
    collection = client.get_collection(name=index_info["collection_name"])
    embedder = embedder or KUREAdapter(config)
    k = int(config["retrieval"]["evaluation_max_k"])
    metric = config["index"]["distance_metric"]

    output: list[dict] = []
    for q in questions:
        qid = str(q["query_id"])
        query = str(q["query"])

        try:
            # latency에는 Query Embedding + Vector 검색 시간을 함께 포함한다.
            t0 = time.perf_counter()
            qvec = embedder.encode_queries([query])[0].tolist()
            raw = collection.query(
                query_embeddings=[qvec],
                n_results=min(k, collection.count()),
                include=["metadatas", "documents", "distances"],
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0

            ids = (raw.get("ids") or [[]])[0]
            metas = (raw.get("metadatas") or [[]])[0]
            distances = (raw.get("distances") or [[]])[0]

            results = []
            for rank, (chunk_id, meta, distance) in enumerate(
                zip(ids, metas, distances), start=1
            ):
                meta = meta or {}
                d = float(distance)
                document_id = str(meta.get("document_id", "")).strip()
                if not document_id:
                    raise ValueError(
                        f"검색 결과 Metadata에 document_id가 없습니다: chunk_id={chunk_id}"
                    )

                results.append(
                    {
                        "rank": rank,
                        "chunk_id": str(chunk_id),
                        "document_id": document_id,
                        "distance": d,
                        "similarity": _distance_to_similarity(d, metric),
                    }
                )

            output.append(
                {
                    "query_id": qid,
                    "query": query,
                    "retrieval_latency_ms": latency_ms,
                    "results": results,
                }
            )

        except Exception as e:
            # 질문 단위 실패는 trace에 남긴다.
            # Evaluation 단계에서 retrieval_failure_count가 0이 아니면 확인 가능하다.
            output.append(
                {
                    "query_id": qid,
                    "query": query,
                    "retrieval_latency_ms": 0.0,
                    "results": [],
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    if len(output) != len(questions):
        raise RuntimeError("질문 수와 검색 결과 수가 일치하지 않습니다.")
    return output
