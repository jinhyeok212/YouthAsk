"""Validate C01 R2-R4 against Hyeonsu's retrieval handoff contract."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from scripts.validate_c02_c03_results import read_jsonl, validate_run


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
CHUNKS = ROOT / "data/processed/ontong_youth_full_v1/chunks/fixed_800_ov120_v1/chunks.jsonl"
OUTPUT_JSON = EXPERIMENTS / "C01_RESULT_VALIDATION.json"
OUTPUT_MD = EXPERIMENTS / "C01_RESULT_VALIDATION.md"


def main() -> None:
    chunks = read_jsonl(CHUNKS)
    chunk_map = {str(row["chunk_id"]): str(row["document_id"]) for row in chunks}
    runs = [validate_run("C01", repetition, chunk_map) for repetition in (2, 3, 4)]
    baseline_signature = runs[0]["ranking_signature"]
    mismatches = {
        query_id
        for run in runs[1:]
        for query_id, chunk_ids in run["ranking_signature"].items()
        if baseline_signature.get(query_id) != chunk_ids
    }
    valid = all(run["valid"] for run in runs) and not mismatches
    payload = {
        "valid": valid,
        "ranking_mismatch_query_count": len(mismatches),
        "ranking_mismatch_query_ids": sorted(mismatches),
        "representative_average_ms": statistics.median(run["average_retrieval_latency_ms"] for run in runs),
        "representative_p95_ms": statistics.median(run["p95_retrieval_latency_ms"] for run in runs),
        "runs": runs,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# C01 검색 결과 검증",
        "",
        f"- 전체 판정: **{'PASS' if valid else 'FAIL'}**",
        "- 검증 범위: R2~R4, 47질문, Top-5 순위·청크 ID·latency·반복 일관성",
        f"- 평균 대표값: {payload['representative_average_ms']:.3f}ms",
        f"- p95 대표값: {payload['representative_p95_ms']:.3f}ms",
        f"- 반복 순위 불일치 질문: {len(mismatches)}건",
        "",
        "| 실행 | 47질문 | Top-5 순위 | 청크 ID | latency | 평균·p95 | 오류 | 판정 |",
        "|---|---|---|---|---|---|---:|---|",
    ]
    for run in runs:
        chunks_ok = not run["missing_chunk_id_count"] and not run["invalid_condition_chunk_id_count"] and not run["chunk_document_mismatch_count"]
        lines.append(
            f"| {run['experiment_id']} | {'정상' if run['query_count'] == 47 else '비정상'} | "
            f"{'정상' if run['top5_rank_rows_valid'] else '비정상'} | {'정상' if chunks_ok else '비정상'} | "
            f"{'정상' if run['question_latency_count'] == 47 else '비정상'} | "
            f"{'정상' if run['average_matches_summary'] and run['p95_matches_summary'] else '비정상'} | "
            f"{run['runtime_error_count']} | {'PASS' if run['valid'] else 'FAIL'} |"
        )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"valid": valid, "report": str(OUTPUT_MD)}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if valid else 1)


if __name__ == "__main__":
    main()
