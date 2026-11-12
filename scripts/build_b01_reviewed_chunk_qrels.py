"""Build the reviewed B01 chunk qrels from question intent and gold documents.

The evaluation set has document-level qrels but no evidence spans.  For the
section-heading baseline, each question type maps to the section that contains
the answer.  Every selected chunk is still constrained to a document-level
gold document, and the script fails if a question/document pair has no matching
evidence section.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--document-qrels", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    questions = {row["query_id"]: row for row in read_jsonl(args.questions)}
    document_qrels = read_jsonl(args.document_qrels)

    gold_document_ids = {row["document_id"] for row in document_qrels}
    chunks_by_document_and_section: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for chunk in read_jsonl(args.chunks):
        document_id = chunk.get("document_id")
        if document_id in gold_document_ids:
            chunks_by_document_and_section[(document_id, chunk.get("section_slug"))].append(chunk)

    output_rows: list[dict] = []
    missing: list[tuple[str, str, str]] = []
    for qrel in document_qrels:
        query_id = qrel["query_id"]
        document_id = qrel["document_id"]
        question = questions[query_id]
        question_type = question["question_type"]
        section_slug = SECTION_BY_QUESTION_TYPE[question_type]
        matches = chunks_by_document_and_section[(document_id, section_slug)]
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
                    "mapping_method": "reviewed_question_type_section",
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
