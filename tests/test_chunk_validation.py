from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.chunking.build_chunk_qrels import build_chunk_qrels
from src.chunking.build_chunks import build_chunks
from src.chunking.validate_chunks import validate_chunks


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class ChunkingAutomationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.documents_path = self.root / "data" / "documents.jsonl"
        self.chunks_path = self.root / "data" / "chunks.jsonl"
        self.qrels_path = self.root / "eval" / "qrels.jsonl"
        self.chunk_qrels_path = self.root / "eval" / "qrels_chunk.jsonl"

        write_jsonl(
            self.documents_path,
            [
                {
                    "document_id": "policy_001",
                    "title": "청년 월세 지원",
                    "retrieval_text": "청년 월세 지원은 주거비를 지원합니다. 신청은 온라인으로 합니다.",
                    "category": "주거",
                    "source": "온통청년",
                },
                {
                    "document_id": "policy_002",
                    "title": "청년 일자리 지원",
                    "content": "청년 일자리 정책은 취업 준비와 직무 교육을 지원합니다.",
                    "category": "일자리",
                    "source": "온통청년",
                },
            ],
        )
        write_jsonl(
            self.qrels_path,
            [
                {"query_id": "q001", "ground_truth_document_ids": ["policy_001"]},
                {"query_id": "q002", "document_id": "policy_002", "relevance": 1},
            ],
        )

        self.config = {
            "experiment_id": "exp_test_chunking_v1",
            "dataset": {
                "document_path": str(self.documents_path),
                "chunk_path": str(self.chunks_path),
            },
            "evaluation": {
                "document_qrels_path": str(self.qrels_path),
                "chunk_qrels_path": str(self.chunk_qrels_path),
            },
            "chunking": {
                "version": "c2_section_20_ov5_v1",
                "size": 20,
                "overlap": 5,
                "unit": "characters",
            },
        }
        self.dataset_info = {
            "document_path": str(self.documents_path),
            "manifest_path": str(self.root / "data" / "dataset_manifest.json"),
            "document_count": 2,
            "sha256": "test",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_build_chunks_creates_contract_outputs(self) -> None:
        result = build_chunks(self.config, self.dataset_info)

        self.assertEqual(set(result), {"chunk_path", "manifest_path", "chunk_count", "chunk_qrels_path"})
        self.assertTrue(Path(result["chunk_path"]).exists())
        self.assertTrue(Path(result["manifest_path"]).exists())
        self.assertTrue(Path(result["chunk_qrels_path"]).exists())
        self.assertGreater(result["chunk_count"], 0)

        chunks = read_jsonl(self.chunks_path)
        self.assertTrue(all("text" in chunk for chunk in chunks))
        self.assertTrue(all(chunk["chunk_id"].startswith(chunk["document_id"]) for chunk in chunks))

    def test_validate_chunks_accepts_valid_chunks(self) -> None:
        build_chunks(self.config, self.dataset_info)
        validation = validate_chunks(
            self.documents_path,
            self.chunks_path,
            chunk_size=20,
            overlap=5,
        )
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["document_count"], 2)

    def test_validate_chunks_rejects_duplicate_chunk_id(self) -> None:
        write_jsonl(
            self.chunks_path,
            [
                {
                    "chunk_id": "dup",
                    "document_id": "policy_001",
                    "text": "정상 청크",
                    "char_length": 5,
                },
                {
                    "chunk_id": "dup",
                    "document_id": "policy_001",
                    "text": "다른 청크",
                    "char_length": 5,
                },
            ],
        )
        with self.assertRaises(ValueError):
            validate_chunks(self.documents_path, self.chunks_path, chunk_size=20, overlap=5)

    def test_validate_chunks_rejects_unknown_document_id(self) -> None:
        write_jsonl(
            self.chunks_path,
            [
                {
                    "chunk_id": "unknown__chunk_000",
                    "document_id": "unknown",
                    "text": "정상 청크",
                    "char_length": 5,
                }
            ],
        )
        with self.assertRaises(ValueError):
            validate_chunks(self.documents_path, self.chunks_path, chunk_size=20, overlap=5)

    def test_build_chunk_qrels_maps_document_qrels_to_chunk_qrels(self) -> None:
        build_chunks(self.config, self.dataset_info)
        result = build_chunk_qrels(self.qrels_path, self.chunks_path, self.chunk_qrels_path)

        self.assertEqual(result["query_count"], 2)
        rows = read_jsonl(self.chunk_qrels_path)
        self.assertEqual({row["query_id"] for row in rows}, {"q001", "q002"})
        self.assertTrue(all(row["ground_truth_chunk_ids"] for row in rows))


if __name__ == "__main__":
    unittest.main()

