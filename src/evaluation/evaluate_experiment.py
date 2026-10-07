"""Runner adapter for deterministic document/chunk retrieval evaluation."""

from pathlib import Path
import math
import json
from jsonschema import Draft202012Validator

from src.evaluation.evaluator import (
    _read_jsonl, _require_non_empty_string, evaluate_document_queries,
    evaluate_chunk_queries, summarize_document_metrics, summarize_chunk_metrics,
    validate_query_alignment,
)
from src.evaluation.failure_analyzer import analyze_failures
from src.experiments.contracts import validate_retrieval_results

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def input_path(value):
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_qrels(path, unit):
    """Accept repository row qrels and the initial handoff's ID-list format."""
    grouped = {}
    for row in _read_jsonl(input_path(path)):
        query_id = _require_non_empty_string(row, "query_id", str(path))
        plural = f"ground_truth_{unit}_ids"
        ids = row.get(plural) if plural in row else [row.get(f"{unit}_id")]
        if not isinstance(ids, list) or not ids or any(
            not isinstance(item, str) or not item.strip() for item in ids
        ):
            raise ValueError(f"{query_id}: invalid {unit} qrels")
        relevance = row.get("relevance", 1)
        if isinstance(relevance, bool) or not isinstance(relevance, (int, float)) or not math.isfinite(relevance):
            raise ValueError(f"{query_id}: invalid relevance")
        if relevance > 0:
            grouped.setdefault(query_id, set()).update(ids)
    return grouped


def evaluate_experiment(config: dict, retrieval_results: list[dict]) -> dict:
    """Evaluate original chunk ranks, without deduplicating document ranks.

    MRR is truncated at evaluation_max_k. Runtime errors contribute zero and
    remain explicitly marked; the writer prevents a successful Runner exit.
    """
    rows = validate_retrieval_results(retrieval_results)
    max_k = config["retrieval"]["evaluation_max_k"]
    if isinstance(max_k, bool) or not isinstance(max_k, int) or max_k < 5:
        raise ValueError("Hit@5 requires evaluation_max_k >= 5")
    evaluation = config["evaluation"]
    questions = _read_jsonl(input_path(evaluation["questions_path"]))
    question_ids = []
    for question in questions:
        query_id = _require_non_empty_string(question, "query_id", "questions")
        _require_non_empty_string(question, "query", query_id)
        if query_id in question_ids:
            raise ValueError(f"duplicate question query_id: {query_id}")
        question_ids.append(query_id)
    validate_query_alignment(rows, dict.fromkeys(question_ids, set()))
    document_qrels = load_qrels(evaluation["document_qrels_path"], "document")
    chunk_qrels = load_qrels(evaluation["chunk_qrels_path"], "chunk")
    validate_query_alignment(rows, document_qrels)
    validate_query_alignment(rows, chunk_qrels)
    by_id = {row["query_id"]: row for row in rows}
    rows = [by_id[query_id] for query_id in question_ids]
    for row in rows:
        if len(row["results"]) > max_k:
            raise ValueError(f"{row['query_id']}: results exceed evaluation_max_k")
        error = row.get("error")
        if error is not None and (not isinstance(error, str) or not error.strip()):
            raise ValueError(f"{row['query_id']}: invalid error field")
        if error and row["results"]:
            raise ValueError(f"{row['query_id']}: error must have empty results")
    documents = evaluate_document_queries(rows, document_qrels)
    chunks = evaluate_chunk_queries(rows, chunk_qrels)
    summary = {}
    for prefix, values in (("document", summarize_document_metrics(documents)),
                           ("chunk", summarize_chunk_metrics(chunks))):
        summary.update({key: value for key, value in values.items() if key.startswith(prefix + "_")})
    latencies = sorted(float(row["retrieval_latency_ms"]) for row in rows)
    # Nearest-rank percentile, valid for even one query.
    summary.update(
        question_count=len(rows), evaluated_question_count=len(rows),
        evaluation_max_k=max_k,
        average_retrieval_latency_ms=sum(latencies) / len(latencies),
        p95_retrieval_latency_ms=latencies[math.ceil(.95 * len(latencies)) - 1],
        runtime_error_count=sum(bool(row.get("error")) for row in rows),
        document_failure_count=sum(item["hit_at_5"] == 0 for item in documents),
        chunk_failure_count=sum(item["hit_at_5"] == 0 for item in chunks),
    )
    summary["status"] = "FAILED" if summary["runtime_error_count"] else "COMPLETED"
    metrics = [dict(query_id=row["query_id"], query=row["query"],
                    document=doc, chunk=chunk, error=row.get("error"),
                    retrieval_latency_ms=row["retrieval_latency_ms"])
               for row, doc, chunk in zip(rows, documents, chunks)]
    failures = analyze_failures(metrics)
    summary["search_failure_question_count"] = sum(
        not item.get("error") and not item["chunk"]["hit_at_5"] for item in metrics
    )
    result = {"metrics_summary": summary, "metrics_by_query": metrics,
              "failure_cases": failures}
    schema = json.loads((PROJECT_ROOT / "schemas/experiment_result.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(result)
    return result
