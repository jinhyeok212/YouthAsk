"""Document·Chunk의 Hit@k, RR, MRR, Context Precision·Recall 테스트."""

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.evaluation.evaluator import evaluate_chunk_queries, summarize_chunk_metrics
from src.evaluation.evaluate_experiment import evaluate_experiment

from src.evaluation.retrieval_metrics import (
    calculate_context_metrics,
    calculate_hit_at_k,
    calculate_mean_hit_at_k,
    calculate_mrr,
    calculate_reciprocal_rank,
    find_first_relevant_rank,
)


class RetrievalMetricsTest(unittest.TestCase):
    """ID 종류와 관계없이 공통 검색 평가지표 계산이 정확한지 확인한다."""

    # 정답 ID가 1위에 있을 때의 평가지표를 확인한다.
    def test_gold_id_at_rank_1(self) -> None:
        first_rank = find_first_relevant_rank(
            ["정책_A", "정책_B", "정책_C"],
            {"정책_A"},
        )

        self.assertEqual(first_rank, 1)
        self.assertEqual(calculate_hit_at_k(first_rank, 1), 1)
        self.assertEqual(calculate_hit_at_k(first_rank, 3), 1)
        self.assertEqual(calculate_hit_at_k(first_rank, 5), 1)
        self.assertEqual(calculate_reciprocal_rank(first_rank), 1.0)

    # 정답 ID가 4위에 있을 때의 평가지표를 확인한다.
    def test_gold_id_at_rank_4(self) -> None:
        first_rank = find_first_relevant_rank(
            ["정책_A", "정책_B", "정책_C", "정책_D", "정책_E"],
            {"정책_D"},
        )

        self.assertEqual(first_rank, 4)
        self.assertEqual(calculate_hit_at_k(first_rank, 1), 0)
        self.assertEqual(calculate_hit_at_k(first_rank, 3), 0)
        self.assertEqual(calculate_hit_at_k(first_rank, 5), 1)
        self.assertEqual(calculate_reciprocal_rank(first_rank), 0.25)

    # 정답 ID가 Top-5에 없을 때 모든 Hit@k와 RR이 0인지 확인한다.
    def test_gold_id_not_retrieved(self) -> None:
        first_rank = find_first_relevant_rank(
            ["정책_A", "정책_B", "정책_C", "정책_D", "정책_E"],
            {"정책_F"},
        )

        self.assertIsNone(first_rank)
        self.assertEqual(calculate_hit_at_k(first_rank, 1), 0)
        self.assertEqual(calculate_hit_at_k(first_rank, 3), 0)
        self.assertEqual(calculate_hit_at_k(first_rank, 5), 0)
        self.assertEqual(calculate_reciprocal_rank(first_rank), 0.0)

    # Gold ID가 여러 개면 가장 먼저 검색된 Gold의 순위를 사용하는지 확인한다.
    def test_multiple_gold_ids_use_first_match(self) -> None:
        first_rank = find_first_relevant_rank(
            ["정책_A", "정책_B", "정책_C", "정책_D"],
            {"정책_B", "정책_D"},
        )

        self.assertEqual(first_rank, 2)
        self.assertEqual(calculate_reciprocal_rank(first_rank), 0.5)

    # 질문별 Hit@k의 평균이 올바르게 계산되는지 확인한다.
    def test_calculate_mean_hit_at_k(self) -> None:
        self.assertAlmostEqual(
            calculate_mean_hit_at_k([1, 1, 0, 1]),
            0.75,
        )

    # 질문별 RR의 평균인 MRR이 올바르게 계산되는지 확인한다.
    def test_calculate_mrr(self) -> None:
        self.assertAlmostEqual(
            calculate_mrr([1.0, 0.5, 0.25, 0.0]),
            0.4375,
        )

    # 계산할 값이 없을 때 잘못된 평균을 만들지 않고 중단하는지 확인한다.
    def test_empty_metric_values_raise_error(self) -> None:
        with self.assertRaises(ValueError):
            calculate_mean_hit_at_k([])

        with self.assertRaises(ValueError):
            calculate_mrr([])


