import json

import pytest

from src.data.validate_documents import validate_documents


def _config(doc_path, manifest_path):
    return {
        "dataset": {
            "version": "v1",
            "preprocessing_version": "p1",
            "document_path": str(doc_path),
            "manifest_path": str(manifest_path),
        },
        "chunking": {"target_field": "retrieval_text"},
    }


def test_duplicate_document_id_is_rejected(tmp_path):
    doc_path = tmp_path / "documents.jsonl"
    manifest_path = tmp_path / "dataset_manifest.json"
    rows = [
        {"document_id": "p1", "title": "A", "retrieval_text": "text", "source": "ontong"},
        {"document_id": "p1", "title": "B", "retrieval_text": "text", "source": "ontong"},
    ]
    doc_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    with pytest.raises(ValueError, match="중복 document_id"):
        validate_documents(_config(doc_path, manifest_path))


def test_category_is_not_required(tmp_path):
    doc_path = tmp_path / "documents.jsonl"
    manifest_path = tmp_path / "dataset_manifest.json"
    rows = [
        {"document_id": "p1", "title": "A", "retrieval_text": "text", "source": "ontong"},
    ]
    doc_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    result = validate_documents(_config(doc_path, manifest_path))
    assert result["document_count"] == 1


def test_target_field_is_required(tmp_path):
    doc_path = tmp_path / "documents.jsonl"
    manifest_path = tmp_path / "dataset_manifest.json"
    rows = [
        {"document_id": "p1", "title": "A", "source": "ontong"},
    ]
    doc_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    with pytest.raises(ValueError, match="검색 대상 텍스트"):
        validate_documents(_config(doc_path, manifest_path))
