from __future__ import annotations

import hashlib
import re
from typing import Any


SECTION_LABELS = [
    "정책명",
    "정책 요약",
    "지원 내용",
    "참여 대상",
    "추가 신청 자격",
    "신청 기간",
    "사업 기간",
    "신청 방법",
    "심사 방법",
    "제출 서류",
    "기타 사항",
    "주관 기관",
    "운영 기관",
    "정책 대분류",
    "정책 중분류",
    "정책 키워드",
    "신청 URL",
    "참고 URL",
]

SECTION_SLUGS = {
    "정책명": "title",
    "정책 요약": "summary",
    "지원 내용": "support",
    "참여 대상": "target",
    "추가 신청 자격": "eligibility_extra",
    "신청 기간": "application_period",
    "사업 기간": "business_period",
    "신청 방법": "application_method",
    "심사 방법": "screening",
    "제출 서류": "documents",
    "기타 사항": "notes",
    "주관 기관": "supervising_agency",
    "운영 기관": "operating_agency",
    "정책 대분류": "category",
    "정책 중분류": "middle_category",
    "정책 키워드": "keywords",
    "신청 URL": "application_url",
    "참고 URL": "reference_url",
}

FIXED_STRATEGIES = {"fixed", "character", "char"}
SECTION_STRATEGIES = {"section", "c2_section", "section_aware"}


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def scalar(value: Any) -> str | int | float | bool:
    if isinstance(value, bool | int | float | str):
        return value
    if value is None:
        return ""
    return str(value)


def document_id(document: dict[str, Any]) -> str:
    return str(document.get("document_id") or document.get("doc_id") or "").strip()


def chunk_spans(text_length: int, chunk_size: int, overlap: int) -> list[tuple[int, int]]:
    if text_length <= 0:
        return []
    if chunk_size <= 0:
        raise ValueError("chunking.size는 0보다 커야 합니다.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunking.overlap은 0 이상이고 chunking.size보다 작아야 합니다.")

    spans: list[tuple[int, int]] = []
    step = chunk_size - overlap
    start = 0
    while start < text_length:
        end = min(start + chunk_size, text_length)
        spans.append((start, end))
        if end >= text_length:
            break
        start += step
    return spans


def base_metadata(
    document: dict[str, Any],
    *,
    version: str,
    strategy: str,
    size: int,
    overlap: int,
    target_field: str,
) -> dict[str, str | int | float | bool]:
    metadata: dict[str, str | int | float | bool] = {
        "chunking_version": version,
        "chunking_strategy": strategy,
        "chunk_size": size,
        "overlap": overlap,
        "target_field": target_field,
        "title": scalar(document.get("title", "")),
        "category": scalar(document.get("category", "")),
        "source": scalar(document.get("source", "")),
        "url": scalar(document.get("url", "")),
    }
    for key, value in (document.get("metadata") or {}).items():
        metadata.setdefault(key, scalar(value))
    return metadata


def section_pattern() -> re.Pattern[str]:
    labels = "|".join(re.escape(label) for label in sorted(SECTION_LABELS, key=len, reverse=True))
    return re.compile(rf"(?m)^({labels}):\s*")


def parse_sections(text: str) -> list[dict[str, Any]]:
    matches = list(section_pattern().finditer(text))
    if not matches:
        return [
            {
                "section_index": 0,
                "section_name": "본문",
                "section_slug": "body",
                "section_text": text,
                "start_char": 0,
                "end_char": len(text),
            }
        ]

    sections: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        label = match.group(1)
        section_text = text[start:end].strip()
        if not section_text:
            continue
        sections.append(
            {
                "section_index": index,
                "section_name": label,
                "section_slug": SECTION_SLUGS.get(label, "section"),
                "section_text": section_text,
                "start_char": start,
                "end_char": end,
            }
        )
    return sections


def title_prefix(document: dict[str, Any], section_name: str) -> str:
    title = str(document.get("title") or "").strip()
    if not title or section_name == "정책명":
        return ""
    return f"정책명: {title}\n\n"


