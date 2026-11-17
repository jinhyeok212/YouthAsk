from collections import defaultdict
from copy import deepcopy

import pytest

from scripts.prepare_chunking_comparison_200 import parameter_check, remap
from scripts.report_chunking_comparison_200 import quality_key


def test_selection_respects_declared_document_hit5_priority():
    higher_hit = {"document_hit_at_5": .965, "document_mrr": .923, "document_hit_at_1": .895, "context_recall_at_5": .91}
    higher_mrr = {"document_hit_at_5": .960, "document_mrr": .928, "document_hit_at_1": .905, "context_recall_at_5": .92}
    assert quality_key(higher_hit) > quality_key(higher_mrr)


def test_unrequested_model_change_is_rejected():
    base = {"embedding": {"batch_size": 32}, "retrieval": {"evaluation_max_k": 5},
            "chunking": {"strategy": "section", "size": 800, "overlap": 120}}
    candidate = deepcopy(base)
    candidate["chunking"]["strategy"] = "fixed"
    assert parameter_check(base, candidate, ("fixed", 800, 120, "v1"))
    candidate["embedding"]["batch_size"] = 16
    with pytest.raises(ValueError, match="Unauthorized"):
        parameter_check(base, candidate, ("fixed", 800, 120, "v1"))


def test_requested_overlap_cannot_silently_change():
    base = {"embedding": {}, "retrieval": {}, "chunking": {"strategy": "section", "size": 800, "overlap": 120}}
    with pytest.raises(ValueError, match="not respected"):
        parameter_check(base, base, ("section", 800, 0, "v1"))


def test_split_fact_stays_in_denominator_and_unrelated_chunk_is_not_gold():
    text = "신청 시작은 3월 1일, 마감은 3월 30일. 온라인으로 접수한다. 담당 기관 안내."
    facts = [{"query_id": "q", "fact_id": fid, "scope": "", "review_status": "approved",
              "source_evidence": [{"document_id": "d", "quote": quote, "start_char": text.index(quote),
                                   "end_char": text.index(quote)+len(quote)}]}
             for fid, quote in [("period", "신청 시작은 3월 1일, 마감은 3월 30일."), ("method", "온라인으로 접수한다.")]]
    chunk_texts = ["신청 시작은 3월 1일,", "마감은 3월 30일.", "온라인으로 접수한다.", "담당 기관 안내."]
    chunks = [{"chunk_id": str(i), "document_id": "d", "text": t, "start_char": text.index(t)} for i,t in enumerate(chunk_texts)]
    config = {"chunking": {"strategy": "fixed", "version": "fixed_v1"}}
    maps, qrels = remap(config, [{"query_id": "q", "question_type": "application_method"}], facts, chunks,
                        {"d": {"retrieval_text": text}}, defaultdict(list))
    assert any(r["fact_id"] == "period" and r["chunk_id"] is None for r in maps)
    assert [r["chunk_id"] for r in qrels] == ["2"]


def test_policy_name_repeated_prefix_does_not_make_every_section_gold():
    quote = "정책명: 청년지원"
    facts = [{"query_id": "q", "fact_id": "name", "scope": "정책 식별", "review_status": "approved",
              "source_evidence": [{"document_id": "d", "quote": quote, "start_char": 0, "end_char": len(quote)}]}]
    chunks = [{"chunk_id": section, "document_id": "d", "section": section, "text": quote} for section in ["title", "support"]]
    _, qrels = remap({"chunking": {"strategy": "section", "version": "section_v1"}},
                    [{"query_id": "q", "question_type": "specific_policy_search"}], facts, chunks,
                    {"d": {"retrieval_text": quote}}, defaultdict(list))
    assert [r["chunk_id"] for r in qrels] == ["title"]
