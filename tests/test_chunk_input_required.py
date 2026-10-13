import json

import pytest

from src.chunking.build_chunks import build_chunks


def test_missing_prebuilt_chunks_fails_clearly(tmp_path):
    docs = tmp_path / "documents.jsonl"
    docs.write_text(
        json.dumps({"document_id": "d1", "retrieval_text": "text"}) + "\n",
        encoding="utf-8",
    )
    config = {
        "dataset": {"version": "d1", "preprocessing_version": "p1"},
        "chunking": {
            "version": "c1",
            "strategy": "section",
            "size": 800,
            "overlap": 120,
            "unit": "characters",
            "target_field": "retrieval_text",
            "chunk_path": str(tmp_path / "missing_chunks.jsonl"),
            "manifest_path": str(tmp_path / "chunk_manifest.json"),
        },
        "evaluation": {"chunk_qrels_path": str(tmp_path / "qrels_chunk.jsonl")},
    }
    dataset_info = {"document_path": str(docs), "sha256": "abc"}
    with pytest.raises(FileNotFoundError, match="청크를 자동 생성하지 않습니다"):
        build_chunks(config, dataset_info)
