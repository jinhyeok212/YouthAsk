from pathlib import Path

from src.common.paths import PROJECT_ROOT, resolve_project_path


def test_project_relative_path_is_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    resolved = resolve_project_path("schemas/experiment.schema.json")
    assert resolved == (PROJECT_ROOT / "schemas/experiment.schema.json").resolve()
    assert resolved.exists()
