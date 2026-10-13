from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.common.io import load_json, load_yaml
from src.common.paths import resolve_cli_path, resolve_project_path as _resolve_project_path


# ---------------------------------------------------------------------------
# Backward-compatible public API
# ---------------------------------------------------------------------------
# The team repository already had tests/code importing these names from the
# original Experiment Runner.  Keep them available while using the v4 runtime
# implementation underneath.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "experiments" / "exp_full_kure_v1.yaml"
)
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "experiment.schema.json"


class ConfigValidationError(ValueError):
    """Raised when an experiment configuration violates its contract."""


def resolve_project_path(
    configured_path: str | Path,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    """Legacy-compatible path resolver.

    The legacy public API only accepts paths inside ``project_root``.  The v4
    runtime uses ``src.common.paths.resolve_project_path`` internally so it can
    also resolve CLI/config paths independently of the current working folder.
    """
    path = Path(configured_path).expanduser()
    if path.is_absolute():
        raise ConfigValidationError(
            f"설정 파일에는 절대 경로를 사용할 수 없습니다: {configured_path}"
        )

    root = Path(project_root).resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ConfigValidationError(
            f"설정 경로가 프로젝트 폴더 밖을 가리킵니다: {configured_path}"
        ) from exc
    return resolved


_PATH_FIELDS = (
    ("dataset", "document_path"),
    ("dataset", "manifest_path"),
    ("chunking", "chunk_path"),
    ("chunking", "manifest_path"),
    ("evaluation", "questions_path"),
    ("evaluation", "document_qrels_path"),
    ("evaluation", "chunk_qrels_path"),
    ("index", "db_path"),
    ("index", "manifest_path"),
    ("output", "root"),
)


def _format_json_path(parts: list[Any]) -> str:
    if not parts:
        return "$"
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result


def load_json_schema(path: str | Path) -> dict:
    schema = load_json(path)
    if not isinstance(schema, dict):
        raise ConfigValidationError(
            "Experiment Schema의 최상위 값은 object여야 합니다."
        )
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ConfigValidationError(
            f"JSON Schema 자체가 올바르지 않습니다: {exc}"
        ) from exc
    return schema


def validate_schema(config: dict, schema: dict) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(config),
        key=lambda error: list(error.absolute_path),
    )
    if not errors:
        return

    messages = [
        f"- {_format_json_path(list(error.absolute_path))}: {error.message}"
        for error in errors
    ]
    raise ConfigValidationError(
        "Experiment Schema 검증에 실패했습니다.\n" + "\n".join(messages)
    )


def validate_semantics(
    config: dict,
    project_root: Path = PROJECT_ROOT,
) -> None:
    """Validate cross-field rules shared by legacy and v4 configs."""
    chunking = config.get("chunking", {})
    retrieval = config.get("retrieval", {})

    if "size" in chunking and "overlap" in chunking:
        size = int(chunking["size"])
        overlap = int(chunking["overlap"])
        if overlap >= size:
            raise ConfigValidationError(
                "chunking.overlap은 chunking.size보다 작아야 합니다. "
                f"현재 값: overlap={overlap}, size={size}"
            )

    if "evaluation_max_k" in retrieval and "context_top_k" in retrieval:
        max_k = int(retrieval["evaluation_max_k"])
        context_k = int(retrieval["context_top_k"])
        if context_k > max_k:
            raise ConfigValidationError(
                "retrieval.context_top_k는 retrieval.evaluation_max_k보다 "
                "클 수 없습니다. "
                f"현재 값: context_top_k={context_k}, evaluation_max_k={max_k}"
            )

        ks = config.get("evaluation", {}).get("ks", [1, 3, 5])
        if not ks:
            raise ConfigValidationError(
                "evaluation.ks는 최소 하나 이상의 K를 가져야 합니다."
            )
        normalized = [int(k) for k in ks]
        if any(k <= 0 for k in normalized):
            raise ConfigValidationError(
                "evaluation.ks의 모든 값은 1 이상이어야 합니다."
            )
        if len(set(normalized)) != len(normalized):
            raise ConfigValidationError("evaluation.ks에 중복 값이 있습니다.")
        if max(normalized) > max_k:
            raise ConfigValidationError(
                "evaluation.ks의 최댓값은 retrieval.evaluation_max_k보다 "
                "클 수 없습니다."
            )

    experiment_id = config.get("experiment_id")
    base_experiment_id = config.get("base_experiment_id")
    if experiment_id and base_experiment_id == experiment_id:
        raise ConfigValidationError(
            "base_experiment_id는 현재 experiment_id와 같을 수 없습니다."
        )

    # Preserve the legacy safety rule for relative configured paths, but only
    # for fields that actually exist in the current config shape.
    for parent, key in _PATH_FIELDS:
        section = config.get(parent)
        if not isinstance(section, dict):
            continue
        value = section.get(key)
        if value in (None, ""):
            continue
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            resolve_project_path(path, project_root=project_root)


