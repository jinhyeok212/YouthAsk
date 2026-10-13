"""Document and query embedding interfaces."""
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
KURE-v1 + ChromaDB 단일 파일 임베딩/검색 파이프라인
===================================================

대상 입력:
    c2_section_800_chunks.jsonl

현재 데이터 스키마 예:
{
    "chunk_id": "...",
    "document_id": "...",
    "chunk_index": 0,
    "section": "overview",
    "section_chunk_index": 0,
    "text": "...",                  # 실제 임베딩 대상
    "body_text": "...",
    "text_char_count": 346,
    "body_char_count": 182,
    "source": "ontong_youth",
    "title": "...",
    "url": "...",
    "metadata": {...}
}

이 스크립트가 하는 일:
1. JSONL 로드/검증
2. KURE-v1 모델 로드
3. chunk["text"] 임베딩
4. 임베딩 정합성 검증
5. ChromaDB Persistent Collection 생성
6. Chunk + Vector + Metadata 저장
7. Manifest 저장
8. 선택적으로 테스트 Query를 임베딩하여 Top-k 검색

설치:
    pip install -U sentence-transformers chromadb torch numpy tqdm

실행 예:
    python kure_chroma_pipeline.py \
        --input c2_section_800_chunks.jsonl \
        --db-dir ./chroma_db \
        --collection c2_kure_v1_section800_v1 \
        --rebuild

검색까지 같이 테스트:
    python kure_chroma_pipeline.py \
        --input c2_section_800_chunks.jsonl \
        --db-dir ./chroma_db \
        --collection c2_kure_v1_section800_v1 \
        --rebuild \
        --test-query "춘천시 청년근로자에게 어떤 복지 지원을 하나요?" \
        --top-k 5

이미 만든 DB에서 검색만:
    python kure_chroma_pipeline.py \
        --db-dir ./chroma_db \
        --collection c2_kure_v1_section800_v1 \
        --search-only \
        --test-query "지원 대상의 나이 조건은 무엇인가요?" \
        --top-k 5

Metadata Filter 예:
    python kure_chroma_pipeline.py \
        --db-dir ./chroma_db \
        --collection c2_kure_v1_section800_v1 \
        --search-only \
        --test-query "신청 방법은?" \
        --where-json '{"section":"application"}'
