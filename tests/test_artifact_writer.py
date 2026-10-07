import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_experiment_metrics import fixture
from src.evaluation.evaluate_experiment import evaluate_experiment
from src.experiments.artifact_writer import write_experiment_artifacts
from src.experiments.runner import run_experiment


class ArtifactWriterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config, self.rows = fixture(self.root)
        index = self.root / "index.json"
        index.write_text('{"model": "fixture"}', encoding="utf-8")
        self.context = {
            "dataset_info": {"document_path": "fixture", "manifest_path": "fixture",
                             "document_count": 2, "sha256": "fixture"},
            "chunk_info": {"chunk_path": "fixture", "manifest_path": "fixture",
                           "chunk_count": 6, "chunk_qrels_path": "fixture"},
            "index_info": {"manifest_path": str(index), "index_version": "fixture",
                           "db_path": "fixture", "collection_name": "fixture", "reused": True},
            "retrieval_results": self.rows,
            "evaluation_result": evaluate_experiment(self.config, self.rows),
            "run_metadata": {"experiment_id": "fixture", "status": "COMPLETED",
                             "started_at": "fixture", "completed_at": "fixture"},
        }

    def test_save_and_no_overwrite(self):
        result = write_experiment_artifacts(self.config, self.context)
        output = Path(result["output_dir"])
        self.assertEqual(len(result["written_files"]), 7)
        self.assertEqual(len((output / "metrics_by_query.jsonl").read_text(encoding="utf-8").splitlines()), 3)
        original = (output / "metrics_summary.json").read_bytes()
        with self.assertRaises(FileExistsError):
            write_experiment_artifacts(self.config, self.context)
        self.assertEqual(original, (output / "metrics_summary.json").read_bytes())

    def test_existing_index_trace_and_log_are_preserved(self):
        output = Path(self.config["runtime"]["output_root"]) / "fixture"
        output.mkdir(parents=True)
        (output / "run.log").write_text("runner log", encoding="utf-8")
        (output / "index_manifest.json").write_text("{}", encoding="utf-8")
        self.context["index_info"]["manifest_path"] = str(output / "index_manifest.json")
        traces = "".join(json.dumps(row) + "\n" for row in self.rows)
        (output / "traces.jsonl").write_text(traces, encoding="utf-8")
        write_experiment_artifacts(self.config, self.context)
        self.assertEqual((output / "traces.jsonl").read_text(encoding="utf-8"), traces)
        self.assertEqual((output / "run.log").read_text(encoding="utf-8"), "runner log")

    def test_runtime_error_saves_diagnostics_then_raises(self):
        self.rows[0].update(results=[], error="database unavailable")
        self.context["evaluation_result"] = evaluate_experiment(self.config, self.rows)
        with self.assertRaisesRegex(RuntimeError, "q0"):
            write_experiment_artifacts(self.config, self.context)
        output = Path(self.config["runtime"]["output_root"]) / "fixture"
        manifest = json.loads((output / "experiment_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["run_metadata"]["status"], "FAILED")

    def test_real_runner_with_fixture_upstream(self):
        functions = {
            "validate_documents": lambda config: self.context["dataset_info"],
            "build_chunks": lambda config, info: self.context["chunk_info"],
            "resolve_index": lambda config, info: self.context["index_info"],
            "run_batch_retrieval": lambda config, info: self.rows,
            "evaluate_experiment": evaluate_experiment,
            "write_experiment_artifacts": write_experiment_artifacts,
        }
        self.config["pipeline"] = {"entrypoints": {name: name for name in functions}}
        self.config["runtime"]["output_root"] = "out"
        with patch("src.experiments.runner.load_callable", side_effect=functions.__getitem__), \
             patch("src.evaluation.evaluate_experiment.PROJECT_ROOT", self.root):
            # Keep the real result schema available under this fixture root.
            schema = Path(__file__).resolve().parents[1] / "schemas/experiment_result.schema.json"
            (self.root / "schemas").mkdir()
            (self.root / "schemas/experiment_result.schema.json").write_bytes(schema.read_bytes())
            result = run_experiment(self.config, project_root=self.root)
        output = Path(result["artifact_info"]["output_dir"])
        self.assertTrue((output / "run.log").exists())
        self.assertEqual(result["evaluation_result"]["metrics_summary"]["question_count"], 3)
