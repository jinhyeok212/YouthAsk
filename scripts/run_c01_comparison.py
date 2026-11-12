"""Run C01 R1-R4 and write progress/repetition summaries."""

from __future__ import annotations

import copy
import csv
import json
import os
import traceback
from pathlib import Path

from src.experiments.config_validator import load_and_validate_config
from src.experiments.runner import run_pipeline


ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = ROOT / "configs/experiments/c01_20261112_r1.yaml"
STATUS_PATH = ROOT / "experiments/C01_COMPARISON_STATUS.json"
SUMMARY_CSV = ROOT / "experiments/C01_REPETITION_SUMMARY.csv"


def completed_result(experiment_id: str) -> dict | None:
    path = ROOT / "experiments" / experiment_id / "metrics_summary.json"
    if not path.exists():
        return None
    return {
        "experiment_id": experiment_id,
        "status": "SUCCESS",
        "metrics_summary": json.loads(path.read_text(encoding="utf-8")),
    }


def write_status(rows: list[dict], active: str | None, error: str | None = None) -> None:
    STATUS_PATH.write_text(
        json.dumps({"active_experiment_id": active, "runs": rows, "error": error}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_csv(rows: list[dict]) -> None:
    fields = [
        "experiment_id", "status", "average_retrieval_latency_ms",
        "p95_retrieval_latency_ms", "max_retrieval_latency_ms",
        "document_hit_at_1", "document_hit_at_3", "document_hit_at_5",
        "document_mrr", "chunk_hit_at_1", "chunk_hit_at_3",
        "chunk_hit_at_5", "chunk_mrr", "retrieval_failure_count",
    ]
    with SUMMARY_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            metrics = row.get("metrics_summary", {})
            writer.writerow({"experiment_id": row["experiment_id"], "status": row.get("status")} | {key: metrics.get(key) for key in fields[2:]})


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.chdir(ROOT)
    base = load_and_validate_config(str(BASE_CONFIG), "schemas/experiment_v4.schema.json")
    rows: list[dict] = []
    write_status(rows, None)
    try:
        for repetition in (1, 2, 3, 4):
            experiment_id = f"C01-20261112-R{repetition}"
            existing = completed_result(experiment_id)
            if existing is not None:
                rows.append(existing)
                write_status(rows, experiment_id)
                continue
            config = copy.deepcopy(base)
            config["experiment_id"] = experiment_id
            config["experiment_name"] = f"full-dataset-kure-fixed-800-overlap120-repeat-{repetition}"
            config["base_experiment_id"] = "B01-20261104-R4" if repetition == 1 else "C01-20261112-R1"
            write_status(rows, experiment_id)
            result = run_pipeline(config)
            rows.append(result)
            write_status(rows, experiment_id)
            write_csv(rows)
        write_status(rows, None)
        write_csv(rows)
    except Exception:
        error = traceback.format_exc()
        write_status(rows, None, error)
        write_csv(rows)
        raise


if __name__ == "__main__":
    main()
