import json

from src.chunking.validate_chunks import validate_chunks


def test_valid_chunk_sequence(tmp_path):
    path = tmp_path / "chunks.jsonl"
    rows = [
        {"chunk_id": "p1_chunk_001", "document_id": "p1", "chunk_index": 0, "text": "a"},
        {"chunk_id": "p1_chunk_002", "document_id": "p1", "chunk_index": 1, "text": "b"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert validate_chunks(str(path), {"p1"}) == 2
