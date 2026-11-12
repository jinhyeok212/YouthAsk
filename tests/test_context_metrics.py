import unittest
from unittest.mock import patch

from src.evaluation.retrieval_metrics import calculate_context_metrics
from src.evaluation.evaluator import evaluate_chunk_queries, summarize_chunk_metrics
from src.evaluation.evaluate_experiment import evaluate_experiment


class ContextMetricsTest(unittest.TestCase):
    def test_rank_coverage_duplicates_and_empty_results(self):
        metrics = calculate_context_metrics(["x", "a", "a", "b"], {"a", "b", "c"})
        self.assertAlmostEqual(metrics["context_precision"], 0.5)
        self.assertAlmostEqual(metrics["context_recall"], 2 / 3)
        self.assertEqual(calculate_context_metrics([], {"a"}),
                         {"context_precision": 0.0, "context_recall": 0.0})
        self.assertEqual(calculate_context_metrics(["x"], {"a"})["context_precision"], 0)
        with self.assertRaises(ValueError):
            calculate_context_metrics(["a"], set())

    def test_earlier_evidence_improves_precision_only(self):
        early = calculate_context_metrics(["a", "x"], {"a", "b"})
        late = calculate_context_metrics(["x", "a"], {"a", "b"})
        self.assertGreater(early["context_precision"], late["context_precision"])
        self.assertEqual(early["context_recall"], late["context_recall"])

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
        for metric in ("context_precision", "context_recall"):
            self.assertEqual(baseline[f"chunk_{metric}"], summary[f"chunk_{metric}"])
            self.assertEqual(summary[f"chunk_{metric}_at_1"], 0)
            self.assertEqual(summary[f"chunk_{metric}_at_2"], 0.5)


if __name__ == "__main__":
    unittest.main()