def validate_config_dict(config: dict, schema: dict) -> None:
    """Validate JSON Schema plus cross-field constraints."""
    validate_schema(config, schema)
    validate_semantics(config)


def validate_input_files(
    config: dict,
    project_root: Path = PROJECT_ROOT,
) -> None:
    required_paths = {
        "dataset.document_path": config.get("dataset", {}).get("document_path"),
        "chunking.chunk_path": config.get("chunking", {}).get("chunk_path"),
        "evaluation.questions_path": config.get("evaluation", {}).get("questions_path"),
        "evaluation.document_qrels_path": config.get("evaluation", {}).get(
            "document_qrels_path"
        ),
        "evaluation.chunk_qrels_path": config.get("evaluation", {}).get(
            "chunk_qrels_path"
        ),
    }

    missing: list[str] = []
    for field_name, configured_path in required_paths.items():
        if not configured_path:
            missing.append(f"- {field_name}: <missing>")
            continue

        path = Path(str(configured_path)).expanduser()
        if path.is_absolute():
            resolved = path.resolve()
        else:
            resolved = (Path(project_root).resolve() / path).resolve()

        if not resolved.is_file():
            missing.append(f"- {field_name}: {configured_path}")

    if missing:
        raise ConfigValidationError(
            "다음 입력 파일이 존재하지 않습니다.\n" + "\n".join(missing)
        )


def validate_experiment_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    check_files: bool = False,
    project_root: Path = PROJECT_ROOT,
) -> dict:
    """Legacy-compatible config loader used by existing team tests/code."""
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = Path(project_root) / config_file

    schema_file = Path(schema_path)
    if not schema_file.is_absolute():
        schema_file = Path(project_root) / schema_file

    if not config_file.is_file():
        raise FileNotFoundError(f"Experiment YAML을 찾을 수 없습니다: {config_file}")
    if not schema_file.is_file():
        raise FileNotFoundError(f"Experiment Schema를 찾을 수 없습니다: {schema_file}")

    config = load_yaml(config_file)
    schema = load_json_schema(schema_file)
    validate_schema(config, schema)
    validate_semantics(config, project_root=project_root)
    if check_files:
        validate_input_files(config, project_root=project_root)
    return config


# ---------------------------------------------------------------------------
# v4 runtime API
# ---------------------------------------------------------------------------
def _resolve_runtime_paths(config: dict) -> dict:
    resolved = deepcopy(config)

    for parent, key in _PATH_FIELDS:
        section = resolved.get(parent)
        if (
            not isinstance(section, dict)
            or key not in section
            or section[key] in (None, "")
        ):
            continue
        section[key] = str(_resolve_project_path(section[key]))

    return resolved


def load_and_validate_config(
    config_path: str | Path,
    schema_path: str | Path = "schemas/experiment_v4.schema.json",
) -> dict:
    config_file = resolve_cli_path(config_path)
    schema_file = resolve_cli_path(schema_path)

    if not config_file.exists():
        raise FileNotFoundError(f"실험 YAML을 찾을 수 없습니다: {config_file}")
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema를 찾을 수 없습니다: {schema_file}")

    raw_config = load_yaml(config_file)
    schema = load_json_schema(schema_file)
    validate_config_dict(raw_config, schema)

    # v4 runtime requires prebuilt chunks, while the legacy team config/schema
    # remains backward compatible.  Keep this requirement local to v4.
    chunking = raw_config.get("chunking", {})
    missing_v4 = [
        name
        for name in ("chunk_path", "manifest_path")
        if not str(chunking.get(name, "")).strip()
    ]
    if missing_v4:
        raise ConfigValidationError(
            "v4 실행에는 기존 chunks.jsonl과 chunk manifest가 필요합니다: "
            + ", ".join(f"chunking.{name}" for name in missing_v4)
        )

    resolved = _resolve_runtime_paths(raw_config)
    resolved.setdefault("evaluation", {}).setdefault("ks", [1, 3, 5])
    resolved.setdefault("execution", {}).setdefault(
        "retrieval_error_policy", "partial"
    )
    resolved.setdefault("output", {}).setdefault(
        "root", str(_resolve_project_path("experiments"))
    )
    resolved["_runtime"] = {
        "config_path": str(config_file),
        "schema_path": str(schema_file),
    }
    return resolved


def inspect_input_readiness(config: dict) -> dict:
    """Check actual files required by the team-ready baseline runner."""
    paths = {
        "documents": config["dataset"]["document_path"],
        "chunks": config["chunking"]["chunk_path"],
        "questions": config["evaluation"]["questions_path"],
        "document_qrels": config["evaluation"]["document_qrels_path"],
        "chunk_qrels": config["evaluation"]["chunk_qrels_path"],
    }
    exists = {name: Path(path).is_file() for name, path in paths.items()}
    return {
        "files": exists,
        "input_files_ready": all(exists.values()),
    }
