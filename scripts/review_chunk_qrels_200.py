"""Prepare review artifacts and export only explicit human approvals; never run models."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chunking.build_chunk_qrels import validate_chunk_qrels
from src.chunking.manifest import qrels_sidecar_paths
from src.experiments.config_validator import load_and_validate_config

DEFAULT_CONFIG = "configs/experiments/exp_full_kure_200_v1.yaml"
EDITABLE = {"human_decision", "reviewer", "human_evidence_quote", "human_note"}
SECTIONS = {
    "application_method": {"application_method"}, "period": {"application_period"},
    "application_period": {"application_period"}, "documents": {"documents"},
    "required_documents": {"documents"}, "eligibility": {"eligibility_extra", "support"},
    "support_content": {"support"}, "specific_policy_search": {"title"},
}
RAW_FIELDS = {
    "title": "plcyNm", "support": "plcySprtCn", "eligibility_extra": "addAplyQlfcCndCn",
    "application_period": "aplyYmd", "application_method": "plcyAplyMthdCn",
    "documents": "sbmsnDcmntCn", "screening": "srngMthdCn", "notes": "etcMttrCn",
}
MANUAL_OBSERVATIONS = {
    ("oy_eval_repair_q0037", "ontong_youth_20250316005400210640"):
        "직접 대조: 원문 지원 절은 '20만원 상당'을 명시하지만 참고답변의 '1인당 연간 최대'를 같은 표현으로 명시하지 않는다. 공연/전시·예매 7만원·뮤지컬 1회는 원문에 있다. 필요한 사실 범위를 사람이 확인할 것.",
    ("oy_eval_v2r_q0015", "ontong_youth_20250814005400211517"):
        "직접 대조: 연령·관내 예비창업자는 eligibility_extra, 미등록 사업자 및 단체 대표의 원주 거주는 support 청크의 지원 대상에 분리되어 있다. 한 청크로 전체 자격을 충족한다고 간주하지 말고 복수 청크 지지 범위를 검수할 것.",
    ("oy_eval200_new_0030", "ontong_youth_20260325005400212271"):
        "직접 대조: 참고답변은 '시·군·구청장이 인정', 해당 Gold 원문은 '청송군이 인정'이라고 되어 있다. 연령·소득·가구 정의와 인정 주체를 분리해서 검수하고 원본 답변은 변경하지 않을 것.",
    ("oy_eval200_new_0070", "ontong_youth_20260406005400212464"):
        "직접 대조: 소득 60%/100%, 재산 122/470백만원, 전입신고 및 보증금·월세 요건 폐지 사실은 원문에 있다. 참고답변은 원문의 '(자세한 내용은 FAQ참고)'·'기존'을 생략하고 날짜 뒤 '시행'을 포함한다. 전체 문자열 일치로 승인할 수 없으므로 필요한 사실 단위로 확인할 것.",
    ("oy_eval200_new_0100", "ontong_youth_20260406005400212464"):
        "직접 대조: 소득 60%/100%, 재산 122/470백만원, 전입신고 및 보증금·월세 요건 폐지 사실은 원문에 있다. 참고답변의 생략·'시행' 추가와 질문의 미추홀구 범위가 해당 시 단위 Gold에서 충분히 지지되는지 확인할 것.",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_rows(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path, rows):
    with Path(path).open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def create_review_report(output, rows, report):
    """Write a human-readable exception report, with source quotes kept verbatim."""
    by_pair = defaultdict(list)
    for row in rows:
        by_pair[row["query_id"], row["document_id"]].append(row)
    diagnostics = []
    for pair in report["gold_pairs_without_approve_recommendation"]:
        candidates = by_pair[pair["query_id"], pair["document_id"]]
        best = sorted(candidates, key=lambda r: (-float(r["candidate_score_only"]), r["chunk_id"]))[:3]
        answer, source = best[0]["reference_answer"], best[0]["source_retrieval_text"]
        normalized_source_match = normalize(answer) in normalize(source)
        raw_related = {}
        for row in candidates:
            raw_related.update(json.loads(row["source_raw_record_related"]))
        raw_match_fields = [k for k, v in raw_related.items() if isinstance(v, str) and normalize(answer) in normalize(v)]
        if normalized_source_match:
            reason = "공백·기호를 제거하면 원본 retrieval_text에서 전체 답변을 찾을 수 있음. 정규화 일치만으로는 승인하지 않음."
        elif raw_match_fields:
            reason = "raw_record에는 전체 답변에 대응하는 값이 있으나 retrieval_text/청크에는 분할·변형 가능성. 필요한 사실을 직접 대조해야 함."
        else:
            reason = "전체 답변이 원문 한 곳과 직접 대응하는지 확인하지 못함. 복수 원문 필드·분할 청크 및 수치·조건 차이를 우선 검수해야 함."
        if pair["query_id"] == "oy_eval_repair_q0077":
            reason += " 질문은 장애인 신청방법이지만 question_type은 specific_policy_search이므로 의미에 따라 검수하고 기존 승인 내용은 수정하지 않음."
        manual = MANUAL_OBSERVATIONS.get((pair["query_id"], pair["document_id"]), "")
        if manual:
            reason += " " + manual
        diagnostics.append({"query_id": pair["query_id"], "document_id": pair["document_id"],
                            "query": best[0]["query"], "reference_answer": answer,
                            "reason": reason, "normalized_source_match_candidate_only": normalized_source_match,
                            "normalized_raw_match_fields_candidate_only": raw_match_fields,
                            "top_candidates": [{k: r[k] for k in ("chunk_id", "section", "recommendation", "chunk_text", "exact_excerpt_for_review", "match_reason", "source_raw_record_related")} for r in best]})
    write_json(output / "review_needed_details.json", diagnostics)
    lines = ["# Chunk Qrels 검수 필요 항목 보고서", "",
             "상태: 자동 추천 완료 / 사용자 승인 0건 / 최종 qrels_chunk.jsonl 미생성.", "",
             f"질문 200개, Document Gold 연결 207건 전체를 포함했다. 원본 청크 {report['total_source_chunk_count']:,}개 중 Gold 문서 소속 후보 {len(rows):,}개를 검수 CSV에 담았다.", "",
             f"추천 분포: APPROVE {report['recommendation_counts'].get('APPROVE', 0)} / REVIEW {report['recommendation_counts'].get('REVIEW', 0)} / REJECT {report['recommendation_counts'].get('REJECT', 0)}.", "",
             "APPROVE는 원본과 청크에 참고답변 전체가 직접 포함되는 경우의 추천이다. 이는 사용자 승인이 아니며, 질문의 지역·기간·대상·예외·필요 사실이 실제로 충족되는지 최종 확인해야 한다.", "",
             "정책명 질문은 title 청크만 추천 대상으로 삼았다. 다른 청크에 반복된 정책명 접두어는 승인 근거로 쓰지 않았다. 관련 절·일부 인용·정규화 일치·후보 점수는 검수 보조 자료이며 승인 근거를 대신하지 않는다.", "",
             f"APPROVE 추천이 없는 질문은 {len(report['questions_without_approve_recommendation'])}개, Gold 연결은 {len(diagnostics)}건이다. 아래 모든 연결은 후보가 존재한다. 추천 부재와 후보 누락은 구분한다.", "",
             "## 우선 검수할 Gold 연결", "",
             "정렬 점수는 검수 순서용이다. 상위 3개만 보고 정답을 제한하지 말고 CSV의 동일 query_id/document_id 전체 청크를 확인한다.", ""]
    for item in diagnostics:
        lines.extend([f"### {item['query_id']} / {item['document_id']}", "",
                      "질문: " + item["query"], "", "참고답변(원문):", "",
                      "```text", item["reference_answer"], "```", "", item["reason"], ""])
        for candidate in item["top_candidates"]:
            lines.extend([f"- `{candidate['chunk_id']}` / {candidate['section']} / {candidate['recommendation']}",
                          "  - " + candidate["match_reason"]])
        lines.append("")
    lines.extend(["## 연결 및 최종 승인 검증", "",
                  "- 후보 query_id 범위: 200/200; Document Gold 연결: 207/207.",
                  "- 없는 chunk_id, chunk-document 불일치, 버전 불일치, 중복 query-document-chunk 매핑: 모두 0건.",
                  "- 사용자 승인된 정답 청크: 0건. 현재 최종 승인 관점의 누락은 질문 200개 / Gold 연결 207건이며, 검수 전 상태다.",
                  "- 최종 생성기는 사용자 APPROVE만 반영하고 200개 질문 및 207개 Gold 연결 모두 승인된 청크를 갖추었는지 검사한다. 의미상 Gold를 지지할 청크가 없다면 승인이나 relevance를 강제하지 말고 검수 필요로 남겨야 한다.", ""])
    with (output / "review_needed_report.md").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))


def normalize(value):
    # Candidate ranking only. Never establishes approval or supplies evidence.
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).lower()


def quoted_in_source(quote, document):
    return bool(quote) and (quote in document["retrieval_text"] or any(
        isinstance(value, str) and quote in value for value in document["raw_record"].values()))


def recommend(question, document, chunk):
    answer, text = question["reference_answer"], chunk["text"]
    section = chunk["section"]
    policy_name = answer.startswith("정책명:")
    expected_sections = {"title"} if policy_name else SECTIONS.get(question["question_type"], set())
    exact = answer in text and quoted_in_source(answer, document)
    year_q = set(re.findall(r"20\d{2}", question["query"]))
    year_title = set(re.findall(r"20\d{2}", document["title"]))
    flags = []
    if year_q and year_title and not year_q & year_title:
        flags.append("question_title_year_mismatch")
    if question["question_type"] == "specific_policy_search" and not policy_name:
        flags.append("question_type_requires_semantic_review")
    normalized_answer, normalized_text = normalize(answer), normalize(text)
    normalized_full = bool(normalized_answer) and normalized_answer in normalized_text
    # Exact substring is displayed as an excerpt, never called a complete fact.
    match = SequenceMatcher(None, answer, text, autojunk=False).find_longest_match()
    quote = answer[match.a:match.a + match.size] if match.size >= 12 else ""
    if quote and not quoted_in_source(quote, document):
        quote = ""
    grams_a = {normalized_answer[i:i+3] for i in range(max(0, len(normalized_answer)-2))}
    grams_t = {normalized_text[i:i+3] for i in range(max(0, len(normalized_text)-2))}
    score = len(grams_a & grams_t) / max(1, len(grams_a))
    if policy_name and section != "title":
        status, reason = "REJECT", "정책명 접두어 반복만으로 하위 청크를 정답으로 추천하지 않음; title 청크에서 정책 식별 검수"
    elif exact and not flags:
        status, reason = "APPROVE", "참고답변 전체가 청크 본문과 원본 retrieval_text/raw_record에 문자 그대로 포함됨; 질문과 해당 사실의 의미는 사람 최종 확인 필요"
        quote = answer
    elif exact:
        status, reason = "REVIEW", "전체 답변은 직접 일치하나 질문 유형/연도 불일치 가능성 확인 필요"
        quote = answer
    elif normalized_full:
        status, reason = "REVIEW", "정규화 후에만 전체 답변 일치; 공백·기호·수치·조건을 원문과 직접 대조해야 함"
    elif section in expected_sections or quote or score >= .35:
        status, reason = "REVIEW", "관련 절/직접 일치 부분이 있으나 전체 답변 지지를 확정하지 못함; 분할 사실·조건·예외·수치 검수 필요"
    else:
        status, reason = "REJECT", "이 청크 단독으로 질문의 참고답변을 지지하는 직접 근거를 확인하지 못함; 문서 Gold만으로 승인하지 않음"
    return {"recommendation": status, "match_reason": reason,
            "direct_full_answer_match": str(exact).lower(),
            "exact_excerpt_for_review": quote,
            "normalized_full_match_candidate_only": str(normalized_full).lower(),
            "candidate_score_only": f"{score:.6f}", "review_flags": "|".join(flags)}


def load_inputs(config_path):
    config = load_and_validate_config(config_path)
    ev, ch = config["evaluation"], config["chunking"]
    sidecars = qrels_sidecar_paths(Path(ev["chunk_qrels_path"]))
    paths = {"questions": ev["questions_path"], "document_qrels": ev["document_qrels_path"],
             "documents": config["dataset"]["document_path"], "chunks": ch["chunk_path"],
             "chunk_manifest": ch["manifest_path"], "runner_candidates": str(sidecars["candidates"]),
             "runner_review_required": str(sidecars["review_required"]),
             "evaluation_manifest": str(Path(ev["questions_path"]).with_name("evaluation_manifest.json"))}
    provenance = json.loads(Path(paths["evaluation_manifest"]).read_text(encoding="utf-8"))
    paths["source_csv"] = provenance["source_csv"]["path"]
    if sha(paths["source_csv"]) != provenance["source_csv"]["sha256"]:
        raise ValueError("Original approved CSV hash changed")
    if sha(paths["documents"]) != provenance["source_dataset"]["sha256"]:
        raise ValueError("Source documents hash changed")
    for key, name in (("questions", "eval_questions.jsonl"), ("document_qrels", "qrels.jsonl")):
        if sha(paths[key]) != provenance["outputs"][name]["sha256"]:
            raise ValueError(f"Evaluation input hash changed: {key}")
    questions = read_rows(paths["questions"])
    gold = read_rows(paths["document_qrels"])
    documents = read_rows(paths["documents"])
    chunks = read_rows(paths["chunks"])
    if len(questions) != 200 or len({q["query_id"] for q in questions}) != 200 or len(gold) != 207:
        raise ValueError("Expected 200 unique questions and 207 Gold links")
    qmap = {q["query_id"]: q for q in questions}
    dmap = {d["document_id"]: d for d in documents}
    cmap = {c["chunk_id"]: c for c in chunks}
    if len(cmap) != len(chunks) or len(dmap) != len(documents):
        raise ValueError("Duplicate document/chunk IDs")
    pairs = {(r["query_id"], r["document_id"]) for r in gold}
    if len(pairs) != 207 or pairs != {(q["query_id"], d) for q in questions for d in q["ground_truth_document_ids"]}:
        raise ValueError("Question/document Gold coverage mismatch")
    with Path(paths["source_csv"]).open(encoding="utf-8-sig", newline="") as handle:
        source = list(csv.DictReader(handle))
    if len(source) != 200 or any(s["query_id"] != q["query_id"] or s["query"] != q["query"] or s["reference_answer"] != q["reference_answer"] for s, q in zip(source, questions)):
        raise ValueError("Original CSV question/reference answer mismatch")
    chunk_manifest = json.loads(Path(paths["chunk_manifest"]).read_text(encoding="utf-8"))
    if chunk_manifest["chunk_sha256"] != sha(paths["chunks"]):
        raise ValueError("Chunk manifest hash mismatch")
    signature = chunk_manifest["signature"]
    expected_signature = {"chunking_version": ch["version"], "strategy": ch["strategy"],
                          "size": ch["size"], "overlap": ch["overlap"], "unit": ch["unit"],
                          "target_field": ch["target_field"], "dataset_sha256": sha(paths["documents"])}
    if any(signature.get(key) != value for key, value in expected_signature.items()):
        raise ValueError("Chunk manifest signature differs from experiment config")
    for chunk in chunks:
        if (chunk["document_id"] not in dmap or chunk.get("chunking_version") != ch["version"]
                or chunk.get("metadata", {}).get("chunking_version", ch["version"]) != ch["version"]):
            raise ValueError("Unknown chunk document or wrong chunking.version")
    review_pairs = {(r["query_id"], r.get("document_id")) for r in read_rows(paths["runner_review_required"])}
    if not review_pairs.issubset(pairs):
        raise ValueError("Runner review contains unknown Gold pair")
    return config, paths, questions, gold, dmap, cmap


def prepare(config_path, output):
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite review directory: {output}")
    config, paths, questions, gold, dmap, cmap = load_inputs(config_path)
    input_hashes = {key: {"path": str(Path(path).resolve()), "sha256": sha(path)} for key, path in paths.items()}
    by_doc = defaultdict(list)
    for chunk in cmap.values():
        by_doc[chunk["document_id"]].append(chunk)
    rows, summaries, pair_summaries = [], [], []
    for q in questions:
        question_rows = []
        for document_id in q["ground_truth_document_ids"]:
            doc = dmap[document_id]
            if not by_doc[document_id]:
                raise ValueError(f"Gold document has no chunks: {document_id}")
            pair_rows = []
            for chunk in by_doc[document_id]:
                related_fields = {"plcyNm", "plcyExplnCn", RAW_FIELDS.get(chunk["section"], "")}
                related_fields.update(RAW_FIELDS.get(s, "") for s in SECTIONS.get(q["question_type"], set()))
                if q["question_type"] in {"eligibility", "support_content"}:
                    related_fields.add("ptcpPrpTrgtCn")
                raw = {k: v for k, v in doc["raw_record"].items() if k in related_fields}
                row = {"candidate_id": hashlib.sha256((q["query_id"] + "\0" + chunk["chunk_id"]).encode()).hexdigest()[:24],
                       "query_id": q["query_id"], "document_id": document_id, "chunk_id": chunk["chunk_id"],
                       "chunking_version": config["chunking"]["version"], "query": q["query"],
                       "question_type": q["question_type"], "reference_answer": q["reference_answer"],
                       "source_title": doc["title"], "section": chunk["section"],
                       "chunk_text": chunk["text"], "source_retrieval_text": doc["retrieval_text"],
                       "source_raw_record_related": json.dumps(raw, ensure_ascii=False),
                       **recommend(q, doc, chunk), "human_decision": "", "reviewer": "",
                       "human_evidence_quote": "", "human_note": ""}
                pair_rows.append(row)
            pair_rows.sort(key=lambda r: ({"APPROVE": 0, "REVIEW": 1, "REJECT": 2}[r["recommendation"]], -float(r["candidate_score_only"]), r["chunk_id"]))
            rows.extend(pair_rows)
            question_rows.extend(pair_rows)
            counts = Counter(r["recommendation"] for r in pair_rows)
            pair_summaries.append({"query_id": q["query_id"], "document_id": document_id,
                                   "candidate_count": len(pair_rows), "recommendation_counts": dict(counts),
                                   "recommended_chunk_ids": [r["chunk_id"] for r in pair_rows if r["recommendation"] == "APPROVE"],
                                   "needs_evidence_review": not counts["APPROVE"]})
        counts = Counter(r["recommendation"] for r in question_rows)
        missing_pairs = [r["document_id"] for r in pair_summaries if r["query_id"] == q["query_id"] and r["needs_evidence_review"]]
        summaries.append({"query_id": q["query_id"], "query": q["query"], "reference_answer": q["reference_answer"],
                          "gold_document_ids": json.dumps(q["ground_truth_document_ids"], ensure_ascii=False),
                          "candidate_count": len(question_rows), "approve_recommendation_count": counts["APPROVE"],
                          "review_count": counts["REVIEW"], "reject_recommendation_count": counts["REJECT"],
                          "recommended_chunk_ids": json.dumps([r["chunk_id"] for r in question_rows if r["recommendation"] == "APPROVE"], ensure_ascii=False),
                          "gold_documents_without_approve_recommendation": json.dumps(missing_pairs),
                          "human_approved_count": 0, "final_status": "PENDING_HUMAN_REVIEW"})
    pairs = {(r["query_id"], r["document_id"]) for r in rows}
    triples = {(r["query_id"], r["document_id"], r["chunk_id"]) for r in rows}
    if len(pairs) != 207 or len(triples) != len(rows) or len({r["candidate_id"] for r in rows}) != len(rows):
        raise ValueError("Candidate coverage/duplicate validation failed")
    report = {"question_count": 200, "document_gold_link_count": 207, "candidate_count": len(rows),
              "total_source_chunk_count": len(cmap), "recommendation_counts": dict(Counter(r["recommendation"] for r in rows)),
              "questions_without_approve_recommendation": [s["query_id"] for s in summaries if not s["approve_recommendation_count"]],
              "gold_pairs_without_approve_recommendation": [p for p in pair_summaries if p["needs_evidence_review"]],
              "candidate_query_coverage": 200, "candidate_gold_pair_coverage": len(pairs),
              "unknown_chunk_id_count": 0, "chunk_document_mismatch_count": 0,
              "chunking_version_mismatch_count": 0, "duplicate_candidate_mapping_count": 0,
              "human_approved_count": 0, "final_qrels_created": False,
              "final_missing_question_count": 200, "final_missing_gold_pair_count": 207,
              "all_candidates_require_human_decision": True,
              "pair_summary": pair_summaries}
    output.mkdir(parents=True, exist_ok=False)
    write_rows(output / "candidates.snapshot.jsonl", rows)
    write_csv(output / "chunk_qrels_review.csv", rows)
    write_csv(output / "query_candidate_summary.csv", summaries)
    write_json(output / "validation_report.json", report)
    create_review_report(output, rows, report)
    manifest = {"chunking_version": config["chunking"]["version"], "config_path": str(Path(config_path).resolve()),
                "inputs": input_hashes, "editable_columns": sorted(EDITABLE),
                "artifacts": {p.name: sha(p) for p in output.iterdir()},
                "final_qrels_path": config["evaluation"]["chunk_qrels_path"]}
    write_json(output / "review_manifest.json", manifest)
    return report


def validate_final(rows, questions, gold, cmap, version):
    seen = set()
    pairs = {(r["query_id"], r["document_id"]) for r in gold}
    covered = set()
    for row in rows:
        cid, qid, did = row.get("chunk_id"), row.get("query_id"), row.get("document_id")
        if cid not in cmap or (qid, did) not in pairs or cmap[cid]["document_id"] != did:
            raise ValueError("Unknown chunk/query/Gold document or chunk-document mismatch")
        if row.get("chunking_version") != version or cmap[cid].get("chunking_version") != version:
            raise ValueError("chunking.version mismatch")
        if (qid, cid) in seen:
            raise ValueError("Duplicate query-chunk mapping")
        if type(row.get("relevance")) is not int or row["relevance"] != 1:
            raise ValueError("Approved qrels must have integer relevance=1")
        seen.add((qid, cid))
        covered.add((qid, did))
    missing_pairs = sorted(pairs - covered)
    missing_queries = sorted({q["query_id"] for q in questions} - {r["query_id"] for r in rows})
    if missing_pairs or missing_queries:
        raise ValueError(f"Incomplete approved coverage: missing_questions={len(missing_queries)}, missing_gold_pairs={len(missing_pairs)}; {missing_pairs[:10]}")
    return {"status": "PASS", "question_count": len(questions), "gold_pair_count": len(covered), "approved_chunk_mapping_count": len(rows)}


def export_approved(config_path, review_dir, reviewed_csv, output):
    config, paths, questions, gold, dmap, cmap = load_inputs(config_path)
    manifest = json.loads((review_dir / "review_manifest.json").read_text(encoding="utf-8"))
    for item in manifest["inputs"].values():
        if sha(item["path"]) != item["sha256"]:
            raise ValueError(f"Stale review input: {item['path']}")
    for key, path in paths.items():
        if sha(path) != manifest["inputs"][key]["sha256"]:
            raise ValueError(f"Current config input differs from review: {key}")
    snapshot = review_dir / "candidates.snapshot.jsonl"
    if sha(snapshot) != manifest["artifacts"][snapshot.name]:
        raise ValueError("Candidate snapshot changed")
    original = read_rows(snapshot)
    by_id = {r["candidate_id"]: r for r in original}
    with reviewed_csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or []) != set(original[0]) or len(reader.fieldnames) != len(original[0]):
            raise ValueError("Review CSV columns changed")
        reviewed = list(reader)
    if len(reviewed) != len(original) or len({r['candidate_id'] for r in reviewed}) != len(original):
        raise ValueError("Missing/duplicate review rows")
    approvals = []
    for row in reviewed:
        base = by_id.get(row["candidate_id"])
        if base is None or any(row.get(k) != v for k, v in base.items() if k not in EDITABLE):
            raise ValueError("Immutable candidate content changed")
        decision = row["human_decision"].strip()
        if decision not in {"", "APPROVE", "REVIEW", "REJECT"}:
            raise ValueError("Invalid human_decision")
        if decision != "APPROVE":
            continue
        quote = row["human_evidence_quote"]
        if not row["reviewer"].strip() or not row["human_note"].strip():
            raise ValueError("APPROVE requires reviewer and human_note")
        if len(quote.strip()) < 8 or quote not in cmap[row["chunk_id"]]["text"] or not quoted_in_source(quote, dmap[row["document_id"]]):
            raise ValueError("APPROVE requires a verbatim evidence quote in both chunk and source")
        approvals.append({"query_id": row["query_id"], "document_id": row["document_id"], "chunk_id": row["chunk_id"],
                          "relevance": 1, "chunking_version": row["chunking_version"],
                          "matched_section": row["section"], "evidence_text": quote,
                          "reviewed_by": row["reviewer"], "review_note": row["human_note"]})
    result = validate_final(approvals, questions, gold, cmap, config["chunking"]["version"])
    receipt_path = output.with_name(output.stem + ".human_approval.json")
    if output.exists() or receipt_path.exists():
        raise FileExistsError("Refusing to overwrite final qrels or human approval receipt")
    # Reject output paths that collide with any source or review artifact.
    forbidden = {Path(p).resolve() for p in paths.values()} | {p.resolve() for p in review_dir.iterdir()}
    if output.resolve() in forbidden or receipt_path.resolve() in forbidden:
        raise ValueError("Output collides with protected inputs")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_rows(output, approvals)
    validate_chunk_qrels(output, paths["chunks"])
    write_json(receipt_path, {**result, "review_csv_sha256": sha(reviewed_csv), "qrels_sha256": sha(output),
                              "review_manifest_sha256": sha(review_dir / "review_manifest.json"), "inputs": manifest["inputs"]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    subs = parser.add_subparsers(dest="command", required=True)
    create = subs.add_parser("prepare")
    create.add_argument("--output-dir", type=Path, required=True)
    export = subs.add_parser("export-approved")
    export.add_argument("--review-dir", type=Path, required=True)
    export.add_argument("--review-csv", type=Path, required=True)
    export.add_argument("--output", type=Path)
    validate = subs.add_parser("validate-final")
    validate.add_argument("--qrels", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.config, args.output_dir)
        result = {key: value for key, value in result.items() if key != "pair_summary"}
    elif args.command == "export-approved":
        config = load_and_validate_config(args.config)
        result = export_approved(args.config, args.review_dir, args.review_csv,
                                 args.output or Path(config["evaluation"]["chunk_qrels_path"]))
    else:
        config, paths, questions, gold, _, cmap = load_inputs(args.config)
        result = validate_final(read_rows(args.qrels), questions, gold, cmap, config["chunking"]["version"])
        validate_chunk_qrels(args.qrels, paths["chunks"])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
