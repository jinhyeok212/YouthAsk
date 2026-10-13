from __future__ import annotations

import math

from src.evaluation.failure_analyzer import classify_failure
from src.evaluation.qrels import load_chunk_qrels, load_document_qrels


def _first_relevant_rank(retrieved: list[str], relevant: set[str]) -> int | None:
    for rank, item_id in enumerate(retrieved, start=1):
        if item_id in relevant:
            return rank
    return None


def _hit(first_rank: int | None, k: int) -> int:
    return int(first_rank is not None and first_rank <= k)


def _mrr(first_rank: int | None) -> float:
    return 0.0 if first_rank is None else 1.0 / first_rank


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    idx = max(0, min(len(xs) - 1, math.ceil(p * len(xs)) - 1))
    return float(xs[idx])


def evaluate_experiment(config: dict, retrieval_results: list[dict]) -> dict:
    doc_qrels = load_document_qrels(config["evaluation"]["document_qrels_path"])
    chunk_qrels = load_chunk_qrels(config["evaluation"]["chunk_qrels_path"])
    ks = sorted(int(k) for k in config.get("evaluation", {}).get("ks", [1, 3, 5]))
    failure_k = max(ks)

    query_ids = [r["query_id"] for r in retrieval_results]
    if len(query_ids) != len(set(query_ids)):
        raise ValueError("검색 결과에 중복 query_id가 있습니다.")

    by_query: list[dict] = []
    for row in retrieval_results:
        qid = row["query_id"]
        if qid not in doc_qrels:
            raise ValueError(f"문서 qrels 누락: query_id={qid}")
        if qid not in chunk_qrels:
            raise ValueError(f"Chunk qrels 누락: query_id={qid}")

        runtime_error = row.get("error")
        doc_ids = [str(r.get("document_id", "")) for r in row["results"]]
        chunk_ids = [str(r.get("chunk_id", "")) for r in row["results"]]
        d_rank = _first_relevant_rank(doc_ids, doc_qrels[qid])
        c_rank = _first_relevant_rank(chunk_ids, chunk_qrels[qid])

        item = {
            "query_id": qid,
            "document_mrr": _mrr(d_rank),
            "document_first_relevant_rank": d_rank,
            "chunk_mrr": _mrr(c_rank),
            "chunk_first_relevant_rank": c_rank,
            "retrieval_latency_ms": float(row["retrieval_latency_ms"]),
            "runtime_error": runtime_error,
        }
        for k in ks:
            item[f"document_hit_at_{k}"] = _hit(d_rank, k)
            item[f"chunk_hit_at_{k}"] = _hit(c_rank, k)

        item["failure_type"] = classify_failure(item, failure_k=failure_k)
        by_query.append(item)

    if set(query_ids) != set(doc_qrels):
        missing = sorted(set(doc_qrels) - set(query_ids))
        extra = sorted(set(query_ids) - set(doc_qrels))
        raise ValueError(
            f"평가 질문/검색 결과 불일치: missing={missing[:10]}, extra={extra[:10]}"
        )

    n = len(by_query)
    if n == 0:
        raise ValueError("평가 결과가 0건입니다.")

    def avg(field: str) -> float:
        return sum(float(r[field]) for r in by_query) / n

    latencies = [r["retrieval_latency_ms"] for r in by_query if not r["runtime_error"]]
    failures = [r for r in by_query if r["failure_type"]]
    runtime_failures = [r for r in by_query if r["runtime_error"]]

    summary: dict[str, float | int] = {}
    for k in ks:
        summary[f"document_hit_at_{k}"] = avg(f"document_hit_at_{k}")
    summary["document_mrr"] = avg("document_mrr")
    for k in ks:
        summary[f"chunk_hit_at_{k}"] = avg(f"chunk_hit_at_{k}")
    summary["chunk_mrr"] = avg("chunk_mrr")
    summary["average_retrieval_latency_ms"] = (
        sum(latencies) / len(latencies) if latencies else 0.0
    )
    summary["p95_retrieval_latency_ms"] = _percentile(latencies, 0.95)
    summary["retrieval_failure_count"] = len(runtime_failures)
    summary["evaluation_query_count"] = n
    summary["evaluation_ks"] = ks

    for key, value in summary.items():
        if key.startswith(("document_hit", "chunk_hit")) or key.endswith("_mrr"):
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"Metric 범위 오류: {key}={value}")

    return {
        "metrics_summary": summary,
        "metrics_by_query": by_query,
        "failure_cases": failures,
    }
