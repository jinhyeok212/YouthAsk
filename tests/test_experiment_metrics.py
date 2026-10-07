"""Small fixed inputs: no model, database or network required."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.evaluation.evaluate_experiment import evaluate_experiment
from src.experiments.contracts import validate_evaluation_result


def fixture(root):
    config = {"experiment_id": "fixture", "runtime": {"output_root": str(root / "out")},
              "retrieval": {"evaluation_max_k": 5}, "evaluation": {}}
    files = {
        "questions_path": [{"query_id": f"q{i}", "query": f"질문 {i}"} for i in range(3)],
        "document_qrels_path": [{"query_id": f"q{i}", "document_id": "gold"} for i in range(3)],
        "chunk_qrels_path": [{"query_id": f"q{i}", "chunk_id": "gold_chunk"} for i in range(3)],
    }
    for name, values in files.items():
        path = root / (name + ".jsonl")
        path.write_text("".join(json.dumps(row) + "\n" for row in values), encoding="utf-8")
        config["evaluation"][name] = str(path)
    rows = []
    for i, gold_rank in enumerate((1, 3, None)):
        results = [dict(rank=rank, document_id="gold" if rank == gold_rank else "other",
                        chunk_id="gold_chunk" if rank == gold_rank else f"other_{rank}",
                        distance=.2, similarity=.8) for rank in range(1, 6)]
        rows.append(dict(query_id=f"q{i}", query=f"질문 {i}",
                         retrieval_latency_ms=10 * (i + 1), results=results))
    return config, rows


class ExperimentMetricsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config, self.rows = fixture(Path(self.temp.name))

    def test_known_metrics_and_determinism(self):
        before = copy.deepcopy(self.rows)
        result = evaluate_experiment(self.config, self.rows)
        validate_evaluation_result(result)
        for prefix in ("document", "chunk"):
            self.assertAlmostEqual(result["metrics_summary"][prefix + "_hit_at_1"], 1 / 3)
            self.assertAlmostEqual(result["metrics_summary"][prefix + "_hit_at_3"], 2 / 3)
            self.assertAlmostEqual(result["metrics_summary"][prefix + "_mrr"], 4 / 9)
        self.assertEqual(result["metrics_summary"]["average_retrieval_latency_ms"], 20)
        self.assertEqual(result["metrics_summary"]["p95_retrieval_latency_ms"], 30)
        self.assertEqual(result, evaluate_experiment(self.config, self.rows))
        self.assertEqual(before, self.rows)

    def test_original_document_rank_is_preserved(self):
        result = evaluate_experiment(self.config, self.rows)
        self.assertEqual(result["metrics_by_query"][1]["document"]["first_relevant_rank"], 3)

    def test_chunk_miss_and_runtime_error_are_distinct(self):
        self.rows[0]["results"][0]["chunk_id"] = "wrong"
        self.rows[1].update(results=[], error="embedding failed")
        result = evaluate_experiment(self.config, self.rows)
        self.assertEqual([case["failure_type"] for case in result["failure_cases"]],
                         ["chunk_not_in_top_5", "runtime_error", "document_not_in_top_5"])
        self.assertEqual(result["metrics_summary"]["status"], "FAILED")

    def test_missing_query_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "q2"):
            evaluate_experiment(self.config, self.rows[:2])

    def test_missing_qrels_is_rejected(self):
        Path(self.config["evaluation"]["chunk_qrels_path"]).write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            evaluate_experiment(self.config, self.rows)

    def test_duplicate_query_is_rejected(self):
        with self.assertRaises(TypeError):
            evaluate_experiment(self.config, self.rows + [self.rows[0]])

    def test_invalid_rank_and_latency_are_rejected(self):
        for field, value in (("rank", 2), ("distance", float("nan"))):
            rows = copy.deepcopy(self.rows)
            rows[0]["results"][0][field] = value
            with self.assertRaises(TypeError):
                evaluate_experiment(self.config, rows)
        self.rows[0]["retrieval_latency_ms"] = -1
        with self.assertRaises(TypeError):
            evaluate_experiment(self.config, self.rows)

    def test_max_k_is_enforced(self):
        self.config["retrieval"]["evaluation_max_k"] = 3
        with self.assertRaises(ValueError):
            evaluate_experiment(self.config, self.rows)


if __name__ == "__main__":
    unittest.main()
