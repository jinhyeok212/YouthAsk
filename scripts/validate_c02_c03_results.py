"""Validate the retrieval artifacts that constitute Hyeonsu's handoff scope."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
STATUS_PATH = EXPERIMENTS / "C02_C03_COMPARISON_STATUS.json"
OUTPUT_JSON = EXPERIMENTS / "C02_C03_RESULT_VALIDATION.json"
OUTPUT_MD = EXPERIMENTS / "C02_C03_RESULT_VALIDATION.md"
EXPECTED_QUERY_COUNT = 47

CONDITIONS = {
    "C02": ROOT / "data/processed/ontong_youth_full_v1/chunks/section_heading_500_ov120_v1/chunks.jsonl",
    "C03": ROOT / "data/processed/ontong_youth_full_v1/chunks/section_heading_800_ov0_v1/chunks.jsonl",
}


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def nearest_rank_p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))]


def wait_for_runs(timeout_hours: float) -> None:
    deadline = time.time() + timeout_hours * 3600
    while time.time() < deadline:
        if STATUS_PATH.exists():
            status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            if status.get("error"):
                raise RuntimeError(f"Comparison runner failed:\n{status['error']}")
            if status.get("active_experiment_id") is None and len(status.get("runs", [])) >= 8:
                return
        time.sleep(60)
    raise TimeoutError(f"C02/C03 did not finish within {timeout_hours} hours")


def validate_run(condition: str, repetition: int, chunk_map: dict[str, str]) -> dict:
    experiment_id = f"{condition}-20261112-R{repetition}"
    run_dir = EXPERIMENTS / experiment_id
    retrieval_path = run_dir / "retrieval_results.jsonl"
    metrics_path = run_dir / "metrics_summary.json"
    by_query_path = run_dir / "metrics_by_query.jsonl"
    required = (retrieval_path, metrics_path, by_query_path)
    missing_files = [str(path) for path in required if not path.exists()]
    if missing_files:
        raise FileNotFoundError(f"{experiment_id} missing files: {missing_files}")

    retrieval = read_jsonl(retrieval_path)
    by_query = read_jsonl(by_query_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    query_ids = [str(row.get("query_id") or "") for row in retrieval]
    if len(retrieval) != EXPECTED_QUERY_COUNT or len(set(query_ids)) != EXPECTED_QUERY_COUNT:
        errors.append(f"query rows/unique IDs are not {EXPECTED_QUERY_COUNT}")
    if len(by_query) != EXPECTED_QUERY_COUNT:
        errors.append(f"metrics_by_query rows are not {EXPECTED_QUERY_COUNT}")

    latencies: list[float] = []
    ranking_signature: dict[str, list[str]] = {}
    missing_chunk_ids = 0
    invalid_chunk_ids = 0
    document_mismatches = 0
    invalid_rank_rows = 0
    runtime_errors = 0
    for row in retrieval:
        query_id = str(row.get("query_id") or "")
        try:
            latency = float(row["retrieval_latency_ms"])
            if not math.isfinite(latency) or latency < 0:
                raise ValueError
            latencies.append(latency)
        except (KeyError, TypeError, ValueError):
            errors.append(f"{query_id}: invalid retrieval_latency_ms")

        results = row.get("results") or []
        if [item.get("rank") for item in results] != [1, 2, 3, 4, 5]:
            invalid_rank_rows += 1
        chunk_ids: list[str] = []
        for item in results:
            chunk_id = str(item.get("chunk_id") or "")
            chunk_ids.append(chunk_id)
            if not chunk_id:
                missing_chunk_ids += 1
            elif chunk_id not in chunk_map:
                invalid_chunk_ids += 1
            elif str(item.get("document_id") or "") != chunk_map[chunk_id]:
                document_mismatches += 1
        ranking_signature[query_id] = chunk_ids
        runtime_errors += int(bool(row.get("error")))

    recomputed_average = sum(latencies) / len(latencies) if latencies else 0.0
    recomputed_p95 = nearest_rank_p95(latencies) if latencies else 0.0
    average_matches = math.isclose(
        recomputed_average, float(metrics.get("average_retrieval_latency_ms", -1)), rel_tol=0, abs_tol=1e-9
    )
    p95_matches = math.isclose(
        recomputed_p95, float(metrics.get("p95_retrieval_latency_ms", -1)), rel_tol=0, abs_tol=1e-9
    )
    if not average_matches:
        errors.append("average latency does not match question-level values")
    if not p95_matches:
        errors.append("p95 latency does not match question-level values")
    if missing_chunk_ids or invalid_chunk_ids or document_mismatches or invalid_rank_rows:
        errors.append("rank/chunk/document validation failed")
    if runtime_errors or int(metrics.get("retrieval_failure_count", -1)) != 0:
        errors.append("runtime retrieval errors found")

    failure_counts = Counter(
        str(row["failure_type"]) for row in by_query if row.get("failure_type")
    )
    return {
        "experiment_id": experiment_id,
        "valid": not errors,
        "errors": errors,
        "query_count": len(retrieval),
        "top5_rank_rows_valid": invalid_rank_rows == 0,
        "missing_chunk_id_count": missing_chunk_ids,
        "invalid_condition_chunk_id_count": invalid_chunk_ids,
        "chunk_document_mismatch_count": document_mismatches,
        "question_latency_count": len(latencies),
        "average_retrieval_latency_ms": recomputed_average,
        "p95_retrieval_latency_ms": recomputed_p95,
        "average_matches_summary": average_matches,
        "p95_matches_summary": p95_matches,
        "runtime_error_count": runtime_errors,
        "ranking_signature": ranking_signature,
        "failure_counts": dict(sorted(failure_counts.items())),
        "metrics_summary": metrics,
    }


def write_report(payload: dict) -> None:
    lines = [
        "# C02·C03 검색 결과 검증",
        "",
        f"- 전체 판정: **{'PASS' if payload['valid'] else 'FAIL'}**",
        "- 검증 범위: R2~R4, 조건별 47질문, Top-5 순위·청크 ID·latency·반복 일관성",
        "",
        "| 조건 | 실행 | 47질문 | Top-5 순위 | 청크 ID | latency 47건 | 평균·p95 재계산 | 실행 오류 | 판정 |",
        "|---|---|---|---|---|---|---|---:|---|",
    ]
    for condition in ("C02", "C03"):
        for run in payload["conditions"][condition]["runs"]:
            lines.append(
                "| {condition} | {experiment_id} | {queries} | {ranks} | {chunks} | {latencies} | {summary} | {errors} | {valid} |".format(
                    condition=condition,
                    experiment_id=run["experiment_id"],
                    queries="정상" if run["query_count"] == EXPECTED_QUERY_COUNT else "비정상",
                    ranks="정상" if run["top5_rank_rows_valid"] else "비정상",
                    chunks="정상" if not run["missing_chunk_id_count"] and not run["invalid_condition_chunk_id_count"] and not run["chunk_document_mismatch_count"] else "비정상",
                    latencies="정상" if run["question_latency_count"] == EXPECTED_QUERY_COUNT else "비정상",
                    summary="정상" if run["average_matches_summary"] and run["p95_matches_summary"] else "비정상",
                    errors=run["runtime_error_count"],
                    valid="PASS" if run["valid"] else "FAIL",
                )
            )
    lines.extend(["", "## 반복 측정 요약", ""])
    lines.append("| 조건 | 평균 대표값(중앙값) | p95 대표값(중앙값) | 순위 불일치 질문 수 | 판정 |")
    lines.append("|---|---:|---:|---:|---|")
    for condition in ("C02", "C03"):
        item = payload["conditions"][condition]
        lines.append(
            f"| {condition} | {item['representative_average_ms']:.3f}ms | {item['representative_p95_ms']:.3f}ms | {item['ranking_mismatch_query_count']} | {'PASS' if item['valid'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "이 파일과 조건별 `retrieval_results.jsonl`, `metrics_by_query.jsonl`, `metrics_summary.json`을 평가 담당자에게 전달한다.",
            "",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout-hours", type=float, default=24.0)
    args = parser.parse_args()
    if args.wait:
        wait_for_runs(args.timeout_hours)

    conditions: dict[str, dict] = {}
    overall_valid = True
    for condition, chunks_path in CONDITIONS.items():
        chunks = read_jsonl(chunks_path)
        chunk_map = {str(row["chunk_id"]): str(row["document_id"]) for row in chunks}
        runs = [validate_run(condition, repetition, chunk_map) for repetition in (2, 3, 4)]
        baseline_signature = runs[0]["ranking_signature"]
        mismatched_queries = {
            query_id
            for run in runs[1:]
            for query_id, chunk_ids in run["ranking_signature"].items()
            if baseline_signature.get(query_id) != chunk_ids
        }
        condition_valid = all(run["valid"] for run in runs) and not mismatched_queries
        conditions[condition] = {
            "valid": condition_valid,
            "ranking_mismatch_query_count": len(mismatched_queries),
            "ranking_mismatch_query_ids": sorted(mismatched_queries),
            "representative_average_ms": statistics.median(
                run["average_retrieval_latency_ms"] for run in runs
            ),
            "representative_p95_ms": statistics.median(
                run["p95_retrieval_latency_ms"] for run in runs
            ),
            "runs": runs,
        }
        overall_valid = overall_valid and condition_valid

    payload = {"valid": overall_valid, "conditions": conditions}
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(payload)
    print(json.dumps({"valid": overall_valid, "json": str(OUTPUT_JSON), "report": str(OUTPUT_MD)}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if overall_valid else 1)


if __name__ == "__main__":
    main()
