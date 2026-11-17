import copy

import pytest

from src.common.io import write_jsonl
from src.evaluation.evaluate_experiment import evaluate_experiment
from scripts.prepare_context_eval_200_v1 import fact_units, locate_candidate


@pytest.fixture
def multi_gold(tmp_path):
    quote = "19세 이상 청년"
    evidence = [{"document_id": d, "source_field": "retrieval_text", "quote": quote,
                 "start_char": 0, "end_char": len(quote)} for d in ("d1", "d2")]
    values = {
        "questions": [{"query_id": "q1", "query": "대상은?"}],
        "documents": [{"document_id": d, "retrieval_text": quote} for d in ("d1", "d2")],
        "chunks": [{"chunk_id": c, "document_id": d, "text": quote} for c, d in (("c1", "d1"), ("c2", "d2"))],
        "doc_qrels": [{"query_id": "q1", "document_id": d} for d in ("d1", "d2")],
        "qrels": [{"query_id": "q1", "chunk_id": c, "document_id": d, "relevance": 1,
                   "review_status": "approved"} for c, d in (("c1", "d1"), ("c2", "d2"))],
        "facts": [{"query_id": "q1", "fact_id": "age", "fact_text": quote, "document_id": "d1",
                   "source_location": "retrieval_text[0:9]", "review_status": "approved", "source_evidence": evidence}],
        "mapping": [{"query_id": "q1", "fact_id": "age", "chunk_id": c,
                     "chunking_version": "v1", "review_status": "approved"} for c in ("c1", "c2")],
    }
    path = lambda key: str(tmp_path / (key + ".jsonl"))
    config = {"dataset": {"document_path": path("documents")},
              "chunking": {"version": "v1", "chunk_path": path("chunks")},
              "retrieval": {"evaluation_max_k": 5},
              "evaluation": {"questions_path": path("questions"), "document_qrels_path": path("doc_qrels"),
                             "chunk_qrels_path": path("qrels"), "ks": [1, 3, 5],
                             "context_metrics": {"enabled": True, "version": "ctx", "k": 5,
                                                 "required_facts_path": path("facts"), "chunk_fact_map_path": path("mapping")}}}

    def run(changes=None):
        data = copy.deepcopy(values)
        if changes:
            changes(data)
        for key, rows in data.items():
            write_jsonl(path(key), rows)
        return evaluate_experiment(config, [{"query_id": "q1", "retrieval_latency_ms": 1,
                                            "results": [{"rank": 1, "chunk_id": "c2", "document_id": "d2"}]}])
    return run


def test_alternative_gold_supports_one_unique_fact(multi_gold):
    result = multi_gold()
    row = result["metrics_by_query"][0]
    assert row["required_fact_ids"] == ["age"]
    assert row["supported_fact_ids"] == ["age"]
    assert row["context_recall_at_5"] == 1


@pytest.mark.parametrize("case", ["offset", "quote", "non_gold", "partial_chunk", "no_canonical_evidence"])
def test_source_and_mapping_must_be_real(multi_gold, case):
    def edit(data):
        if case == "offset":
            data["facts"][0]["source_evidence"][0]["start_char"] = 1
        elif case == "quote":
            data["facts"][0]["source_evidence"][0]["quote"] = "만들어낸 사실"
        elif case == "non_gold":
            data["doc_qrels"].pop()
        elif case == "partial_chunk":
            data["chunks"][1]["text"] = "19세"
        else:
            data["facts"][0]["source_evidence"].pop(0)
    with pytest.raises(ValueError):
        multi_gold(edit)


def test_headers_are_context_not_recall_denominator():
    units = fact_units("○ 공통 검진\n- 혈액검사: 빈혈\n- 소변검사: 요당")
    assert len(units) == 2
    assert all(scope == "○ 공통 검진" for scope, _ in units)


def test_form_conditions_stay_with_the_form():
    units = fact_units("① 위임장 1부\n - 대리인이 접수하는 경우\n② 신청서 1부", document_list=True)
    assert len(units) == 2
    assert "대리인이 접수하는 경우" in units[0][1]


def test_source_span_preserves_closing_punctuation():
    source = "제출 서류: 추천서 (선택사항)\n다른 절"
    start, end = locate_candidate("추천서 (선택사항)", source)
    assert source[start:end].endswith("(선택사항)")