class ContextMetricsTest(unittest.TestCase):
    def test_rank_coverage_duplicates_and_empty_results(self):
        metrics = calculate_context_metrics(["x", "a", "a", "b"], {"a", "b", "c"},
            {"f1", "f2", "f3"}, {"a": {"f1"}, "b": {"f2"}, "c": {"f3"}})
        self.assertAlmostEqual(metrics["context_precision"], 0.5)
        self.assertAlmostEqual(metrics["context_recall"], 2 / 3)
        self.assertEqual(calculate_context_metrics([], {"a"}, {"f1"}, {"a": {"f1"}}),
                         {"context_precision": 0.0, "context_recall": 0.0})
        self.assertEqual(calculate_context_metrics(["x"], {"a"})["context_precision"], 0)
        self.assertIsNone(calculate_context_metrics(["a"], {"a"})["context_recall"])
        self.assertEqual(calculate_context_metrics(["a"], set())["context_precision"], 0)

    def test_earlier_evidence_improves_precision_only(self):
        early = calculate_context_metrics(["a", "x"], {"a", "b"}, {"f1", "f2"}, {"a": {"f1"}})
        late = calculate_context_metrics(["x", "a"], {"a", "b"}, {"f1", "f2"}, {"a": {"f1"}})
        self.assertGreater(early["context_precision"], late["context_precision"])
        self.assertEqual(early["context_recall"], late["context_recall"])
        self.assertEqual(early["context_recall"], 0.5)

    def test_baseline_and_runner_agree(self):
        rows = [{"query_id": "q", "retrieval_latency_ms": 1,
                 "results": [{"chunk_id": "x", "document_id": "x"},
                             {"chunk_id": "a", "document_id": "a"}]}]
        gold = {"q": {"a", "b"}}
        baseline = summarize_chunk_metrics(evaluate_chunk_queries(rows, gold))
        with patch("src.evaluation.evaluate_experiment.load_document_qrels", return_value=gold), \
             patch("src.evaluation.evaluate_experiment.load_chunk_qrels", return_value=gold):
            result = evaluate_experiment({"evaluation": {
                "document_qrels_path": "unused", "chunk_qrels_path": "unused",
                "ks": [1, 2]}}, rows)
        summary = result["metrics_summary"]
        self.assertEqual(baseline["chunk_mrr"], summary["chunk_mrr"])
        self.assertNotIn("chunk_context_recall", summary)



