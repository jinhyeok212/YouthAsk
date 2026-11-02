from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]

CHUNKING_VERSION_PLACEHOLDER = "{chunking_version}"


def project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expand_chunking_path(value: str | Path, chunking_version: str) -> str:
    """경로의 {chunking_version} 자리표시자를 치환한다.

    설정 로더가 한 번 치환한 경로를 모든 단계가 같이 쓰도록 하기 위한 함수다.
    다른 중괄호 표현은 건드리지 않는다.
    """
    return str(value).replace(CHUNKING_VERSION_PLACEHOLDER, str(chunking_version))


def configured_chunk_paths(config: dict[str, Any]) -> tuple[Path, Path, Path]:
    """YAML/스키마 계약 위치의 경로를 그대로 사용한다.

    chunking.chunk_path, chunking.manifest_path, evaluation.chunk_qrels_path.
    build_chunks는 경로를 재작성하지 않는다. 경로가 바뀌면 평가 단계가
    다른 파일을 읽게 되기 때문이다.
    """
    chunking = config["chunking"]
    version = str(chunking["version"])
    values = {
        "chunking.chunk_path": chunking["chunk_path"],
        "chunking.manifest_path": chunking["manifest_path"],
        "evaluation.chunk_qrels_path": config["evaluation"]["chunk_qrels_path"],
    }
    paths: list[Path] = []
    for name, value in values.items():
        expanded = expand_chunking_path(value, version)
        if "{" in expanded or "}" in expanded:
            raise ValueError(f"{name}에 지원하지 않는 경로 자리표시자가 있습니다: {value}")
        paths.append(project_path(expanded))
    return paths[0], paths[1], paths[2]


def qrels_sidecar_paths(chunk_qrels_path: Path) -> dict[str, Path]:
    """확정 qrels 옆에 두는 자동 생성 후보/검수 대상/메타 파일 경로."""
    stem = chunk_qrels_path.stem
    return {
        "candidates": chunk_qrels_path.with_name(f"{stem}.candidates.jsonl"),
        "review_required": chunk_qrels_path.with_name(f"{stem}_review_required.jsonl"),
        "meta": chunk_qrels_path.with_name(f"{stem}.meta.json"),
    }


def chunk_signature(config: dict[str, Any], dataset_info: dict[str, Any]) -> dict[str, Any]:
    """main/C2 bootstrap manifest와 같은 필드 구성의 signature."""
    chunking = config["chunking"]
    dataset = config["dataset"]
    return {
        "dataset_version": dataset["version"],
        "preprocessing_version": dataset.get("preprocessing_version", ""),
        "dataset_sha256": dataset_info["sha256"],
        "chunking_version": chunking["version"],
        "strategy": chunking["strategy"],
        "size": int(chunking["size"]),
        "overlap": int(chunking["overlap"]),
        "unit": chunking.get("unit", "characters"),
        "target_field": chunking["target_field"],
    }


def generated_chunk_signature(
    config: dict[str, Any],
    dataset_info: dict[str, Any],
    scheme: str,
) -> dict[str, Any]:
    """generate 모드 signature. chunk_id 규칙이 다르면 다른 산출물로 본다."""
    return chunk_signature(config, dataset_info) | {
        "mode": "generate",
        "chunk_id_scheme": scheme,
    }


def check_manifest(manifest_path: Path, chunk_path: Path, signature: dict[str, Any]) -> dict[str, Any]:
    """기존 manifest가 현재 조건과 같고 청크 파일이 바뀌지 않았는지 확인한다."""
    manifest = read_json(manifest_path)
    if manifest.get("signature") != signature:
        raise ValueError(
            "기존 Chunk Manifest 설정과 현재 YAML이 다릅니다. "
            "다른 조건의 청크를 같은 경로에 덮어쓰지 않습니다. "
            "새 chunking.version 또는 새 chunk_path를 사용하세요: "
            f"{manifest_path}"
        )

    manifest_sha = manifest.get("chunk_sha256")
    actual_sha = sha256_file(chunk_path)
    if manifest_sha != actual_sha:
        raise ValueError(
            "Chunk Manifest SHA256 불일치: "
            f"manifest={manifest_sha}, actual={actual_sha}"
        )
    return manifest


def guard_partial_outputs(manifest_path: Path, chunk_path: Path) -> None:
    if chunk_path.exists() and not manifest_path.exists():
        raise ValueError(
            "기존 chunks.jsonl은 있지만 chunk_manifest.json이 없습니다. "
            f"조건을 확인할 수 없어 덮어쓰지 않습니다: {chunk_path}"
        )
    if manifest_path.exists() and not chunk_path.exists():
        raise ValueError(
            "chunk_manifest.json은 있지만 chunks.jsonl이 없습니다. "
            f"불완전한 산출물이므로 확인 후 다시 실행하세요: {manifest_path}"
        )


