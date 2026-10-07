"""Run read-only Chroma retrieval for every configured evaluation question.

The experiment runner calls :func:`run_batch_retrieval`.  Model loading and
collection access are kept behind small factory functions so the batch logic
can be unit-tested without KURE-v1, a GPU, or a real Chroma database.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.rag.retriever import (
    KUREQueryEmbedder,
    RetrievalConfig,
    Retriever,
    load_read_only_collection,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class EvaluationQuestion:
    """The fields from an evaluation row that retrieval consumes."""

    query_id: str
    query: str


def _project_path(raw_path: Any, field_name: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"{field_name} must be a non-empty project-relative path")

    configured = Path(raw_path)
    if configured.is_absolute():
        raise ValueError(f"{field_name} must be project-relative: {raw_path}")

    resolved = (PROJECT_ROOT / configured).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{field_name} points outside the project: {raw_path}") from exc
    return resolved


def load_evaluation_questions(path: Path) -> list[EvaluationQuestion]:
    """Load and validate all questions while preserving JSONL order."""

    if not path.is_file():
        raise FileNotFoundError(f"Evaluation questions file not found: {path}")

    questions: list[EvaluationQuestion] = []
    seen_query_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in evaluation questions at line {line_number}: {exc.msg}"
                ) from exc

            if not isinstance(row, Mapping):
                raise ValueError(
                    f"Evaluation question at line {line_number} must be a JSON object"
                )

            query_id = row.get("query_id")
            query = row.get("query")
            if not isinstance(query_id, str) or not query_id.strip():
                raise ValueError(
                    f"query_id must be a non-empty string at line {line_number}"
                )
            if not isinstance(query, str) or not query.strip():
                raise ValueError(
                    f"query must be a non-empty string for query_id={query_id!r}"
                )

            query_id = query_id.strip()
            query = query.strip()
            if query_id in seen_query_ids:
                raise ValueError(f"Duplicate query_id in evaluation questions: {query_id}")
            seen_query_ids.add(query_id)
            questions.append(EvaluationQuestion(query_id=query_id, query=query))

    if not questions:
        raise ValueError(f"Evaluation questions file is empty: {path}")
    return questions


def _resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested

    try:
        import torch
    except ImportError:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def create_query_embedder(embedding_config: Mapping[str, Any]) -> KUREQueryEmbedder:
    """Create the query-only embedder from the shared experiment config."""

    return KUREQueryEmbedder(
        model_name=str(embedding_config["model"]),
        device=_resolve_device(str(embedding_config["device"])),
        expected_dimension=int(embedding_config["dimension"]),
    )


def open_existing_collection(index_info: Mapping[str, Any]) -> tuple[Any, Any]:
    """Open an existing collection; this function never creates an index."""

    db_path = _project_path(index_info.get("db_path"), "index_info.db_path")
    collection_name = index_info.get("collection_name")
    if not isinstance(collection_name, str) or not collection_name.strip():
        raise ValueError("index_info.collection_name must be a non-empty string")
    return load_read_only_collection(db_path, collection_name)


def _require_mapping(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"config.{key} must be an object")
    return value


def _validate_result(result: Any, top_k: int, query_id: str) -> dict[str, Any]:
    """Guard the stage invariants before handing results to the runner."""

    if not isinstance(result, Mapping):
        raise TypeError(f"Retriever result must be a mapping for query_id={query_id}")
    normalized = dict(result)
    if normalized.get("query_id") != query_id:
        raise ValueError(f"Retriever returned the wrong query_id for {query_id}")

    chunks = normalized.get("results")
    if not isinstance(chunks, list):
        raise TypeError(f"Retriever results must be a list for query_id={query_id}")
    if len(chunks) > top_k:
        raise ValueError(
            f"Retriever returned more than evaluation_max_k results for query_id={query_id}"
        )

    for expected_rank, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, Mapping):
            raise TypeError(
                f"Retrieved item at rank {expected_rank} must be a mapping "
                f"for query_id={query_id}"
            )
        if chunk.get("rank") != expected_rank:
            raise ValueError(
                f"Ranks must start at 1 and be consecutive for query_id={query_id}"
            )
        for field_name in ("chunk_id", "document_id"):
            value = chunk.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Retrieved {field_name} is missing at rank {expected_rank} "
                    f"for query_id={query_id}"
                )
    return normalized


def _iter_retrieval_results(
    questions: list[EvaluationQuestion],
    retriever: Retriever,
    top_k: int,
) -> Iterator[dict[str, Any]]:
    for question in questions:
        try:
            raw_result = retriever.retrieve(
                query_id=question.query_id,
                query=question.query,
                top_k=top_k,
            )
            yield _validate_result(raw_result, top_k, question.query_id)
        except Exception as exc:
            raise RuntimeError(
                f"Retrieval failed for query_id={question.query_id}: {exc}"
            ) from exc


def run_batch_retrieval(
    config: dict,
    index_info: dict,
) -> list[dict[str, Any]]:
    """Retrieve Top-k chunks for every evaluation question in input order.

    A failure for any question raises an exception containing its ``query_id``.
    This matches the shared ``runtime.fail_fast: true`` policy and prevents an
    incomplete evaluation set from being reported as a successful experiment.
    """

    if not isinstance(config, Mapping):
        raise TypeError("config must be a mapping")
    if not isinstance(index_info, Mapping):
        raise TypeError("index_info must be a mapping")

    evaluation = _require_mapping(config, "evaluation")
    retrieval = _require_mapping(config, "retrieval")
    embedding = _require_mapping(config, "embedding")
    index_config = _require_mapping(config, "index")

    top_k = retrieval.get("evaluation_max_k")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("config.retrieval.evaluation_max_k must be a positive integer")

    index_version = index_info.get("index_version")
    if not isinstance(index_version, str) or not index_version.strip():
        raise ValueError("index_info.index_version must be a non-empty string")

    distance_metric = index_config.get("distance_metric")
    if distance_metric != "cosine":
        raise ValueError(
            "Batch retrieval currently derives similarity from cosine distance only"
        )

    question_path = _project_path(
        evaluation.get("questions_path"), "evaluation.questions_path"
    )
    questions = load_evaluation_questions(question_path)
    embedder = create_query_embedder(embedding)
    client, collection = open_existing_collection(index_info)
    try:
        retriever = Retriever(
            embedder=embedder,
            collection=collection,
            config=RetrievalConfig(
                embedding_model=str(embedding["model"]),
                index_version=index_version,
                distance_metric=distance_metric,
                evaluation_max_k=top_k,
            ),
        )
        results = list(_iter_retrieval_results(questions, retriever, top_k))
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            with suppress(Exception):
                close()

    if len(results) != len(questions):
        raise RuntimeError(
            "Retrieval result count does not match the evaluation question count"
        )
    return results
