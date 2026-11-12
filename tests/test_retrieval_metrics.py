"""Document·Chunk의 Hit@k, RR, MRR, Context Precision·Recall 테스트."""

import unittest
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
