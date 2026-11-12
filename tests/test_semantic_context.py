import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.evaluation.semantic_context import (
    OpenAIContextJudge, evaluate_semantic_context, load_references,
    prepare_requests, score_verdict,
)
from src.evaluation.evaluate_experiment import evaluate_experiment


class SemanticContextTest(unittest.TestCase):
    def setUp(self):
        self.ref = {"query_id": "q", "query": "Who qualifies?",
                    "reference_answer": "Age 19 or older; resident in Seoul.",
                    "required_facts": ["Age at least 19", "Seoul resident"],
                    "review_status": "approved"}
        self.rows = [{"query_id": "q", "query": self.ref["query"],
                      "retrieval_latency_ms": 1, "results": [
                          {"rank": 1, "chunk_id": "x", "document_id": "d", "text": "Other policy"},
                          {"rank": 2, "chunk_id": "a", "document_id": "d", "text": "Age 19 or older"}]}]
        self.config = {"evaluation": {"semantic_context": {
            "enabled": True, "references_path": "refs.jsonl", "top_k": 2, "model": "test-model"},
            "document_qrels_path": "docs", "chunk_qrels_path": "qrels", "ks": [1, 2]},
            "chunking": {"chunk_path": "chunks.jsonl"}}
        self.verdict = {"chunks": [
            {"chunk_id": "x", "relevant": False, "reason": "Wrong policy"},
            {"chunk_id": "a", "relevant": True, "reason": "Age evidence"}],
            "facts": [{"fact": "Age at least 19", "supported": True,
                       "reason": "Explicit age", "evidence": [{"chunk_id": "a", "quote": "Age 19 or older"}]},
                      {"fact": "Seoul resident", "supported": False,
                       "reason": "Not mentioned", "evidence": []}]}

    def request(self):
        with patch("src.evaluation.semantic_context.read_jsonl", return_value=[self.ref]):
            return prepare_requests(self.config, self.rows)[0]

    def test_precision_and_fact_coverage(self):
        self.assertEqual(score_verdict(self.request(), self.verdict), {
            "semantic_context_precision": 0.5, "semantic_context_recall": 0.5})

    def test_rejects_invented_evidence_missing_facts_and_wrong_order(self):
        for mutate in (
            lambda v: v["facts"][0]["evidence"][0].update(quote="invented"),
            lambda v: v["facts"].pop(),
            lambda v: v["chunks"].reverse(),
            lambda v: v["facts"][1].update(supported=True),
        ):
            verdict = copy.deepcopy(self.verdict)
            mutate(verdict)
            with self.assertRaises(ValueError):
                score_verdict(self.request(), verdict)

    def test_reference_review_duplicates_and_alignment(self):
        for rows in ([dict(self.ref, review_status="pending")],
                     [dict(self.ref, required_facts=[])], [self.ref, self.ref],
                     [dict(self.ref, query_id="other")]):
            with patch("src.evaluation.semantic_context.read_jsonl", return_value=rows):
                with self.assertRaises(ValueError):
                    load_references("refs", {"q"})

    def test_existing_chunk_fallback_and_question_check(self):
        del self.rows[0]["results"][1]["text"]
        with patch("src.evaluation.semantic_context.read_jsonl", side_effect=[
            [self.ref], [{"chunk_id": "a", "retrieval_text": "Age 19 or older"}]]):
            request = prepare_requests(self.config, self.rows)[0]
        self.assertEqual(request["contexts"][1]["text"], "Age 19 or older")
        self.rows[0]["query"] = "different"
        with patch("src.evaluation.semantic_context.read_jsonl", side_effect=[
            [self.ref], [{"chunk_id": "a", "text": "body"}]]):
            with self.assertRaises(ValueError):
                prepare_requests(self.config, self.rows)

    def test_disabled_makes_no_calls(self):
        judge = Mock()
        self.assertIsNone(evaluate_semantic_context({}, self.rows, judge))
        judge.assert_not_called()

    def test_empty_retrieval_is_zero_without_judge_call(self):
        self.rows[0]["results"] = []
        self.rows[0]["error"] = "retrieval failed"
        judge = Mock()
        with patch("src.evaluation.semantic_context.read_jsonl", return_value=[self.ref]), \
             patch("src.evaluation.semantic_context.sha256_file", return_value="hash"):
            result = evaluate_semantic_context(self.config, self.rows, judge)
        judge.assert_not_called()
        self.assertEqual(result["metrics_summary"]["semantic_context_recall"], 0)
        self.assertEqual(result["judgments"][0]["request"]["retrieval_error"], "retrieval failed")

    def test_all_requests_are_validated_before_judging(self):
        self.rows.append(dict(self.rows[0], query_id="missing-reference"))
        judge = Mock()
        with patch("src.evaluation.semantic_context.read_jsonl", return_value=[self.ref]):
            with self.assertRaises(ValueError):
                evaluate_semantic_context(self.config, self.rows, judge)
        judge.assert_not_called()

    def test_runner_uses_same_semantic_evaluator(self):
        judge = Mock(return_value={"verdict": self.verdict, "resolved_model": "test-model"})
        with patch("src.evaluation.semantic_context.read_jsonl", return_value=[self.ref]), \
             patch("src.evaluation.semantic_context.sha256_file", return_value="hash"), \
             patch("src.evaluation.semantic_context.OpenAIContextJudge", return_value=judge), \
             patch("src.evaluation.evaluate_experiment.load_document_qrels", return_value={"q": {"d"}}), \
             patch("src.evaluation.evaluate_experiment.load_chunk_qrels", return_value={"q": {"a"}}):
            result = evaluate_experiment(self.config, self.rows)
        self.assertEqual(result["metrics_summary"]["semantic_context_recall"], 0.5)
        self.assertEqual(result["metrics_by_query"][0]["semantic_context_precision"], 0.5)
        self.assertEqual(result["semantic_context"]["manifest"]["top_k"], 2)

    def test_sdk_structured_output_and_refusal(self):
        client = Mock()
        response = SimpleNamespace(status="completed", output_text=json.dumps(self.verdict),
                                   id="response", model="test-model", usage=None)
        client.responses.create.return_value = response
        with patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=Mock(return_value=client))}), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "fake-test-key"}):
            judge = OpenAIContextJudge({"model": "test-model"})
            self.assertEqual(judge(self.request())["verdict"], self.verdict)
        args = client.responses.create.call_args.kwargs
        self.assertFalse(args["store"])
        self.assertTrue(args["text"]["format"]["strict"])
        response.output_text = ""
        with self.assertRaises(ValueError):
            judge(self.request())

    def test_baseline_connection_and_saved_judgments(self):
        from src.evaluation.evaluator import run_chunk_evaluation
        judge = Mock(return_value={"verdict": self.verdict})
        with patch("src.evaluation.evaluator.load_retrieval_results", return_value=self.rows), \
             patch("src.evaluation.evaluator.load_chunk_qrels", return_value={"q": {"a"}}), \
             patch("src.evaluation.evaluator.create_chunk_evaluation_manifest", return_value={}), \
             patch("src.evaluation.evaluator.save_chunk_evaluation"), \
             patch("src.evaluation.semantic_context.save_semantic_context") as save, \
             patch("src.evaluation.semantic_context.read_jsonl", return_value=[self.ref]), \
             patch("src.evaluation.semantic_context.sha256_file", return_value="hash"), \
             patch("src.evaluation.semantic_context.OpenAIContextJudge", return_value=judge):
            metrics, summary, manifest = run_chunk_evaluation(
                "retrieval", "qrels", "output", semantic_config=self.config)
        self.assertEqual(summary["semantic_context_precision"], 0.5)
        self.assertEqual(metrics[0]["semantic_context_recall"], 0.5)
        self.assertEqual(manifest["semantic_context"]["prompt_version"], "semantic_context_v1")
        save.assert_called_once()

    def test_config_schema_and_runtime_reference_path(self):
        from pathlib import Path
        from jsonschema import Draft202012Validator
        from src.experiments.config_validator import _resolve_runtime_paths
        schema = json.loads(Path("schemas/experiment_v4.schema.json").read_text(encoding="utf-8"))
        semantic_schema = schema["properties"]["evaluation"]["properties"]["semantic_context"]
        validator = Draft202012Validator(semantic_schema)
        self.assertFalse(list(validator.iter_errors(self.config["evaluation"]["semantic_context"])))
        self.assertTrue(list(validator.iter_errors({"enabled": True})))
        self.assertFalse(list(validator.iter_errors({"enabled": False})))
        resolved = _resolve_runtime_paths(self.config)
        self.assertTrue(Path(resolved["evaluation"]["semantic_context"]["references_path"]).is_absolute())

    def test_top_k_rejected_before_indexing(self):
        from src.experiments.config_validator import validate_semantics, ConfigValidationError
        self.config["retrieval"] = {"evaluation_max_k": 1}
        with self.assertRaises(ConfigValidationError):
            validate_semantics(self.config)

    def test_macro_average_includes_empty_retrieval(self):
        ref2 = dict(self.ref, query_id="q2")
        self.rows.append({"query_id": "q2", "results": [], "retrieval_latency_ms": 0})
        judge = Mock(return_value={"verdict": self.verdict})
        with patch("src.evaluation.semantic_context.read_jsonl", return_value=[self.ref, ref2]), \
             patch("src.evaluation.semantic_context.sha256_file", return_value="hash"):
            result = evaluate_semantic_context(self.config, self.rows, judge)
        self.assertEqual(result["metrics_summary"]["semantic_context_precision"], 0.25)
        self.assertEqual(result["metrics_summary"]["semantic_context_recall"], 0.25)
        judge.assert_called_once()


if __name__ == "__main__":
    unittest.main()
