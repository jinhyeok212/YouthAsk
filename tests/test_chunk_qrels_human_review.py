import csv
import json
from copy import deepcopy

import pytest

from scripts import review_chunk_qrels_200 as review
from scripts.finalize_delegated_chunk_review_200 import evidence


def test_policy_identity_evidence_keeps_name_instead_of_only_description():
    answer = "정책명: 제4기 청년협의체 모집"
    row = {"reference_answer": answer, "chunk_text": answer + "\n\n정책 설명: 청년 참여를 지원합니다.",
           "exact_excerpt_for_review": answer, "chunk_id": "c1"}
    doc = {"retrieval_text": row["chunk_text"], "raw_record": {}}
    assert evidence(row, doc) == answer


def test_semantic_review_quotes_actual_source_instead_of_normalized_answer():
    row = {"reference_answer": "○ 지원금 100만원 ○ 방문 신청", "chunk_text": "정책명: 청년지원\n\n지원 내용: ○ 지원금 100만원\n○ 방문 신청",
           "exact_excerpt_for_review": "", "chunk_id": "c1"}
    doc = {"retrieval_text": row["chunk_text"], "raw_record": {}}
    quote = evidence(row, doc)
    assert quote in row["chunk_text"] and quote in doc["retrieval_text"]
    assert quote != row["reference_answer"]


def test_delegated_review_rejects_untraceable_quote():
    row = {"reference_answer": "없는 참고답변", "chunk_text": "원본에 없는 청크 본문", "exact_excerpt_for_review": "", "chunk_id": "c1"}
    doc = {"retrieval_text": "다른 원문", "raw_record": {}}
    with pytest.raises(ValueError, match="No verbatim evidence"):
        evidence(row, doc)


def test_normalized_match_never_approves():
    q = {"reference_answer": "온라인 신청 후 서류 제출", "query": "어떻게 신청하나요?", "question_type": "application_method"}
    doc = {"title": "정책", "retrieval_text": "온라인 신청 후 서류 제출", "raw_record": {"plcyAplyMthdCn": "온라인 신청 후 서류 제출"}}
    chunk = {"text": "온라인  신청 후 서류 제출", "section": "application_method"}
    result = review.recommend(q, doc, chunk)
    assert result["recommendation"] == "REVIEW"
    assert result["direct_full_answer_match"] == "false"
    assert result["normalized_full_match_candidate_only"] == "true"


def test_full_verbatim_answer_requires_source_and_policy_title_section():
    q = {"reference_answer": "정책명: 청년 주거 지원", "query": "어떤 정책인가요?", "question_type": "specific_policy_search"}
    doc = {"title": "청년 주거 지원", "retrieval_text": q["reference_answer"], "raw_record": {"plcyNm": "청년 주거 지원"}}
    chunk = {"text": q["reference_answer"], "section": "title"}
    assert review.recommend(q, doc, chunk)["recommendation"] == "APPROVE"
    chunk["section"] = "category"
    assert review.recommend(q, doc, chunk)["recommendation"] == "REJECT"
    chunk["section"] = "title"
    doc["retrieval_text"] = "다른 정책"
    assert review.recommend(q, doc, chunk)["recommendation"] != "APPROVE"


@pytest.fixture
def export_case(tmp_path, monkeypatch):
    version = "section_heading_800_ov120_v1"
    quote = "온라인 신청 후 서류를 제출합니다."
    questions = [{"query_id": "q1"}, {"query_id": "q2"}]
    gold = [{"query_id": "q1", "document_id": "d1"}, {"query_id": "q1", "document_id": "d2"},
            {"query_id": "q2", "document_id": "d2"}]
    docs = {d: {"retrieval_text": quote, "raw_record": {"method": quote}} for d in ["d1", "d2"]}
    chunks = {cid: {"chunk_id": cid, "document_id": did, "text": quote, "chunking_version": version}
              for cid, did in [("c1", "d1"), ("c2", "d2"), ("c3", "d2")]}
    chunk_path = tmp_path / "chunks.jsonl"
    review.write_rows(chunk_path, list(chunks.values()))
    config = {"chunking": {"version": version}, "evaluation": {"chunk_qrels_path": str(tmp_path / "final.jsonl")}}
    paths = {"chunks": str(chunk_path)}
    monkeypatch.setattr(review, "load_inputs", lambda path: (config, paths, questions, gold, docs, chunks))
    rows = []
    for index, (qid, did, cid) in enumerate([("q1", "d1", "c1"), ("q1", "d2", "c2"), ("q2", "d2", "c2"), ("q2", "d2", "c3")]):
        rows.append({"candidate_id": str(index), "query_id": qid, "document_id": did, "chunk_id": cid,
                     "chunking_version": version, "section": "application_method", "chunk_text": quote,
                     "recommendation": "APPROVE", "human_decision": "", "reviewer": "",
                     "human_evidence_quote": "", "human_note": ""})
    directory = tmp_path / "review"
    directory.mkdir()
    snapshot = directory / "candidates.snapshot.jsonl"
    review.write_rows(snapshot, rows)
    review.write_json(directory / "review_manifest.json", {"inputs": {"chunks": {"path": str(chunk_path), "sha256": review.sha(chunk_path)}},
                                                           "artifacts": {snapshot.name: review.sha(snapshot)}})
    csv_path = tmp_path / "reviewed.csv"
    output = tmp_path / "final.jsonl"
    return directory, csv_path, output, rows, quote, questions, gold, chunks, version


