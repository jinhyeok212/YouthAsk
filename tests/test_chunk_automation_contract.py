"""PR #26 리뷰 회귀 테스트.

모든 테스트는 실제 팀 YAML(exp_full_kure_v4_team.yaml)을 읽어 데이터 경로만
임시 폴더로 바꾼 뒤, 실제 v4 설정 로더(load_and_validate_config)를 거쳐 실행한다.
dataset.chunk_path 같은 테스트 전용 필드는 추가하지 않는다.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml

from src.chunking import manifest as manifest_module
from src.chunking.build_chunk_qrels import approve_chunk_qrels, resolve_chunk_qrels
from src.chunking.build_chunks import build_chunks
from src.chunking.generators import chunk_id_scheme, generate_chunks
from src.chunking.validate_chunks import validate_chunks
from src.evaluation.evaluate_experiment import evaluate_experiment
from src.evaluation.validate_inputs import validate_evaluation_inputs
from src.experiments import runner
from src.experiments.config_validator import ConfigValidationError, load_and_validate_config


ROOT = Path(__file__).resolve().parents[1]
TEAM_YAML = ROOT / "configs" / "experiments" / "exp_full_kure_v4_team.yaml"
SCHEMA = ROOT / "schemas" / "experiment_v4.schema.json"

TEXT_1 = "정책명: 청년 월세 지원\n신청 방법: 온라인 신청만 가능합니다.\n제출 서류: 주민등록등본"
TEXT_2 = "정책명: 청년 일자리 지원\n지원 내용: 직무 교육을 제공합니다."


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_qrels() -> list[dict]:
    start = TEXT_1.index("온라인 신청")
    return [
        {
            "query_id": "q001",
            "document_id": "policy_001",
            "relevance": 1,
            "evidence_start_char": start,
            "evidence_end_char": start + len("온라인 신청"),
        },
        {"query_id": "q002", "document_id": "policy_002", "relevance": 1, "evidence_text": "직무 교육"},
    ]


def no_evidence_qrels() -> list[dict]:
    # 저장소 47문항 qrels와 같은 형태: 근거 span/text, chunk_id 없음
    return [
        {"query_id": "q001", "document_id": "policy_001", "relevance": 1},
        {"query_id": "q002", "document_id": "policy_002", "relevance": 1},
    ]


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.documents = root / "data" / "documents.jsonl"
        self.questions = root / "eval" / "questions.jsonl"
        self.document_qrels = root / "eval" / "qrels.jsonl"
        write_jsonl(
            self.documents,
            [
                {"document_id": "policy_001", "title": "청년 월세 지원", "retrieval_text": TEXT_1},
                {"document_id": "policy_002", "title": "청년 일자리 지원", "retrieval_text": TEXT_2},
            ],
        )
        write_jsonl(
            self.questions,
            [
                {"query_id": "q001", "query": "월세 지원 신청 방법은?"},
                {"query_id": "q002", "query": "일자리 지원 내용은?"},
            ],
        )
        self.dataset_info = {
            "document_path": str(self.documents),
            "manifest_path": str(root / "data" / "dataset_manifest.json"),
            "document_count": 2,
            "sha256": sha(self.documents),
        }

    def load(self, name: str = "exp", **chunking_overrides) -> dict:
        """실제 팀 YAML에서 데이터 경로만 바꿔 v4 로더로 읽는다."""
        raw = yaml.safe_load(TEAM_YAML.read_text(encoding="utf-8"))
        raw = copy.deepcopy(raw)
        raw["experiment_id"] = name
        raw["dataset"]["document_path"] = str(self.documents)
        raw["dataset"]["manifest_path"] = self.dataset_info["manifest_path"]
        raw["chunking"]["chunk_path"] = str(self.root / "chunks" / "{chunking_version}" / "chunks.jsonl")
        raw["chunking"]["manifest_path"] = str(
            self.root / "chunks" / "{chunking_version}" / "chunk_manifest.json"
        )
        raw["chunking"].update(chunking_overrides)
        raw["evaluation"]["questions_path"] = str(self.questions)
        raw["evaluation"]["document_qrels_path"] = str(self.document_qrels)
        raw["evaluation"]["chunk_qrels_path"] = str(
            self.root / "eval" / "chunk_qrels" / "{chunking_version}" / "qrels_chunk.jsonl"
        )
        raw["index"]["db_path"] = str(self.root / "index")
        raw["output"]["root"] = str(self.root / "experiments")
        path = self.root / f"{name}.yaml"
        path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        config = load_and_validate_config(path, SCHEMA)
        assert "chunk_path" not in config["dataset"]
        return config


def generate_overrides(version: str = "section_heading_40_ov5_v1", strategy: str = "section") -> dict:
    return {"mode": "generate", "version": version, "strategy": strategy, "size": 40, "overlap": 5}


def fake_retrieval(chunk_qrels_path: Path) -> list[dict]:
    """정답 chunk를 1위로 돌려주는 가짜 검색 결과."""
    rows = []
    for row in read_jsonl(chunk_qrels_path):
        rows.append(
            {
                "query_id": row["query_id"],
                "query": row["query_id"],
                "retrieval_latency_ms": 1.0,
                "results": [
                    {
                        "rank": 1,
                        "chunk_id": row["chunk_id"],
                        "document_id": row["document_id"],
                        "distance": 0.1,
                        "similarity": 0.9,
                    }
                ],
            }
        )
    return rows


@pytest.fixture()
def ws(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path)


# ---------------------------------------------------------------------------
# P1-1: 실제 팀 YAML 계약(chunking.chunk_path / chunking.manifest_path)
# ---------------------------------------------------------------------------
def test_team_yaml_reuse_registers_prebuilt_c2_chunks(ws: Workspace) -> None:
    config = ws.load()
    assert config["chunking"]["version"] == "c2_section_800_v1"
    assert config["chunking"].get("mode", "reuse") == "reuse"

    chunk_path = Path(config["chunking"]["chunk_path"])
    write_jsonl(
        chunk_path,
        [
            {"chunk_id": "policy_001__overview__000", "document_id": "policy_001", "chunk_index": 0,
             "section": "overview", "text": "월세 지원 개요"},
            {"chunk_id": "policy_001__application__000", "document_id": "policy_001", "chunk_index": 1,
             "section": "application", "text": "온라인 신청"},
            {"chunk_id": "policy_002__overview__000", "document_id": "policy_002", "chunk_index": 0,
             "section": "overview", "text": "일자리 지원 개요"},
        ],
    )
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    write_jsonl(
        qrels_path,
        [
            {"query_id": "q001", "document_id": "policy_001", "chunk_id": "policy_001__application__000",
             "relevance": 1, "matched_section": "application", "chunking_version": "c2_section_800_v1"},
            {"query_id": "q002", "document_id": "policy_002", "chunk_id": "policy_002__overview__000",
             "relevance": 1, "matched_section": "overview", "chunking_version": "c2_section_800_v1"},
        ],
    )
    write_jsonl(ws.document_qrels, no_evidence_qrels())
    qrels_sha = sha(qrels_path)

    first = build_chunks(config, ws.dataset_info)
    manifest_bytes = Path(first["manifest_path"]).read_bytes()
    second = build_chunks(config, ws.dataset_info)

    assert first["chunk_path"] == config["chunking"]["chunk_path"]
    assert first["manifest_path"] == config["chunking"]["manifest_path"]
    assert first["chunk_qrels_status"] == "ready"
    assert first["chunk_qrels_review_status"] == "legacy_bootstrap"
    assert second["chunks_reused"] is True
    assert sha(qrels_path) == qrels_sha
    assert Path(second["manifest_path"]).read_bytes() == manifest_bytes
    assert validate_evaluation_inputs(config, ws.dataset_info, second)["status"] == "VALID"


def test_team_yaml_reuse_without_prebuilt_chunks_does_not_generate(ws: Workspace) -> None:
    config = ws.load()
    with pytest.raises(FileNotFoundError, match="청크를 자동 생성하지 않습니다"):
        build_chunks(config, ws.dataset_info)
    assert not Path(config["chunking"]["chunk_path"]).exists()
    assert not Path(config["chunking"]["manifest_path"]).exists()


# ---------------------------------------------------------------------------
# P1-2: 생성한 qrels를 입력 검증/평가가 그대로 사용
# ---------------------------------------------------------------------------
def test_generated_qrels_flow_into_validation_and_evaluation(ws: Workspace) -> None:
    write_jsonl(ws.document_qrels, evidence_qrels())
    # 템플릿 이전의 기본 위치에 과거 qrels가 있어도 읽으면 안 된다.
    stale = ws.root / "eval" / "qrels_chunk.jsonl"
    write_jsonl(stale, [{"query_id": "q001", "document_id": "policy_001", "chunk_id": "stale__000"}])
    config = ws.load(**generate_overrides())

    chunk_info = build_chunks(config, ws.dataset_info)
    assert chunk_info["chunk_qrels_status"] == "ready"
    assert chunk_info["chunk_qrels_path"] == config["evaluation"]["chunk_qrels_path"]
    assert "section_heading_40_ov5_v1" in chunk_info["chunk_qrels_path"]
    runner._assert_chunk_paths_consistent(config, chunk_info)

    assert validate_evaluation_inputs(config, ws.dataset_info, chunk_info)["status"] == "VALID"
    evaluation = evaluate_experiment(config, fake_retrieval(Path(chunk_info["chunk_qrels_path"])))
    assert evaluation["metrics_summary"]["chunk_hit_at_1"] == 1.0


def test_existing_qrels_for_other_chunks_are_preserved_and_rejected(ws: Workspace) -> None:
    write_jsonl(ws.document_qrels, evidence_qrels())
    config = ws.load(**generate_overrides())
    build_chunks(config, ws.dataset_info)
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    meta_path = qrels_path.with_name("qrels_chunk.meta.json")

    # 메타가 다른 청크(SHA)를 가리키도록 만든다: 과거 청크 기준의 qrels
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["chunk_sha256"] = "other-chunks"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    before = sha(qrels_path)

    with pytest.raises(ValueError, match="다른 청크 기준"):
        build_chunks(config, ws.dataset_info)
    assert sha(qrels_path) == before


def test_review_required_stops_runner_before_index(ws: Workspace, monkeypatch) -> None:
    write_jsonl(ws.document_qrels, no_evidence_qrels())
    config = ws.load(name="exp_review", **generate_overrides())
    calls: list[str] = []
    monkeypatch.setattr(runner, "validate_documents", lambda cfg: ws.dataset_info)
    monkeypatch.setattr(runner, "resolve_index", lambda cfg, info: calls.append("index"))
    monkeypatch.setattr(runner, "evaluate_experiment", lambda cfg, rows: calls.append("evaluate"))

    with pytest.raises(runner.ChunkQrelsReviewRequired, match="qrels_chunk_review_required.jsonl"):
        runner.run_pipeline(config)

    assert calls == []
    assert not (Path(config["output"]["root"]) / "exp_review").exists()
    assert not Path(config["evaluation"]["chunk_qrels_path"]).exists()


# ---------------------------------------------------------------------------
# P1-3: 검수한 qrels는 재실행으로 바뀌지 않는다
# ---------------------------------------------------------------------------
def test_reviewed_qrels_are_kept_on_rerun(ws: Workspace) -> None:
    write_jsonl(ws.document_qrels, no_evidence_qrels())
    config = ws.load(**generate_overrides())

    first = build_chunks(config, ws.dataset_info)
    assert first["chunk_qrels_status"] == "review_required"

    # 사람이 검수해서 확정본을 만든다.
    chunks = read_jsonl(Path(first["chunk_path"]))
    by_doc = {}
    for chunk in chunks:
        by_doc.setdefault(chunk["document_id"], chunk)
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    write_jsonl(
        qrels_path,
        [
            {"query_id": "q001", "document_id": "policy_001", "chunk_id": by_doc["policy_001"]["chunk_id"],
             "relevance": 1, "matched_section": by_doc["policy_001"]["section"],
             "chunking_version": config["chunking"]["version"]},
            {"query_id": "q002", "document_id": "policy_002", "chunk_id": by_doc["policy_002"]["chunk_id"],
             "relevance": 1, "chunking_version": config["chunking"]["version"]},
        ],
    )
    reviewed_sha = sha(qrels_path)

    second = build_chunks(config, ws.dataset_info)
    meta_bytes = Path(second["chunk_qrels_meta_path"]).read_bytes()
    third = build_chunks(config, ws.dataset_info)

    assert second["chunk_qrels_status"] == third["chunk_qrels_status"] == "ready"
    assert second["chunk_qrels_review_status"] == "reviewed"
    assert second["chunk_sha256"] == first["chunk_sha256"]
    assert sha(qrels_path) == reviewed_sha
    assert Path(third["chunk_qrels_meta_path"]).read_bytes() == meta_bytes
    assert validate_evaluation_inputs(config, ws.dataset_info, third)["status"] == "VALID"


# ---------------------------------------------------------------------------
# P2-1: fixed / section이 실제 설정 로더를 통과
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy", ["fixed", "section"])
def test_supported_strategies_pass_v4_loader_and_run(ws: Workspace, strategy: str) -> None:
    write_jsonl(ws.document_qrels, evidence_qrels())
    config = ws.load(**generate_overrides(version=f"{strategy}_40_ov5_v1", strategy=strategy))
    chunk_info = build_chunks(config, ws.dataset_info)
    assert chunk_info["chunk_count"] > 0
    assert f"{strategy}_40_ov5_v1" in chunk_info["chunk_path"]


@pytest.mark.parametrize("strategy", ["char", "c2_section", "foo"])
def test_unsupported_strategies_are_rejected_by_v4_loader(ws: Workspace, strategy: str) -> None:
    with pytest.raises(ConfigValidationError, match="strategy"):
        ws.load(**generate_overrides(strategy=strategy))


def test_generate_mode_rejects_c2_version(ws: Workspace) -> None:
    with pytest.raises(ConfigValidationError, match="c2_"):
        ws.load(mode="generate")


@pytest.mark.parametrize(
    "name", ["exp_chunk_generate_fixed_example.yaml", "exp_chunk_generate_section_example.yaml"]
)
def test_example_yamls_pass_v4_loader(name: str) -> None:
    config = load_and_validate_config(ROOT / "configs" / "experiments" / name, SCHEMA)
    version = config["chunking"]["version"]
    assert config["chunking"]["mode"] == "generate"
    assert version in config["chunking"]["chunk_path"]
    assert version in config["evaluation"]["chunk_qrels_path"]


# ---------------------------------------------------------------------------
# P2-2: 실패 후 입력만 고치면 수동 삭제 없이 재실행 가능
# ---------------------------------------------------------------------------
def test_failed_run_can_be_retried_after_fixing_qrels(ws: Workspace) -> None:
    write_jsonl(ws.document_qrels, [{"document_id": "policy_001", "relevance": 1}])
    config = ws.load(**generate_overrides())
    chunk_dir = Path(config["chunking"]["chunk_path"]).parent

    with pytest.raises(ValueError, match="query_id"):
        build_chunks(config, ws.dataset_info)
    assert not Path(config["chunking"]["chunk_path"]).exists()
    assert not Path(config["chunking"]["manifest_path"]).exists()

    write_jsonl(ws.document_qrels, evidence_qrels())
    result = build_chunks(config, ws.dataset_info)
    assert result["chunk_qrels_status"] == "ready"
    assert not list(chunk_dir.glob("*.tmp"))


def test_failure_after_staging_leaves_no_partial_outputs(ws: Workspace) -> None:
    write_jsonl(ws.document_qrels, evidence_qrels())
    config = ws.load(**generate_overrides())
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    # 새 청크와 맞지 않는 확정 qrels가 미리 있으면 청크 생성 후 검증 단계에서 실패한다.
    write_jsonl(qrels_path, [{"query_id": "q001", "document_id": "policy_001", "chunk_id": "missing"}])
    before = sha(qrels_path)

    with pytest.raises(ValueError, match="존재하지 않는 정답 Chunk"):
        build_chunks(config, ws.dataset_info)

    chunk_path = Path(config["chunking"]["chunk_path"])
    assert not chunk_path.exists()
    assert not Path(config["chunking"]["manifest_path"]).exists()
    assert not list(chunk_path.parent.glob("*.tmp"))
    assert not list(qrels_path.parent.glob("*.tmp"))
    assert sha(qrels_path) == before


# ---------------------------------------------------------------------------
# 재검토 P1: 확정 이후 원본 문서 qrels(정답 근거)가 바뀌면 과거 정답으로 채점하지 않는다
# ---------------------------------------------------------------------------
FIXED = generate_overrides(version="fixed_40_ov5_v1", strategy="fixed")


def _evidence_rows(q001_evidence: dict) -> list[dict]:
    return [
        {"query_id": "q001", "document_id": "policy_001", "relevance": 1, **q001_evidence},
        {"query_id": "q002", "document_id": "policy_002", "relevance": 1, "evidence_text": "직무 교육"},
    ]


def _span_of(text: str) -> dict:
    start = TEXT_1.index(text)
    return {"evidence_start_char": start, "evidence_end_char": start + len(text)}


@pytest.mark.parametrize(
    "changed_evidence",
    [{"evidence_text": "주민등록등본"}, _span_of("주민등록등본")],
    ids=["evidence_text", "evidence_span"],
)
def test_changed_source_evidence_requires_review(ws: Workspace, changed_evidence: dict) -> None:
    write_jsonl(ws.document_qrels, _evidence_rows({"evidence_text": "온라인 신청"}))
    config = ws.load(**FIXED)
    first = build_chunks(config, ws.dataset_info)
    assert first["chunk_qrels_review_status"] == "auto_ready"
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    meta_path = Path(first["chunk_qrels_meta_path"])
    qrels_before, meta_before = sha(qrels_path), sha(meta_path)
    old_answer = {r["chunk_id"] for r in read_jsonl(qrels_path) if r["query_id"] == "q001"}

    # 같은 query_id/document_id에서 근거만 바꾼다.
    write_jsonl(ws.document_qrels, _evidence_rows(changed_evidence))
    second = build_chunks(config, ws.dataset_info)

    assert second["chunk_qrels_status"] == "review_required"
    assert second["chunk_qrels_review_status"] == "source_changed"
    assert sha(qrels_path) == qrels_before
    assert sha(meta_path) == meta_before
    review = read_jsonl(Path(second["chunk_qrels_review_required_path"]))
    q001 = next(row for row in review if row["query_id"] == "q001")
    assert set(q001["confirmed_chunk_ids"]) == old_answer
    assert set(q001["candidate_chunk_ids"]) != old_answer
    with pytest.raises(runner.ChunkQrelsReviewRequired):
        runner._assert_chunk_qrels_ready(second)

    # 사람이 확인하기 전까지는 재실행해도 계속 멈춘다.
    assert build_chunks(config, ws.dataset_info)["chunk_qrels_status"] == "review_required"


def test_source_change_without_answer_change_keeps_auto_qrels(ws: Workspace) -> None:
    write_jsonl(ws.document_qrels, _evidence_rows({"evidence_text": "온라인 신청"}))
    config = ws.load(**FIXED)
    first = build_chunks(config, ws.dataset_info)
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    qrels_before = sha(qrels_path)

    write_jsonl(ws.document_qrels, _evidence_rows({"evidence_text": "온라인 신청", "note": "오타 수정"}))
    second = build_chunks(config, ws.dataset_info)

    assert second["chunk_qrels_status"] == "ready"
    assert second["chunk_qrels_review_status"] == "auto_ready"
    assert sha(qrels_path) == qrels_before
    meta = json.loads(Path(first["chunk_qrels_meta_path"]).read_text(encoding="utf-8"))
    assert meta["source_document_qrels_sha256"] == sha(ws.document_qrels)


def test_reviewed_qrels_need_approval_after_source_change(ws: Workspace) -> None:
    write_jsonl(ws.document_qrels, _evidence_rows({"evidence_text": "온라인 신청"}))
    config = ws.load(**FIXED)
    build_chunks(config, ws.dataset_info)
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])

    # 사람이 확정본을 고친다 → reviewed
    rows = read_jsonl(qrels_path)
    rows[0]["reviewer_note"] = "확인함"
    write_jsonl(qrels_path, rows)
    assert build_chunks(config, ws.dataset_info)["chunk_qrels_review_status"] == "reviewed"
    reviewed_sha = sha(qrels_path)

    # 정답 결과가 같아 보여도 사람이 검수한 정답은 자동으로 다시 승인하지 않는다.
    write_jsonl(ws.document_qrels, _evidence_rows({"evidence_text": "온라인 신청", "note": "수정"}))
    assert build_chunks(config, ws.dataset_info)["chunk_qrels_status"] == "review_required"

    meta = approve_chunk_qrels(config)
    assert meta["status"] == "reviewed"
    assert meta["source_document_qrels_sha256"] == sha(ws.document_qrels)

    after = build_chunks(config, ws.dataset_info)
    assert after["chunk_qrels_status"] == "ready"
    assert after["chunk_qrels_review_status"] == "reviewed"
    assert sha(qrels_path) == reviewed_sha
    assert validate_evaluation_inputs(config, ws.dataset_info, after)["status"] == "VALID"


def test_missing_source_qrels_is_not_silently_ignored(ws: Workspace) -> None:
    write_jsonl(ws.document_qrels, _evidence_rows({"evidence_text": "온라인 신청"}))
    config = ws.load(**FIXED)
    build_chunks(config, ws.dataset_info)
    ws.document_qrels.unlink()

    with pytest.raises(ValueError, match="정답 근거 변경 여부"):
        build_chunks(config, ws.dataset_info)


# ---------------------------------------------------------------------------
# 재검토 P2: 파일 반영(commit) 도중 실패해도 수동 삭제 없이 재시도할 수 있다
# ---------------------------------------------------------------------------
def _fail_replace_once(monkeypatch, target_name: str) -> None:
    """임시 파일 → target_name 교체에서 한 번만 PermissionError를 낸다."""
    real_replace = os.replace
    state = {"failed": False}

    def fake_replace(src, dst):
        if not state["failed"] and str(src).endswith(".tmp") and Path(dst).name == target_name:
            state["failed"] = True
            raise PermissionError(f"주입된 잠금 오류: {dst}")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fake_replace)


def _leftovers(*dirs: Path) -> list[Path]:
    return [
        path
        for directory in dirs
        for pattern in ("*.tmp", "*.bak", ".staged_commit.*")
        for path in directory.glob(pattern)
    ]


@pytest.mark.parametrize(
    "target_name", ["chunks.jsonl", "qrels_chunk.meta.json", "chunk_manifest.json"],
    ids=["first_file", "middle_file", "manifest_last"],
)
def test_commit_failure_rolls_back_and_retry_succeeds(ws: Workspace, monkeypatch, target_name: str) -> None:
    write_jsonl(ws.document_qrels, evidence_qrels())
    config = ws.load(**generate_overrides())
    chunk_path = Path(config["chunking"]["chunk_path"])
    manifest_path = Path(config["chunking"]["manifest_path"])
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])

    with monkeypatch.context() as patch:
        _fail_replace_once(patch, target_name)
        with pytest.raises(PermissionError, match="주입된"):
            build_chunks(config, ws.dataset_info)

    # 이번 실행이 새로 만든 파일은 모두 되돌아간다.
    for path in (chunk_path, manifest_path, qrels_path, qrels_path.with_name("qrels_chunk.meta.json")):
        assert not path.exists(), path
    assert _leftovers(chunk_path.parent, qrels_path.parent) == []

    result = build_chunks(config, ws.dataset_info)
    assert result["chunk_qrels_status"] == "ready"
    assert _leftovers(chunk_path.parent, qrels_path.parent) == []


def test_commit_failure_restores_existing_files(ws: Workspace, monkeypatch) -> None:
    write_jsonl(ws.document_qrels, evidence_qrels())
    config = ws.load(**generate_overrides())
    first = build_chunks(config, ws.dataset_info)
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    meta_path = Path(first["chunk_qrels_meta_path"])

    rows = read_jsonl(qrels_path)
    rows[0]["reviewer_note"] = "확인함"
    write_jsonl(qrels_path, rows)
    qrels_before, meta_before = sha(qrels_path), meta_path.read_bytes()

    # 다음 실행은 기존 meta를 reviewed로 갱신한다. 그 교체에서 실패시킨다.
    with monkeypatch.context() as patch:
        _fail_replace_once(patch, "qrels_chunk.meta.json")
        with pytest.raises(PermissionError):
            build_chunks(config, ws.dataset_info)

    assert meta_path.read_bytes() == meta_before
    assert sha(qrels_path) == qrels_before
    assert _leftovers(meta_path.parent, Path(first["chunk_path"]).parent) == []
    assert build_chunks(config, ws.dataset_info)["chunk_qrels_review_status"] == "reviewed"


def test_interrupted_commit_is_recovered_on_next_run(ws: Workspace, monkeypatch) -> None:
    write_jsonl(ws.document_qrels, evidence_qrels())
    config = ws.load(**generate_overrides())
    chunk_path = Path(config["chunking"]["chunk_path"])

    # 되돌리기 전에 프로세스가 끝난 상황: 저널과 반쪽 산출물이 남는다.
    with monkeypatch.context() as patch:
        _fail_replace_once(patch, "chunk_manifest.json")

        def crash(entries):
            raise OSError("되돌리기 전에 종료")

        patch.setattr(manifest_module, "_rollback", crash)
        with pytest.raises(OSError):
            build_chunks(config, ws.dataset_info)
    assert chunk_path.exists()
    assert not Path(config["chunking"]["manifest_path"]).exists()
    assert list(chunk_path.parent.glob(".staged_commit.*.json"))

    result = build_chunks(config, ws.dataset_info)
    assert result["chunk_qrels_status"] == "ready"
    assert _leftovers(chunk_path.parent, Path(config["evaluation"]["chunk_qrels_path"]).parent) == []


# ---------------------------------------------------------------------------
# 재검토 P3: section 청킹에서 첫 제목 앞의 본문을 버리지 않는다
# ---------------------------------------------------------------------------
PREAMBLE_TEXT = "만 19세부터 34세까지만 신청 가능합니다.\n지원 내용: 매월 20만원 지원"


def _section_chunks(text: str) -> list[dict]:
    return generate_chunks(
        [{"document_id": "d1", "title": "청년 지원", "retrieval_text": text}],
        version="section_test_v1",
        strategy="section",
        size=40,
        overlap=5,
        unit="characters",
        target_field="retrieval_text",
    )


def _assert_source_covered(text: str, chunks: list[dict]) -> None:
    covered = set()
    for chunk in chunks:
        covered.update(range(chunk["start_char"], chunk["end_char"]))
    missing = [i for i, char in enumerate(text) if not char.isspace() and i not in covered]
    assert missing == [], text[min(missing):]
    for line in text.splitlines():
        assert any(line.split(":")[-1].strip() in chunk["text"] for chunk in chunks), line


@pytest.mark.parametrize(
    "text",
    [
        PREAMBLE_TEXT,
        "자격 요건: 무주택 청년\n지원 내용: 매월 20만원 지원",
        "제목 없이 설명만 있는 정책 문서입니다.",
    ],
    ids=["leading_sentence", "unknown_heading", "no_heading"],
)
def test_section_chunks_keep_text_before_first_heading(text: str) -> None:
    chunks = _section_chunks(text)
    _assert_source_covered(text, chunks)
    assert chunks[0]["section_index"] == 0
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)


def test_section_chunks_starting_with_heading_are_unchanged() -> None:
    chunks = _section_chunks(TEXT_1)
    _assert_source_covered(TEXT_1, chunks)
    assert [chunk["section_slug"] for chunk in chunks] == ["title", "application_method", "documents"]
    assert chunks[0]["chunk_id"] == "d1__sec_00_title__chunk_000"
    assert chunk_id_scheme("section") == "section_heading_v2"


def test_coverage_validation_detects_dropped_text(tmp_path: Path) -> None:
    documents = tmp_path / "documents.jsonl"
    chunks_path = tmp_path / "chunks.jsonl"
    write_jsonl(documents, [{"document_id": "d1", "retrieval_text": PREAMBLE_TEXT}])
    start = PREAMBLE_TEXT.index("지원 내용")
    body = PREAMBLE_TEXT[start:]
    write_jsonl(
        chunks_path,
        [{"chunk_id": "d1__0", "document_id": "d1", "chunk_index": 0, "text": body,
          "start_char": start, "end_char": len(PREAMBLE_TEXT)}],
    )
    with pytest.raises(ValueError, match="포함되지 않은 문서"):
        validate_chunks(documents, chunks_path, chunk_size=40, overlap=5,
                        strict_max_length=False, coverage_target_field="retrieval_text")


def test_preamble_evidence_maps_to_chunk_end_to_end(ws: Workspace) -> None:
    write_jsonl(
        ws.documents,
        [
            {"document_id": "policy_001", "title": "청년 월세 지원", "retrieval_text": PREAMBLE_TEXT},
            {"document_id": "policy_002", "title": "청년 일자리 지원", "retrieval_text": TEXT_2},
        ],
    )
    ws.dataset_info["sha256"] = sha(ws.documents)
    write_jsonl(ws.document_qrels, _evidence_rows({"evidence_text": "만 19세부터 34세까지만"}))
    config = ws.load(**generate_overrides(version="section_heading_v2_40_ov5", strategy="section"))

    chunk_info = build_chunks(config, ws.dataset_info)
    assert chunk_info["chunk_qrels_status"] == "ready"
    answer = next(r for r in read_jsonl(Path(chunk_info["chunk_qrels_path"])) if r["query_id"] == "q001")
    assert "__sec_00_preamble__" in answer["chunk_id"]


# ---------------------------------------------------------------------------
# 재검토 v3 P2: 원본 추적 중인 확정본을 reuse해도 원본 변경을 확인한다
# ---------------------------------------------------------------------------
def _legacy_c2_config(ws: Workspace) -> dict:
    config = ws.load()
    write_jsonl(
        Path(config["chunking"]["chunk_path"]),
        [
            {"chunk_id": "policy_001__application__000", "document_id": "policy_001", "chunk_index": 0,
             "section": "application", "text": "온라인 신청"},
            {"chunk_id": "policy_002__overview__000", "document_id": "policy_002", "chunk_index": 0,
             "section": "overview", "text": "일자리 지원 개요"},
        ],
    )
    write_jsonl(
        Path(config["evaluation"]["chunk_qrels_path"]),
        [
            {"query_id": "q001", "document_id": "policy_001", "chunk_id": "policy_001__application__000",
             "relevance": 1},
            {"query_id": "q002", "document_id": "policy_002", "chunk_id": "policy_002__overview__000",
             "relevance": 1},
        ],
    )
    write_jsonl(ws.document_qrels, no_evidence_qrels())
    return config


def _meta_of(info: dict) -> dict:
    return json.loads(Path(info["chunk_qrels_meta_path"]).read_text(encoding="utf-8"))


def _generated_then_reuse_config(ws: Workspace) -> tuple[dict, dict]:
    write_jsonl(ws.document_qrels, _evidence_rows({"evidence_text": "온라인 신청"}))
    overrides = dict(FIXED)
    generated = build_chunks(ws.load(**overrides), ws.dataset_info)
    assert generated["chunk_qrels_review_status"] == "auto_ready"
    overrides["mode"] = "reuse"
    return ws.load(name="exp_reuse", **overrides), generated


def test_generated_qrels_can_be_reused_with_same_source(ws: Workspace) -> None:
    config, generated = _generated_then_reuse_config(ws)
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    qrels_before = sha(qrels_path)
    meta_before = Path(generated["chunk_qrels_meta_path"]).read_bytes()

    reused = build_chunks(config, ws.dataset_info)

    assert reused["chunk_qrels_status"] == "ready"
    assert reused["chunking_mode"] == "reuse"
    assert sha(qrels_path) == qrels_before
    assert Path(reused["chunk_qrels_meta_path"]).read_bytes() == meta_before
    assert validate_evaluation_inputs(config, ws.dataset_info, reused)["status"] == "VALID"


def test_approved_legacy_c2_can_be_reused(ws: Workspace) -> None:
    config = _legacy_c2_config(ws)
    first = build_chunks(config, ws.dataset_info)
    assert _meta_of(first)["source_document_qrels_sha256"] is None

    approved = approve_chunk_qrels(config)
    assert approved["source_document_qrels_sha256"] == sha(ws.document_qrels)

    again = build_chunks(config, ws.dataset_info)
    assert again["chunk_qrels_status"] == "ready"
    assert again["chunk_qrels_review_status"] == "reviewed"


@pytest.mark.parametrize("tracked_by", ["generate", "approve"])
def test_reuse_detects_source_change_for_tracked_qrels(ws: Workspace, tracked_by: str) -> None:
    if tracked_by == "generate":
        config, _ = _generated_then_reuse_config(ws)
        changed = _evidence_rows({"evidence_text": "주민등록등본"})
    else:
        config = _legacy_c2_config(ws)
        build_chunks(config, ws.dataset_info)
        approve_chunk_qrels(config)
        changed = no_evidence_qrels() + [{"query_id": "q003", "document_id": "policy_001", "relevance": 1}]
    qrels_path = Path(config["evaluation"]["chunk_qrels_path"])
    meta_path = qrels_path.with_name("qrels_chunk.meta.json")
    qrels_before, meta_before = sha(qrels_path), sha(meta_path)

    write_jsonl(ws.document_qrels, changed)
    result = build_chunks(config, ws.dataset_info)

    assert result["chunk_qrels_status"] == "review_required"
    assert result["chunk_qrels_review_status"] == "source_changed"
    assert sha(qrels_path) == qrels_before
    assert sha(meta_path) == meta_before
    with pytest.raises(runner.ChunkQrelsReviewRequired):
        runner._assert_chunk_qrels_ready(result)


def test_reuse_of_tracked_qrels_without_source_file_is_input_error(ws: Workspace) -> None:
    config, _ = _generated_then_reuse_config(ws)
    ws.document_qrels.unlink()
    with pytest.raises(ValueError, match="정답 근거 변경 여부"):
        build_chunks(config, ws.dataset_info)


def test_tracked_qrels_without_source_path_is_input_error(ws: Workspace) -> None:
    config, generated = _generated_then_reuse_config(ws)
    chunk_path = Path(generated["chunk_path"])
    with pytest.raises(ValueError, match="document_qrels_path"):
        resolve_chunk_qrels(
            chunk_qrels_path=Path(config["evaluation"]["chunk_qrels_path"]),
            chunk_path=chunk_path,
            chunks=read_jsonl(chunk_path),
            chunk_sha256=sha(chunk_path),
            chunking_version=config["chunking"]["version"],
            document_qrels_path=None,
            allow_auto=False,
            bootstrap_status="legacy_bootstrap",
            staged=manifest_module.StagedOutputs(),
        )


def test_untracked_legacy_c2_reuse_is_unchanged(ws: Workspace) -> None:
    config = _legacy_c2_config(ws)
    first = build_chunks(config, ws.dataset_info)
    meta_bytes = Path(first["chunk_qrels_meta_path"]).read_bytes()

    # 출처를 모르는 legacy 확정본은 원본 qrels가 바뀌어도 기존처럼 진행한다.
    write_jsonl(ws.document_qrels, no_evidence_qrels()[:1])
    second = build_chunks(config, ws.dataset_info)

    assert first["chunk_qrels_review_status"] == second["chunk_qrels_review_status"] == "legacy_bootstrap"
    assert second["chunk_qrels_status"] == "ready"
    assert Path(second["chunk_qrels_meta_path"]).read_bytes() == meta_bytes
