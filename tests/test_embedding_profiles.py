"""Tests that do not download embedding model weights."""

import unittest

import numpy as np

from src.indexing.profiled_embedder import ProfiledEmbedder
from src.rag.embedding_profiles import PROFILES, get_profile, get_profile_by_model


class EmbeddingProfileTests(unittest.TestCase):
    def test_dimensions_and_input_contracts(self) -> None:
        kure = PROFILES["kure_v3"]
        snowflake = PROFILES["snowflake_arctic_l_v2_ko"]

        self.assertEqual(kure.dimension, 2048)
        self.assertEqual(kure.query_method, "encode_query")
        self.assertEqual(kure.document_method, "encode_document")
        self.assertEqual(snowflake.dimension, 1024)
        self.assertEqual(snowflake.query_prefix, "query: ")
        self.assertEqual(snowflake.document_prefix, "")

    def test_revision_mismatch_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            get_profile("kure_v3", "main")

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            get_profile("unknown")

    def test_model_lookup_keeps_kure_v1_on_legacy_path(self) -> None:
        self.assertIsNone(get_profile_by_model("nlpai-lab/KURE-v1"))
        self.assertEqual(
            get_profile_by_model("nlpai-lab/KURE-v3"), PROFILES["kure_v3"]
        )

    def test_snowflake_prefixes_queries_but_not_documents(self) -> None:
        calls = []

        class FakeModel:
            def encode(self, texts, **kwargs):
                calls.append(list(texts))
                vectors = np.zeros((len(texts), 1024), dtype=np.float32)
                vectors[:, 0] = 1.0
                return vectors

        embedder = ProfiledEmbedder.__new__(ProfiledEmbedder)
        embedder.profile = PROFILES["snowflake_arctic_l_v2_ko"]
        embedder.batch_size = 32
        embedder.model = FakeModel()

        embedder.encode_queries(["청년 지원은?"])
        embedder.encode_documents(["지원 정책 본문"])

        self.assertEqual(calls[0], ["query: 청년 지원은?"])
        self.assertEqual(calls[1], ["지원 정책 본문"])

    def test_kure_v3_uses_asymmetric_sentence_transformer_methods(self) -> None:
        calls = []

        class FakeModel:
            def _vectors(self, texts):
                vectors = np.zeros((len(texts), 2048), dtype=np.float32)
                vectors[:, 0] = 1.0
                return vectors

            def encode_query(self, texts, **kwargs):
                calls.append(("query", list(texts)))
                return self._vectors(texts)

            def encode_document(self, texts, **kwargs):
                calls.append(("document", list(texts)))
                return self._vectors(texts)

        embedder = ProfiledEmbedder.__new__(ProfiledEmbedder)
        embedder.profile = PROFILES["kure_v3"]
        embedder.batch_size = 32
        embedder.model = FakeModel()

        embedder.encode_queries(["질문"])
        embedder.encode_documents(["문서"])

        self.assertEqual(calls, [("query", ["질문"]), ("document", ["문서"])])


if __name__ == "__main__":
    unittest.main()
