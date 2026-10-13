from __future__ import annotations

from src.common.io import sha256_file, utc_now_iso


def build_dataset_manifest(config: dict, document_path: str, document_count: int) -> dict:
    """Dataset Manifest payload를 만드는 전용 함수.

    데이터 검증과 Manifest 생성 책임을 분리해 두면 테스트와 재사용이 쉬워진다.
    """
    dataset = config["dataset"]
    return {
        "dataset_version": dataset["version"],
        "preprocessing_version": dataset["preprocessing_version"],
        "document_path": document_path,
        "document_count": document_count,
        "sha256": sha256_file(document_path),
        "created_at_utc": utc_now_iso(),
    }