"""


import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

try:
    import chromadb
except ImportError as e:
    raise ImportError(
        "chromadb가 설치되어 있지 않습니다. "
        "`pip install -U chromadb` 를 실행하세요."
    ) from e


# ============================================================
# 기본 설정
# ============================================================

DEFAULT_MODEL_NAME = "nlpai-lab/KURE-v1"
DEFAULT_COLLECTION = "c2_kure_v1_section800_v1"
DEFAULT_DB_DIR = "./chroma_db"

# 현재 업로드된 데이터에서는 text가 검색용 Chunk 텍스트임.
DEFAULT_TEXT_FIELD = "text"

# Chroma에 한 번에 넣는 레코드 수.
# 환경에 따라 128~1000 정도에서 조절 가능.
DEFAULT_DB_BATCH_SIZE = 256

# KURE 임베딩 batch.
# GPU 메모리 부족 시 32 -> 16 -> 8 순서로 낮추면 됨.
DEFAULT_EMBED_BATCH_SIZE = 32


# ============================================================
# 유틸리티
# ============================================================

def choose_device(requested: str) -> str:
    """Resolve auto/cuda/cpu/mps and fail clearly for unavailable explicit devices."""
    requested = requested.lower()

    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("embedding.device=cuda 이지만 CUDA를 사용할 수 없습니다.")
        return "cuda"

    if requested == "mps":
        mps_available = (
            hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()
        )
        if not mps_available:
            raise RuntimeError("embedding.device=mps 이지만 MPS를 사용할 수 없습니다.")
        return "mps"

    if requested == "cpu":
        return "cpu"

    if requested != "auto":
        raise ValueError(f"지원하지 않는 device 값입니다: {requested}")

    if torch.cuda.is_available():
        return "cuda"

    if (
        hasattr(torch.backends, "mps")
        and torch.backends.mps.is_available()
    ):
        return "mps"

    return "cpu"


def batched(seq: Sequence[Any], batch_size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(seq), batch_size):
        yield seq[start : start + batch_size]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """
    입력 데이터 버전 추적용 SHA256.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def json_safe_metadata_value(value: Any) -> Optional[Any]:
    """
    Chroma Metadata에 안전하게 들어가도록 값 정리.

    현재 입력 metadata 안에는 list가 존재함:
      normalized_lclsf_list
      normalized_mclsf_list
      normalized_keywords

    Chroma 버전별 list metadata 지원 차이를 피하기 위해
    list/dict는 JSON 문자열로 변환한다.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if np.isfinite(value):
            return value
        return None

    if isinstance(value, str):
        # 공백-only 값은 저장하지 않음.
        cleaned = value.strip()
        return cleaned if cleaned else None

    if isinstance(value, (list, dict, tuple)):
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    return str(value)


def build_chroma_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    검색 결과 분석에 필요한 Top-level 필드 + 원본 metadata를 병합한다.
    """
    result: Dict[str, Any] = {}

    # 평가/추적에 중요한 top-level 필드.
    important_fields = [
        "document_id",
        "chunk_index",
        "section",
        "section_chunk_index",
        "source",
        "title",
        "url",
        "text_char_count",
        "body_char_count",
    ]

    for key in important_fields:
        if key in row:
            value = json_safe_metadata_value(row[key])
            if value is not None:
                result[key] = value

    nested = row.get("metadata") or {}
    if not isinstance(nested, dict):
        raise ValueError(
            f"metadata가 dict가 아닙니다. chunk_id={row.get('chunk_id')}"
        )

    for key, raw_value in nested.items():
        value = json_safe_metadata_value(raw_value)
        if value is None:
            continue

        # top-level 값이 있으면 그것을 우선.
        if key not in result:
            result[key] = value

    return result


# ============================================================
# 데이터 로딩 / 검증
# ============================================================

