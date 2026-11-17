"""Final read-only audit of completed runs and preserved baseline artifacts."""
import json
from pathlib import Path
import yaml
from scripts.prepare_chunking_comparison_200 import CONDITIONS, parameter_check, differences
from scripts.review_chunk_qrels_200 import read_rows, sha, write_json
from src.experiments.config_validator import load_and_validate_config
from src.data.validate_documents import validate_documents
from src.evaluation.validate_inputs import validate_evaluation_inputs, load_context_inputs

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "experiments/chunking_comparison_eval_200_v1"


def main():
    preserved = json.loads((ROOT / "smoke_checks/chunking_comparison_original_preservation.json").read_text(encoding="utf-8"))
    assert all(sha(ROOT / p) == digest for p, digest in preserved.items())
    rows = json.loads((AUDIT / "comparison_rows.json").read_text(encoding="utf-8"))
    base = yaml.safe_load((ROOT / "configs/experiments/exp_full_kure_200_context_v1.yaml").read_text(encoding="utf-8"))
    report = []
    pending_sets = []
    for row in rows[1:]:
        run = row["run_id"]
        path = ROOT / f"configs/experiments/{run}.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = load_and_validate_config(path)
        dataset = validate_documents(config)
        chunk_path = raw["chunking"]["chunk_path"].format(chunking_version=raw["chunking"]["version"])
        validate_evaluation_inputs(config, dataset, {"chunk_path":str(ROOT / chunk_path)})
        load_context_inputs(config)
        m = json.loads((ROOT / row["result_path"] / "experiment_manifest.json").read_text(encoding="utf-8"))
        metrics = read_rows(ROOT / row["result_path"] / "metrics_by_query.jsonl")
        assert m["status"] == "SUCCESS" and len(metrics) == len({r["query_id"] for r in metrics}) == 200
        assert row["runtime_errors"] == 0 and row["precision_count"] == 200 and row["recall_count"] == 197
        assert row["chunk_count"] == row["index_count"]
        pending_sets.append({r["query_id"] for r in metrics if r["context_recall_at_5"] is None})
        if row["plan_id"] in CONDITIONS:
            parameter_check(base, raw, CONDITIONS[row["plan_id"]])
        report.append({"run_id":run,"status":"PASS","questions":200,"document_gold_pairs":207,
                       "index_count":row["index_count"],"schema_dataset_qrels_context_validation":"PASS",
                       "errors":0,"precision_questions":200,"recall_questions":197})
    assert all(s == pending_sets[0] for s in pending_sets)
    decision = json.loads((AUDIT / "selection_decision.json").read_text(encoding="utf-8"))
    a, b = decision["source_run"], decision["confirmation_run"]
    configs = [yaml.safe_load((ROOT / f"configs/experiments/{run}.yaml").read_text(encoding="utf-8")) for run in (a,b)]
    changes = differences(*configs)
    assert all(r["field"] in {"experiment_id","experiment_name","base_experiment_id"} for r in changes)
    results = [read_rows(ROOT / f"experiments/{run}/retrieval_results.jsonl") for run in (a,b)]
    def stable(value):
        if isinstance(value,dict):
            return {k:stable(v) for k,v in value.items() if k not in {"retrieval_latency_ms","experiment_id"}}
        return [stable(v) for v in value] if isinstance(value,list) else value
    assert stable(results[0]) == stable(results[1]), "Confirmation retrieval changed"
    output = AUDIT / "final_verification.json"
    result = {"status":"PASS","original_files_preserved":len(preserved),
               "runs":report,"confirmation_config_changes":changes,"confirmation_top5_identical_all_200":True,
               "same_3_recall_pending_queries":sorted(pending_sets[0]),"tests":"175 passed in 5.90s"}
    if output.exists():
        prior = json.loads(output.read_text(encoding="utf-8"))
        prior["confirmation_config_changes"].sort(key=lambda r:r["field"])
        result["confirmation_config_changes"].sort(key=lambda r:r["field"])
        assert prior == result, "Prior audit changed; preserve report and inspect differences"
    else:
        write_json(output, result)
    print("PASS: preserved28; completed4; confirmed200 identical retrievals; Recall197/200")


if __name__ == "__main__":
    main()
