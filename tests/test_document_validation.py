import json
import importlib.util

import pytest

from src.data.build_dataset_manifest import build_dataset_manifest
from src.data.validate_documents import validate_documents


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def valid_doc(document_id="doc_1"):
    return {
        "document_id": document_id,
        "title": "Policy title",
        "source": "ontong_youth",
        "url": "",
        "content": "Policy title\n\nSupport content",
        "retrieval_text": "Policy title\n\nSupport content",
        "metadata": {"primary_category": "employment", "normalization_status": "OK"},
        "raw_record": {},
    }


def base_config(tmp_path):
    return {
        "project_root": str(tmp_path),
        "dataset": {
            "version": "ontong_youth_full_v1",
            "preprocessing_version": "prep_v1",
            "document_path": "data/processed/ontong_youth_full_v1/documents.jsonl",
            "manifest_path": "data/processed/ontong_youth_full_v1/dataset_manifest.json",
            "quality_report_path": "data/processed/ontong_youth_full_v1/data_quality_report.csv",
        },
    }


def prepare_documents(tmp_path, rows):
    data_dir = tmp_path / "data" / "processed" / "ontong_youth_full_v1"
    data_dir.mkdir(parents=True)
    documents_path = data_dir / "documents.jsonl"
    write_jsonl(documents_path, rows)
    return documents_path


def test_validate_documents_config_returns_dataset_info(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "processed" / "ontong_youth_full_v1"
    data_dir.mkdir(parents=True)
    documents_path = data_dir / "documents.jsonl"
    write_jsonl(documents_path, [valid_doc()])

    config = base_config(tmp_path)
    build_dataset_manifest(config)

    info = validate_documents(config)

    assert info["document_path"] == "data/processed/ontong_youth_full_v1/documents.jsonl"
    assert info["manifest_path"] == "data/processed/ontong_youth_full_v1/dataset_manifest.json"
    assert info["document_count"] == 1
    assert len(info["sha256"]) == 64
    assert info["preprocessing_version"] == "prep_v1"


def test_validate_documents_config_rejects_duplicate_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "processed" / "ontong_youth_full_v1"
    data_dir.mkdir(parents=True)
    documents_path = data_dir / "documents.jsonl"
    write_jsonl(documents_path, [valid_doc("doc_1"), valid_doc("doc_1")])

    config = base_config(tmp_path)
    build_dataset_manifest(config)

    with pytest.raises(ValueError, match="duplicate document_id"):
        validate_documents(config)


def test_validate_documents_config_rejects_broken_json_with_line_number(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "processed" / "ontong_youth_full_v1"
    data_dir.mkdir(parents=True)
    documents_path = data_dir / "documents.jsonl"
    documents_path.write_text(json.dumps(valid_doc(), ensure_ascii=False) + "\n{broken\n", encoding="utf-8")
    config = base_config(tmp_path)

    with pytest.raises(ValueError, match="line 2|:2"):
        build_dataset_manifest(config)


def test_validate_documents_config_rejects_non_object_jsonl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "processed" / "ontong_youth_full_v1"
    data_dir.mkdir(parents=True)
    documents_path = data_dir / "documents.jsonl"
    documents_path.write_text(json.dumps(valid_doc(), ensure_ascii=False) + "\n[]\n", encoding="utf-8")
    config = base_config(tmp_path)

    with pytest.raises(ValueError, match="expected JSON object"):
        build_dataset_manifest(config)


def test_validate_documents_config_rejects_missing_required_field(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    doc = valid_doc()
    del doc["retrieval_text"]
    prepare_documents(tmp_path, [doc])
    config = base_config(tmp_path)
    build_dataset_manifest(config)

    with pytest.raises(ValueError, match="missing required fields"):
        validate_documents(config)


def test_validate_documents_config_rejects_blank_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prepare_documents(
        tmp_path,
        [
            {
                **valid_doc(),
                "document_id": " ",
                "title": " ",
                "retrieval_text": " ",
                "metadata": {"primary_category": " "},
            }
        ],
    )
    config = base_config(tmp_path)
    build_dataset_manifest(config)

    with pytest.raises(ValueError, match="blank document_id"):
        validate_documents(config)


def test_validate_documents_config_rejects_version_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prepare_documents(tmp_path, [valid_doc()])
    config = base_config(tmp_path)
    build_dataset_manifest(config)
    config["dataset"]["version"] = "other_version"

    with pytest.raises(ValueError, match="dataset_version mismatch"):
        validate_documents(config)


def test_validate_documents_config_rejects_manifest_count_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prepare_documents(tmp_path, [valid_doc()])
    config = base_config(tmp_path)
    build_dataset_manifest(config)
    manifest_path = tmp_path / "data" / "processed" / "ontong_youth_full_v1" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["document_count"] = 999
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="document_count mismatch"):
        validate_documents(config)


def test_validate_documents_config_rejects_manifest_hash_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    documents_path = prepare_documents(tmp_path, [valid_doc()])
    config = base_config(tmp_path)
    build_dataset_manifest(config)
    with documents_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(valid_doc("doc_2"), ensure_ascii=False) + "\n")

    with pytest.raises(ValueError, match="document_count mismatch|SHA256"):
        validate_documents(config)


def test_validate_documents_result_matches_contract_if_available(tmp_path, monkeypatch):
    try:
        contract_spec = importlib.util.find_spec("src.experiments.contracts")
    except ModuleNotFoundError:
        contract_spec = None
    if contract_spec is None:
        pytest.skip("PM contract module is not present yet")
    from src.experiments.contracts import validate_stage_result

    monkeypatch.chdir(tmp_path)
    prepare_documents(tmp_path, [valid_doc()])
    config = base_config(tmp_path)
    build_dataset_manifest(config)
    validate_stage_result("validate_documents", validate_documents(config))
