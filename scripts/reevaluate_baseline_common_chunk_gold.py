"""Re-evaluate saved Baseline ranks under the same fact-based Gold rule as C01-03.

This is a separate annotation/evaluation artifact, not another model/search run.
"""
from __future__ import annotations

import copy
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_chunking_comparison_200 import remap, BASE_CONFIG, AUDIT
from scripts.review_chunk_qrels_200 import read_rows,sha,write_rows,write_json
from src.experiments.config_validator import load_and_validate_config
from src.evaluation.evaluate_experiment import evaluate_experiment


def main():
    out=AUDIT/"baseline_common_gold_evaluation"
    if out.exists():
        raise FileExistsError(out)
    cfg=load_and_validate_config(BASE_CONFIG)
    docs={d["document_id"]:d for d in read_rows(cfg["dataset"]["document_path"])}
    chunks=read_rows(cfg["chunking"]["chunk_path"])
    sections=defaultdict(list)
    for c in chunks:
        sections[c["document_id"]].append(c)
    questions=read_rows(cfg["evaluation"]["questions_path"])
    facts=read_rows(cfg["evaluation"]["context_metrics"]["required_facts_path"])
    mapping,gold=remap(cfg,questions,facts,chunks,docs,sections)
    old_gold=read_rows(cfg["evaluation"]["chunk_qrels_path"])
    previous={(r["query_id"],r["chunk_id"]) for r in old_gold}
    extra=[r for r in gold if (r["query_id"],r["chunk_id"]) not in previous]
    if {(r["query_id"],r["chunk_id"]) for r in gold}-previous != {
        ("oy_eval200_new_0039","ontong_youth_20250618005400111002__sec_03_application_method__chunk_000"),
        ("oy_eval200_new_0054","ontong_youth_20251124005400211941__sec_04_application_method__chunk_000"),
    }:
        raise ValueError("Unexpected change to the reviewed Baseline Gold scope")
    out.mkdir()
    write_rows(out/"qrels_chunk.jsonl",gold)
    write_rows(out/"chunk_fact_map.jsonl",mapping)
    comparison_config=copy.deepcopy(cfg)
    comparison_config["evaluation"]["chunk_qrels_path"]=str(out/"qrels_chunk.jsonl")
    comparison_config["evaluation"]["context_metrics"]["chunk_fact_map_path"]=str(out/"chunk_fact_map.jsonl")
    source=ROOT/"experiments/exp_full_kure_200_context_v1/retrieval_results.jsonl"
    result=evaluate_experiment(comparison_config,read_rows(source))
    write_json(out/"resolved_evaluation_config.json",comparison_config)
    write_json(out/"metrics_summary.json",result["metrics_summary"])
    write_rows(out/"metrics_by_query.jsonl",result["metrics_by_query"])
    write_json(out/"evaluation_manifest.json",{
        "source_search_run_id":"exp_full_kure_200_context_v1", "evaluation_id":"baseline_common_fact_gold_v1",
        "search_or_embedding_executed":False,"source_retrieval_sha256":sha(source),
        "original_gold_count":len(old_gold),"common_gold_count":len(gold),"reviewed_added_mappings":extra,
        "reason":"0039 application-method explicitly requires application/self-introduction forms; 0054 application-method explicitly requires project plan/business certificate/local-tax proof. These fully support submitted required facts.",
        "fact_sha256":sha(cfg["evaluation"]["context_metrics"]["required_facts_path"]),
        "context_inputs":result["context_metrics"],"status":"SEPARATE_COMMON_RULE_REEVALUATION"})
    print(json.dumps(result["metrics_summary"],ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