def generate_fixed_chunks(
    documents: list[dict[str, Any]],
    *,
    version: str,
    strategy: str,
    size: int,
    overlap: int,
    target_field: str,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for document in documents:
        did = document_id(document)
        if not did:
            raise ValueError("document_id가 없는 문서가 있습니다.")
        text = str(document.get(target_field) or "")
        if not text.strip():
            raise ValueError(f"document_id={did} 문서의 {target_field}가 비어 있습니다.")

        spans = chunk_spans(len(text), size, overlap)
        for chunk_index, (start_char, end_char) in enumerate(spans):
            chunk_text = text[start_char:end_char]
            chunk_id = f"{did}__chunk_{chunk_index:03d}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": did,
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "start_char": start_char,
                    "end_char": end_char,
                    "char_length": len(chunk_text),
                    "document_text_length": len(text),
                    "text_hash": short_hash(chunk_text),
                    "chunking_version": version,
                    "metadata": base_metadata(
                        document,
                        version=version,
                        strategy=strategy,
                        size=size,
                        overlap=overlap,
                        target_field=target_field,
                    )
                    | {"size_meaning": "final chunk text character limit"},
                }
            )
    return chunks


def generate_section_chunks(
    documents: list[dict[str, Any]],
    *,
    version: str,
    strategy: str,
    size: int,
    overlap: int,
    target_field: str,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for document in documents:
        did = document_id(document)
        if not did:
            raise ValueError("document_id가 없는 문서가 있습니다.")
        text = str(document.get(target_field) or "")
        if not text.strip():
            raise ValueError(f"document_id={did} 문서의 {target_field}가 비어 있습니다.")

        chunk_index = 0
        for section in parse_sections(text):
            prefix = title_prefix(document, section["section_name"])
            body = section["section_text"]
            # C2의 size는 최종 text 길이가 아니라 section body 분할 기준이다.
            spans = chunk_spans(len(body), size, min(overlap, max(0, size - 1)))
            for part_index, (body_start, body_end) in enumerate(spans):
                body_text = body[body_start:body_end].strip()
                chunk_text = f"{prefix}{body_text}".strip()
                chunk_id = (
                    f"{did}__sec_{section['section_index']:02d}_"
                    f"{section['section_slug']}__chunk_{part_index:03d}"
                )
                source_start = int(section["start_char"]) + body_start
                source_end = min(int(section["start_char"]) + body_end, int(section["end_char"]))
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "document_id": did,
                        "chunk_index": chunk_index,
                        "section_index": section["section_index"],
                        "section_name": section["section_name"],
                        "section_slug": section["section_slug"],
                        "section_part_index": part_index,
                        "text": chunk_text,
                        "start_char": source_start,
                        "end_char": source_end,
                        "char_length": len(chunk_text),
                        "source_char_length": body_end - body_start,
                        "document_text_length": len(text),
                        "text_hash": short_hash(chunk_text),
                        "chunking_version": version,
                        "metadata": base_metadata(
                            document,
                            version=version,
                            strategy=strategy,
                            size=size,
                            overlap=overlap,
                            target_field=target_field,
                        )
                        | {
                            "section_name": section["section_name"],
                            "section_slug": section["section_slug"],
                            "title_prefix_added": bool(prefix),
                            "size_meaning": (
                                "section body split limit; final text may include title prefix"
                            ),
                        },
                    }
                )
                chunk_index += 1
    return chunks


def generate_chunks(
    documents: list[dict[str, Any]],
    *,
    version: str,
    strategy: str,
    size: int,
    overlap: int,
    unit: str,
    target_field: str,
) -> list[dict[str, Any]]:
    if unit not in {"characters", "character", "chars"}:
        raise ValueError(f"지원하지 않는 chunking.unit입니다: {unit}")
    normalized_strategy = strategy.lower()
    if normalized_strategy in FIXED_STRATEGIES:
        return generate_fixed_chunks(
            documents,
            version=version,
            strategy=normalized_strategy,
            size=size,
            overlap=overlap,
            target_field=target_field,
        )
    if normalized_strategy in SECTION_STRATEGIES:
        return generate_section_chunks(
            documents,
            version=version,
            strategy=normalized_strategy,
            size=size,
            overlap=overlap,
            target_field=target_field,
        )
    raise ValueError(f"지원하지 않는 chunking.strategy입니다: {strategy}")

