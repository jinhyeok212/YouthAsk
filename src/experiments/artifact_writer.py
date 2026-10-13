from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from src.common.io import utc_now_iso, write_json, write_jsonl
from src.experiments.environment import collect_environment_info


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _config_for_artifact(config: dict) -> dict:
    return {k: v for k, v in config.items() if k != "_runtime"}


def write_experiment_artifacts(config: dict, run_context: dict) -> dict:
    """Write artifacts into a staging directory and publish atomically."""
    output_root = Path(config.get("output", {}).get("root", "experiments"))
    out = output_root / config["experiment_id"]

    if out.exists():
        raise FileExistsError(
            "기존 실험 결과를 덮어쓰지 않습니다. "
            f"experiment_id를 새 버전으로 변경하세요: {out}"
        )

    staging_root = output_root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    stage = staging_root / f"{config['experiment_id']}__{uuid4().hex[:8]}"
    stage.mkdir(parents=True, exist_ok=False)

    try:
        retrieval = run_context["retrieval_results"]
        evaluation = run_context["evaluation"]
        dataset_info = run_context["dataset_info"]
        chunk_info = run_context["chunk_info"]
        index_info = run_context["index_info"]
        evaluation_info = run_context.get("evaluation_info")
        status = run_context.get("status", "SUCCESS")
        log_path = run_context.get("run_log_path")

        write_jsonl(stage / "retrieval_results.jsonl", retrieval)
        write_jsonl(stage / "traces.jsonl", retrieval)
        write_json(stage / "metrics_summary.json", evaluation["metrics_summary"])
        write_jsonl(stage / "metrics_by_query.jsonl", evaluation["metrics_by_query"])
        write_json(stage / "environment.json", collect_environment_info())
        write_json(stage / "resolved_config.json", _config_for_artifact(config))

        failure_path = stage / "failure_cases.csv"
        with failure_path.open("w", encoding="utf-8-sig", newline="") as f:
            fields = [
                "query_id",
                "failure_type",
                "document_first_relevant_rank",
                "chunk_first_relevant_rank",
                "retrieval_latency_ms",
                "runtime_error",
            ]
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in evaluation["failure_cases"]:
                writer.writerow({k: row.get(k) for k in fields})

        experiment_manifest = {
            "experiment_id": config["experiment_id"],
            "experiment_name": config.get("experiment_name"),
            "base_experiment_id": config.get("base_experiment_id"),
            "status": status,
            "schema_version": config["schema_version"],
            "dataset": dataset_info,
            "chunking": chunk_info,
            "index": index_info,
            "embedding": config["embedding"],
            "retrieval": config["retrieval"],
            "evaluation": {
                "version": config["evaluation"]["version"],
                "ks": config["evaluation"].get("ks", [1, 3, 5]),
                "validation": evaluation_info,
            },
            "git_commit": _git_commit(),
            "created_at_utc": utc_now_iso(),
        }
        write_json(stage / "experiment_manifest.json", experiment_manifest)

        shutil.copy2(index_info["manifest_path"], stage / "index_manifest.json")

        source_config = config.get("_runtime", {}).get("config_path")
        if source_config and Path(source_config).exists():
            shutil.copy2(source_config, stage / "experiment_config.yaml")

        if log_path and Path(log_path).exists():
            shutil.copy2(log_path, stage / "run.log")

        # Same filesystem rename: consumers never observe a half-written final folder.
        stage.rename(out)

        return {
            "output_dir": str(out),
            "experiment_manifest_path": str(out / "experiment_manifest.json"),
            "metrics_summary_path": str(out / "metrics_summary.json"),
            "failure_cases_path": str(out / "failure_cases.csv"),
            "environment_path": str(out / "environment.json"),
        }

    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
