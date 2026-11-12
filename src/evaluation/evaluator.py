"""검색 결과와 정답표를 읽고 Document·Chunk 검색 성능을 평가한다.

이 파일은 검색 결과와 Document 또는 Chunk 단위 qrels를 연결해 질문별 결과와
전체 요약을 만든다. 실제 평가지표 계산은 ``retrieval_metrics.py``에 구현한다.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from src.evaluation.retrieval_metrics import (
    calculate_context_metrics,
    calculate_hit_at_k,
    calculate_mean_hit_at_k,
    calculate_mrr,
    calculate_reciprocal_rank,
    find_first_relevant_rank,
)


JsonObject = dict[str, Any]
DocumentQrels = dict[str, set[str]]
ChunkQrels = dict[str, set[str]]


def _read_jsonl(path: str | Path) -> list[JsonObject]:
    """JSONL 파일을 읽고 JSON 형식이 잘못된 줄을 알려준다."""
    input_path = Path(path)
    rows: list[JsonObject] = []

    with input_path.open("r", encoding="utf-8-sig") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{input_path}의 {line_number}번째 줄은 올바른 JSON이 아닙니다: "
                    f"{error}"
                ) from error

            if not isinstance(row, dict):
                raise ValueError(
                    f"{input_path}의 {line_number}번째 줄은 JSON 객체여야 합니다."
                )
            rows.append(row)

    return rows


def _require_non_empty_string(row: JsonObject, field: str, source: str) -> str:
    """필수 필드가 비어 있지 않은 문자열인지 확인한다."""
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}의 '{field}' 값은 비어 있지 않은 문자열이어야 합니다.")
    return value


def load_retrieval_results(path: str | Path) -> list[JsonObject]:
    """검색 결과를 읽고 query_id 누락과 중복을 확인한다."""
    rows = _read_jsonl(path)
    seen_query_ids: set[str] = set()

    for row_number, row in enumerate(rows, start=1):
        source = f"검색 결과 {row_number}번째 행"
        query_id = _require_non_empty_string(row, "query_id", source)

        if query_id in seen_query_ids:
            raise ValueError(f"검색 결과에 중복된 query_id가 있습니다: {query_id}")
        seen_query_ids.add(query_id)

        results = row.get("results")
        if not isinstance(results, list):
            raise ValueError(f"{source}의 'results' 값은 리스트여야 합니다.")

    return rows


def load_document_qrels(path: str | Path) -> DocumentQrels:
    """문서 qrels를 읽고 query_id별 정답 문서 집합으로 묶는다.

    하나의 질문에 정답 문서가 여러 개일 수 있으므로 set으로 보관한다.
    완전히 같은 qrels 행이 중복되면 set에서 자연스럽게 하나로 정리된다.
    """
    rows = _read_jsonl(path)
    grouped_qrels: defaultdict[str, set[str]] = defaultdict(set)

    for row_number, row in enumerate(rows, start=1):
        source = f"qrels {row_number}번째 행"
        query_id = _require_non_empty_string(row, "query_id", source)
        document_id = _require_non_empty_string(row, "document_id", source)
        grouped_qrels[query_id].add(document_id)

    return dict(grouped_qrels)


def load_chunk_qrels(path: str | Path) -> ChunkQrels:
    """Chunk qrels를 읽고 query_id별 정답 청크 집합으로 묶는다.

    하나의 질문에 정답 청크가 여러 개이면 모두 Gold로 보관한다.
    """
    rows = _read_jsonl(path)
    grouped_qrels: defaultdict[str, set[str]] = defaultdict(set)

    for row_number, row in enumerate(rows, start=1):
        source = f"Chunk qrels {row_number}번째 행"
        query_id = _require_non_empty_string(row, "query_id", source)
        chunk_id = _require_non_empty_string(row, "chunk_id", source)
        grouped_qrels[query_id].add(chunk_id)

    return dict(grouped_qrels)


def validate_query_alignment(
    retrieval_results: Iterable[JsonObject],
    qrels_by_query_id: dict[str, set[str]],
) -> None:
    """검색 결과와 qrels에 같은 query_id가 들어 있는지 확인한다."""
    retrieval_query_ids = {
        _require_non_empty_string(row, "query_id", "retrieval result")
        for row in retrieval_results
    }
    qrels_query_ids = set(qrels_by_query_id)

    missing_qrels = sorted(retrieval_query_ids - qrels_query_ids)
    missing_retrieval = sorted(qrels_query_ids - retrieval_query_ids)

    problems: list[str] = []
    if missing_qrels:
        problems.append(f"qrels가 없는 검색 질문: {missing_qrels}")
    if missing_retrieval:
        problems.append(f"검색 결과가 없는 qrels 질문: {missing_retrieval}")

    if problems:
        raise ValueError("query_id 연결에 실패했습니다. " + "; ".join(problems))


def load_and_validate_inputs(
    retrieval_results_path: str | Path,
    qrels_path: str | Path,
) -> tuple[list[JsonObject], DocumentQrels]:
    """검색 결과와 문서 정답표를 읽고 질문 ID가 일치하는지 확인한다."""
    # 검색 담당자가 만든 질문별 Top-5 검색 결과를 읽는다.
    retrieval_results = load_retrieval_results(retrieval_results_path)

    # 평가 질문별 정답 document_id가 담긴 qrels를 읽는다.
    document_qrels = load_document_qrels(qrels_path)

    # 두 파일에 들어 있는 query_id가 서로 빠짐없이 일치하는지 확인한다.
    validate_query_alignment(retrieval_results, document_qrels)

    # 검증이 끝난 검색 결과와 질문별 정답 문서 집합을 반환한다.
    return retrieval_results, document_qrels


def evaluate_document_queries(
    retrieval_results: list[JsonObject],
    document_qrels: DocumentQrels,
) -> list[JsonObject]:
    """모든 질문의 Document 검색 평가 결과를 만든다."""
    query_metrics: list[JsonObject] = []

    for retrieval_row in retrieval_results:
        query_id = retrieval_row["query_id"]
        gold_document_ids = document_qrels[query_id]

        # Top-5 검색 결과에서 document_id를 순위 순서대로 가져온다.
        retrieved_document_ids = [
            result["document_id"]
            for result in retrieval_row["results"]
        ]

        # 검색된 정답 문서 중 가장 먼저 등장한 순위를 계산한다.
        first_relevant_rank = find_first_relevant_rank(
            retrieved_document_ids,
            gold_document_ids,
        )

        # Top-5 안에서 실제로 검색된 정답 document_id를 찾는다.
        matched_gold_document_ids = list(
            dict.fromkeys(
                document_id
                for document_id in retrieved_document_ids
                if document_id in gold_document_ids
            )
        )

        # 질문 하나의 Document 평가 결과를 만든다.
        query_metrics.append(
            {
                "query_id": query_id,
                "gold_document_ids": sorted(gold_document_ids),
                **calculate_context_metrics(retrieved_document_ids, gold_document_ids),
                "matched_gold_document_ids": matched_gold_document_ids,
                "first_relevant_rank": first_relevant_rank,
                "hit_at_1": calculate_hit_at_k(first_relevant_rank, 1),
                "hit_at_3": calculate_hit_at_k(first_relevant_rank, 3),
                "hit_at_5": calculate_hit_at_k(first_relevant_rank, 5),
                "reciprocal_rank": calculate_reciprocal_rank(first_relevant_rank),
            }
        )

    return query_metrics


def summarize_document_metrics(
    query_metrics: list[JsonObject],
) -> JsonObject:
    """질문별 결과를 모아 전체 Document 평가 결과를 만든다."""
    if not query_metrics:
        raise ValueError("전체 평가 결과를 계산할 질문별 결과가 없습니다.")

    # 질문별 Hit@1·3·5와 RR을 각각 모은다.
    hit_at_1_values = [result["hit_at_1"] for result in query_metrics]
    hit_at_3_values = [result["hit_at_3"] for result in query_metrics]
    hit_at_5_values = [result["hit_at_5"] for result in query_metrics]
    reciprocal_ranks = [result["reciprocal_rank"] for result in query_metrics]

    # 질문별 값을 평균 내 전체 Hit@1·3·5와 MRR을 계산한다.
    document_hit_at_1 = calculate_mean_hit_at_k(hit_at_1_values)
    document_hit_at_3 = calculate_mean_hit_at_k(hit_at_3_values)
    document_hit_at_5 = calculate_mean_hit_at_k(hit_at_5_values)
    document_mrr = calculate_mrr(reciprocal_ranks)

    # 대시보드에서 함께 보여줄 Top-5 성공·실패 질문 수를 계산한다.
    top_5_success_count = sum(hit_at_5_values)
    top_5_failure_count = len(query_metrics) - top_5_success_count

    return {
        "question_count": len(query_metrics),
        "document_hit_at_1": document_hit_at_1,
        "document_hit_at_3": document_hit_at_3,
        "document_hit_at_5": document_hit_at_5,
        "document_mrr": document_mrr,
        "document_context_precision": sum(r["context_precision"] for r in query_metrics) / len(query_metrics),
        "document_context_recall": sum(r["context_recall"] for r in query_metrics) / len(query_metrics),
        "top_5_success_count": top_5_success_count,
        "top_5_failure_count": top_5_failure_count,
    }


def evaluate_chunk_queries(
    retrieval_results: list[JsonObject],
    chunk_qrels: ChunkQrels,
) -> list[JsonObject]:
    """모든 질문의 Chunk 검색 평가 결과를 만든다."""
    validate_query_alignment(retrieval_results, chunk_qrels)
    query_metrics: list[JsonObject] = []

    for retrieval_row in retrieval_results:
        query_id = retrieval_row["query_id"]
        gold_chunk_ids = chunk_qrels[query_id]

        # Top-5 검색 결과에서 chunk_id를 순위 순서대로 가져온다.
        retrieved_chunk_ids = [
            _require_non_empty_string(result, "chunk_id", f"{query_id} 검색 결과")
            for result in retrieval_row["results"]
        ]

        # 여러 Gold Chunk 중 가장 먼저 등장한 순위를 계산한다.
        first_relevant_rank = find_first_relevant_rank(
            retrieved_chunk_ids,
            gold_chunk_ids,
        )

        # Top-5 안에서 실제로 검색된 Gold chunk_id를 찾는다.
        matched_gold_chunk_ids = list(
            dict.fromkeys(
                chunk_id
                for chunk_id in retrieved_chunk_ids
                if chunk_id in gold_chunk_ids
            )
        )

        # 질문 하나의 Chunk Hit@k와 RR을 계산한다.
        query_metrics.append(
            {
                "query_id": query_id,
                "gold_chunk_ids": sorted(gold_chunk_ids),
                **calculate_context_metrics(retrieved_chunk_ids, gold_chunk_ids),
                "matched_gold_chunk_ids": matched_gold_chunk_ids,
                "first_relevant_rank": first_relevant_rank,
                "hit_at_1": calculate_hit_at_k(first_relevant_rank, 1),
                "hit_at_3": calculate_hit_at_k(first_relevant_rank, 3),
                "hit_at_5": calculate_hit_at_k(first_relevant_rank, 5),
                "reciprocal_rank": calculate_reciprocal_rank(first_relevant_rank),
            }
        )

    return query_metrics


def summarize_chunk_metrics(query_metrics: list[JsonObject]) -> JsonObject:
    """질문별 결과를 모아 전체 Chunk 평가 결과를 만든다."""
    if not query_metrics:
        raise ValueError("전체 평가 결과를 계산할 질문별 결과가 없습니다.")

    # 질문별 Chunk Hit@1·3·5와 RR을 각각 모은다.
    hit_at_1_values = [result["hit_at_1"] for result in query_metrics]
    hit_at_3_values = [result["hit_at_3"] for result in query_metrics]
    hit_at_5_values = [result["hit_at_5"] for result in query_metrics]
    reciprocal_ranks = [result["reciprocal_rank"] for result in query_metrics]

    # 질문별 값을 평균 내 전체 Chunk Hit@1·3·5와 MRR을 계산한다.
    return {
        "question_count": len(query_metrics),
        "chunk_hit_at_1": calculate_mean_hit_at_k(hit_at_1_values),
        "chunk_hit_at_3": calculate_mean_hit_at_k(hit_at_3_values),
        "chunk_hit_at_5": calculate_mean_hit_at_k(hit_at_5_values),
        "chunk_mrr": calculate_mrr(reciprocal_ranks),
        "chunk_context_precision": sum(r["context_precision"] for r in query_metrics) / len(query_metrics),
        "chunk_context_recall": sum(r["context_recall"] for r in query_metrics) / len(query_metrics),
        "top_5_success_count": sum(hit_at_5_values),
        "top_5_failure_count": len(query_metrics) - sum(hit_at_5_values),
    }


def create_evaluation_manifest(
    retrieval_results: list[JsonObject],
    document_qrels: DocumentQrels,
) -> JsonObject:
    """KURE-v1 Baseline Document 평가에 사용한 설정 정보를 만든다."""
    if not retrieval_results:
        raise ValueError("평가 설정을 만들 Retrieval 결과가 없습니다.")

    first_result = retrieval_results[0]

    return {
        "experiment_id": "exp_baseline_kure_v1",
        "evaluation_scope": "document",
        "dataset_version": "ontong_youth_mvp_400_v1",
        "chunking_version": "c2_section_800_ov120_v1",
        "embedding_model": first_result["embedding_model"],
        "index_version": first_result["index_version"],
        "distance_metric": first_result["distance_metric"],
        "evaluation_max_k": first_result["evaluation_max_k"],
        "question_count": len(retrieval_results),
        "qrels_count": sum(len(ids) for ids in document_qrels.values()),
    }


def save_document_evaluation(
    query_metrics: list[JsonObject],
    summary: JsonObject,
    manifest: JsonObject,
    output_dir: str | Path,
) -> tuple[Path, Path, Path]:
    """질문별 결과, 전체 요약, 평가 설정을 각각 파일로 저장한다."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    metrics_path = output_path / "document_metrics.jsonl"
    summary_path = output_path / "document_summary.json"
    manifest_path = output_path / "document_evaluation_manifest.json"

    # 질문별 평가 결과는 한 줄에 질문 하나씩 JSONL로 저장한다.
    with metrics_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for result in query_metrics:
            output_file.write(json.dumps(result, ensure_ascii=False) + "\n")

    # 전체 Document 평가지표는 하나의 JSON 파일로 저장한다.
    with summary_path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(summary, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    # 평가에 사용한 데이터와 검색 설정은 Manifest JSON으로 저장한다.
    with manifest_path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(manifest, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    return metrics_path, summary_path, manifest_path


def create_chunk_evaluation_manifest(
    retrieval_results: list[JsonObject],
    chunk_qrels: ChunkQrels,
) -> JsonObject:
    """KURE-v1 Baseline Chunk 평가에 사용한 설정 정보를 만든다."""
    if not retrieval_results:
        raise ValueError("평가 설정을 만들 Retrieval 결과가 없습니다.")

    first_result = retrieval_results[0]
    return {
        "experiment_id": "exp_baseline_kure_v1",
        "evaluation_scope": "chunk",
        "dataset_version": "ontong_youth_mvp_400_v1",
        "chunking_version": "c2_section_800_v1",
        "embedding_model": first_result["embedding_model"],
        "index_version": first_result["index_version"],
        "distance_metric": first_result["distance_metric"],
        "evaluation_max_k": first_result["evaluation_max_k"],
        "question_count": len(retrieval_results),
        "qrels_count": sum(len(ids) for ids in chunk_qrels.values()),
    }


def save_chunk_evaluation(
    query_metrics: list[JsonObject],
    summary: JsonObject,
    manifest: JsonObject,
    output_dir: str | Path,
) -> tuple[Path, Path, Path]:
    """Chunk 질문별 결과, 전체 요약, 평가 설정을 별도 파일로 저장한다."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metrics_path = output_path / "chunk_metrics.jsonl"
    summary_path = output_path / "chunk_summary.json"
    manifest_path = output_path / "chunk_evaluation_manifest.json"

    with metrics_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for result in query_metrics:
            output_file.write(json.dumps(result, ensure_ascii=False) + "\n")

    with summary_path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(summary, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    with manifest_path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(manifest, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    return metrics_path, summary_path, manifest_path


def run_document_evaluation(
    retrieval_results_path: str | Path,
    qrels_path: str | Path,
    output_dir: str | Path,
) -> tuple[list[JsonObject], JsonObject, JsonObject]:
    """Document 평가 전체 과정을 순서대로 실행하고 결과를 저장한다."""
    # 검색 결과와 qrels를 읽고 query_id 연결을 확인한다.
    retrieval_results, document_qrels = load_and_validate_inputs(
        retrieval_results_path,
        qrels_path,
    )

    # 질문별 Document 평가 결과를 만든다.
    query_metrics = evaluate_document_queries(
        retrieval_results,
        document_qrels,
    )

    # 전체 Hit@1·3·5와 MRR 요약을 만든다.
    summary = summarize_document_metrics(query_metrics)

    # 이번 Baseline 평가에 사용한 설정 정보를 만든다.
    manifest = create_evaluation_manifest(
        retrieval_results,
        document_qrels,
    )

    # 질문별 결과, 전체 요약, 평가 설정을 각각 파일로 저장한다.
    save_document_evaluation(
        query_metrics,
        summary,
        manifest,
        output_dir,
    )

    return query_metrics, summary, manifest


def run_chunk_evaluation(
    retrieval_results_path: str | Path,
    qrels_path: str | Path,
    output_dir: str | Path,
) -> tuple[list[JsonObject], JsonObject, JsonObject]:
    """Chunk 평가 전체 과정을 순서대로 실행하고 결과를 저장한다."""
    # 청크 순위가 포함된 Retrieval 결과를 읽는다.
    retrieval_results = load_retrieval_results(retrieval_results_path)

    # 질문별 Gold chunk_id가 담긴 Chunk qrels를 읽는다.
    chunk_qrels = load_chunk_qrels(qrels_path)

    # 질문별 Chunk Hit@1·3·5와 RR을 계산한다.
    query_metrics = evaluate_chunk_queries(retrieval_results, chunk_qrels)

    # 전체 Chunk Hit@1·3·5와 MRR 요약을 만든다.
    summary = summarize_chunk_metrics(query_metrics)

    # 이번 Chunk 평가에 사용한 설정 정보를 만든다.
    manifest = create_chunk_evaluation_manifest(retrieval_results, chunk_qrels)

    # Document 평가 결과와 섞이지 않도록 Chunk 평가 파일을 따로 저장한다.
    save_chunk_evaluation(query_metrics, summary, manifest, output_dir)

    return query_metrics, summary, manifest
