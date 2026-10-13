from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


def load_yaml(path: str | Path) -> dict:
    """YAML 설정 파일을 Python dict로 읽는다."""
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML 최상위 값은 object여야 합니다: {path}")
    return data


def load_json(path: str | Path) -> dict:
    """JSON 파일을 dict로 읽는다."""
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: str | Path) -> list[dict]:
    """JSONL 파일을 한 줄씩 검증하며 읽는다.

    실패 시 어느 줄에서 문제가 났는지 바로 알 수 있게 line number를 포함한다.
    """
    rows: list[dict] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSONL 파싱 실패: {path}:{line_no} - {e}") from e
            if not isinstance(row, dict):
                raise ValueError(f"JSONL 각 행은 object여야 합니다: {path}:{line_no}")
            rows.append(row)
    return rows


def ensure_parent(path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def write_json(path: str | Path, data: Any) -> None:
    ensure_parent(path)
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> None:
    ensure_parent(path)
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path: str | Path) -> str:
    """파일 내용 자체의 SHA256을 계산한다.

    파일 경로가 같아도 내용이 바뀌었는지 검출할 수 있으므로
    재현성과 Manifest 검증에 사용한다.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
