"""Unit tests for the experiment batch retrieval adapter."""

from __future__ import annotations

import json

import pytest

from src.retrieval import batch_retriever
from src.retrieval.trace_writer import write_retrieval_traces


class FakeClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeCollection:
    def __init__(self):
        self.queries = []

    def count(self):
        return 2

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {
            "ids": [["chunk-1", "chunk-2"]],
            "documents": [["first", "second"]],
            "metadatas": [[
                {"document_id": "doc-1"},
                {"document_id": "doc-2"},
            ]],
            "distances": [[0.1, 0.25]],
        }


class FakeEmbedder:
    def embed_query(self, query):
        return [0.1, 0.2, 0.3]


def _config(questions_path):
    return {
        "evaluation": {"questions_path": questions_path},
        "retrieval": {"evaluation_max_k": 5},
        "embedding": {
            "model": "nlpai-lab/KURE-v1",
            "dimension": 1024,
            "device": "cpu",
        },
        "index": {"distance_metric": "cosine"},
    }


def _index_info():
    return {
        "index_version": "index_full_kure_v1",
        "db_path": "indexes/chroma/index_full_kure_v1",
        "collection_name": "ontong_youth_full_kure_v1",
    }


def _write_questions(tmp_path, rows):
    path = tmp_path / "questions.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def test_run_batch_retrieval_returns_every_question_in_order(tmp_path, monkeypatch):
    questions_path = _write_questions(
        tmp_path,
        [
            {"query_id": "q001", "query": "첫 질문"},
            {"query_id": "q002", "query": "둘째 질문"},
        ],
    )
    client = FakeClient()
    collection = FakeCollection()
    monkeypatch.setattr(batch_retriever, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        batch_retriever, "create_query_embedder", lambda _: FakeEmbedder()
    )
    monkeypatch.setattr(
        batch_retriever,
        "open_existing_collection",
        lambda _: (client, collection),
    )

    results = batch_retriever.run_batch_retrieval(
        _config("questions.jsonl"), _index_info()
    )

    assert [row["query_id"] for row in results] == ["q001", "q002"]
    assert all(len(row["results"]) == 2 for row in results)
    assert results[0]["results"][0] == {
        "rank": 1,
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "distance": 0.1,
        "similarity": 0.9,
        "text": "first",
        "metadata": {"document_id": "doc-1"},
    }
    assert len(collection.queries) == 2
    assert all(call["n_results"] == 2 for call in collection.queries)
    assert client.closed is True


@pytest.mark.parametrize(
    "rows, message",
    [
        (
            [
                {"query_id": "q001", "query": "one"},
                {"query_id": "q001", "query": "two"},
            ],
            "Duplicate query_id",
        ),
        ([{"query_id": "q001", "query": "   "}], "query must be"),
    ],
)
def test_load_evaluation_questions_rejects_invalid_rows(tmp_path, rows, message):
    path = _write_questions(tmp_path, rows)
    with pytest.raises(ValueError, match=message):
        batch_retriever.load_evaluation_questions(path)


def test_query_failure_identifies_query_and_closes_client(tmp_path, monkeypatch):
    _write_questions(tmp_path, [{"query_id": "q-bad", "query": "question"}])
    client = FakeClient()
    collection = FakeCollection()
    collection.query = lambda **_: (_ for _ in ()).throw(RuntimeError("db unavailable"))
    monkeypatch.setattr(batch_retriever, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        batch_retriever, "create_query_embedder", lambda _: FakeEmbedder()
    )
    monkeypatch.setattr(
        batch_retriever,
        "open_existing_collection",
        lambda _: (client, collection),
    )

    with pytest.raises(RuntimeError, match="query_id=q-bad"):
        batch_retriever.run_batch_retrieval(
            _config("questions.jsonl"), _index_info()
        )
    assert client.closed is True


def test_trace_writer_protects_existing_output(tmp_path):
    output = tmp_path / "traces.jsonl"
    assert write_retrieval_traces([{"query_id": "q001"}], output) == 1
    with pytest.raises(FileExistsError):
        write_retrieval_traces([{"query_id": "q002"}], output)
