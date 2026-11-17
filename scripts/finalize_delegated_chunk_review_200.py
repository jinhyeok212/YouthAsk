"""Apply Codex's source-reviewed decisions under the user's explicit delegation.

This is a reviewed decision record, not a general semantic auto-approval tool.
Inputs are pinned by human_review_v1/review_manifest.json. No model/index calls.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.review_chunk_qrels_200 import (
    export_approved, load_inputs, quoted_in_source, read_rows, sha, write_csv,
    write_json, write_rows,
)

CONFIG = "configs/experiments/exp_full_kure_200_v1.yaml"
BASE = ROOT / "data/evaluation/eval_200_v1/chunk_qrels/section_heading_800_ov120_v1"
REVIEW = BASE / "human_review_v1"
OUTPUT = BASE / "delegated_review_v1"
REVIEWER = "Codex (사용자 명시적 위임 검수; 사람 직접 검수 아님)"

def evidence(row, document):
    text = row["chunk_text"]
    body = text.split("\n\n", 1)[-1]
    # Keep exact source evidence. Never turn normalized text into a quotation.
    answer = row["reference_answer"]
    if answer in text and quoted_in_source(answer, document):
        return answer
    if quoted_in_source(body, document):
        return body
    quote = row["exact_excerpt_for_review"]
    if len(quote.strip()) >= 8 and quote in text and quoted_in_source(quote, document):
        return quote
    raise ValueError(f"No verbatim evidence: {row['chunk_id']}")


def main():
    if OUTPUT.exists() or (BASE / "qrels_chunk.jsonl").exists():
        raise FileExistsError("Delegated review/final already exists; never overwrite")
    config, paths, questions, gold, dmap, cmap = load_inputs(CONFIG)
    manifest = json.loads((REVIEW / "review_manifest.json").read_text(encoding="utf-8"))
    for info in manifest["inputs"].values():
        if sha(info["path"]) != info["sha256"]:
            raise ValueError("Review input changed")
    snapshot = REVIEW / "candidates.snapshot.jsonl"
    if sha(snapshot) != manifest["artifacts"][snapshot.name]:
        raise ValueError("Review snapshot changed")
    rows = read_rows(snapshot)
    by_pair = defaultdict(list)
    for row in rows:
        by_pair[row["query_id"], row["document_id"]].append(row)
    # Final decisions use explicitly recorded IDs, never a similarity threshold.
    report_path = REVIEW / "validation_report.json"
    if sha(report_path) != manifest["artifacts"][report_path.name]:
        raise ValueError("Reviewed exception report changed")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    plan = json.loads((ROOT / "docs/chunking/eval_200_v1_delegated_decisions.json").read_text(encoding="utf-8"))
    expected_pairs = {(p["query_id"], p["document_id"]) for p in report["gold_pairs_without_approve_recommendation"]}
    if len(plan) != 53 or {(p["query_id"], p["document_id"]) for p in plan} != expected_pairs:
        raise ValueError("Explicit decision plan does not cover the reviewed exceptions")
    selected = {}
    for pair in plan:
        by_id = {r["chunk_id"]: r for r in by_pair[pair["query_id"], pair["document_id"]]}
        for chunk_id in pair["selected_chunk_ids"]:
            row = by_id[chunk_id]
            selected[row["candidate_id"]] = ("SOURCE_FACT_REVIEW", pair["reason"])
    # Direct-answer rows were inspected by question/section; source containment is
    # independently rechecked here. A known semantic false positive is overridden.
    for row in rows:
        if row["recommendation"] == "APPROVE" and row["query_id"] != "oy_eval200_new_0053":
            if row["reference_answer"] not in cmap[row["chunk_id"]]["text"] or not quoted_in_source(row["reference_answer"], dmap[row["document_id"]]):
                raise ValueError("Direct evidence no longer matches")
            selected[row["candidate_id"]] = ("DIRECT_ANSWER_REVIEW", "질문이 묻는 " + row["question_type"] + " 사실을 해당 청크와 원문에서 대조했으며 참고답변 전체가 직접 포함됨. 제목 접두어만 있는 다른 하위 청크는 제외. 수집 원문 기준이며 현행 정책 여부를 외부 검증한 것은 아님.")
    for row in rows:
        if row["query_id"] == "oy_eval200_new_0053" and row["section"] in {"documents", "application_url"}:
            selected[row["candidate_id"]] = ("QUESTION_REFERENCE_MISMATCH_OVERRIDE",
                "질문은 접수방법이지만 참고답변과 application_method 원문은 자격만 설명하여 그 청크를 불채택. 실제 '신청서 및 자기소개서, 관련 증빙자료 등 업로드(공고문 참조)'와 '신청 URL' 청크가 접수에 필요한 직접 사실을 지지하므로 두 청크를 선정. 사이트 내 상세클릭절차·이메일/방문 여부는 추정하지 않음. 원본 참고답변은 수정하지 않음.")
    audit, summaries = [], []
    for row in rows:
        row["reviewer"] = REVIEWER
        if row["candidate_id"] in selected:
            method, reason = selected[row["candidate_id"]]
            quote = evidence(row, dmap[row["document_id"]])
            row.update(human_decision="APPROVE", human_evidence_quote=quote, human_note=reason)
            doc = dmap[row["document_id"]]
            source_text = doc["retrieval_text"]
            source_field = "retrieval_text"
            if quote not in source_text:
                source_field, source_text = next(("raw_record."+k, v) for k, v in doc["raw_record"].items() if isinstance(v, str) and quote in v)
            audit.append({"query_id": row["query_id"], "document_id": row["document_id"], "chunk_id": row["chunk_id"],
                          "query": row["query"], "reference_answer": row["reference_answer"], "chunk_text": row["chunk_text"],
                          "evidence_quote": quote, "source_field": source_field,
                          "source_quote_start": source_text.index(quote), "source_quote_end": source_text.index(quote)+len(quote),
                          "chunk_quote_start": row["chunk_text"].index(quote), "chunk_quote_end": row["chunk_text"].index(quote)+len(quote),
                          "review_method": method, "reviewed_by": REVIEWER, "reason": reason,
                          "source_raw_record_related": json.loads(row["source_raw_record_related"]),
                          "original_recommendation": row["recommendation"]})
        else:
            if row["query_id"] == "oy_eval200_new_0053" and row["section"] == "application_method":
                reason = "참고답변과는 일치하나 질문이 묻는 접수방법이 아니라 자격만 설명하므로 정답 청크에서 제외. 실제 업로드 안내와 신청URL을 별도 선정."
            else:
                reason = "질문이 요구하는 사실의 완결 근거로 선정하지 않음. 이 Gold 연결에서 직접 근거를 확인한 청크를 별도 선정했으며, 문서가 Gold라는 이유로 모든 하위 청크를 정답 처리하지 않음. 부분적으로 관련된 내용이 전혀 없다는 판정은 아님."
            row.update(human_decision="REJECT", human_evidence_quote="", human_note=reason)
    for q in questions:
        items = [a for a in audit if a["query_id"] == q["query_id"]]
        summaries.append({"query_id": q["query_id"], "query": q["query"], "reference_answer": q["reference_answer"],
                          "gold_document_count": len(q["ground_truth_document_ids"]), "approved_chunk_count": len(items),
                          "approved_chunk_ids": json.dumps([a["chunk_id"] for a in items]),
                          "review_methods": "|".join(sorted({a["review_method"] for a in items})),
                          "decision_reasons": "\n".join(dict.fromkeys(a["reason"] for a in items)),
                          "reviewed_by": REVIEWER})
    OUTPUT.mkdir(exist_ok=False)
    write_json(OUTPUT / "exception_decision_plan.json", plan)
    write_rows(OUTPUT / "approved_evidence_audit.jsonl", audit)
    write_csv(OUTPUT / "delegated_review.csv", rows)
    write_csv(OUTPUT / "query_review_summary.csv", summaries)
    result = export_approved(CONFIG, REVIEW, OUTPUT / "delegated_review.csv", BASE / "qrels_chunk.jsonl")
    approval_path = BASE / "qrels_chunk.human_approval.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval.update(approval_mode="user_delegated_agent_review", reviewer=REVIEWER, not_human_manual_review=True)
    approval_path.write_text(json.dumps(approval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_json(OUTPUT / "delegation_receipt.json", {
        **result, "reviewer_type": "agent", "reviewed_by": REVIEWER,
        "authorization": "User explicitly asked Codex to perform the review and prepare the final Runner inputs in this conversation.",
        "not_human_manual_review": True, "methods": dict(Counter(a["review_method"] for a in audit)),
        "final_qrels_sha256": sha(BASE / "qrels_chunk.jsonl"),
        "artifacts": {p.name: sha(p) for p in OUTPUT.iterdir()},
        "caveat": "Binary relevance identifies source-supported answer-bearing chunks. A chunk may support part of a multi-chunk/multi-Gold answer; complete reference support is checked at the combined evidence level. Query 0053 has an unchanged reference-answer mismatch documented in its audit."})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
