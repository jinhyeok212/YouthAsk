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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ChunkingAutomationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.documents_path = self.root / "data" / "documents.jsonl"
        self.configured_chunks_path = self.root / "data" / "chunks.jsonl"
        self.qrels_path = self.root / "eval" / "qrels.jsonl"
        self.configured_chunk_qrels_path = self.root / "eval" / "qrels_chunk.jsonl"

        text1 = "정책명: 청년 월세 지원\n신청 방법: 온라인 신청만 가능합니다.\n제출 서류: 주민등록등본"
        text2 = "정책명: 청년 일자리 지원\n지원 내용: 직무 교육을 제공합니다."
        evidence_start = text1.index("온라인 신청")
        evidence_end = evidence_start + len("온라인 신청")

        write_jsonl(
            self.documents_path,
            [
                {
                    "document_id": "policy_001",
                    "title": "청년 월세 지원",
                    "retrieval_text": text1,
                    "category": "주거",
                    "source": "온통청년",
                },
                {
                    "document_id": "policy_002",
                    "title": "청년 일자리 지원",
                    "retrieval_text": text2,
                    "category": "일자리",
                    "source": "온통청년",
                },
            ],
        )
        write_jsonl(
            self.qrels_path,
            [
                {
                    "query_id": "q001",
                    "document_id": "policy_001",
                    "relevance": 1,
                    "evidence_start_char": evidence_start,
                    "evidence_end_char": evidence_end,
                },
                {
                    "query_id": "q002",
                    "ground_truth_document_ids": ["policy_002"],
                },
            ],
        )

        self.config = self.make_config("fixed_20_ov5_v1", "fixed", 20, 5)
        self.dataset_info = {
            "document_path": str(self.documents_path),
            "manifest_path": str(self.root / "data" / "dataset_manifest.json"),
            "document_count": 2,
            "sha256": "dataset-sha-test",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_config(self, version: str, strategy: str, size: int, overlap: int) -> dict:
        return {
            "experiment_id": f"exp_test_{version}",
            "dataset": {
                "version": "test_dataset_v1",
                "preprocessing_version": "test_preprocess_v1",
                "document_path": str(self.documents_path),
                "chunk_path": str(self.configured_chunks_path),
            },
            "evaluation": {
                "document_qrels_path": str(self.qrels_path),
                "chunk_qrels_path": str(self.configured_chunk_qrels_path),
            },
            "chunking": {
                "version": version,
                "strategy": strategy,
                "size": size,
                "overlap": overlap,
                "unit": "characters",
                "target_field": "retrieval_text",
            },
        }

    def test_build_chunks_creates_condition_isolated_outputs(self) -> None:
        result = build_chunks(self.config, self.dataset_info)

        self.assertTrue(Path(result["chunk_path"]).exists())
        self.assertTrue(Path(result["manifest_path"]).exists())
        self.assertTrue(Path(result["chunk_qrels_path"]).exists())
        self.assertIn("fixed_20_ov5_v1", result["chunk_path"])
        self.assertGreater(result["chunk_count"], 0)
        self.assertEqual(result["chunk_qrels_status"], "review_required")

        manifest = read_json(Path(result["manifest_path"]))
        self.assertEqual(manifest["signature"]["chunking_version"], "fixed_20_ov5_v1")
        self.assertEqual(manifest["signature"]["strategy"], "fixed")
        self.assertEqual(manifest["generator"]["size_meaning"], "final chunk text character limit")

    def test_same_input_and_condition_reuses_identical_chunks(self) -> None:
        first = build_chunks(self.config, self.dataset_info)
        first_chunks = read_jsonl(Path(first["chunk_path"]))
        first_sha = first["chunk_sha256"]

        second = build_chunks(self.config, self.dataset_info)
        second_chunks = read_jsonl(Path(second["chunk_path"]))

        self.assertEqual(first["chunk_path"], second["chunk_path"])
        self.assertEqual(first_sha, second["chunk_sha256"])
        self.assertEqual(
            [row["chunk_id"] for row in first_chunks],
            [row["chunk_id"] for row in second_chunks],
        )
        self.assertEqual(
            [row["text"] for row in first_chunks],
            [row["text"] for row in second_chunks],
        )

    def test_different_conditions_create_separate_paths(self) -> None:
        fixed = build_chunks(self.config, self.dataset_info)
        section_config = self.make_config("section_40_ov5_v1", "section", 40, 5)
        section = build_chunks(section_config, self.dataset_info)

        self.assertNotEqual(fixed["chunk_path"], section["chunk_path"])
        self.assertIn("fixed_20_ov5_v1", fixed["chunk_path"])
        self.assertIn("section_40_ov5_v1", section["chunk_path"])

        section_manifest = read_json(Path(section["manifest_path"]))
        self.assertIn("section body split limit", section_manifest["generator"]["size_meaning"])

    def test_validate_chunks_rejects_duplicate_chunk_id(self) -> None:
        chunks_path = self.root / "bad" / "chunks.jsonl"
        write_jsonl(
            chunks_path,
            [
                {
                    "chunk_id": "dup",
                    "document_id": "policy_001",
                    "chunk_index": 0,
                    "text": "정상 청크",
                    "char_length": 5,
                },
                {
                    "chunk_id": "dup",
                    "document_id": "policy_001",
                    "chunk_index": 1,
                    "text": "다른 청크",
                    "char_length": 5,
                },
            ],
        )
        with self.assertRaises(ValueError):
            validate_chunks(self.documents_path, chunks_path, chunk_size=20, overlap=5)

    def test_build_chunk_qrels_maps_only_evidence_backed_rows(self) -> None:
        result = build_chunks(self.config, self.dataset_info)
        qrels_result = build_chunk_qrels(
            self.qrels_path,
            result["chunk_path"],
            result["chunk_qrels_path"],
            result["chunk_qrels_review_required_path"],
        )

        mapped = read_jsonl(Path(result["chunk_qrels_path"]))
        review = read_jsonl(Path(result["chunk_qrels_review_required_path"]))

        self.assertEqual(qrels_result["status"], "review_required")
        self.assertEqual({row["query_id"] for row in mapped}, {"q001"})
        self.assertEqual({row["query_id"] for row in review}, {"q002"})
        self.assertTrue(all(row["mapping_method"] == "evidence_span" for row in mapped))


if __name__ == "__main__":
    unittest.main()

