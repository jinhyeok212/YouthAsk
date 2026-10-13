import json
from pathlib import Path

import pytest

from src.experiments.artifact_writer import write_experiment_artifacts


def test_completed_experiment_is_not_overwritten(tmp_path):
    out = tmp_path / "experiments" / "exp1"
    out.mkdir(parents=True)
    (out / "metrics_summary.json").write_text("{}", encoding="utf-8")

    config = {
        "experiment_id": "exp1",
        "schema_version": "1.0",
        "output": {"root": str(tmp_path / "experiments")},
        "embedding": {},
        "retrieval": {},
        "evaluation": {"version": "v1"},
    }

    with pytest.raises(FileExistsError):
        write_experiment_artifacts(
            config,
            {
                "retrieval_results": [],
                "evaluation": {"metrics_summary": {}, "metrics_by_query": [], "failure_cases": []},
                "dataset_info": {},
                "chunk_info": {},
                "index_info": {},
            },
        )