def approve(rows, quote):
    result = deepcopy(rows)
    for row in result[:3]:
        row.update(human_decision="APPROVE", reviewer="사용자", human_evidence_quote=quote, human_note="질문에 대한 신청 절차를 직접 확인")
    return result


def test_recommendations_alone_never_export(export_case):
    directory, csv_path, output, rows, *_ = export_case
    review.write_csv(csv_path, rows)
    with pytest.raises(ValueError, match="Incomplete approved coverage"):
        review.export_approved("config", directory, csv_path, output)
    assert not output.exists()


def test_export_only_explicit_approvals_and_no_overwrite(export_case):
    directory, csv_path, output, rows, quote, *_ = export_case
    review.write_csv(csv_path, approve(rows, quote))
    result = review.export_approved("config", directory, csv_path, output)
    assert result["approved_chunk_mapping_count"] == 3
    final = review.read_rows(output)
    assert all(row["chunk_id"] != "c3" for row in final)
    assert {(r["query_id"], r["document_id"]) for r in final} == {("q1", "d1"), ("q1", "d2"), ("q2", "d2")}
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        review.export_approved("config", directory, csv_path, output)
    assert before == output.read_bytes()


@pytest.mark.parametrize("case", ["tamper", "duplicate", "no_reviewer", "invented_quote", "no_note", "missing_gold", "stale_source"])
def test_export_rejects_unsafe_or_incomplete_approval(export_case, case):
    directory, csv_path, output, rows, quote, *_ = export_case
    edited = approve(rows, quote)
    if case == "tamper":
        edited[0]["chunk_id"] = "invented"
    elif case == "duplicate":
        edited[1] = edited[0].copy()
    elif case == "no_reviewer":
        edited[0]["reviewer"] = ""
    elif case == "invented_quote":
        edited[0]["human_evidence_quote"] = "원문에 존재하지 않는 신청 절차"
    elif case == "no_note":
        edited[0]["human_note"] = ""
    elif case == "missing_gold":
        edited[1]["human_decision"] = "REVIEW"
    else:
        (directory.parent / "chunks.jsonl").write_text("{}\n", encoding="utf-8")
    review.write_csv(csv_path, edited)
    with pytest.raises(ValueError):
        review.export_approved("config", directory, csv_path, output)
    assert not output.exists()


@pytest.mark.parametrize("case", ["unknown_chunk", "wrong_document", "version", "duplicate", "relevance", "missing_question"])
def test_final_mapping_validation(export_case, case):
    _, _, _, _, _, questions, gold, chunks, version = export_case
    rows = [{**g, "chunk_id": "c1" if g["document_id"] == "d1" else "c2", "chunking_version": version, "relevance": 1} for g in gold]
    if case == "unknown_chunk":
        rows[0]["chunk_id"] = "absent"
    elif case == "wrong_document":
        rows[0]["chunk_id"] = "c2"
    elif case == "version":
        rows[0]["chunking_version"] = "other"
    elif case == "duplicate":
        rows.append(rows[0].copy())
    elif case == "relevance":
        rows[0]["relevance"] = True
    else:
        rows.pop()
    with pytest.raises(ValueError):
        review.validate_final(rows, questions, gold, chunks, version)
