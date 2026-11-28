"""SentenceTransformer wrapper for models with asymmetric retrieval inputs."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from src.rag.embedding_profiles import EmbeddingProfile


class ProfiledEmbedder:
    """Apply a pinned model profile to document and query encoding."""

    def __init__(
        self,
        profile: EmbeddingProfile,
        device: str,
        batch_size: int,
        dtype: str = "float32",
        model_factory: Any = None,
    ) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        dtype_map = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        if dtype not in dtype_map:
            raise ValueError(f"지원하지 않는 dtype입니다: {dtype}")
        if device == "cpu" and dtype == "float16":
            raise ValueError("CPU에서는 float16을 지원 설정으로 사용하지 않습니다.")

        self.profile = profile
        self.device = device
        self.batch_size = batch_size
        self.dtype = dtype
        factory = model_factory or SentenceTransformer
        self.model = factory(
            profile.model_name,
            revision=profile.revision,
            device=device,
            model_kwargs={"torch_dtype": dtype_map[dtype]},
        )
        if hasattr(self.model, "get_embedding_dimension"):
            actual_dimension = self.model.get_embedding_dimension()
        else:
            actual_dimension = self.model.get_sentence_embedding_dimension()
        if actual_dimension != profile.dimension:
            raise RuntimeError(
                "모델 차원이 profile과 다릅니다: "
                f"expected={profile.dimension}, actual={actual_dimension}"
            )

    def _encode(self, texts: Sequence[str], input_type: str) -> np.ndarray:
        if input_type == "query":
            method_name = self.profile.query_method
            prefix = self.profile.query_prefix
            batch_size = 1
        else:
            method_name = self.profile.document_method
            prefix = self.profile.document_prefix
            batch_size = self.batch_size

        prepared = [f"{prefix}{text}" for text in texts]
        vectors = getattr(self.model, method_name)(
            prepared,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=self.profile.normalize,
        )
        vectors = np.asarray(vectors, dtype=np.float32)
        self._validate(vectors, len(texts))
        return vectors

    def encode_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._encode(texts, "document")

    def encode_queries(self, queries: Sequence[str]) -> np.ndarray:
        if not queries:
            return np.empty((0, self.profile.dimension), dtype=np.float32)
        cleaned = [str(query).strip() for query in queries]
        if any(not query for query in cleaned):
            raise ValueError("빈 query가 있습니다.")
        return self._encode(cleaned, "query")

    def _validate(self, vectors: np.ndarray, expected_count: int) -> None:
        expected_shape = (expected_count, self.profile.dimension)
        if vectors.shape != expected_shape:
            raise ValueError(
                f"Embedding shape 불일치: expected={expected_shape}, actual={vectors.shape}"
            )
        if not np.all(np.isfinite(vectors)):
            raise ValueError("Embedding에 NaN 또는 Inf가 존재합니다.")
        norms = np.linalg.norm(vectors, axis=1)
        if np.any(norms == 0):
            raise ValueError("0-vector가 존재합니다.")
        if self.profile.normalize and not np.allclose(norms, 1.0, atol=1e-3):
            raise ValueError(
                f"정규화 검증 실패: min={norms.min():.6f}, max={norms.max():.6f}"
            )
