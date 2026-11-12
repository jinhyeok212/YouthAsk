"""Build comparable chunk qrels for section and fixed chunking experiments.

The 47-question evaluation set provides document relevance and question intent,
but not character-level evidence spans.  We therefore use one reviewed intent to
section rule for every condition.  Section chunks are matched by section slug;
fixed chunks are matched when their source span overlaps that same section.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from src.chunking.generators import parse_sections


SECTION_BY_QUESTION_TYPE = {
    "specific_policy_search": "title",
    "eligibility": "support",
    "application_period": "application_period",
    "application_method": "application_method",
    "support_content": "support",
    "required_documents": "documents",
}


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def overlaps(chunk: dict, start: int, end: int) -> bool:
    return int(chunk["start_char"]) < end and start < int(chunk["end_char"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--document-qrels", type=Path, required=True)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    questions = {row["query_id"]: row for row in read_jsonl(args.questions)}
    document_qrels = read_jsonl(args.document_qrels)
    gold_document_ids = {row["document_id"] for row in document_qrels}
    documents = {
        row["document_id"]: row
        for row in read_jsonl(args.documents)
        if row["document_id"] in gold_document_ids
    }
    chunks_by_document: dict[str, list[dict]] = defaultdict(list)
    for chunk in read_jsonl(args.chunks):
        if chunk.get("document_id") in gold_document_ids:
            chunks_by_document[chunk["document_id"]].append(chunk)

    output_rows: list[dict] = []
    missing: list[tuple[str, str, str]] = []
    for qrel in document_qrels:
        query_id = qrel["query_id"]
        document_id = qrel["document_id"]
        question_type = questions[query_id]["question_type"]
        section_slug = SECTION_BY_QUESTION_TYPE[question_type]
        candidates = chunks_by_document[document_id]

        if candidates and candidates[0].get("section_slug") is not None:
            matches = [row for row in candidates if row.get("section_slug") == section_slug]
            mapping_method = "reviewed_question_type_section"
        else:
            text = str(documents[document_id].get("retrieval_text") or "")
            section_spans = [
                (int(section["start_char"]), int(section["end_char"]))
                for section in parse_sections(text)
                if section["section_slug"] == section_slug
            ]
            matches = [
                chunk
                for chunk in candidates
                if any(overlaps(chunk, start, end) for start, end in section_spans)
            ]
            mapping_method = "reviewed_question_type_section_span_overlap"

        if not matches:
            missing.append((query_id, document_id, section_slug))
            continue
        for chunk in matches:
            output_rows.append(
                {
                    "query_id": query_id,
                    "document_id": document_id,
                    "chunk_id": chunk["chunk_id"],
                    "relevance": qrel.get("relevance", 1),
                    "mapping_method": mapping_method,
                    "question_type": question_type,
                    "evidence_section": section_slug,
                    "chunking_version": chunk["chunking_version"],
                }
            )

    if missing:
        raise ValueError(f"Missing reviewed evidence sections: {missing}")
    if {row["query_id"] for row in output_rows} != set(questions):
        raise ValueError("Reviewed chunk qrels do not cover every evaluation question")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "output": str(args.output),
                "row_count": len(output_rows),
                "query_count": len({row["query_id"] for row in output_rows}),
                "mapping_rules": SECTION_BY_QUESTION_TYPE,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
