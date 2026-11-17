"""Convert the approved CSV to document-level evaluation inputs; no model calls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ROOT / "data/processed/ontong_youth_full_v1/documents.jsonl"
OUTPUT = ROOT / "data/evaluation/eval_200_v1"
REQUIRED = ("query_id", "query", "reference_answer", "ground_truth_document_ids")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def jsonl_bytes(rows: list[dict]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")


def convert(source: Path, documents: Path = DOCUMENTS, output: Path = OUTPUT) -> dict:
    # Read exact bytes once, so hashes describe the data actually converted.
    source_bytes = source.read_bytes()  # Missing input is fatal; never synthesize it.
    document_bytes = documents.read_bytes()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite evaluation directory: {output}")
    reader = csv.DictReader(io.StringIO(source_bytes.decode("utf-8-sig"), newline=""))
    columns = reader.fieldnames or []
    if len(columns) != len(set(columns)) or not set(REQUIRED).issubset(columns):
        raise ValueError("Missing required or duplicate CSV columns")
    rows = list(reader)
    if len(rows) != 200:
        raise ValueError(f"Expected 200 questions, got {len(rows)}")
    document_rows = [json.loads(line) for line in document_bytes.decode("utf-8-sig").splitlines() if line.strip()]
    document_ids = [row["document_id"] for row in document_rows]
    if any(not isinstance(item, str) or not item.strip() for item in document_ids):
        raise ValueError("Blank source document ID")
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("Duplicate source document IDs")
    known_documents = set(document_ids)
    questions, qrels = [], []
    seen_queries: set[str] = set()
    distribution: Counter = Counter()
    for number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Malformed CSV row {number}")
        for key in REQUIRED:
            if not row[key].strip():
                raise ValueError(f"Blank {key} at CSV row {number}")
        query_id = row["query_id"]
        if query_id.strip() in seen_queries:
            raise ValueError(f"Duplicate query_id: {query_id}")
        seen_queries.add(query_id.strip())
        gold = json.loads(row["ground_truth_document_ids"])
        if not isinstance(gold, list) or not gold:
            raise ValueError(f"Expected nonempty Gold JSON array: {query_id}")
        if any(not isinstance(item, str) or not item.strip() for item in gold):
            raise ValueError(f"Blank or invalid Gold ID: {query_id}")
        if len(gold) != len(set(gold)):
            raise ValueError(f"Duplicate Gold ID: {query_id}")
        missing = set(gold) - known_documents
        if missing:
            raise ValueError(f"Gold IDs absent from documents.jsonl: {query_id}: {sorted(missing)}")
        # Preserve every source column, including answers and approval notes.
        # Only decode the JSON array; do not infer evidence or source locations.
        questions.append({**row, "ground_truth_document_ids": gold})
        qrels.extend({"query_id": query_id, "document_id": item, "relevance": 1} for item in gold)
        distribution[len(gold)] += 1
    if len(qrels) != 207:
        raise ValueError(f"Expected 207 Gold links, got {len(qrels)}")

    outputs = {"eval_questions.jsonl": jsonl_bytes(questions), "qrels.jsonl": jsonl_bytes(qrels)}
    manifest = {
        "evaluation_version": "eval_200_v1",
        "source_csv": {"path": str(source.resolve()), "sha256": digest(source_bytes)},
        "source_dataset": {"path": str(documents.resolve()), "sha256": digest(document_bytes), "document_count": len(document_rows)},
        "question_count": len(questions),
        "document_gold_link_count": len(qrels),
        "unique_gold_document_count": len({row["document_id"] for row in qrels}),
        "gold_documents_per_question": dict(sorted(distribution.items())),
        "outputs": {name: {"path": name, "sha256": digest(content)} for name, content in outputs.items()},
        "validation": {
            "status": "PASS", "unique_query_id_count": len(seen_queries),
            "blank_query_id_count": 0, "blank_query_count": 0,
            "blank_reference_answer_count": 0, "blank_gold_id_count": 0,
            "duplicate_query_id_count": 0, "duplicate_gold_pair_count": 0,
            "missing_gold_document_ids": [], "source_columns_preserved": True,
            "all_questions_have_document_gold": True,
        },
        "chunk_qrels_status": "pending_separate_review",
        "notes": [
            "Provenance manifest only; not a required Runner input.",
            "reference_answer is preserved verbatim and is not mapped to evidence_text or offsets.",
            "No chunks, chunk qrels, embeddings, indexes or experiment results are generated.",
            "Output hashes exclude this manifest to avoid self-reference.",
        ],
    }
    # All input validation finishes before the first output mutation.
    output.mkdir(parents=True, exist_ok=False)
    for name, content in outputs.items():
        with (output / name).open("xb") as handle:
            handle.write(content)
    with (output / "evaluation_manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--documents", default=DOCUMENTS, type=Path)
    parser.add_argument("--output", default=OUTPUT, type=Path)
    args = parser.parse_args()
    print(json.dumps(convert(args.source, args.documents, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