class ContextReviewIntegrationTest(unittest.TestCase):
    """PM 운영 기준: row 입력·검수·사실 커버리지·저장 연결을 검증한다."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.questions = [{"query_id": q, "query": q} for q in ("q1", "q2", "q3")]
        self.documents = [{"document_id": "d"}]
        self.chunks = [{"chunk_id": c, "document_id": "d"} for c in ("c1", "c2", "c3", "x")]
        self.qrels = [{"query_id": q["query_id"], "document_id": "d", "chunk_id": c,
            "relevance": 1, "review_status": "approved", "chunking_version": "c_v1"}
            for q in self.questions for c in ("c1", "c2", "c3")]
        self.facts = [{"query_id": q["query_id"], "fact_id": f, "fact_text": f,
            "document_id": "d", "source_location": "eligibility", "review_status": "approved"}
            for q in self.questions for f in ("age", "period")]
        self.mapping = [{"query_id": q["query_id"], "fact_id": f, "chunk_id": c,
            "chunking_version": "c_v1", "review_status": "approved"}
            for q in self.questions for f, c in (("age", "c1"), ("age", "c2"), ("period", "c3"))]
        def path(name):
            return str(self.root / (name + ".jsonl"))
        self.config = {"experiment_id": "context_test", "schema_version": "1.1", "embedding": {},
            "output": {"root": str(self.root / "experiments")},
            "dataset": {"document_path": path("documents")},
            "chunking": {"version": "c_v1", "chunk_path": path("chunks")},
            "retrieval": {"evaluation_max_k": 5}, "evaluation": {"version": "v1",
                "questions_path": path("questions"), "document_qrels_path": path("doc_qrels"),
                "chunk_qrels_path": path("qrels"), "ks": [1, 3, 5],
                "context_metrics": {"enabled": True, "version": "context_v1", "k": 5,
                    "required_facts_path": path("facts"), "chunk_fact_map_path": path("mapping")}}}
        self.rows = [{"query_id": "q1", "retrieval_latency_ms": 1, "results": [
            {"chunk_id": c, "document_id": "d"} for c in ("c1", "c2", "x")]},
            {"query_id": "q2", "retrieval_latency_ms": 1, "results": []},
            {"query_id": "q3", "retrieval_latency_ms": 0, "results": [], "error": "DB failure"}]
        self.write_inputs()

    def write_inputs(self):
        from src.common.io import write_jsonl

        for name in ("questions", "documents", "chunks", "qrels", "facts", "mapping"):
            write_jsonl(self.root / (name + ".jsonl"), getattr(self, name))
        write_jsonl(self.root / "doc_qrels.jsonl", [
            {"query_id": q["query_id"], "document_id": "d"} for q in self.questions])

    def evaluate(self):
        self.write_inputs()
        return evaluate_experiment(self.config, self.rows)

    def test_fact_coverage_and_execution_errors(self):
        result = self.evaluate()
        first = result["metrics_by_query"][0]
        self.assertEqual(first["context_precision_at_5"], 1)
        self.assertEqual(first["context_recall_at_5"], 0.5)
        self.assertEqual(first["supported_fact_ids"], ["age"])
        self.assertEqual(first["missing_fact_ids"], ["period"])
        self.assertAlmostEqual(result["metrics_summary"]["context_recall_at_5"], 1 / 6)
        self.assertEqual(result["metrics_summary"]["context_recall_evaluated_query_count"], 3)
        self.assertEqual(result["metrics_by_query"][2]["context_recall_status"], "execution_error")
        self.assertEqual(result["metrics_by_query"][1]["context_recall_at_5"], 0)

    def test_pending_annotations_are_not_zero(self):
        self.facts[2]["review_status"] = "pending"
        self.qrels[3]["review_status"] = "pending"
        result = self.evaluate()
        second = result["metrics_by_query"][1]
        self.assertIsNone(second["context_precision_at_5"])
        self.assertIsNone(second["context_recall_at_5"])
        self.assertEqual(second["context_recall_reason"], "required_facts_unreviewed")
        self.assertEqual(result["metrics_summary"]["context_recall_evaluated_query_count"], 2)
        self.assertEqual(result["metrics_summary"]["context_recall_status"], "partial")
        self.assertEqual(result["metrics_summary"]["context_recall_at_5"], 0.25)

    def test_missing_mapping_differs_from_reviewed_no_support(self):
        self.mapping = [r for r in self.mapping if not (r["query_id"] == "q1" and r["fact_id"] == "period")]
        self.assertIsNone(self.evaluate()["metrics_by_query"][0]["context_recall_at_5"])
        self.mapping.append({"query_id": "q1", "fact_id": "period", "chunk_id": None,
            "chunking_version": "c_v1", "review_status": "approved"})
        self.assertEqual(self.evaluate()["metrics_by_query"][0]["context_recall_at_5"], 0.5)

    def test_duplicate_fact_references_and_versions_are_rejected(self):
        import copy
        original = copy.deepcopy(self.mapping)
        for changes in ({"chunk_id": "unknown"}, {"fact_id": "unknown"},
                        {"chunking_version": "other"}, {"query_id": "unknown"},
                        {"review_status": "typo"}):
            self.mapping = copy.deepcopy(original)
            self.mapping[0].update(changes)
            with self.assertRaises(ValueError):
                self.evaluate()
        self.mapping = original + [original[0]]
        with self.assertRaises(ValueError):
            self.evaluate()
        self.mapping = original
        self.facts.append(dict(self.facts[0]))
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_whole_run_query_mismatch_is_not_a_partial_score(self):
        self.rows.pop()
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_unreviewed_all_has_null_average(self):
        self.facts = []
        self.mapping = []
        for row in self.qrels:
            row.pop("review_status")
        summary = self.evaluate()["metrics_summary"]
        self.assertIsNone(summary["context_recall_at_5"])
        self.assertIsNone(summary["context_precision_at_5"])
        self.assertEqual(summary["context_recall_evaluated_query_count"], 0)

    def test_top_k_is_independent_of_answer_context_size(self):
        self.config["retrieval"]["context_top_k"] = 1
        self.rows[0]["results"] = [{"chunk_id": "x", "document_id": "d"} for _ in range(5)]
        self.rows[0]["results"].append({"chunk_id": "c3", "document_id": "d"})
        first = self.evaluate()["metrics_by_query"][0]
        self.assertEqual(first["context_recall_at_5"], 0)
        self.assertEqual(first["chunk_mrr"], 0)

    def test_config_schema_bounds_and_paths(self):
        from jsonschema import Draft202012Validator
        from src.experiments.config_validator import _resolve_runtime_paths
        from src.evaluation.validate_inputs import validate_context_config

        schema = json.loads(Path("schemas/experiment_v4.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema["properties"]["evaluation"]["properties"]["context_metrics"])
        settings = self.config["evaluation"]["context_metrics"]
        self.assertFalse(list(validator.iter_errors(settings)))
        self.assertTrue(list(validator.iter_errors({"enabled": True})))
        self.assertFalse(list(validator.iter_errors({"enabled": False})))
        for k in (0, 6):
            settings["k"] = k
            with self.assertRaises(ValueError):
                validate_context_config(self.config)
        settings["k"] = 5
        settings["chunk_fact_map_path"] = "data/{chunking_version}/chunk_fact_map.jsonl"
        resolved = _resolve_runtime_paths(self.config)
        value = resolved["evaluation"]["context_metrics"]["chunk_fact_map_path"]
        self.assertTrue(Path(value).is_absolute())
        self.assertIn("c_v1", value)

    def test_baseline_and_runner_save_same_scores(self):
        from src.evaluation.evaluator import run_chunk_evaluation
        from src.common.io import write_jsonl

        self.write_inputs()
        write_jsonl(self.root / "retrieval.jsonl", self.rows)
        with patch("src.evaluation.evaluator.create_chunk_evaluation_manifest", return_value={}):
            metrics, summary, manifest = run_chunk_evaluation(self.root / "retrieval.jsonl",
                self.root / "qrels.jsonl", self.root / "baseline", context_config=self.config)
        runner = self.evaluate()
        self.assertEqual(summary["context_recall_at_5"], runner["metrics_summary"]["context_recall_at_5"])
        self.assertEqual(metrics[0]["supported_fact_ids"], ["age"])
        self.assertIn("sha256", manifest["context_metrics"]["inputs"]["required_facts_path"])
        saved = json.loads((self.root / "baseline" / "chunk_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["context_recall_at_5"], summary["context_recall_at_5"])

    def test_runner_artifacts_store_scores_and_input_hashes(self):
        from src.experiments.artifact_writer import write_experiment_artifacts

        evaluation = self.evaluate()
        manifest_path = self.root / "index_manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        result = write_experiment_artifacts(self.config, {
            "retrieval_results": self.rows, "evaluation": evaluation, "dataset_info": {}, "chunk_info": {},
            "index_info": {"manifest_path": str(manifest_path)}})
        output = Path(result["output_dir"])
        saved = json.loads((output / "experiment_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["evaluation"]["context_metrics"]["version"], "context_v1")
        rows = [json.loads(r) for r in (output / "metrics_by_query.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[0]["missing_fact_ids"], ["period"])

    def test_pre_index_validation_reports_review_inputs(self):
        from src.evaluation.validate_inputs import validate_evaluation_inputs

        info = validate_evaluation_inputs(self.config, self.config["dataset"], self.config["chunking"])
        self.assertEqual(info["context_metrics"]["version"], "context_v1")
        self.mapping[0]["chunking_version"] = "wrong"
        self.write_inputs()
        with self.assertRaises(ValueError):
            validate_evaluation_inputs(self.config, self.config["dataset"], self.config["chunking"])

    def test_missing_file_is_fatal_but_disabled_metrics_do_not_read_it(self):
        (self.root / "facts.jsonl").unlink()
        with self.assertRaises(FileNotFoundError):
            evaluate_experiment(self.config, self.rows)
        self.config["evaluation"]["context_metrics"]["enabled"] = False
        result = evaluate_experiment(self.config, self.rows)
        self.assertNotIn("context_recall_at_5", result["metrics_summary"])

    def test_baseline_mrr_is_at_five_and_runtime_failure_is_zero(self):
        results = [{"chunk_id": "x"} for _ in range(5)] + [{"chunk_id": "c1"}]
        baseline = evaluate_chunk_queries([{"query_id": "q1", "results": results}], {"q1": {"c1"}})
        self.assertEqual(baseline[0]["reciprocal_rank"], 0)
        baseline = evaluate_chunk_queries([{"query_id": "q1", "results": [{"chunk_id": "c1"}],
            "error": "DB failure"}], {"q1": {"c1"}})
        self.assertEqual(baseline[0]["hit_at_1"], 0)


if __name__ == "__main__":
    unittest.main()