def build_manifest(
    *,
    config: dict[str, Any],
    dataset_info: dict[str, Any],
    signature: dict[str, Any],
    document_path: Path,
    chunk_path: Path,
    chunk_sha256: str,
    chunk_count: int,
    validation: dict[str, Any],
    scheme: str,
) -> dict[str, Any]:
    strategy = str(config["chunking"]["strategy"])
    size_meaning = (
        "section body split limit; final text may include title prefix"
        if scheme.startswith("section")
        else "final chunk text character limit"
    )
    return {
        "signature": signature,
        "document_path": str(document_path),
        "document_sha256": sha256_file(document_path),
        "chunk_path": str(chunk_path),
        "chunk_count": chunk_count,
        "chunk_sha256": chunk_sha256,
        "created_at_utc": utc_now_iso(),
        "generator": {
            "strategy": strategy,
            "chunk_id_scheme": scheme,
            "size_meaning": size_meaning,
            "chunk_id_deterministic": True,
        },
        "validation": validation,
        "dataset_info": dataset_info,
    }


COMMIT_JOURNAL_GLOB = ".staged_commit.*.json"


class StagedOutputs:
    """최종 경로 옆 임시 파일에 먼저 쓰고, 검증이 끝나면 한꺼번에 반영한다.

    같은 폴더 안 os.replace이므로 파일 단위 교체는 원자적이다.
    commit 전에 실패하면 이번 실행이 만든 임시 파일만 지운다.
    commit 도중 실패하면 이미 반영한 파일을 되돌린다. 기존 파일은 .bak으로
    옮겨 두었다가 복원하고, 이번 실행이 새로 만든 파일만 지운다.
    되돌리기 전에 프로세스가 끝나도 journal_dir의 저널로 다음 실행에서 복구한다.
    """

    def __init__(self, journal_dir: Path | None = None) -> None:
        self._token = uuid4().hex[:8]
        self._staged: list[tuple[Path, Path]] = []
        self._journal_dir = journal_dir

    def path_for(self, final_path: Path) -> Path:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = final_path.with_name(f".{final_path.name}.{self._token}.tmp")
        self._staged.append((temp_path, final_path))
        return temp_path

    def commit(self) -> None:
        # 등록 순서대로 반영한다. manifest를 마지막에 등록해 완료 표시로 쓴다.
        entries = [
            {
                "temp": str(temp_path),
                "final": str(final_path),
                "backup": (
                    str(final_path.with_name(f".{final_path.name}.{self._token}.bak"))
                    if final_path.exists()
                    else None
                ),
            }
            for temp_path, final_path in self._staged
        ]
        journal_dir = self._journal_dir or (self._staged[0][1].parent if self._staged else None)
        journal_path = journal_dir / f".staged_commit.{self._token}.json" if journal_dir else None
        if journal_path is not None:
            _write_journal(journal_path, "applying", entries)

        try:
            for entry in entries:
                if entry["backup"]:
                    os.replace(entry["final"], entry["backup"])
                os.replace(entry["temp"], entry["final"])
        except BaseException:
            # 되돌리기도 실패하면 저널이 남아 다음 실행에서 복구된다.
            _rollback(entries)
            if journal_path is not None:
                journal_path.unlink(missing_ok=True)
            raise

        if journal_path is not None:
            _write_journal(journal_path, "committed", entries)
        _discard_backups(entries)
        if journal_path is not None:
            journal_path.unlink(missing_ok=True)
        self._staged.clear()

    def cleanup(self) -> None:
        for temp_path, _ in self._staged:
            temp_path.unlink(missing_ok=True)
        self._staged.clear()


def _write_journal(path: Path, state: str, entries: list[dict[str, Any]]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    write_json(temp_path, {"state": state, "entries": entries, "updated_at_utc": utc_now_iso()})
    os.replace(temp_path, path)


def _rollback(entries: list[dict[str, Any]]) -> None:
    """반영 순서의 역순으로 되돌린다. 아직 반영되지 않은 항목은 그대로 둔다."""
    for entry in reversed(entries):
        final_path = Path(entry["final"])
        if entry["backup"]:
            backup_path = Path(entry["backup"])
            if backup_path.exists():
                os.replace(backup_path, final_path)
        else:
            # commit 시작 시 없던 파일: 이번 실행이 만든 것이므로 지운다.
            final_path.unlink(missing_ok=True)
        Path(entry["temp"]).unlink(missing_ok=True)


def _discard_backups(entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        if entry["backup"]:
            Path(entry["backup"]).unlink(missing_ok=True)
        Path(entry["temp"]).unlink(missing_ok=True)


def recover_interrupted_commits(journal_dir: Path) -> list[str]:
    """이전 실행이 commit 도중 끝나 남긴 저널을 처리한다.

    applying 상태면 반영 전 상태로 되돌리고, committed 상태면 남은 백업만 지운다.
    처리한 저널 경로 목록을 반환한다.
    """
    if not journal_dir.exists():
        return []
    recovered: list[str] = []
    for journal_path in sorted(journal_dir.glob(COMMIT_JOURNAL_GLOB)):
        journal = read_json(journal_path)
        entries = journal.get("entries") or []
        try:
            if journal.get("state") == "committed":
                _discard_backups(entries)
            else:
                _rollback(entries)
        except OSError as e:
            raise RuntimeError(
                "이전 실행의 중단된 파일 반영을 복구하지 못했습니다. "
                f"파일 잠금을 해제한 뒤 다시 실행하세요: journal={journal_path}"
            ) from e
        journal_path.unlink(missing_ok=True)
        recovered.append(str(journal_path))
    return recovered
