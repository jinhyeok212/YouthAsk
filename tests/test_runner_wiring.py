from src.experiments import runner


def test_runner_calls_modules_in_order(monkeypatch, tmp_path):
    calls = []
    config = {
        "experiment_id": "exp_test",
        "output": {"root": str(tmp_path / "experiments")},
    }

    monkeypatch.setattr(runner, "_configure_logging", lambda config: None)
    monkeypatch.setattr(
        runner,
        "validate_documents",
        lambda config: calls.append("data") or {
            "document_path": "docs.jsonl",
            "manifest_path": "dataset_manifest.json",
            "document_count": 1,
            "sha256": "abc",
        },
    )
    monkeypatch.setattr(runner, "validate_dataset_info", lambda payload: None)
    monkeypatch.setattr(
        runner,
        "build_chunks",
        lambda config, dataset_info: calls.append("chunk") or {
            "chunk_path": "chunks.jsonl",
            "manifest_path": "chunk_manifest.json",
            "chunk_count": 1,
            "chunk_qrels_path": "qrels_chunk.jsonl",
        },
    )
    monkeypatch.setattr(runner, "validate_chunk_info", lambda payload: None)
    monkeypatch.setattr(
        runner,
        "validate_evaluation_inputs",
        lambda config, dataset_info, chunk_info: calls.append("eval_input") or {"status": "VALID"},
    )
    monkeypatch.setattr(
        runner,
        "resolve_index",
        lambda config, chunk_info: calls.append("index") or {
            "index_version": "i1",
            "db_path": "db",
            "collection_name": "c1",
            "reused": False,
            "manifest_path": "index_manifest.json",
            "index_count": 1,
        },
    )
    monkeypatch.setattr(runner, "validate_index_info", lambda payload: None)
    monkeypatch.setattr(
        runner,
        "run_batch_retrieval",
        lambda config, index_info: calls.append("retrieval") or [
            {
                "query_id": "q1",
                "query": "question",
                "retrieval_latency_ms": 1.0,
                "results": [],
            }
        ],
    )
    monkeypatch.setattr(runner, "validate_retrieval_results", lambda payload: None)
    monkeypatch.setattr(
        runner,
        "evaluate_experiment",
        lambda config, retrieval_results: calls.append("evaluation") or {
            "metrics_summary": {},
            "metrics_by_query": [],
            "failure_cases": [],
        },
    )
    monkeypatch.setattr(
        runner,
        "write_experiment_artifacts",
        lambda config, context: calls.append("artifact") or {"output_dir": "out"},
    )

    result = runner.run_pipeline(config)

    assert calls == ["data", "chunk", "eval_input", "index", "retrieval", "evaluation", "artifact"]
    assert result["status"] == "SUCCESS"
