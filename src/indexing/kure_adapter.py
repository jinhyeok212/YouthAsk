"""Adapter from the existing KURE-v1 implementation to runner contracts."""

from __future__ import annotations

from typing import List

import numpy as np


class KUREAdapter:
    def __init__(self, config: dict) -> None:
        from src.rag.embedding import KUREEmbedder, choose_device

        embedding_cfg = config["embedding"]
        model_name = embedding_cfg["model"]
        revision = embedding_cfg.get("revision")
        batch_size = int(embedding_cfg["batch_size"])
        device = choose_device(embedding_cfg.get("device", "auto"))

        self.expected_dimension = int(embedding_cfg["dimension"])
        self.normalize = bool(embedding_cfg["normalize"])

        if not self.normalize:
            raise ValueError(
                "현재 KUREEmbedder는 normalize_embeddings=True로 구현되어 있습니다. "
                "embedding.normalize=true를 사용하세요."
            )

        self.embedder = KUREEmbedder(
            model_name=model_name,
            device=device,
            batch_size=batch_size,
            revision=revision,
        )

        actual_dim = self.embedder.embedding_dim
        if actual_dim is not None and actual_dim != self.expected_dimension:
            raise ValueError(
                "Embedding dimension 불일치: "
                f"config={self.expected_dimension}, model={actual_dim}"
            )

    @property
    def dimension(self) -> int:
        return self.expected_dimension

    def encode_documents(self, texts: List[str]) -> np.ndarray:
        return self.embedder.embed_documents(texts=texts, show_progress_bar=False)

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        if not queries:
            return np.empty((0, self.expected_dimension), dtype=np.float32)
        return np.vstack([self.embedder.embed_query(q) for q in queries]).astype(np.float32)
