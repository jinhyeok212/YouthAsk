"""Build C02/C03 indexes by reusing byte-identical B01 chunk embeddings.

Reused vectors are safe because the embedding model, pinned revision,
normalization, and chunk text are identical.  Target metadata and documents are
always written from the target chunk rows; changed texts are encoded normally.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from src.chunking.build_chunks import build_chunks
from src.data.validate_documents import validate_documents
from src.experiments.config_validator import load_and_validate_config
from src.indexing.build_index import _collection_names, _create_collection
from src.indexing.build_index_manifest import build_index_manifest, save_manifest
from src.indexing.kure_adapter import KUREAdapter
from src.rag.embedding import batched, build_chroma_metadata, load_chunks


ROOT = Path(__file__).resolve().parents[1]
BASELINE_CHUNKS = ROOT / "data/processed/ontong_youth_full_v1/chunks/section_heading_800_ov120_v1/chunks.jsonl"
BASELINE_DB = ROOT / "indexes/chroma/index_b01_kure_section800_ov120_v1"
BASELINE_COLLECTION = "ontong_youth_b01_kure_section800_ov120_v1"
CONFIGS = (
    ROOT / "configs/experiments/c02_20261112_r1.yaml",
    ROOT / "configs/experiments/c03_20261112_r1.yaml",
)


def text_hashes(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                values[str(row["chunk_id"])] = str(row["text_hash"])
    return values


def fetch_embeddings(collection: Any, ids: list[str]) -> dict[str, np.ndarray]:
    if not ids:
        return {}
    result = collection.get(ids=ids, include=["embeddings"])
    returned_ids = [str(value) for value in result.get("ids") or []]
    embeddings = result.get("embeddings")
    if embeddings is None:
        raise RuntimeError("Baseline collection did not return embeddings")
    return {
        chunk_id: np.asarray(vector, dtype=np.float32)
        for chunk_id, vector in zip(returned_ids, embeddings)
    }


def build_one(config_path: Path, baseline_hashes: dict[str, str], baseline_collection: Any) -> dict:
    config = load_and_validate_config(str(config_path), "schemas/experiment_v4.schema.json")
    dataset_info = validate_documents(config)
    chunk_info = build_chunks(config, dataset_info)
    rows, stats = load_chunks(Path(chunk_info["chunk_path"]), text_field="text")
    if stats["chunk_count"] != int(chunk_info["chunk_count"]):
        raise ValueError("Target chunk count mismatch")

    index_cfg = config["index"]
    db_path = Path(index_cfg["db_path"])
    final_name = str(index_cfg["collection_name"])
    manifest_path = Path(index_cfg.get("manifest_path", db_path / f"{final_name}__manifest.json"))
    db_path.mkdir(parents=True, exist_ok=True)

    import chromadb

    client = chromadb.PersistentClient(path=str(db_path))
    if final_name in _collection_names(client) or manifest_path.exists():
        raise FileExistsError(f"Target index already exists: {db_path} / {final_name}")

    temp_name = f"{final_name}__building__{uuid4().hex[:8]}"
    collection = _create_collection(client, temp_name, str(index_cfg["distance_metric"]))
    batch_size = int(index_cfg.get("db_batch_size", 256))
    if hasattr(client, "get_max_batch_size"):
        batch_size = min(batch_size, int(client.get_max_batch_size()))

    adapter: KUREAdapter | None = None
    reused_count = 0
    encoded_count = 0
    started = time.perf_counter()
    try:
        for batch_rows in batched(rows, batch_size):
            reusable_ids = [
                str(row["chunk_id"])
                for row in batch_rows
                if baseline_hashes.get(str(row["chunk_id"])) == str(row.get("text_hash"))
            ]
            reused = fetch_embeddings(baseline_collection, reusable_ids)
            changed_rows = [row for row in batch_rows if str(row["chunk_id"]) not in reused]
            changed_vectors: dict[str, np.ndarray] = {}
            if changed_rows:
                if adapter is None:
                    adapter = KUREAdapter(config)
                vectors = adapter.encode_documents([str(row["text"]) for row in changed_rows])
                changed_vectors = {
                    str(row["chunk_id"]): vector
                    for row, vector in zip(changed_rows, vectors)
                }

            ordered_vectors = [
                reused.get(str(row["chunk_id"]), changed_vectors.get(str(row["chunk_id"])))
                for row in batch_rows
            ]
            if any(vector is None for vector in ordered_vectors):
                raise RuntimeError("An embedding was neither reused nor encoded")
            matrix = np.asarray(ordered_vectors, dtype=np.float32)
            if matrix.ndim != 2 or matrix.shape[1] != int(config["embedding"]["dimension"]):
                raise ValueError(f"Embedding shape mismatch: {matrix.shape}")
            if not np.isfinite(matrix).all():
                raise ValueError("Embedding contains NaN or Inf")

            collection.add(
                ids=[str(row["chunk_id"]) for row in batch_rows],
                documents=[str(row["text"]) for row in batch_rows],
                embeddings=matrix.tolist(),
                metadatas=[build_chroma_metadata(row) for row in batch_rows],
            )
            reused_count += len(reused)
            encoded_count += len(changed_rows)

        actual_count = collection.count()
        if actual_count != int(chunk_info["chunk_count"]):
            raise RuntimeError(f"Index count mismatch: {actual_count} != {chunk_info['chunk_count']}")
        collection.modify(name=final_name)
    except Exception:
        try:
            client.delete_collection(temp_name)
        except Exception:
            pass
        raise

    elapsed = time.perf_counter() - started
    manifest = build_index_manifest(
        config,
        chunk_info,
        index_count=int(chunk_info["chunk_count"]),
        build_time_seconds=round(elapsed, 4),
        reused=False,
    )
    manifest["embedding_reuse"] = {
        "source_collection": BASELINE_COLLECTION,
        "source_chunk_version": "section_heading_800_ov120_v1",
        "reused_identical_text_count": reused_count,
        "newly_encoded_count": encoded_count,
    }
    save_manifest(manifest_path, manifest)
    return {
        "condition": config["experiment_id"].split("-")[0],
        "index_count": int(chunk_info["chunk_count"]),
        "reused_count": reused_count,
        "encoded_count": encoded_count,
        "build_time_seconds": round(elapsed, 4),
    }


def main() -> None:
    import chromadb

    baseline_client = chromadb.PersistentClient(path=str(BASELINE_DB))
    baseline_collection = baseline_client.get_collection(name=BASELINE_COLLECTION)
    baseline_hashes = text_hashes(BASELINE_CHUNKS)
    results = [
        build_one(config_path, baseline_hashes, baseline_collection)
        for config_path in CONFIGS
    ]
    output = ROOT / "experiments/C02_C03_INDEX_REUSE_BUILD.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
