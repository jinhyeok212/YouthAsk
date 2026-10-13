"""기존 Chroma Index 재사용 또는 새 Index 생성을 결정하는 Runner Entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from src.indexing.build_index import build_new_index
from src.indexing.build_index_manifest import (
    build_index_manifest,
    load_manifest,
    manifest_matches,
    save_manifest,
)


def _collection_names(client: Any) -> set[str]:
    names: set[str] = set()
    for item in client.list_collections():
        if isinstance(item, str):
            names.add(item)
        else:
            names.add(str(item.name))
    return names


def resolve_index(config: dict, chunk_info: dict) -> Dict[str, Any]:
    """
    Runner 계약:
        resolve_index(config, chunk_info) -> dict

    CASE 1: Collection + Manifest 둘 다 있고 현재 설정과 같음 → 재사용
    CASE 2: 둘 다 있지만 설정이 다름 → 기존 것을 보호하기 위해 중단
    CASE 3: 둘 중 하나만 있음 → 불완전 상태이므로 중단
    CASE 4: 둘 다 없음 → 새 Index 생성
    """
    import chromadb

    index_cfg = config["index"]
    db_path = Path(index_cfg["db_path"])
    collection_name = index_cfg["collection_name"]
    manifest_path = Path(
        index_cfg.get(
            "manifest_path",
            db_path / f"{collection_name}__manifest.json",
        )
    )

    db_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(db_path))

    collection_exists = collection_name in _collection_names(client)
    manifest_exists = manifest_path.exists()

    if collection_exists and manifest_exists:
        manifest = load_manifest(manifest_path)
        if not manifest_matches(manifest, config, chunk_info):
            raise ValueError(
                "같은 Collection 이름이 존재하지만 현재 YAML과 Manifest 조건이 다릅니다. "
                "기존 Index를 덮어쓰지 않습니다. 새 index.version/db_path/collection_name을 사용하세요."
            )

        collection = client.get_collection(name=collection_name)
        actual_count = collection.count()
        expected_count = int(chunk_info["chunk_count"])
        if actual_count != expected_count:
            raise RuntimeError(
                "기존 Index record 수와 현재 Chunk 수가 다릅니다: "
                f"expected={expected_count}, actual={actual_count}"
            )

        return {
            "index_version": index_cfg["version"],
            "db_path": str(db_path),
            "collection_name": collection_name,
            "reused": True,
            "manifest_path": str(manifest_path),
            "index_count": actual_count,
            "build_time_seconds": 0.0,
        }

    if collection_exists != manifest_exists:
        raise RuntimeError(
            "Index 상태가 불완전합니다: "
            f"collection_exists={collection_exists}, manifest_exists={manifest_exists}. "
            "Collection과 Manifest를 함께 확인하세요."
        )

    result = build_new_index(config, chunk_info)
    manifest = build_index_manifest(
        config,
        chunk_info,
        index_count=result["index_count"],
        build_time_seconds=result["build_time_seconds"],
        reused=False,
    )
    save_manifest(manifest_path, manifest)

    result["manifest_path"] = str(manifest_path)
    return result
