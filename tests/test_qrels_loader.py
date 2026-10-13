import json

import pytest

from src.evaluation.qrels import load_chunk_qrels, load_document_qrels


def _write_jsonl(path, rows):
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
        encoding="utf-8",
    )


def test_row_based_document_qrels_support_multiple_gold_docs(tmp_path):
    path = tmp_path / "qrels.jsonl"
    _write_jsonl(
        path,
        [
            {"query_id": "q1", "document_id": "d1", "relevance": 1},
            {"query_id": "q1", "document_id": "d2", "relevance": 1},
        ],
    )
    assert load_document_qrels(str(path)) == {"q1": {"d1", "d2"}}


def test_row_based_chunk_qrels_support_multiple_gold_chunks(tmp_path):
    path = tmp_path / "qrels_chunk.jsonl"
    _write_jsonl(
        path,
        [
            {"query_id": "q1", "chunk_id": "c1", "relevance": 1},
            {"query_id": "q1", "chunk_id": "c2", "relevance": 1},
        ],
    )
    assert load_chunk_qrels(str(path)) == {"q1": {"c1", "c2"}}


def test_exact_duplicate_qrels_pair_is_rejected(tmp_path):
    path = tmp_path / "qrels_chunk.jsonl"
    _write_jsonl(
        path,
        [
            {"query_id": "q1", "chunk_id": "c1", "relevance": 1},
            {"query_id": "q1", "chunk_id": "c1", "relevance": 1},
        ],
    )
    with pytest.raises(ValueError, match="중복 qrels 조합"):
        load_chunk_qrels(str(path))
