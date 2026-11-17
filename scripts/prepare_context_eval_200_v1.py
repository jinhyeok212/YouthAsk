"""Source-traceable fact preparation for the explicitly delegated 200-query review."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.review_chunk_qrels_200 import read_rows, sha, write_csv, write_json, write_rows

VERSION = "context_eval_200_v1"
BASE = ROOT / "data/evaluation/eval_200_v1"
OUT = BASE / VERSION
CHUNK_VERSION = "section_heading_800_ov120_v1"
CHUNKS = ROOT / f"data/processed/ontong_youth_full_v1/chunks/eval_200_v1/{CHUNK_VERSION}/chunks.jsonl"
OLD_QRELS = BASE / f"chunk_qrels/{CHUNK_VERSION}/qrels_chunk.jsonl"
REVIEWER = "Codex (사용자 위임 검수; 사람 직접 검수 아님)"


def locate_candidate(reference, source):
    # Only locate the source. Outputs always retain original characters/offsets.
    keep = lambda char: bool(re.match(r"[0-9A-Za-z가-힣]", char))
    indices = [i for i, char in enumerate(source) if keep(char)]
    normalized = "".join(source[i].lower() for i in indices)
    wanted = "".join(c.lower() for c in reference if keep(c))
    start = normalized.find(wanted)
    if start < 0 or not wanted:
        return None
    lo, hi = indices[start], indices[start + len(wanted) - 1] + 1
    # Preserve closing punctuation and complete the original final line. Some
    # approved references end mid-word; never use that fragment as a fact.
    lo = source.rfind("\n", 0, lo) + 1
    newline = source.find("\n", hi)
    hi = len(source) if newline < 0 else newline
    return lo, hi


def fact_units(text, document_list=False):
    """Keep exceptions/continuations together, separate explicit list facts.

    Context labels stay visible; a phrase under an exclusion heading must not
    silently become an eligibility condition. No sentence/number is rewritten.
    """
    lines = text.splitlines(keepends=True)
    units, current, scope = [], "", ""
    header_words = {"지원내용", "지원대상", "신청방법", "신청자격및방법", "신청서류", "제출서류", "자격요건", "소득재산요건", "보수", "근무시간", "지원제외", "제외대상", "공통", "근로자", "학생", "개별검진", "공통검진",
        "사업화지원금지원", "기타지원", "교육컨설팅등필수프로그램지원", "응시자격요건", "행사개요", "사업내용", "홈페이지", "지원방법", "고용이음지원근로자지원", "조직적응지원사업주지원", "시제품제작지원", "재료비지원", "멘토링교육프로그램", "기업지원금공통", "청년지원금비수도권유형지역별상이", "신청인", "접수방법", "집합프로그램", "본인이주소를두는경우", "직계존속이주소를두는경우", "공모부문", "후속프로그램", "제작비지원", "역량강화지원", "직무교육", "일경험프로그램", "청년밀착형프로그램", "멘토링프로그램", "필수제출서류", "아래요건을모두충족하는자", "근로조건", "대학교졸업생가지요건", "대학", "대학학생", "한국장학재단", "인턴활동", "신청절차"}
    header_words.update({"위조건을모두만족해야합니다", "비대면신청", "법인신청", "공고일기준아래의조건을모두충족하는가구", "아래가다항목을모두충족해야함", "아래항목을모두충족해야함", "생산비절감및보유기술확보지원", "개별서류신청자격및경력등확인서류", "해당시주민등록상거주지가광주광역시가아닌경우제출"})
    marker = re.compile(r"^\s*(?:[○ㅇ□❍•▪▸①-⑳❶-❿◎]|[-·－]\s*|\d+[.)]\s|[가-하]\.\s|\[(?:연\s*령|주\s*소|소\s*득|주\s*택)[^]]*\]|\((?:소\s*득|주\s*택)\))")
    for line in lines:
        clean = line.strip()
        if not clean:
            if current:
                current += line
            continue
        header_key = re.sub(r"[^가-힣]", "", clean)
        if header_key in header_words:
            if current.strip():
                units.append((scope, current.strip()))
                current = ""
            scope = clean
            continue
        is_new = bool(marker.match(line))
        if document_list and re.match(r"^\s*[-·]\s", line) and re.match(r"^\s*(?:[①-⑳]|\d+[.)])", current):
            is_new = False  # Conditions of a numbered form stay with that form.
        if document_list and re.match(r"^\s*[-·]\s", line) and re.search(r"택\s*1|중\s*1개|중\s*하나", current):
            is_new = False  # Alternatives are one requirement, not all mandatory.
        if current and is_new:
            units.append((scope, current.strip()))
            current = ""
            if scope and clean[:1] == scope.strip()[:1] and clean[:1] in "○ㅇ□❍◎":
                scope = ""
        elif current and not re.match(r"^\s*(?:※|\*|\[|\(|경우|신청 가능)", line) and not marker.match(current.splitlines()[0]):
            # Unbulleted complete lines (e.g. savings amounts) are separate facts.
            if len(current.strip()) >= 12 and len(clean) >= 12:
                units.append((scope, current.strip()))
                current = ""
        current += line
    if current.strip():
        units.append((scope, current.strip()))
    return units or [("", text.strip())]


def source_spans(question, documents, audit):
    qid = question["query_id"]
    primary = documents[question["ground_truth_document_ids"][0]]
    source = primary["retrieval_text"]
    if qid == "oy_eval200_new_0053":
        # The unchanged reference describes eligibility, not the asked method.
        return [(a["document_id"], a["evidence_quote"], "질문 기준: 접수방법; 참고답변 불일치 유지") for a in audit[qid]]
    if qid == "oy_eval_v2r_q0015":
        values = []
        for a in audit[qid]:
            quote = a["evidence_quote"]
            if a["chunk_id"].find("support") >= 0:
                quote = quote[quote.index("지원 대상:"):]
            values.append((a["document_id"], quote, "분할된 자격 조건"))
        return values
    span = locate_candidate(question["reference_answer"], source)
    if span is None:
        raise ValueError(f"Cannot trace reference to primary source: {qid}")
    quote = source[span[0]:span[1]]
    # Narrow two known overly broad references to the facts actually asked.
    if qid == "oy_eval200_new_0008":
        quote = quote[quote.index("ㅇ 신청방법"):quote.index("ㅇ 제출서류")].strip()
    elif qid == "oy_eval200_new_0003":
        quote = quote.split("\n")[0]
    elif qid == "oy_eval_repair_q0027":
        quote = quote[quote.index("□ 신청방법"):]
    elif qid == "oy_eval200_new_0022":
        quote = quote[quote.index("□ 신청자"):]
    elif qid == "oy_eval_repair_q0077":
        quote = quote[quote.index("[장애인]"):quote.index("▪필수 기재사항")].strip()
    return [(primary["document_id"], quote, "검수된 참고답변의 실제 원문 범위")]


def prepare():
    if OUT.exists():
        raise FileExistsError(OUT)
    questions = read_rows(BASE / "eval_questions.jsonl")
    documents = {d["document_id"]: d for d in read_rows(ROOT / "data/processed/ontong_youth_full_v1/documents.jsonl")}
    chunks = read_rows(CHUNKS)
    by_doc, audit = defaultdict(list), defaultdict(list)
    for chunk in chunks:
        by_doc[chunk["document_id"]].append(chunk)
    for row in read_rows(BASE / f"chunk_qrels/{CHUNK_VERSION}/delegated_review_v1/approved_evidence_audit.jsonl"):
        audit[row["query_id"]].append(row)
    facts, mapping, preview = [], [], []
    seen = set()
    for q in questions:
        qid = q["query_id"]
        for did, source_quote, selection_reason in source_spans(q, documents, audit):
            source = documents[did]["retrieval_text"]
            if source_quote not in source:
                raise ValueError(f"Nonliteral source span: {qid}")
            # Source field labels are context, not separate factual claims.
            source_quote = re.sub(r"^(?:지원 내용|추가 신청 자격|신청 방법|제출 서류):\s*", "", source_quote)
            units = [("신청 기간", source_quote)] if q["question_type"] in {"period", "application_period"} else fact_units(source_quote, q["question_type"] in {"documents", "required_documents"})
            if q["reference_answer"].startswith("정책명:"):
                # Preserve the whole literal policy-name line and title scope.
                units = [("정책 식별", source_quote)]
            if qid in {"oy_eval200_new_0045", "oy_eval200_new_0065"}:
                patterns = [("보증 효력·가입", r"신청일 기준.*?가입한"), ("임차보증금 상한", r"임차보증금 3억원 이하"),
                            ("연소득 구분·상한", r"연소득.*?이하"), ("무주택 여부", r"무주택 임차인")]
                units = [(label, re.search(pattern, source_quote, re.S).group()) for label, pattern in patterns]
            if qid == "oy_eval200_new_0130":
                units = [("미혼 소득 조건(공통 이하 조건 포함)", source_quote), ("신혼 합산소득 조건(공통 이하 조건 포함)", source_quote)]
            for scope, quote in units:
                original_unit = quote
                quote = re.sub(r"^[○ㅇ□❍•▪▸①-⑳❶-❿◎·‣－-]+\s*", "", quote)
                if quote not in source:
                    raise ValueError(f"Nonliteral fact unit: {qid}: {quote}")
                key = (qid, scope, quote)
                if key in seen:
                    continue
                seen.add(key)
                fid = "fact_" + hashlib.sha256((scope + "\0" + quote).encode()).hexdigest()[:16]
                evidence = []
                links = []
                for gold_did in q["ground_truth_document_ids"]:
                    original = documents[gold_did]["retrieval_text"]
                    # Final mapping requires literal complete fact containment.
                    # Alternative phrasings are not approved via similarity.
                    if quote not in original:
                        continue
                    evidence.append({"document_id": gold_did, "source_field": "retrieval_text", "quote": quote,
                                     "start_char": original.index(quote), "end_char": original.index(quote)+len(quote)})
                    for chunk in by_doc[gold_did]:
                        if quote in chunk["text"]:
                            if scope == "정책 식별" and chunk["section"] != "title":
                                continue
                            if scope and scope in original and scope not in chunk["text"]:
                                continue  # Do not lose a conditional/exclusion heading.
                            kind = q["question_type"]
                            if kind in {"documents", "required_documents"} and chunk["section"] not in {"documents", "application_method"}:
                                continue  # A form mentioned in training isn't a submission requirement.
                            if kind == "support_content" and chunk["section"] != "support":
                                continue
                            if kind == "eligibility" and chunk["section"] not in {"eligibility_extra", "support"}:
                                continue
                            links.append({"query_id": qid, "fact_id": fid, "chunk_id": chunk["chunk_id"],
                                          "chunking_version": CHUNK_VERSION, "review_status": "pending", "context_version": VERSION,
                                          "evidence_quote": quote, "reviewed_by": REVIEWER})
                if not evidence:
                    raise ValueError(f"Fact has no original evidence: {qid}/{fid}")
                facts.append({"query_id": qid, "fact_id": fid, "fact_text": (scope + " | " if scope else "") + quote,
                              "document_id": did, "source_location": f"retrieval_text[{source.index(quote)}:{source.index(quote)+len(quote)}]",
                              "source_evidence": evidence, "review_status": "pending", "context_version": VERSION,
                              "scope": scope, "original_source_unit": original_unit,
                              "reviewed_by": REVIEWER, "selection_reason": selection_reason})
                mapping.extend(links or [{"query_id": qid, "fact_id": fid, "chunk_id": None,
                                          "chunking_version": CHUNK_VERSION, "review_status": "pending", "context_version": VERSION,
                                          "reviewed_by": REVIEWER, "reason": "No single chunk contains the complete fact; keep denominator."}])
                preview.append({"query_id": qid, "query": q["query"], "fact_id": fid, "scope": scope, "fact_text": quote,
                                "source_document_id": did, "supporting_gold_documents": len(evidence),
                                "supporting_chunk_count": len(links), "review_status": "pending"})
    OUT.mkdir()
    write_rows(OUT / "required_facts.jsonl", facts)
    write_rows(OUT / "chunk_fact_map.jsonl", mapping)
    write_csv(OUT / "fact_review.csv", preview)
    old = read_rows(OLD_QRELS)
    context_qrels = [{**r, "review_status": "approved", "context_version": VERSION} for r in old]
    target = OUT / CHUNK_VERSION
    target.mkdir()
    write_rows(target / "qrels_chunk.jsonl", context_qrels)
    write_json(OUT / "preparation_manifest.json", {"context_version": VERSION,
        "question_count": len(questions), "fact_count": len(facts), "mapping_count": len(mapping),
        "no_single_support_chunk_fact_count": sum(r["chunk_id"] is None for r in mapping),
        "fact_count_by_query": dict(Counter(r["query_id"] for r in facts)),
        "baseline_qrels_sha256": sha(OLD_QRELS), "baseline_qrels_ids_relevance_unchanged": True,
        "reviewer": REVIEWER, "status": "PENDING_FACT_REVIEW"})
    print(json.dumps({"questions": len(questions), "facts": len(facts), "mappings": len(mapping),
                      "no_single_chunk_facts": sum(r["chunk_id"] is None for r in mapping)}, indent=2))


def approve_source_review():
    """Record the completed delegated review, leaving real source defects pending."""
    facts = read_rows(OUT / "required_facts.jsonl")
    links = read_rows(OUT / "chunk_fact_map.jsonl")
    pending_reasons = {}
    for fact in facts:
        qid, text = fact["query_id"], fact["source_evidence"][0]["quote"]
        reason = None
        if qid == "oy_eval200_new_0025" and text.endswith("관심있는 사"):
            reason = "원본 raw_record와 retrieval_text가 '관심있는 사'에서 절단됨. 누락 문구를 추정하지 않음."
        elif qid == "oy_eval200_new_0120" and text.endswith("건축물 대"):
            reason = "원본 자격 조건이 '인천시 소재 건축물 대'에서 절단됨. 건축물 조건을 완성하지 않음."
        elif qid == "oy_eval200_new_0021" and "상반기 64명(상반기 32명" in text:
            reason = "원본 인원 표기가 상반기64명과 상반기32명/하반기32명으로 모순됨. 임의 정정 금지."
        fact["review_status"] = "pending" if reason else "approved"
        fact["review_reason"] = reason or "질문과 검수된 참고답변 범위를 원본문서의 실제 문장·조건·예외에 대조. 정확한 원문 인용과 전체 사실을 포함한 청크만 연결. 목록 제목은 분모에서 제외하고 대안/조건부 문구를 유지."
        if reason:
            pending_reasons[qid] = reason
    statuses = {(f["query_id"], f["fact_id"]): f["review_status"] for f in facts}
    for link in links:
        link["review_status"] = statuses[link["query_id"], link["fact_id"]]
    for name, rows in (("required_facts.jsonl", facts), ("chunk_fact_map.jsonl", links)):
        (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8")
    preview = [{"query_id": f["query_id"], "fact_id": f["fact_id"], "fact_text": f["fact_text"],
                "source_document_id": f["document_id"], "source_location": f["source_location"],
                "scope": f["scope"], "review_status": f["review_status"], "review_reason": f["review_reason"],
                "supporting_chunks": json.dumps([r["chunk_id"] for r in links if r["query_id"] == f["query_id"] and r["fact_id"] == f["fact_id"]]),
                "reviewed_by": REVIEWER} for f in facts]
    import csv
    with (OUT / "fact_review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(preview[0]))
        writer.writeheader()
        writer.writerows(preview)
    manifest_path = OUT / "preparation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(status="REVIEWED_WITH_SOURCE_EXCEPTIONS", pending_query_reasons=pending_reasons,
                    recall_ready_query_count=200-len(pending_reasons), precision_ready_query_count=200,
                    reviewer_type="user_delegated_agent", review_status_counts=dict(Counter(f["review_status"] for f in facts)),
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in [BASE/"eval_questions.jsonl", BASE/"qrels.jsonl", OLD_QRELS, CHUNKS, ROOT/"data/processed/ontong_youth_full_v1/documents.jsonl"]},
                    artifacts={str(p.relative_to(OUT)): sha(p) for p in OUT.rglob("*") if p.is_file() and p != manifest_path})
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"facts":len(facts), "review_status_counts":manifest["review_status_counts"], "pending_queries":pending_reasons}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "approve-reviewed"], default="prepare", nargs="?")
    args = parser.parse_args()
    prepare() if args.command == "prepare" else approve_source_review()
