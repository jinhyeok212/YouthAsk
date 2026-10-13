from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any


REQUIRED_DOCUMENT_FIELDS = [
    "document_id",
    "title",
    "source",
    "retrieval_text",
    "metadata",
    "raw_record",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: expected JSON object")
            rows.append(row)
    return rows


def read_jsonl_with_line_numbers(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: expected JSON object")
            rows.append((line_no, row))
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_project_path(path_value: str | Path, root: Path | None = None) -> Path:
    root = root or project_root()
    path = Path(path_value)
    if not path.is_absolute():
        path = root / path
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Path is outside the project root: {path_value}") from exc
    return resolved_path


def percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def _has_category(doc: dict[str, Any]) -> bool:
    if str(doc.get("category", "")).strip():
        return True
    metadata = doc.get("metadata") or {}
    return bool(str(metadata.get("primary_category", "")).strip())


def validate_document_records(
    documents: list[dict[str, Any]],
    line_numbers: list[int] | None = None,
) -> dict[str, Any]:
    line_numbers = line_numbers or list(range(1, len(documents) + 1))
    ids = [str(doc.get("document_id", "")).strip() for doc in documents]
    missing_required_field_count = 0
    missing_required_field_examples: list[dict[str, str]] = []
    duplicate_examples: list[dict[str, str]] = []
    first_seen_id_line: dict[str, int] = {}
    duplicate_ids: set[str] = set()
    blank_title_examples: list[dict[str, str]] = []
    blank_retrieval_text_examples: list[dict[str, str]] = []
    blank_document_id_examples: list[dict[str, str]] = []
    blank_category_examples: list[dict[str, str]] = []

    for index, doc in enumerate(documents):
        line_no = line_numbers[index]
        missing = [field for field in REQUIRED_DOCUMENT_FIELDS if field not in doc]
        if not _has_category(doc):
            missing.append("category")
        if missing:
            missing_required_field_count += len(missing)
            if len(missing_required_field_examples) < 20:
                missing_required_field_examples.append(
                    {
                        "line": str(line_no),
                        "document_id": str(doc.get("document_id", "")),
                        "missing_fields": ",".join(missing),
                    }
                )
        document_id = str(doc.get("document_id", "")).strip()
        if document_id:
            if document_id in first_seen_id_line:
                duplicate_ids.add(document_id)
                if len(duplicate_examples) < 20:
                    duplicate_examples.append(
                        {
                            "document_id": document_id,
                            "first_line": str(first_seen_id_line[document_id]),
                            "duplicate_line": str(line_no),
                        }
                    )
            else:
                first_seen_id_line[document_id] = line_no
        elif len(blank_document_id_examples) < 20:
            blank_document_id_examples.append({"line": str(line_no)})

        if not str(doc.get("title", "")).strip() and len(blank_title_examples) < 20:
            blank_title_examples.append({"line": str(line_no), "document_id": document_id})
        if not str(doc.get("retrieval_text", "")).strip() and len(blank_retrieval_text_examples) < 20:
            blank_retrieval_text_examples.append({"line": str(line_no), "document_id": document_id})
        if not _has_category(doc) and len(blank_category_examples) < 20:
            blank_category_examples.append({"line": str(line_no), "document_id": document_id})

    lengths = [len(str(doc.get("retrieval_text", ""))) for doc in documents]
    categories = Counter(
        str((doc.get("metadata") or {}).get("primary_category", "") or "UNKNOWN") for doc in documents
    )
    statuses = Counter(
        str((doc.get("metadata") or {}).get("normalization_status", "") or "UNKNOWN") for doc in documents
    )

    return {
        "document_count": len(documents),
        "duplicate_document_id_count": len(duplicate_ids),
        "duplicate_document_ids": sorted(duplicate_ids)[:100],
        "duplicate_document_id_examples": duplicate_examples,
        "blank_document_id_count": sum(1 for value in ids if not value),
        "blank_document_id_examples": blank_document_id_examples,
        "blank_title_count": sum(1 for doc in documents if not str(doc.get("title", "")).strip()),
        "blank_title_examples": blank_title_examples,
        "blank_retrieval_text_count": sum(
            1 for doc in documents if not str(doc.get("retrieval_text", "")).strip()
        ),
        "blank_retrieval_text_examples": blank_retrieval_text_examples,
        "blank_category_count": sum(1 for doc in documents if not _has_category(doc)),
        "blank_category_examples": blank_category_examples,
        "missing_required_field_count": missing_required_field_count,
        "missing_required_field_examples": missing_required_field_examples,
        "retrieval_text_min_length": min(lengths) if lengths else 0,
        "retrieval_text_avg_length": round(mean(lengths), 3) if lengths else 0,
        "retrieval_text_median_length": median(lengths) if lengths else 0,
        "retrieval_text_p95_length": percentile(lengths, 0.95),
        "retrieval_text_max_length": max(lengths) if lengths else 0,
        "primary_category_counts": dict(categories.most_common()),
        "normalization_status_counts": dict(statuses.most_common()),
    }


def _summarize_blocking_errors(report: dict[str, Any]) -> list[str]:
    checks = [
        ("duplicate_document_id_count", "duplicate document_id"),
        ("blank_document_id_count", "blank document_id"),
        ("blank_title_count", "blank title"),
        ("blank_retrieval_text_count", "blank retrieval_text"),
        ("blank_category_count", "blank category"),
        ("missing_required_field_count", "missing required fields"),
    ]
    errors = []
    for key, label in checks:
        value = int(report.get(key, 0) or 0)
        if value:
            errors.append(f"{label}: {value}")
    return errors


def _dataset_config(config: dict[str, Any]) -> dict[str, Any]:
    dataset = config.get("dataset", config)
    if not isinstance(dataset, dict):
        raise ValueError("config.dataset must be a mapping")
    return dataset


def _config_root(config: dict[str, Any]) -> Path:
    root_value = config.get("project_root") or _dataset_config(config).get("project_root")
    if root_value:
        return Path(root_value).resolve()
    return project_root()


def validate_dataset_files(config: dict[str, Any]) -> dict[str, Any]:
    dataset = _dataset_config(config)
    document_path_value = dataset.get("document_path")
    if not document_path_value:
        raise ValueError("dataset.document_path is required")

    root = _config_root(config)
    document_path = resolve_project_path(document_path_value, root)
    manifest_path = resolve_project_path(
        dataset.get("manifest_path") or document_path.parent / "dataset_manifest.json",
        root,
    )
    quality_report_path = resolve_project_path(
        dataset.get("quality_report_path") or document_path.parent / "data_quality_report.csv",
        root,
    )

    if not document_path.exists():
        raise FileNotFoundError(f"documents.jsonl not found: {document_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"dataset_manifest.json not found: {manifest_path}")

    rows_with_lines = read_jsonl_with_line_numbers(document_path)
    documents = [row for _, row in rows_with_lines]
    line_numbers = [line_no for line_no, _ in rows_with_lines]
    report = validate_document_records(documents, line_numbers)
    blocking_errors = _summarize_blocking_errors(report)
    if blocking_errors:
        detail_parts = []
        for key in [
            "duplicate_document_id_examples",
            "blank_document_id_examples",
            "blank_title_examples",
            "blank_retrieval_text_examples",
            "blank_category_examples",
            "missing_required_field_examples",
        ]:
            if report.get(key):
                detail_parts.append(f"{key}={json.dumps(report[key][:5], ensure_ascii=False)}")
        detail = "\n".join(detail_parts)
        raise ValueError("Document validation failed: " + "; ".join(blocking_errors) + ("\n" + detail if detail else ""))

    sha256 = sha256_file(document_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_version = str(dataset.get("version", "")).strip()
    manifest_version = str(manifest.get("dataset_version") or manifest.get("version") or "").strip()
    if expected_version and manifest_version and expected_version != manifest_version:
        raise ValueError(
            f"Manifest dataset_version mismatch: config={expected_version}, manifest={manifest_version}"
        )

    expected_preprocessing_version = str(dataset.get("preprocessing_version", "")).strip()
    manifest_preprocessing_version = str(manifest.get("preprocessing_version", "")).strip()
    if (
        expected_preprocessing_version
        and manifest_preprocessing_version
        and expected_preprocessing_version != manifest_preprocessing_version
    ):
        raise ValueError(
            "Manifest preprocessing_version mismatch: "
            f"config={expected_preprocessing_version}, manifest={manifest_preprocessing_version}"
        )

    manifest_count = int(manifest.get("document_count", -1))
    if manifest_count != len(documents):
        raise ValueError(
            f"Manifest document_count mismatch: manifest={manifest_count}, actual={len(documents)}"
        )

    manifest_sha = (
        manifest.get("sha256")
        or manifest.get("file_hashes_sha256", {}).get("documents_jsonl")
        or manifest.get("documents_sha256")
        or ""
    )
    if manifest_sha and manifest_sha != sha256:
        raise ValueError("Manifest documents_jsonl SHA256 does not match current documents.jsonl")

    return {
        "document_path": str(document_path.relative_to(root).as_posix()),
        "manifest_path": str(manifest_path.relative_to(root).as_posix()),
        "quality_report_path": str(quality_report_path.relative_to(root).as_posix()),
        "document_count": len(documents),
        "sha256": sha256,
        "dataset_version": manifest.get("dataset_version", ""),
        "preprocessing_version": manifest.get("preprocessing_version", ""),
    }


def validate_documents(input_value: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
    """Validate document records or validate dataset files from an experiment config.

    This dual entrypoint keeps the older record-level validation usable while also
    matching the experiment-runner contract:
    validate_documents(config) -> DatasetInfo.
    """
    if isinstance(input_value, list):
        return validate_document_records(input_value)
    if isinstance(input_value, dict):
        return validate_dataset_files(input_value)
    raise TypeError("validate_documents expects a list of records or a config dict")


def write_csv_report(path: Path, report: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    for key, value in report.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        rows.append({"metric": key, "value": value})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", required=True, type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-csv", type=Path)
    args = parser.parse_args()

    documents = read_jsonl(args.documents)
    report = validate_document_records(documents)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_csv:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        write_csv_report(args.output_csv, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
