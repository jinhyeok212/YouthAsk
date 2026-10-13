from __future__ import annotations


class ContractError(ValueError):
    """Raised when a pipeline stage returns an invalid contract payload."""


def require_keys(name: str, payload: dict, keys: list[str]) -> None:
    missing = [k for k in keys if k not in payload]
    if missing:
        raise ContractError(f"{name} 반환값에 필수 필드가 없습니다: {missing}")


def validate_dataset_info(payload: dict) -> None:
    require_keys(
        "dataset_info",
        payload,
        ["document_path", "manifest_path", "document_count", "sha256"],
    )


def validate_chunk_info(payload: dict) -> None:
    require_keys(
        "chunk_info",
        payload,
        ["chunk_path", "manifest_path", "chunk_count", "chunk_qrels_path"],
    )


def validate_index_info(payload: dict) -> None:
    require_keys(
        "index_info",
        payload,
        [
            "index_version",
            "db_path",
            "collection_name",
            "reused",
            "manifest_path",
            "index_count",
        ],
    )


def validate_retrieval_results(rows: list[dict]) -> None:
    seen: set[str] = set()
    for row in rows:
        require_keys(
            "retrieval_result",
            row,
            ["query_id", "query", "retrieval_latency_ms", "results"],
        )
        qid = row["query_id"]
        if qid in seen:
            raise ContractError(f"중복 query_id 검색 결과: {qid}")
        seen.add(qid)

        for expected_rank, result in enumerate(row["results"], start=1):
            require_keys(
                "retrieval_result_item",
                result,
                ["rank", "chunk_id", "document_id", "distance", "similarity"],
            )
            if result["rank"] != expected_rank:
                raise ContractError(
                    f"검색 Rank 순서 오류: query_id={qid}, "
                    f"expected={expected_rank}, actual={result['rank']}"
                )
            if not str(result["chunk_id"]).strip() or not str(
                result["document_id"]
            ).strip():
                raise ContractError(
                    f"빈 검색 ID: query_id={qid}, rank={expected_rank}"
                )


def validate_stage_result(stage: str, value):
    """Backward-compatible dispatcher used by the team's existing tests/code."""
    normalized = stage.strip().lower()

    if normalized in {"validate_documents", "dataset", "dataset_info"}:
        validate_dataset_info(value)
    elif normalized in {"build_chunks", "validate_chunks", "chunk", "chunk_info"}:
        validate_chunk_info(value)
    elif normalized in {"resolve_index", "index", "index_info"}:
        validate_index_info(value)
    elif normalized in {
        "run_batch_retrieval",
        "batch_retrieval",
        "retrieval",
        "retrieval_results",
    }:
        validate_retrieval_results(value)
    else:
        raise ContractError(f"알 수 없는 stage contract: {stage}")

    return value
