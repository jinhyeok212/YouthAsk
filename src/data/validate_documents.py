from __future__ import annotations

from pathlib import Path

from src.common.io import load_json, read_jsonl, sha256_file, utc_now_iso, write_json


# 실제 프로젝트 Document 계약 기준 필수 필드.
# category는 Document top-level 필수 필드가 아니다.
# 분류 정보는 primary_category 또는 metadata 등에 존재할 수 있으므로 여기서 강제하지 않는다.
REQUIRED_FIELDS = ("document_id", "title", "source")


def _validate_existing_manifest(old: dict, current: dict) -> None:
    """기존 Dataset Manifest와 현재 documents.jsonl의 정합성을 가능한 범위에서 검증한다.

    팀에서 먼저 만든 dataset_manifest.json은 Runner 전용 Manifest와 스키마가 다를 수 있다.
    따라서 '존재하는 공통 필드'만 엄격 비교하고, 없는 필드는 억지로 요구하지 않는다.
    """

    # 문서 수 필드 이름 호환
    count_candidates = (
        "document_count",
        "documents_count",
        "record_count",
        "row_count",
    )
    for key in count_candidates:
        if key in old:
            try:
                old_count = int(old[key])
            except (TypeError, ValueError):
                raise ValueError(
                    f"Dataset Manifest의 {key} 값이 숫자가 아닙니다: {old[key]}"
                )
            if old_count != current["document_count"]:
                raise ValueError(
                    "Dataset Manifest 문서 수 불일치: "
                    f"field={key}, manifest={old_count}, actual={current['document_count']}"
                )
            break

    # SHA256 필드 이름 호환. Manifest에 파일 해시가 있을 때만 검증한다.
    hash_candidates = (
        "sha256",
        "documents_sha256",
        "document_sha256",
        "file_sha256",
    )
    for key in hash_candidates:
        if key in old and old[key]:
            old_sha = str(old[key]).strip()
            if old_sha != current["sha256"]:
                raise ValueError(
                    "Dataset Manifest SHA256 불일치: "
                    f"field={key}, manifest={old_sha}, actual={current['sha256']}"
                )
            break

    # 버전 필드는 기존 Manifest에 동일한 키가 존재할 때만 비교한다.
    # 외부 Manifest의 버전 명명 규칙이 다를 수 있으므로 없는 키를 새로 요구하지 않는다.
    for key in ("dataset_version", "preprocessing_version"):
        if key in old and old[key] is not None:
            expected = current[key]
            actual = old[key]
            if str(actual) != str(expected):
                raise ValueError(
                    "Dataset Manifest 버전 불일치: "
                    f"field={key}, manifest={actual}, config={expected}"
                )


def validate_documents(config: dict) -> dict:
    """documents.jsonl을 검사하고 Dataset Manifest를 생성/호환 검증한다."""

    dataset = config["dataset"]
    chunking = config["chunking"]
    document_path = Path(dataset["document_path"])
    manifest_path = Path(dataset["manifest_path"])
    target_field = chunking["target_field"]

    if not document_path.exists():
        raise FileNotFoundError(f"documents.jsonl이 없습니다: {document_path}")

    rows = read_jsonl(document_path)
    if not rows:
        raise ValueError("documents.jsonl이 비어 있습니다.")

    seen: set[str] = set()

    for i, row in enumerate(rows, start=1):
        doc_id = str(row.get("document_id", "")).strip()

        if not doc_id:
            raise ValueError(f"빈 document_id가 있습니다: line={i}")

        if doc_id in seen:
            raise ValueError(f"중복 document_id가 존재합니다: {doc_id}")

        seen.add(doc_id)

        # 실제 공통 Document 계약의 필수 top-level 필드만 검사한다.
        for field in REQUIRED_FIELDS:
            if not str(row.get(field, "")).strip():
                raise ValueError(
                    f"필수 필드가 비었습니다: document_id={doc_id}, field={field}"
                )

        # Chunking 대상 필드는 YAML에서 결정한다. 현재는 retrieval_text.
        if not str(row.get(target_field, "")).strip():
            raise ValueError(
                "검색 대상 텍스트가 비었습니다: "
                f"document_id={doc_id}, field={target_field}"
            )

        # document row 자체에 dataset_version이 있을 때만 YAML과 비교한다.
        row_version = row.get("dataset_version")
        if row_version is not None and str(row_version) != str(dataset["version"]):
            raise ValueError(
                "Dataset Version 불일치: "
                f"document_id={doc_id}, row={row_version}, config={dataset['version']}"
            )

    actual_sha = sha256_file(document_path)

    manifest = {
        "dataset_version": dataset["version"],
        "preprocessing_version": dataset["preprocessing_version"],
        "document_path": str(document_path),
        "document_count": len(rows),
        "sha256": actual_sha,
        "created_at_utc": utc_now_iso(),
    }

    if manifest_path.exists():
        # 기존 팀 산출물 Manifest는 그대로 보존하고 호환 가능한 필드만 검증한다.
        old = load_json(manifest_path)
        _validate_existing_manifest(old, manifest)
    else:
        # Manifest가 없을 때만 Runner 형식으로 새로 생성한다.
        write_json(manifest_path, manifest)

    return {
        "document_path": str(document_path),
        "manifest_path": str(manifest_path),
        "document_count": len(rows),
        "sha256": actual_sha,
    }
