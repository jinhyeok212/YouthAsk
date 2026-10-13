"""Classify observable retrieval outcomes; do not guess semantic causes."""


def analyze_failures(metrics_by_query: list[dict]) -> list[dict]:
    cases = []
    for row in metrics_by_query:
        if row.get("error"):
            kind = "runtime_error"
        elif not row["document"]["hit_at_5"]:
            kind = "document_not_in_top_5"
        elif not row["chunk"]["hit_at_5"]:
            kind = "chunk_not_in_top_5"
        else:
            continue
        cases.append({
            "query_id": row["query_id"], "query": row["query"],
            "failure_type": kind, "error": row.get("error"),
            "document_first_relevant_rank": row["document"]["first_relevant_rank"],
            "chunk_first_relevant_rank": row["chunk"]["first_relevant_rank"],
            "gold_document_ids": row["document"]["gold_document_ids"],
            "gold_chunk_ids": row["chunk"]["gold_chunk_ids"],
        })
    return cases
