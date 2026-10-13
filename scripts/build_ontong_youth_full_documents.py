from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


DEFAULT_INPUT = Path(
    r"C:\말똥가리\data\processed\ontong_youth_normalization\ontong_youth_policy_normalized_raw_records.jsonl"
)
DEFAULT_OUTPUT_DIR = Path(r"C:\말똥가리\data\processed\ontong_youth_full_v1")


TEXT_FIELDS = [
    ("정책명", "plcyNm"),
    ("정책 설명", "plcyExplnCn"),
    ("지원 내용", "plcySprtCn"),
    ("지원 대상", "ptcpPrpTrgtCn"),
    ("추가 신청 자격", "addAplyQlfcCndCn"),
    ("신청 기간", "aplyYmd"),
    ("사업 기간", "bizPrdEtcCn"),
    ("신청 방법", "plcyAplyMthdCn"),
    ("심사 방법", "srngMthdCn"),
    ("제출 서류", "sbmsnDcmntCn"),
    ("기타 사항", "etcMttrCn"),
    ("주관 기관", "sprvsnInstCdNm"),
    ("운영 기관", "operInstCdNm"),
    ("정책 대분류", "primary_category"),
    ("정책 중분류", "primary_mclsf"),
    ("정책 키워드", "plcyKywdNm"),
    ("신청 URL", "aplyUrlAddr"),
    ("참고 URL 1", "refUrlAddr1"),
    ("참고 URL 2", "refUrlAddr2"),
]


