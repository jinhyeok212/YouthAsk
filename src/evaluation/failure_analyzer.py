from __future__ import annotations


def classify_failure(
    query_metric: dict,
    *,
    failure_k: int,
    low_rank_threshold: int = 3,
) -> str | None:
    """Classify only observable retrieval failures, not semantic causes."""
    if query_metric.get("runtime_error"):
        return "RUNTIME_ERROR"

    doc_key = f"document_hit_at_{failure_k}"
    chunk_key = f"chunk_hit_at_{failure_k}"

    if query_metric.get(doc_key) == 0:
        return f"DOCUMENT_MISS_TOP{failure_k}"
    if query_metric.get(chunk_key) == 0:
        return f"DOCUMENT_HIT_BUT_CHUNK_MISS_TOP{failure_k}"

    chunk_rank = query_metric.get("chunk_first_relevant_rank")
    if chunk_rank and chunk_rank > low_rank_threshold:
        return "LOW_RANK_RELEVANT_CHUNK"
    return None
