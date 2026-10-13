import json

import pytest

from src.evaluation.validate_inputs import validate_evaluation_inputs


def _write_jsonl(path, rows):
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
        encoding="utf-8",
    )


def _base_config(questions, dq, cq):
    return {
        "chunking": {
            "version": "c2_section_800_v1",
        },
        "evaluation": {
            "questions_path": str(questions),
            "document_qrels_path": str(dq),
            "chunk_qrels_path": str(cq),
        },
    }


def test_missing_chunk_qrels_is_rejected_before_index(tmp_path):
    docs = tmp_path / "documents.jsonl"
    chunks = tmp_path / "chunks.jsonl"
    questions = tmp_path / "questions.jsonl"
    dq = tmp_path / "qrels.jsonl"
    cq = tmp_path / "qrels_chunk.jsonl"

    _write_jsonl(docs, [{"document_id": "p1"}])
    _write_jsonl(
        chunks,
        [
            {
                "chunk_id": "p1__overview__000",
                "document_id": "p1",
                "section": "overview",
            }
        ],
    )
    _write_jsonl(questions, [{"query_id": "q1", "query": "질문"}])
    _write_jsonl(
        dq,
        [{"query_id": "q1", "document_id": "p1", "relevance": 1}],
    )
    _write_jsonl(
        cq,
        [
            {
                "query_id": "q2",
                "document_id": "p1",
                "chunk_id": "p1__overview__000",
                "relevance": 1,
                "matched_section": "overview",
                "chunking_version": "c2_section_800_v1",
            }
        ],
    )

    with pytest.raises(ValueError, match="질문/chunk qrels 불일치"):
        validate_evaluation_inputs(
            _base_config(questions, dq, cq),
            {"document_path": str(docs)},
            {"chunk_path": str(chunks)},
        )


def test_multiple_gold_chunks_for_same_query_are_allowed(tmp_path):
    docs = tmp_path / "documents.jsonl"
    chunks = tmp_path / "chunks.jsonl"
    questions = tmp_path / "questions.jsonl"
    dq = tmp_path / "qrels.jsonl"
    cq = tmp_path / "qrels_chunk.jsonl"

    _write_jsonl(docs, [{"document_id": "p1"}])
    _write_jsonl(
        chunks,
        [
            {
                "chunk_id": "p1__eligibility__000",
                "document_id": "p1",
                "section": "eligibility",
            },
            {
                "chunk_id": "p1__eligibility__001",
                "document_id": "p1",
                "section": "eligibility",
            },
        ],
    )
    _write_jsonl(questions, [{"query_id": "q1", "query": "질문"}])
    _write_jsonl(
        dq,
        [{"query_id": "q1", "document_id": "p1", "relevance": 1}],
    )
    _write_jsonl(
        cq,
        [
            {
                "query_id": "q1",
                "document_id": "p1",
                "chunk_id": "p1__eligibility__000",
                "relevance": 1,
                "matched_section": "eligibility",
                "chunking_version": "c2_section_800_v1",
            },
            {
                "query_id": "q1",
                "document_id": "p1",
                "chunk_id": "p1__eligibility__001",
                "relevance": 1,
                "matched_section": "eligibility",
                "chunking_version": "c2_section_800_v1",
            },
        ],
    )

    result = validate_evaluation_inputs(
        _base_config(questions, dq, cq),
        {"document_path": str(docs)},
        {"chunk_path": str(chunks)},
    )

    assert result["status"] == "VALID"
    assert result["question_count"] == 1
    assert result["chunk_qrels_query_count"] == 1
    assert result["chunk_qrels_row_count"] == 2