RAW_API_FIELDS = [
    "plcyNo",
    "bscPlanCycl",
    "bscPlanPlcyWayNo",
    "bscPlanFcsAsmtNo",
    "bscPlanAsmtNo",
    "pvsnInstGroupCd",
    "plcyPvsnMthdCd",
    "plcyAprvSttsCd",
    "plcyNm",
    "plcyKywdNm",
    "plcyExplnCn",
    "lclsfNm",
    "mclsfNm",
    "plcySprtCn",
    "sprvsnInstCd",
    "sprvsnInstCdNm",
    "sprvsnInstPicNm",
    "operInstCd",
    "operInstCdNm",
    "operInstPicNm",
    "sprtSclLmtYn",
    "aplyPrdSeCd",
    "bizPrdSeCd",
    "bizPrdBgngYmd",
    "bizPrdEndYmd",
    "bizPrdEtcCn",
    "plcyAplyMthdCn",
    "srngMthdCn",
    "aplyUrlAddr",
    "sbmsnDcmntCn",
    "etcMttrCn",
    "refUrlAddr1",
    "refUrlAddr2",
    "sprtSclCnt",
    "sprtArvlSeqYn",
    "sprtTrgtMinAge",
    "sprtTrgtMaxAge",
    "sprtTrgtAgeLmtYn",
    "mrgSttsCd",
    "earnCndSeCd",
    "earnMinAmt",
    "earnMaxAmt",
    "earnEtcCn",
    "addAplyQlfcCndCn",
    "ptcpPrpTrgtCn",
    "inqCnt",
    "rgtrInstCd",
    "rgtrInstCdNm",
    "rgtrUpInstCd",
    "rgtrUpInstCdNm",
    "rgtrHghrkInstCd",
    "rgtrHghrkInstCdNm",
    "zipCd",
    "plcyMajorCd",
    "jobCd",
    "schoolCd",
    "aplyYmd",
    "frstRegDt",
    "lastMdfcnDt",
    "sbizCd",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\\n", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    try:
        loaded = json.loads(text)
        if isinstance(loaded, list):
            return [str(item) for item in loaded if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in text.split(",") if item.strip()]


def text_len(row: dict[str, Any], field: str) -> int:
    return len(clean_text(row.get(field, "")))


def has_any(row: dict[str, Any], fields: list[str]) -> bool:
    return any(clean_text(row.get(field, "")) for field in fields)


def compute_quality_score(row: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if text_len(row, "plcyNm") >= 8:
        score += 8
        reasons.append("title_ok")
    if text_len(row, "plcyExplnCn") >= 40:
        score += 14
        reasons.append("description_rich")
    elif text_len(row, "plcyExplnCn") > 0:
        score += 6
        reasons.append("description_present")

    if text_len(row, "plcySprtCn") >= 120:
        score += 26
        reasons.append("support_content_rich_full")
    elif text_len(row, "plcySprtCn") >= 40:
        score += 22
        reasons.append("support_content_rich")
    elif text_len(row, "plcySprtCn") > 0:
        score += 10
        reasons.append("support_content_present")

    if has_any(row, ["ptcpPrpTrgtCn", "addAplyQlfcCndCn", "sprtTrgtMinAge", "sprtTrgtMaxAge"]):
        score += 12
        reasons.append("target_condition_present")
    if text_len(row, "aplyYmd") > 0:
        score += 9
        reasons.append("application_period_present")
    if text_len(row, "plcyAplyMthdCn") > 0:
        score += 9
        reasons.append("application_method_present")
    if text_len(row, "sbmsnDcmntCn") > 0:
        score += 7
        reasons.append("submission_docs_present")
    if has_any(row, ["aplyUrlAddr", "refUrlAddr1"]):
        score += 7
        reasons.append("url_present")
    if has_any(row, ["etcMttrCn", "srngMthdCn", "bizPrdEtcCn"]):
        score += 4
        reasons.append("extra_guidance_present")
    if text_len(row, "plcyKywdNm") > 0:
        score += 5
        reasons.append("keyword_present")
    if clean_text(row.get("normalization_status")) == "OK":
        score += 5
        reasons.append("normalization_ok")
    if clean_text(row.get("primary_category")) == "UNKNOWN":
        score -= 100
        reasons.append("unknown_category_penalty")

    title = clean_text(row.get("plcyNm"))
    if any(word in title for word in ["축제", "공모전", "박람회", "설명회"]):
        score -= 8
        reasons.append("event_like_penalty")

    return score, reasons


def make_structured_text(row: dict[str, Any]) -> str:
    sections: list[str] = []
    for label, field in TEXT_FIELDS:
        value = clean_text(row.get(field, ""))
        if value:
            sections.append(f"{label}: {value}")
    return "\n\n".join(sections).strip()


def make_metadata(row: dict[str, Any], quality_score: int, quality_reasons: list[str]) -> dict[str, Any]:
    return {
        "source": "ontong_youth",
        "source_dataset": "온통청년 청년정책 API",
        "dataset_version": "ontong_youth_full_v1",
        "source_policy_no": clean_text(row.get("plcyNo")),
        "primary_category": clean_text(row.get("primary_category")),
        "primary_mclsf": clean_text(row.get("primary_mclsf")),
        "secondary_categories": parse_json_list(row.get("secondary_categories")),
        "secondary_mclsf": parse_json_list(row.get("secondary_mclsf")),
        "normalized_lclsf_list": parse_json_list(row.get("normalized_lclsf_list")),
        "normalized_mclsf_list": parse_json_list(row.get("normalized_mclsf_list")),
        "normalized_keywords": parse_json_list(row.get("normalized_keywords")),
        "raw_lclsfNm": clean_text(row.get("lclsfNm")),
        "raw_mclsfNm": clean_text(row.get("mclsfNm")),
        "raw_plcyKywdNm": clean_text(row.get("plcyKywdNm")),
        "supervising_agency": clean_text(row.get("sprvsnInstCdNm")),
        "operating_agency": clean_text(row.get("operInstCdNm")),
        "application_period": clean_text(row.get("aplyYmd")),
        "business_start_date": clean_text(row.get("bizPrdBgngYmd")),
        "business_end_date": clean_text(row.get("bizPrdEndYmd")),
        "business_period_note": clean_text(row.get("bizPrdEtcCn")),
        "target_min_age": clean_text(row.get("sprtTrgtMinAge")),
        "target_max_age": clean_text(row.get("sprtTrgtMaxAge")),
        "target_age_limit_yn": clean_text(row.get("sprtTrgtAgeLmtYn")),
        "income_condition_code": clean_text(row.get("earnCndSeCd")),
        "income_min_amount": clean_text(row.get("earnMinAmt")),
        "income_max_amount": clean_text(row.get("earnMaxAmt")),
        "marriage_status_code": clean_text(row.get("mrgSttsCd")),
        "region_zip_codes": clean_text(row.get("zipCd")),
        "application_url": clean_text(row.get("aplyUrlAddr")),
        "reference_url_1": clean_text(row.get("refUrlAddr1")),
        "reference_url_2": clean_text(row.get("refUrlAddr2")),
        "first_registered_at": clean_text(row.get("frstRegDt")),
        "last_modified_at": clean_text(row.get("lastMdfcnDt")),
        "document_quality_score": quality_score,
        "document_quality_reasons": quality_reasons,
        "normalization_status": clean_text(row.get("normalization_status")),
        "source_page": row.get("_source_page", ""),
        "raw_record_index": row.get("_raw_record_index", ""),
    }


def make_raw_record(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field, "") for field in RAW_API_FIELDS}


def make_document(row: dict[str, Any]) -> dict[str, Any]:
    quality_score, quality_reasons = compute_quality_score(row)
    plcy_no = clean_text(row.get("plcyNo"))
    document_id = clean_text(row.get("document_id")) or f"ontong_youth_{plcy_no}"
    content = make_structured_text(row)
    return {
        "document_id": document_id,
        "title": clean_text(row.get("plcyNm")),
        "source": "ontong_youth",
        "url": clean_text(row.get("aplyUrlAddr") or row.get("refUrlAddr1") or row.get("refUrlAddr2")),
        "content": content,
        "retrieval_text": content,
        "metadata": make_metadata(row, quality_score, quality_reasons),
        "raw_record": make_raw_record(row),
    }


def percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def build_quality_rows(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    doc_ids = [doc["document_id"] for doc in documents]
    titles = [doc["title"] for doc in documents]
    urls = [doc["url"] for doc in documents]
    lengths = [len(doc["retrieval_text"]) for doc in documents]
    quality_scores = [int(doc["metadata"]["document_quality_score"]) for doc in documents]
    categories = Counter(doc["metadata"]["primary_category"] or "UNKNOWN" for doc in documents)
    middles = Counter(doc["metadata"]["primary_mclsf"] or "UNKNOWN" for doc in documents)
    statuses = Counter(doc["metadata"]["normalization_status"] or "UNKNOWN" for doc in documents)

    rows: list[dict[str, Any]] = [
        {"metric": "document_count", "value": len(documents)},
        {"metric": "duplicate_document_id_count", "value": len(doc_ids) - len(set(doc_ids))},
        {"metric": "blank_document_id_count", "value": sum(1 for value in doc_ids if not value)},
        {"metric": "blank_title_count", "value": sum(1 for value in titles if not value)},
        {"metric": "blank_url_count", "value": sum(1 for value in urls if not value)},
        {"metric": "blank_retrieval_text_count", "value": sum(1 for doc in documents if not doc["retrieval_text"])},
        {"metric": "retrieval_text_min_length", "value": min(lengths) if lengths else 0},
        {"metric": "retrieval_text_avg_length", "value": round(mean(lengths), 3) if lengths else 0},
        {"metric": "retrieval_text_median_length", "value": median(lengths) if lengths else 0},
        {"metric": "retrieval_text_p95_length", "value": percentile(lengths, 0.95)},
        {"metric": "retrieval_text_max_length", "value": max(lengths) if lengths else 0},
        {"metric": "document_quality_min_score", "value": min(quality_scores) if quality_scores else 0},
        {"metric": "document_quality_avg_score", "value": round(mean(quality_scores), 3) if quality_scores else 0},
        {"metric": "document_quality_median_score", "value": median(quality_scores) if quality_scores else 0},
        {"metric": "document_quality_max_score", "value": max(quality_scores) if quality_scores else 0},
        {"metric": "documents_with_application_url_count", "value": sum(1 for doc in documents if doc["metadata"]["application_url"])},
        {"metric": "documents_with_any_url_count", "value": sum(1 for value in urls if value)},
    ]
    for category, count in categories.most_common():
        rows.append({"metric": f"primary_category.{category}", "value": count})
    for middle, count in middles.most_common():
        rows.append({"metric": f"primary_mclsf.{middle}", "value": count})
    for status, count in statuses.most_common():
        rows.append({"metric": f"normalization_status.{status}", "value": count})
    return rows


def build_schema() -> dict[str, Any]:
    return {
        "schema_name": "ontong_youth_rag_document_v1",
        "dataset_version": "ontong_youth_full_v1",
        "record_unit": "one policy = one document",
        "chunking_target_field": "retrieval_text",
        "fields": {
            "document_id": "문서 고유 ID. 기본 형식은 ontong_youth_{plcyNo}",
            "title": "정책명. 원본 API plcyNm에서 생성",
            "source": "출처 식별자. ontong_youth",
            "url": "대표 URL. 신청 URL 우선, 없으면 참고 URL 사용",
            "content": "주요 정책 필드를 사람이 읽기 쉬운 구조화 텍스트로 결합한 전체 본문",
            "retrieval_text": "후속 chunking/search 대상 텍스트. 현재 content와 동일",
            "metadata": "분류, 기관, 기간, 자격, URL, 정규화, 품질점수 등 검색/필터링용 메타데이터",
            "raw_record": "온통청년 API 원본 주요 필드 보존",
        },
        "raw_record_fields": RAW_API_FIELDS,
        "notes": [
            "원본 API 필드는 raw_record에 보존한다.",
            "검색 및 청킹 담당자는 content가 아니라 retrieval_text를 사용한다.",
            "이 단계에서는 chunk_id, embedding, vector DB, 평가 실행 결과를 만들지 않는다.",
        ],
    }


def build_schema_md() -> str:
    return """# Ontong Youth Full RAG Document Schema v1

## 목적

온통청년 전체 정책 데이터를 RAG 실험 파이프라인에 넣기 위한 공통 문서 구조다.
정책 1개를 문서 1개로 본다.

## 레코드 단위

`one policy = one document`

## 후속 Chunking 대상 필드

`retrieval_text`

`content`와 `raw_record`는 보존/검사용이고, 실제 검색 청킹은 `retrieval_text`를 기준으로 진행한다.

## 주요 필드

- `document_id`: 문서 고유 ID. 기본 형식은 `ontong_youth_{plcyNo}`
- `title`: 정책명
- `source`: `ontong_youth`
- `url`: 대표 URL
- `content`: 주요 정책 필드를 구조화 텍스트로 결합한 본문
- `retrieval_text`: 검색/청킹 대상 텍스트
- `metadata`: 분류, 기관, 기간, 조건, URL, 정규화 상태, 품질점수
- `raw_record`: 온통청년 API 원본 주요 필드

## 아직 하지 않은 작업

- Chunking
- Chunk ID 생성
- Chunk 단위 qrels 생성
- Embedding
- Chroma index 구축
- Retrieval 평가
"""


def run(input_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_jsonl(input_path)
    documents = [make_document(row) for row in rows]
    quality_rows = build_quality_rows(documents)
    schema = build_schema()

    documents_path = output_dir / "documents.jsonl"
    sample_path = output_dir / "documents_sample.json"
    schema_json_path = output_dir / "document_schema.json"
    schema_md_path = output_dir / "DOCUMENT_SCHEMA.md"
    quality_csv_path = output_dir / "data_quality_report.csv"
    legacy_quality_csv_path = output_dir / "document_quality_report.csv"
    manifest_path = output_dir / "dataset_manifest.json"

    write_jsonl(documents_path, documents)
    write_json(sample_path, documents[:5])
    write_json(schema_json_path, schema)
    schema_md_path.write_text(build_schema_md(), encoding="utf-8")
    write_csv(quality_csv_path, quality_rows, ["metric", "value"])
    write_csv(legacy_quality_csv_path, quality_rows, ["metric", "value"])

    output_files = {
        "documents_jsonl": str(documents_path),
        "documents_sample_json": str(sample_path),
        "document_schema_json": str(schema_json_path),
        "document_schema_md": str(schema_md_path),
        "data_quality_report_csv": str(quality_csv_path),
        "document_quality_report_csv": str(legacy_quality_csv_path),
        "dataset_manifest_json": str(manifest_path),
    }
    manifest = {
        "dataset_name": "Ontong Youth Full RAG Documents",
        "dataset_version": "ontong_youth_full_v1",
        "source_normalized_raw_jsonl": str(input_path),
        "schema_name": schema["schema_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(documents),
        "quality": {row["metric"]: row["value"] for row in quality_rows},
        "output_files": output_files,
        "file_hashes_sha256": {
            "source_normalized_raw_jsonl": sha256_file(input_path),
            "documents_jsonl": sha256_file(documents_path),
            "data_quality_report_csv": sha256_file(quality_csv_path),
            "document_schema_json": sha256_file(schema_json_path),
        },
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    manifest = run(args.input, args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
