import csv
import hashlib
import json

import pytest

from scripts.prepare_eval_200_v1 import convert


@pytest.fixture
def inputs(tmp_path):
    rows = [
        {"query_id": f"q{i}", "query": f" 질문 {i} ", "reference_answer": f" 답변 {i} ",
         "ground_truth_document_ids": json.dumps(["d1", "d2"] if i < 7 else ["d1"]),
         "human_review_label": "1", "human_review_note": "원문 유지"}
        for i in range(200)
    ]
    source = tmp_path / "approved.csv"
    documents = tmp_path / "documents.jsonl"
    documents.write_text('{"document_id":"d1"}\n{"document_id":"d2"}\n', encoding="utf-8")
    return rows, source, documents, tmp_path / "output"


def write_csv(source, rows):
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_preserves_multigold_answers_approval_and_exact_hashes(inputs):
    rows, source, documents, output = inputs
    write_csv(source, rows)
    manifest = convert(source, documents, output)
    questions = [json.loads(line) for line in (output / "eval_questions.jsonl").read_text(encoding="utf-8").splitlines()]
    qrels = [json.loads(line) for line in (output / "qrels.jsonl").read_text(encoding="utf-8").splitlines()]
    for original, question in zip(rows, questions):
        assert question == {**original, "ground_truth_document_ids": json.loads(original["ground_truth_document_ids"])}
    assert len(qrels) == 207
    assert qrels[:2] == [{"query_id": "q0", "document_id": item, "relevance": 1} for item in ("d1", "d2")]
    assert not (output / "qrels_chunk.jsonl").exists()
    assert manifest["source_csv"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["source_dataset"]["sha256"] == hashlib.sha256(documents.read_bytes()).hexdigest()
    for name, info in manifest["outputs"].items():
        assert info["sha256"] == hashlib.sha256((output / name).read_bytes()).hexdigest()
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError):
        convert(source, documents, output)
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}


@pytest.mark.parametrize("case", ["count", "links", "duplicate_query", "blank_query", "blank_answer", "blank_id", "missing_document", "empty_array", "non_array", "invalid_json", "duplicate_gold"])
def test_rejects_invalid_inputs_before_creating_outputs(inputs, case):
    rows, source, documents, output = inputs
    if case == "count":
        rows.pop()
    elif case == "links":
        rows[0]["ground_truth_document_ids"] = '["d1"]'
    elif case == "duplicate_query":
        rows[1]["query_id"] = rows[0]["query_id"]
    elif case == "blank_query":
        rows[0]["query"] = " "
    elif case == "blank_answer":
        rows[0]["reference_answer"] = " "
    else:
        rows[0]["ground_truth_document_ids"] = {
            "blank_id": '[""]', "missing_document": '["absent"]',
            "empty_array": '[]', "non_array": '"d1"',
            "invalid_json": '[', "duplicate_gold": '["d1", "d1"]',
        }[case]
    write_csv(source, rows)
    with pytest.raises(ValueError):
        convert(source, documents, output)
    assert not output.exists()


def test_missing_csv_does_not_generate_data(inputs):
    _, source, documents, output = inputs
    with pytest.raises(FileNotFoundError):
        convert(source, documents, output)
    assert not output.exists()
