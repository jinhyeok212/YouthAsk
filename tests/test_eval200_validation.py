import json
import hashlib

import pytest

from src.evaluation.validate_inputs import validate_evaluation_inputs
from src.chunking.manifest import sha256_text_variants as chunk_hash_variants
from src.data.validate_documents import sha256_text_variants as document_hash_variants


def test_eval200_count_is_checked_before_indexing(tmp_path):
    questions = tmp_path / "questions.jsonl"
    questions.write_text(
        json.dumps({"query_id": "q1", "query": "질문"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    config = {
        "evaluation": {
            "questions_path": str(questions),
            "expected_question_count": 200,
        }
    }

    with pytest.raises(ValueError, match="expected=200, actual=1"):
        validate_evaluation_inputs(config, {}, {})


@pytest.mark.parametrize("variant_reader", [document_hash_variants, chunk_hash_variants])
def test_git_text_hash_accepts_lf_and_crlf_checkout(tmp_path, variant_reader):
    path = tmp_path / "rows.jsonl"
    lf_bytes = b'{"id": 1}\n{"id": 2}\n'
    path.write_bytes(lf_bytes)

    expected_crlf = hashlib.sha256(lf_bytes.replace(b"\n", b"\r\n")).hexdigest()

    assert expected_crlf in variant_reader(path)
