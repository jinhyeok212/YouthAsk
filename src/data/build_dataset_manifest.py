from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data.validate_documents import (
    project_root,
    read_jsonl,
    resolve_project_path,
    sha256_file,
    validate_document_records,
)


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


def build_dataset_manifest(config: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
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

    documents = read_jsonl(document_path)
    quality = validate_document_records(documents)
    document_sha = sha256_file(document_path)
    quality_sha = sha256_file(quality_report_path) if quality_report_path.exists() else ""
    dataset_version = dataset.get("version", "ontong_youth_full_v1")
    preprocessing_version = dataset.get("preprocessing_version", "prep_v1")
    relative_document_path = str(document_path.relative_to(root).as_posix())
    relative_manifest_path = str(manifest_path.relative_to(root).as_posix())
    relative_quality_report_path = str(quality_report_path.relative_to(root).as_posix())

    manifest = {
        "dataset_name": dataset.get("name", "Ontong Youth Full RAG Documents"),
        "dataset_version": dataset_version,
        "preprocessing_version": preprocessing_version,
        "schema_name": dataset.get("schema_name", "ontong_youth_rag_document_v1"),
        "source": dataset.get("source", "ontong_youth"),
        "document_path": relative_document_path,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(documents),
        "sha256": document_sha,
        "quality": quality,
        "output_files": {
            "documents_jsonl": relative_document_path,
            "dataset_manifest_json": relative_manifest_path,
            "data_quality_report_csv": relative_quality_report_path,
        },
        "file_hashes_sha256": {
            "documents_jsonl": document_sha,
            "data_quality_report_csv": quality_sha,
        },
    }

    if write:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--quality-report", type=Path)
    parser.add_argument("--dataset-version", default="ontong_youth_full_v1")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    config = {
        "dataset": {
            "version": args.dataset_version,
            "document_path": str(args.documents),
            "manifest_path": str(args.manifest or args.documents.parent / "dataset_manifest.json"),
            "quality_report_path": str(args.quality_report or args.documents.parent / "data_quality_report.csv"),
        }
    }
    manifest = build_dataset_manifest(config, write=not args.no_write)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