def load_chunks(
    input_path: Path,
    text_field: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    JSONL 전체를 읽고 최소 스키마/중복/빈 텍스트를 검증.
    """

    required = {
        "chunk_id",
        "document_id",
        text_field,
    }

    rows: List[Dict[str, Any]] = []
    chunk_ids: List[str] = []
    document_ids: List[str] = []
    sections: Dict[str, int] = {}
    source_counts: Dict[str, int] = {}

    skipped_empty_lines = 0

    with input_path.open("r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            if not raw_line.strip():
                skipped_empty_lines += 1
                continue

            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"JSON 파싱 실패: line={line_no}, error={e}"
                ) from e

            if not isinstance(row, dict):
                raise ValueError(
                    f"각 JSONL row는 object여야 합니다. line={line_no}"
                )

            missing = required - set(row)
            if missing:
                raise ValueError(
                    f"필수 필드 누락: line={line_no}, missing={sorted(missing)}"
                )

            chunk_id = str(row["chunk_id"]).strip()
            document_id = str(row["document_id"]).strip()
            text = row[text_field]

            if not chunk_id:
                raise ValueError(f"빈 chunk_id: line={line_no}")

            if not document_id:
                raise ValueError(f"빈 document_id: line={line_no}")

            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"빈/비정상 검색 텍스트: line={line_no}, chunk_id={chunk_id}"
                )

            chunk_ids.append(chunk_id)
            document_ids.append(document_id)

            section = str(row.get("section", "UNKNOWN"))
            sections[section] = sections.get(section, 0) + 1

            source = str(row.get("source", "UNKNOWN"))
            source_counts[source] = source_counts.get(source, 0) + 1

            rows.append(row)

    duplicate_count = len(chunk_ids) - len(set(chunk_ids))
    if duplicate_count:
        counter: Dict[str, int] = {}
        for cid in chunk_ids:
            counter[cid] = counter.get(cid, 0) + 1
        duplicates = [k for k, v in counter.items() if v > 1][:10]

        raise ValueError(
            f"중복 chunk_id가 {duplicate_count}건 존재합니다. "
            f"예시={duplicates}"
        )

    text_lengths = [len(row[text_field]) for row in rows]

    stats = {
        "chunk_count": len(rows),
        "document_count": len(set(document_ids)),
        "duplicate_chunk_id_count": duplicate_count,
        "skipped_empty_line_count": skipped_empty_lines,
        "text_char_min": min(text_lengths) if text_lengths else 0,
        "text_char_mean": float(np.mean(text_lengths)) if text_lengths else 0.0,
        "text_char_median": float(np.median(text_lengths)) if text_lengths else 0.0,
        "text_char_max": max(text_lengths) if text_lengths else 0,
        "section_counts": sections,
        "source_counts": source_counts,
    }

    return rows, stats


# ============================================================
# KURE-v1
# ============================================================

class KUREEmbedder:
    """
    KURE-v1 문서/질문 임베딩 래퍼.
    """

    def __init__(
        self,
        model_name: str,
        device: str,
        batch_size: int,
        revision: Optional[str] = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.revision = revision

        print("\n" + "=" * 70)
        print("[KURE-v1 모델 로딩]")
        print(f"model       : {self.model_name}")
        print(f"revision    : {self.revision or 'default'}")
        print(f"device      : {self.device}")
        print(f"batch_size  : {self.batch_size}")
        print("=" * 70)

        started = time.perf_counter()

        model_kwargs = {"device": self.device}
        if self.revision:
            model_kwargs["revision"] = self.revision

        self.model = SentenceTransformer(
            self.model_name,
            **model_kwargs,
        )

        # sentence-transformers renamed this API in newer releases.
        if hasattr(self.model, "get_embedding_dimension"):
            self.embedding_dim = self.model.get_embedding_dimension()
        else:
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
        self.max_seq_length = getattr(self.model, "max_seq_length", None)

        print(f"embedding_dim  : {self.embedding_dim}")
        print(f"max_seq_length : {self.max_seq_length}")
        print(f"load_time_sec  : {time.perf_counter() - started:.2f}")

    def embed_documents(
        self,
        texts: List[str],
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        """
        Chunk 문서 임베딩.

        normalize_embeddings=True:
        - cosine 검색 조건을 일관되게 유지
        - 각 벡터의 L2 norm이 약 1이 되도록 함
        """

        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=show_progress_bar,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        embeddings = np.asarray(embeddings, dtype=np.float32)

        self.validate_embeddings(
            embeddings=embeddings,
            expected_count=len(texts),
        )

        return embeddings

    def embed_query(self, query: str) -> np.ndarray:
        """
        사용자 질문 1건 임베딩.
        """

        query = query.strip()
        if not query:
            raise ValueError("query가 비어 있습니다.")

        embedding = self.model.encode(
            [query],
            batch_size=1,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        embedding = np.asarray(embedding, dtype=np.float32)

        self.validate_embeddings(
            embeddings=embedding,
            expected_count=1,
        )

        return embedding[0]

    def validate_embeddings(
        self,
        embeddings: np.ndarray,
        expected_count: int,
    ) -> None:
        """
        임베딩 정합성 검사.
        """

        if embeddings.ndim != 2:
            raise ValueError(
                f"Embedding은 2차원이어야 합니다. shape={embeddings.shape}"
            )

        if embeddings.shape[0] != expected_count:
            raise ValueError(
                f"입력 수와 벡터 수 불일치: "
                f"expected={expected_count}, actual={embeddings.shape[0]}"
            )

        if self.embedding_dim is not None:
            if embeddings.shape[1] != self.embedding_dim:
                raise ValueError(
                    f"Embedding 차원 불일치: "
                    f"model={self.embedding_dim}, actual={embeddings.shape[1]}"
                )

        if not np.all(np.isfinite(embeddings)):
            raise ValueError("Embedding에 NaN 또는 Inf가 존재합니다.")

        norms = np.linalg.norm(embeddings, axis=1)

        if np.any(norms == 0):
            raise ValueError("0-vector가 존재합니다.")

        # normalize_embeddings=True라면 거의 1.
        if not np.allclose(norms, 1.0, atol=1e-3):
            print(
                "[경고] 일부 embedding norm이 1에서 벗어났습니다. "
                f"min={norms.min():.6f}, max={norms.max():.6f}"
            )


# ============================================================
# Chroma
# ============================================================

def get_or_create_collection(
    client: Any,
    collection_name: str,
    rebuild: bool,
) -> Any:
    """
    Chroma 버전별 collection 생성 API 차이를 조금 흡수한다.

    우선 최신 configuration 방식 시도:
        configuration={"hnsw": {"space": "cosine"}}

    실패하면 이전 방식:
        metadata={"hnsw:space": "cosine"}
    """

    if rebuild:
        try:
            client.delete_collection(collection_name)
            print(f"[Chroma] 기존 Collection 삭제: {collection_name}")
        except Exception:
            pass

    try:
        return client.get_collection(collection_name)
    except Exception:
        pass

    try:
        collection = client.create_collection(
            name=collection_name,
            configuration={
                "hnsw": {
                    "space": "cosine",
                }
            },
        )
        print("[Chroma] cosine collection 생성(configuration 방식)")
        return collection

    except (TypeError, ValueError):
        collection = client.create_collection(
            name=collection_name,
            metadata={
                "hnsw:space": "cosine",
            },
        )
        print("[Chroma] cosine collection 생성(metadata 방식)")
        return collection


def upsert_batch(
    collection: Any,
    rows: Sequence[Dict[str, Any]],
    embeddings: np.ndarray,
    text_field: str,
) -> None:

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for row in rows:
        ids.append(str(row["chunk_id"]))
        documents.append(str(row[text_field]))
        metadatas.append(build_chroma_metadata(row))

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings.tolist(),
        metadatas=metadatas,
    )


# ============================================================
# Index Build
# ============================================================

def build_index(
    input_path: Path,
    db_dir: Path,
    collection_name: str,
    model_name: str,
    text_field: str,
    device: str,
    embed_batch_size: int,
    db_batch_size: int,
    rebuild: bool,
) -> Tuple[KUREEmbedder, Any, Dict[str, Any]]:

    print("\n[1/6] JSONL 로드/검증")
    rows, dataset_stats = load_chunks(
        input_path=input_path,
        text_field=text_field,
    )

    print(json.dumps(dataset_stats, ensure_ascii=False, indent=2))

    print("\n[2/6] KURE-v1 모델 준비")
    embedder = KUREEmbedder(
        model_name=model_name,
        device=device,
        batch_size=embed_batch_size,
    )

    print("\n[3/6] ChromaDB 준비")
    db_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(db_dir)
    )

    collection = get_or_create_collection(
        client=client,
        collection_name=collection_name,
        rebuild=rebuild,
    )

    print(f"db_dir      : {db_dir.resolve()}")
    print(f"collection  : {collection_name}")
    print(f"before_count: {collection.count()}")

    print("\n[4/6] Chunk Embedding + ChromaDB Upsert")

    build_started = time.perf_counter()
    total_embedding_sec = 0.0

    all_norm_min = float("inf")
    all_norm_max = 0.0

    batches = list(batched(rows, db_batch_size))

    for batch_rows in tqdm(
        batches,
        desc="Embedding & indexing",
        unit="batch",
    ):
        texts = [
            str(row[text_field])
            for row in batch_rows
        ]

        t0 = time.perf_counter()

        embeddings = embedder.embed_documents(
            texts,
            show_progress_bar=False,
        )

        total_embedding_sec += time.perf_counter() - t0

        norms = np.linalg.norm(embeddings, axis=1)
        all_norm_min = min(all_norm_min, float(norms.min()))
        all_norm_max = max(all_norm_max, float(norms.max()))

        upsert_batch(
            collection=collection,
            rows=batch_rows,
            embeddings=embeddings,
            text_field=text_field,
        )

    build_sec = time.perf_counter() - build_started

    print("\n[5/6] 저장 결과 검증")

    actual_count = collection.count()
    expected_count = dataset_stats["chunk_count"]

    print(f"expected chunk count : {expected_count:,}")
    print(f"chroma record count  : {actual_count:,}")

    if actual_count != expected_count:
        raise RuntimeError(
            "Chroma record 수가 입력 Chunk 수와 다릅니다. "
            f"expected={expected_count}, actual={actual_count}"
        )

    print("\n[6/6] Manifest 저장")

    manifest: Dict[str, Any] = {
        "experiment": {
            "collection_name": collection_name,
            "embedding_model": model_name,
            "text_field": text_field,
            "distance_metric": "cosine",
            "normalize_embeddings": True,
        },
        "input": {
            "path": str(input_path.resolve()),
            "sha256": sha256_file(input_path),
        },
        "dataset_stats": dataset_stats,
        "embedding": {
            "embedding_dimension": embedder.embedding_dim,
            "max_seq_length": embedder.max_seq_length,
            "device": device,
            "embedding_batch_size": embed_batch_size,
            "db_batch_size": db_batch_size,
            "embedding_time_sec": round(total_embedding_sec, 4),
            "full_index_build_time_sec": round(build_sec, 4),
            "vector_norm_min": round(all_norm_min, 6),
            "vector_norm_max": round(all_norm_max, 6),
            "nan_or_inf_count": 0,
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "chromadb": getattr(chromadb, "__version__", "unknown"),
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_name": (
                torch.cuda.get_device_name(0)
                if torch.cuda.is_available()
                else None
            ),
        },
        "created_at_unix": time.time(),
    }

    manifest_path = (
        db_dir
        / f"{collection_name}__manifest.json"
    )

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            manifest,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"manifest: {manifest_path.resolve()}")

    return embedder, collection, manifest


# ============================================================
# Search
# ============================================================

def search(
    embedder: KUREEmbedder,
    collection: Any,
    query: str,
    top_k: int,
    where: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    if collection.count() == 0:
        raise RuntimeError("Collection이 비어 있습니다.")

    query_started = time.perf_counter()

    query_vector = embedder.embed_query(query)

    query_kwargs: Dict[str, Any] = {
        "query_embeddings": [query_vector.tolist()],
        "n_results": min(top_k, collection.count()),
        "include": [
            "documents",
            "metadatas",
            "distances",
        ],
    }

    if where:
        query_kwargs["where"] = where

    raw = collection.query(
        **query_kwargs
    )

    latency_ms = (
        time.perf_counter() - query_started
    ) * 1000.0

    ids = raw.get("ids", [[]])[0]
    documents = raw.get("documents", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    results: List[Dict[str, Any]] = []

    for rank, (cid, doc, meta, distance) in enumerate(
        zip(
            ids,
            documents,
            metadatas,
            distances,
        ),
        start=1,
    ):
        distance = float(distance)

        results.append(
            {
                "rank": rank,
                "chunk_id": cid,
                "document_id": (
                    meta.get("document_id")
                    if isinstance(meta, dict)
                    else None
                ),
                "distance": distance,
                # cosine distance 기준 이해 편의를 위한 파생값.
                # 평가 원본에는 distance를 유지하는 것을 권장.
                "cosine_similarity_estimate": 1.0 - distance,
                "text": doc,
                "metadata": meta,
            }
        )

    return {
        "query": query,
        "top_k": top_k,
        "where": where,
        "retrieval_latency_ms": round(latency_ms, 3),
        "result_count": len(results),
        "results": results,
    }


def load_existing_for_search(
    db_dir: Path,
    collection_name: str,
    model_name: str,
    device: str,
    embed_batch_size: int,
) -> Tuple[KUREEmbedder, Any]:

    if not db_dir.exists():
        raise FileNotFoundError(
            f"Chroma DB 경로가 없습니다: {db_dir}"
        )

    client = chromadb.PersistentClient(
        path=str(db_dir)
    )

    try:
        collection = client.get_collection(
            collection_name
        )
    except Exception as e:
        raise RuntimeError(
            f"Collection을 찾지 못했습니다: {collection_name}"
        ) from e

    embedder = KUREEmbedder(
        model_name=model_name,
        device=device,
        batch_size=embed_batch_size,
    )

    return embedder, collection


# ============================================================
# CLI
# ============================================================

def parse_where(where_json: Optional[str]) -> Optional[Dict[str, Any]]:
    if not where_json:
        return None

    try:
        where = json.loads(where_json)
    except json.JSONDecodeError as e:
        raise ValueError(
            "--where-json 값은 올바른 JSON이어야 합니다."
        ) from e

    if not isinstance(where, dict):
        raise ValueError("--where-json의 최상위 값은 object여야 합니다.")

    return where


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "KURE-v1로 JSONL Chunk를 임베딩하여 "
            "ChromaDB에 저장하고 Top-k 검색하는 단일 스크립트"
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("c2_section_800_chunks.jsonl"),
        help="Chunk JSONL 경로",
    )

    parser.add_argument(
        "--db-dir",
        type=Path,
        default=Path(DEFAULT_DB_DIR),
        help="Chroma Persistent DB 경로",
    )

    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="Chroma Collection 이름",
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_NAME,
        help="Hugging Face / SentenceTransformer 모델명",
    )

    parser.add_argument(
        "--text-field",
        default=DEFAULT_TEXT_FIELD,
        help="임베딩할 JSON 필드. 현재 데이터는 text",
    )

    parser.add_argument(
        "--device",
        choices=["auto", "cuda", "cpu", "mps"],
        default="auto",
    )

    parser.add_argument(
        "--embed-batch-size",
        type=int,
        default=DEFAULT_EMBED_BATCH_SIZE,
    )

    parser.add_argument(
        "--db-batch-size",
        type=int,
        default=DEFAULT_DB_BATCH_SIZE,
    )

    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="같은 이름의 기존 Collection을 삭제하고 새로 생성",
    )

    parser.add_argument(
        "--search-only",
        action="store_true",
        help="인덱스를 만들지 않고 기존 Collection에서 검색만 수행",
    )

    parser.add_argument(
        "--test-query",
        default=None,
        help="Index 구축 후 즉시 테스트할 Query",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--where-json",
        default=None,
        help='Chroma metadata filter JSON. 예: \'{"section":"application"}\'',
    )

    return parser


def main() -> None:
    args = make_parser().parse_args()

    if args.embed_batch_size <= 0:
        raise ValueError("--embed-batch-size는 1 이상이어야 합니다.")

    if args.db_batch_size <= 0:
        raise ValueError("--db-batch-size는 1 이상이어야 합니다.")

    if args.top_k <= 0:
        raise ValueError("--top-k는 1 이상이어야 합니다.")

    device = choose_device(args.device)
    where = parse_where(args.where_json)

    print("\n" + "#" * 70)
    print("KURE-v1 + ChromaDB Retrieval Pipeline")
    print("#" * 70)
    print(f"device      : {device}")
    print(f"db_dir      : {args.db_dir}")
    print(f"collection  : {args.collection}")

    if args.search_only:
        if not args.test_query:
            raise ValueError(
                "--search-only 사용 시 --test-query가 필요합니다."
            )

        embedder, collection = load_existing_for_search(
            db_dir=args.db_dir,
            collection_name=args.collection,
            model_name=args.model,
            device=device,
            embed_batch_size=args.embed_batch_size,
        )

    else:
        if not args.input.exists():
            raise FileNotFoundError(
                f"입력 파일이 없습니다: {args.input}"
            )

        embedder, collection, _manifest = build_index(
            input_path=args.input,
            db_dir=args.db_dir,
            collection_name=args.collection,
            model_name=args.model,
            text_field=args.text_field,
            device=device,
            embed_batch_size=args.embed_batch_size,
            db_batch_size=args.db_batch_size,
            rebuild=args.rebuild,
        )

    if args.test_query:
        print("\n" + "=" * 70)
        print("[테스트 검색]")
        print("=" * 70)

        result = search(
            embedder=embedder,
            collection=collection,
            query=args.test_query,
            top_k=args.top_k,
            where=where,
        )

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )

    print("\n완료.")


if __name__ == "__main__":
    main()

## 
# KURE-v1 + ChromaDB 실행 명령어 정리
# 1. 작업 폴더로 이동
# cd $HOME\Downloads

# 현재 위치 확인:

# pwd
# 2. Python 파일과 데이터 파일 존재 여부 확인
# dir .\kure_chroma_pipeline.py
# dir .\c2_section_800_chunks.jsonl

# 두 파일이 모두 보여야 해.

# 3. 필요한 라이브러리 설치

# 최초 1회만 실행하면 돼.

# python -m pip install -U sentence-transformers chromadb torch numpy tqdm
# 4. KURE-v1 임베딩 + ChromaDB 구축

# 이게 가장 핵심 명령어야.

# python .\kure_chroma_pipeline.py --input .\c2_section_800_chunks.jsonl --db-dir .\chroma_db --collection c2_kure_v1_section800_v1 --rebuild

# 이 명령 하나가 실제로:

# JSONL 데이터 로드
# → 데이터 검증
# → KURE-v1 모델 로드
# → Chunk Embedding 생성
# → 1024차원 Vector 생성
# → ChromaDB Collection 생성
# → Vector + Text + Metadata 저장
# → 저장 개수 검증
# → Manifest 생성

# 까지 전부 수행해.

# 현재 정상 결과는:

# expected chunk count : 2,875
# chroma record count  : 2,875

# 였으니까 임베딩 및 DB 구축 성공 상태야.

# 5. Top-5 검색 테스트

# DB를 이미 만들었으니까 여기서는 --rebuild를 사용하지 않아.

# python .\kure_chroma_pipeline.py --db-dir .\chroma_db --collection c2_kure_v1_section800_v1 --search-only --test-query "청년 근로자가 받을 수 있는 지원은 무엇인가요?" --top-k 5

# 이 명령은:

# 질문 입력
# → KURE-v1 Query Embedding
# → ChromaDB 검색
# → Cosine Distance 계산
# → Top-5 Chunk 반환

# 을 수행해.

# 6. 다른 질문 테스트

# 지원 자격:

# python .\kure_chroma_pipeline.py --db-dir .\chroma_db --collection c2_kure_v1_section800_v1 --search-only --test-query "춘천시 청년근로자 복리후생 지원사업의 지원 자격은 무엇인가요?" --top-k 5

# 지원 내용:

# python .\kure_chroma_pipeline.py --db-dir .\chroma_db --collection c2_kure_v1_section800_v1 --search-only --test-query "청년근로자 사랑채움사업은 얼마를 지원하나요?" --top-k 5

# 신청 기간:

# python .\kure_chroma_pipeline.py --db-dir .\chroma_db --collection c2_kure_v1_section800_v1 --search-only --test-query "청년근로자 사랑채움사업 신청 기간은 언제인가요?" --top-k 5
# 진짜 필요한 명령어만 압축하면

# 실제로 앞으로 기억해야 할 건 사실 3개야.

# cd $HOME\Downloads
# python .\kure_chroma_pipeline.py --input .\c2_section_800_chunks.jsonl --db-dir .\chroma_db --collection c2_kure_v1_section800_v1 --rebuild
# python .\kure_chroma_pipeline.py --db-dir .\chroma_db --collection c2_kure_v1_section800_v1 --search-only --test-query "질문 내용" --top-k 5

# 그리고 구분만 정확히 기억하면 돼.

# --rebuild → 처음 임베딩해서 DB를 새로 만들 때
# --search-only → 이미 만든 DB에서 검색만 할 때
# --test-query → 검색할 질문
# --top-k 5 → 상위 5개 Chunk 반환
# --collection → 사용할 Chroma Collection 이름
# --db-dir → ChromaDB 저장 위치
##