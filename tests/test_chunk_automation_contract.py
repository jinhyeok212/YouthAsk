"""PR #26 리뷰 회귀 테스트.

모든 테스트는 실제 팀 YAML(exp_full_kure_v4_team.yaml)을 읽어 데이터 경로만
임시 폴더로 바꾼 뒤, 실제 v4 설정 로더(load_and_validate_config)를 거쳐 실행한다.
dataset.chunk_path 같은 테스트 전용 필드는 추가하지 않는다.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from src.chunking.build_chunks import build_chunks
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
