"""기존 KUREEmbedder를 재사용해 새 Chroma Index를 안전하게 생성한다."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

import numpy as np

from src.indexing.kure_adapter import KUREAdapter

# 공통 Chunk 계약에서 실제 임베딩 대상 필드는 `text`로 고정한다.
# chunking.target_field는 documents.jsonl에서 어떤 원본 필드를 청킹할지 의미한다.
CHUNK_TEXT_FIELD = "text"


def _create_collection(client: Any, name: str, metric: str) -> Any:
    """Chroma 버전 차이를 고려해 최신 방식 → 이전 metadata 방식 순으로 시도한다."""
    try:
        return client.create_collection(
            name=name,
            configuration={"hnsw": {"space": metric}},
        )
    except (TypeError, ValueError):
        return client.create_collection(
            name=name,
            metadata={"hnsw:space": metric},
        )


def _collection_names(client: Any) -> set[str]:
    """Chroma 버전에 따라 list_collections()가 객체/문자열을 반환하는 차이를 흡수한다."""
    names: set[str] = set()
    for item in client.list_collections():
        if isinstance(item, str):
            names.add(item)
        else:
            names.add(str(item.name))
    return names


def build_new_index(config: dict, chunk_info: dict) -> Dict[str, Any]:
    """
    현재 YAML 조건으로 새 Index를 만든다.

    안전 규칙
    --------
    1) 기존 완성 Collection은 삭제하지 않는다.
    2) 임시 Collection에 먼저 적재한다.
    3) 모든 record 검증이 성공한 뒤 최종 이름으로 변경한다.
    """
    # 무거운 의존성은 실제 인덱싱 시점에만 import한다.
    import chromadb
    from src.rag.embedding import batched, build_chroma_metadata, load_chunks

    chunk_path = Path(chunk_info["chunk_path"])
    index_cfg = config["index"]

    db_path = Path(index_cfg["db_path"])
    final_name = index_cfg["collection_name"]
    metric = index_cfg["distance_metric"]
    db_batch_size = int(index_cfg.get("db_batch_size", 256))

    db_path.mkdir(parents=True, exist_ok=True)

    # 업로드한 기존 embedding.py의 검증 로직을 그대로 재사용한다.
    rows, stats = load_chunks(
        input_path=chunk_path,
        text_field=CHUNK_TEXT_FIELD,
    )

    if stats["chunk_count"] != int(chunk_info["chunk_count"]):
        raise ValueError(
            "chunk_info와 실제 chunks.jsonl의 청크 수가 다릅니다: "
            f"chunk_info={chunk_info['chunk_count']}, file={stats['chunk_count']}"
        )

    client = chromadb.PersistentClient(path=str(db_path))

    # Chroma versions/environments may advertise a smaller maximum batch size.
    if hasattr(client, "get_max_batch_size"):
        try:
            db_batch_size = min(db_batch_size, int(client.get_max_batch_size()))
        except Exception:
            pass

    if final_name in _collection_names(client):
        raise ValueError(
            f"이미 Collection이 존재합니다: {final_name}. "
            "자동 Runner는 기존 Collection을 덮어쓰지 않습니다. "
            "새 index.version/db_path/collection_name을 사용하세요."
        )

    # 중간 실패 결과를 정상 Index로 오인하지 않도록 임시 이름 사용.
    temp_name = f"{final_name}__building__{uuid4().hex[:8]}"
    collection = _create_collection(client, temp_name, metric)
    try:
        # Model initialization can fail too (download/device/dependency errors).
        # Include it in cleanup so an empty temporary collection is not leaked.
        adapter = KUREAdapter(config)
        started = time.perf_counter()

        for batch_rows in batched(rows, db_batch_size):
            texts = [str(row[CHUNK_TEXT_FIELD]) for row in batch_rows]
            vectors = adapter.encode_documents(texts)

            # KUREEmbedder 내부 검증에 더해 Index Builder 경계에서도 재검증한다.
            if vectors.ndim != 2 or vectors.shape[1] != adapter.dimension:
                raise ValueError(
                    "Embedding dimension/shape 오류: "
                    f"expected_dim={adapter.dimension}, actual_shape={vectors.shape}"
                )
            if not np.isfinite(vectors).all():
                raise ValueError("Embedding에 NaN 또는 Inf가 존재합니다.")
            if np.any(np.linalg.norm(vectors, axis=1) == 0):
                raise ValueError("0-vector가 존재합니다.")

            collection.add(
                ids=[str(row["chunk_id"]) for row in batch_rows],
                documents=texts,
                embeddings=vectors.tolist(),
                metadatas=[build_chroma_metadata(row) for row in batch_rows],
            )

        actual_count = collection.count()
        expected_count = int(chunk_info["chunk_count"])
        if actual_count != expected_count:
            raise RuntimeError(
                "Chunk 수와 Chroma record 수가 다릅니다: "
                f"expected={expected_count}, actual={actual_count}"
            )

        # 모든 적재/검증이 성공한 경우에만 최종 Collection 이름 부여.
        collection.modify(name=final_name)

    except Exception:
        # 실패한 임시 Collection만 정리한다. 기존 실험 Collection은 절대 삭제하지 않는다.
        try:
            client.delete_collection(temp_name)
        except Exception:
            pass
        raise

    build_time = time.perf_counter() - started
    return {
        "index_version": index_cfg["version"],
        "db_path": str(db_path),
        "collection_name": final_name,
        "reused": False,
        "index_count": int(chunk_info["chunk_count"]),
        "build_time_seconds": round(build_time, 4),
    }
