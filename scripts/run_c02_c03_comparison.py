"""Run C02/C03 index builds and three reusable-index timing repetitions.

This is intended for a long CPU-only unattended run.  Every repetition keeps
the data, questions, qrels, embedding revision, distance metric, and Top-k
fixed; only the chunk condition differs.
"""

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
CONDITIONS = (
    ("C02", ROOT / "configs/experiments/c02_20261112_r1.yaml"),
    ("C03", ROOT / "configs/experiments/c03_20261112_r1.yaml"),
)
REPETITIONS = (1, 2, 3, 4)
SUMMARY_JSON = ROOT / "experiments/C02_C03_COMPARISON_STATUS.json"
SUMMARY_CSV = ROOT / "experiments/C02_C03_REPETITION_SUMMARY.csv"


def completed_result(experiment_id: str) -> dict | None:
    summary_path = ROOT / "experiments" / experiment_id / "metrics_summary.json"
    if not summary_path.exists():
        return None
    with summary_path.open("r", encoding="utf-8") as handle:
        metrics = json.load(handle)
    return {"experiment_id": experiment_id, "status": "SUCCESS", "metrics_summary": metrics}


def write_status(rows: list[dict], *, active: str | None, error: str | None = None) -> None:
    payload = {"active_experiment_id": active, "runs": rows, "error": error}
    with SUMMARY_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_csv(rows: list[dict]) -> None:
    fields = [
        "experiment_id",
        "condition",
        "repetition",
        "status",
        "average_retrieval_latency_ms",
        "p95_retrieval_latency_ms",
        "max_retrieval_latency_ms",
        "document_hit_at_1",
        "document_hit_at_3",
        "document_hit_at_5",
        "document_mrr",
        "chunk_hit_at_1",
        "chunk_hit_at_3",
        "chunk_hit_at_5",
        "chunk_mrr",
        "retrieval_failure_count",
    ]
    with SUMMARY_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            metrics = row.get("metrics_summary", {})
            writer.writerow(
                {
                    "experiment_id": row["experiment_id"],
                    "condition": row["experiment_id"].split("-")[0],
                    "repetition": row["experiment_id"].rsplit("R", 1)[-1],
                    "status": row.get("status"),
                    **{field: metrics.get(field) for field in fields[4:]},
                }
            )


def main() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.chdir(ROOT)

    rows: list[dict] = []
    write_status(rows, active=None)
    try:
        for condition, config_path in CONDITIONS:
            base = load_and_validate_config(str(config_path), "schemas/experiment_v4.schema.json")
            for repetition in REPETITIONS:
                experiment_id = f"{condition}-20261112-R{repetition}"
                existing = completed_result(experiment_id)
                if existing is not None:
                    rows.append(existing)
                    write_status(rows, active=experiment_id)
                    continue

                config = copy.deepcopy(base)
                config["experiment_id"] = experiment_id
                config["experiment_name"] = (
                    f"{base['experiment_name']}-repeat-{repetition}"
                )
                config["base_experiment_id"] = (
                    "B01-20261104-R4" if repetition == 1 else f"{condition}-20261112-R1"
                )
                write_status(rows, active=experiment_id)
                result = run_pipeline(config)
                rows.append(result)
                write_status(rows, active=experiment_id)
                write_csv(rows)

        write_status(rows, active=None)
        write_csv(rows)
    except Exception:
        error = traceback.format_exc()
        write_status(rows, active=None, error=error)
        write_csv(rows)
        raise


if __name__ == "__main__":
    main()
