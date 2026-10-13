import json

from src.evaluation.evaluate_experiment import (
    _first_relevant_rank,
    _hit,
    _mrr,
    evaluate_experiment,
)


def test_rank_and_metrics():
    retrieved = ["a", "b", "correct", "d"]
    relevant = {"correct"}
    rank = _first_relevant_rank(retrieved, relevant)
    assert rank == 3
    assert _hit(rank, 1) == 0
    assert _hit(rank, 3) == 1
    assert _hit(rank, 5) == 1
    assert _mrr(rank) == 1 / 3


def test_dynamic_hit_at_10(tmp_path):
    dq = tmp_path / "dq.jsonl"
    cq = tmp_path / "cq.jsonl"
    dq.write_text(
        json.dumps({"query_id": "q1", "document_id": "d10", "relevance": 1}) + "\n",
        encoding="utf-8",
    )
    cq.write_text(
        json.dumps({"query_id": "q1", "chunk_id": "c10", "relevance": 1}) + "\n",
        encoding="utf-8",
    )
    config = {
        "evaluation": {
            "document_qrels_path": str(dq),
            "chunk_qrels_path": str(cq),
            "ks": [1, 3, 5, 10],
        }
    }
    results = [
        {
            "query_id": "q1",
            "query": "x",
            "retrieval_latency_ms": 1.0,
            "results": [
                {"document_id": f"d{i}", "chunk_id": f"c{i}"} for i in range(1, 11)
            ],
        }
    ]
    out = evaluate_experiment(config, results)
    assert out["metrics_summary"]["document_hit_at_5"] == 0.0
    assert out["metrics_summary"]["document_hit_at_10"] == 1.0
    assert out["metrics_summary"]["chunk_hit_at_10"] == 1.0
