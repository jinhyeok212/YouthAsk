"""Save Runner artifacts without overwriting existing experiment results."""

import csv
import hashlib
import io
import json
import subprocess

from src.evaluation.evaluate_experiment import input_path, PROJECT_ROOT
from src.experiments.contracts import validate_evaluation_result


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _jsonl(rows):
    return "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows)


def write_experiment_artifacts(config: dict, run_context: dict) -> dict:
    evaluation = validate_evaluation_result(run_context["evaluation_result"])
    experiment_id = config["experiment_id"]
    root = input_path(config["runtime"]["output_root"]).resolve()
    output = (root / experiment_id).resolve()
    if output.parent != root:
        raise ValueError("experiment_id must be a single directory name")
    rows = run_context["retrieval_results"]
    if len(rows) != len(evaluation["metrics_by_query"]):
        raise ValueError("retrieval/evaluation question counts differ")
    failed = any(row.get("error") for row in rows)
    metadata = dict(run_context["run_metadata"])
    metadata["status"] = "FAILED" if failed else metadata["status"]
    hashes = {}
    for field in ("questions_path", "document_qrels_path", "chunk_qrels_path"):
        path = input_path(config["evaluation"][field])
        hashes[field] = hashlib.sha256(path.read_bytes()).hexdigest()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                              capture_output=True, text=True, check=False)
    manifest = {"config": config, "run_metadata": metadata,
                "dataset_info": run_context["dataset_info"],
                "chunk_info": run_context["chunk_info"],
                "index_info": run_context["index_info"],
                "evaluation_sha256": hashes,
                "code_revision": revision.stdout.strip() if revision.returncode == 0 else None}
    buffer = io.StringIO(newline="")
    columns = ["query_id", "query", "failure_type", "error",
               "document_first_relevant_rank", "chunk_first_relevant_rank",
               "gold_document_ids", "gold_chunk_ids"]
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for case in evaluation["failure_cases"]:
        writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, list)
                         else value for key, value in case.items()})
    traces = [dict(row, experiment_id=experiment_id,
                   index_version=run_context["index_info"]["index_version"]) for row in rows]
    payloads = {
        "experiment_manifest.json": _json(manifest),
        "metrics_summary.json": _json(evaluation["metrics_summary"]),
        "metrics_by_query.jsonl": _jsonl(evaluation["metrics_by_query"]),
        "retrieval_results.jsonl": _jsonl(rows),
        "failure_cases.csv": buffer.getvalue(),
    }
    # The index owner creates its manifest; preserve it or copy its exact content.
    index_source = input_path(run_context["index_info"]["manifest_path"])
    index_text = index_source.read_text(encoding="utf-8-sig")
    json.loads(index_text)
    if index_source.resolve() != (output / "index_manifest.json").resolve():
        payloads["index_manifest.json"] = index_text
    if not (output / "traces.jsonl").exists():
        payloads["traces.jsonl"] = _jsonl(traces)
    else:
        # Trace belongs to retrieval when it already exists. Check coverage.
        from src.evaluation.evaluator import _read_jsonl
        existing = _read_jsonl(output / "traces.jsonl")
        ids = [item["query_id"] for item in existing]
        if len(ids) != len(set(ids)) or set(ids) != {row["query_id"] for row in rows}:
            raise ValueError("existing traces do not cover retrieval query IDs")
    for name in payloads:
        if (output / name).exists():
            raise FileExistsError(f"Refusing to overwrite: {output / name}")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in payloads.items():
        with (output / name).open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)
    # Runner owns run.log. Raising here retains diagnostics but prevents COMPLETED.
    if failed:
        ids = [row["query_id"] for row in rows if row.get("error")]
        raise RuntimeError(f"Retrieval runtime errors; diagnostics saved: {ids}")
    return {"output_dir": str(output), "written_files": [str(output / name) for name in payloads]}
