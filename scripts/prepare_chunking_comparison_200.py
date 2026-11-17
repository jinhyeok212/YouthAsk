"""Prepare exactly the requested C01/C02/C03 conditions with frozen KURE inputs."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yaml
from scripts.review_chunk_qrels_200 import read_rows, sha, write_csv, write_json, write_rows
from src.chunking.build_chunks import build_chunks
from src.data.validate_documents import validate_documents
from src.evaluation.validate_inputs import load_context_inputs, validate_evaluation_inputs
from src.experiments.config_validator import load_and_validate_config

BASE_CONFIG = ROOT / "configs/experiments/exp_full_kure_200_context_v1.yaml"
CONTEXT = ROOT / "data/evaluation/eval_200_v1/context_eval_200_v1"
AUDIT = ROOT / "experiments/chunking_comparison_eval_200_v1"
CONDITIONS = {
    "C01": ("fixed", 800, 120, "fixed_800_ov120_v1"),
    "C02": ("section", 500, 120, "section_heading_500_ov120_v1"),
    "C03": ("section", 800, 0, "section_heading_800_ov0_v1"),
}
REVIEWER = "Codex (사용자 위임; 검수된 원문 사실의 전체 포함 및 조건 범위 검증)"
ALLOWED = {
    "experiment_id", "experiment_name", "base_experiment_id", "chunking.version",
    "chunking.strategy", "chunking.size", "chunking.overlap", "chunking.chunk_path", "chunking.manifest_path",
    "evaluation.chunk_qrels_path", "evaluation.context_metrics.chunk_fact_map_path",
    "index.version", "index.db_path", "index.collection_name",
}


def differences(a, b, prefix=""):
    if isinstance(a, dict) and isinstance(b, dict):
        result = []
        for key in a.keys() | b.keys():
            result.extend(differences(a.get(key), b.get(key), prefix + ("." if prefix else "") + key))
        return result
    return [] if a == b else [{"field": prefix, "baseline": a, "candidate": b}]


def parameter_check(base, candidate, condition):
    strategy, size, overlap, _ = condition
    changes = differences(base, candidate)
    unexpected = [r for r in changes if r["field"] not in ALLOWED]
    if unexpected:
        raise ValueError(f"Unauthorized configuration differences: {unexpected}")
    if (candidate["chunking"]["strategy"], candidate["chunking"]["size"], candidate["chunking"]["overlap"]) != (strategy, size, overlap):
        raise ValueError("Requested strategy/size/overlap not respected")
    if candidate["embedding"] != base["embedding"] or candidate["retrieval"] != base["retrieval"]:
        raise ValueError("Embedding/retrieval settings changed")
    return changes


def quoted_occurrences(text, quote):
    offset = 0
    while True:
        found = text.find(quote, offset)
        if found < 0:
            return
        yield found
        offset = found + 1


def remap(config, questions, facts, chunks, documents, baseline_sections):
    """Map complete, already reviewed source claims; no semantic similarity."""
    by_doc = defaultdict(list)
    for chunk in chunks:
        by_doc[chunk["document_id"]].append(chunk)
    qmap = {q["query_id"]: q for q in questions}
    mapping, positives = [], {}
    for fact in facts:
        qid, fid = fact["query_id"], fact["fact_id"]
        q = qmap[qid]
        kind = q["question_type"]
        allowed_sections = ({"documents", "application_method"} if kind in {"documents", "required_documents"}
                            else {"support"} if kind == "support_content"
                            else {"support", "eligibility_extra"} if kind == "eligibility" else None)
        found = set()
        for source in fact["source_evidence"]:
            did, quote = source["document_id"], source["quote"]
            original = documents[did]["retrieval_text"]
            if original[source["start_char"]:source["end_char"]] != quote:
                raise ValueError("Frozen source fact quote changed")
            for chunk in by_doc[did]:
                if quote not in chunk["text"]:
                    continue
                if fact["scope"] == "정책 식별":
                    if config["chunking"]["strategy"] == "section" and chunk.get("section") != "title":
                        continue
                    if config["chunking"]["strategy"] == "fixed" and chunk["start_char"] != 0:
                        continue
                scope = fact.get("scope", "")
                if scope and scope in original and scope not in chunk["text"]:
                    continue
                if config["chunking"]["strategy"] == "section":
                    if allowed_sections and chunk.get("section") not in allowed_sections:
                        continue
                    positions = list(quoted_occurrences(chunk["text"], quote))
                else:
                    positions = []
                    for offset in quoted_occurrences(chunk["text"], quote):
                        absolute = chunk["start_char"] + offset
                        if original[absolute:absolute+len(quote)] != quote:
                            raise ValueError("Fixed chunk/source position mismatch")
                        if allowed_sections and not any(s["section"] in allowed_sections and s["start_char"] <= absolute
                                and absolute+len(quote) <= s["end_char"] for s in baseline_sections[did]):
                            continue
                        positions.append(offset)
                if not positions or chunk["chunk_id"] in found:
                    continue
                found.add(chunk["chunk_id"])
                mapping.append({"query_id": qid, "fact_id": fid, "chunk_id": chunk["chunk_id"],
                                "chunking_version": config["chunking"]["version"], "context_version": "context_eval_200_v1",
                                "review_status": fact["review_status"], "evidence_quote": quote,
                                "chunk_quote_start": positions[0], "chunk_quote_end": positions[0]+len(quote),
                                "reviewed_by": REVIEWER, "mapping_method": "complete_literal_source_fact_with_scope"})
                if fact["review_status"] == "approved":
                    key = qid, chunk["chunk_id"]
                    if key not in positives:
                        positives[key] = {"query_id": qid, "document_id": did, "chunk_id": chunk["chunk_id"],
                                          "relevance": 1, "chunking_version": config["chunking"]["version"],
                                          "context_version": "context_eval_200_v1", "review_status": "approved",
                                          "reviewed_by": REVIEWER, "evidence_text": quote, "source_fact_ids": []}
                        if "section" in chunk:
                            positives[key]["matched_section"] = chunk["section"]
                    positives[key]["source_fact_ids"].append(fid)
        if not found:
            mapping.append({"query_id": qid, "fact_id": fid, "chunk_id": None,
                            "chunking_version": config["chunking"]["version"], "context_version": "context_eval_200_v1",
                            "review_status": fact["review_status"], "reviewed_by": REVIEWER,
                            "reason": "No single chunk fully contains this fact and its required conditional scope; denominator preserved."})
    qrels = list(positives.values())
    question_ids = {q["query_id"] for q in questions}
    if {r["query_id"] for r in qrels} != question_ids:
        raise ValueError(f"Questions with no justified chunk Gold: {question_ids - {r['query_id'] for r in qrels}}")
    if len({(r["query_id"], r["chunk_id"]) for r in qrels}) != len(qrels):
        raise ValueError("Duplicate chunk Gold")
    return mapping, qrels


def prepare(plan_id):
    condition = CONDITIONS[plan_id]
    strategy, size, overlap, version = condition
    base = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    cfg = copy.deepcopy(base)
    suffix = f"{strategy}_{size}_ov{overlap}"
    run_id = f"exp_full_kure_200_{suffix}_v1"
    cfg.update(experiment_id=run_id, experiment_name=run_id.replace("_", "-"), base_experiment_id=base["experiment_id"])
    cfg["chunking"].update(version=version, strategy=strategy, size=size, overlap=overlap)
    cfg["evaluation"]["chunk_qrels_path"] = f"data/evaluation/eval_200_v1/context_eval_200_v1/{version}/qrels_chunk.jsonl"
    cfg["evaluation"]["context_metrics"]["chunk_fact_map_path"] = f"data/evaluation/eval_200_v1/context_eval_200_v1/{version}/chunk_fact_map.jsonl"
    namespace = f"index_full_kure_200_{suffix}_v1"
    cfg["index"].update(version=namespace, db_path=f"indexes/chroma/{namespace}", collection_name=f"ontong_youth_full_kure_200_{suffix}_v1")
    changes = parameter_check(base, cfg, condition)
    path = ROOT / f"configs/experiments/{run_id}.yaml"
    if path.exists() or (ROOT / cfg["evaluation"]["chunk_qrels_path"]).exists():
        raise FileExistsError(f"Existing config/Gold is protected: {run_id}")
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(cfg, handle, allow_unicode=True, sort_keys=False)
    config = load_and_validate_config(path)
    dataset = validate_documents(config)
    initial = build_chunks(config, dataset)  # Generate only; never resolves an Index.
    chunks = read_rows(initial["chunk_path"])
    questions = read_rows(config["evaluation"]["questions_path"])
    facts = read_rows(config["evaluation"]["context_metrics"]["required_facts_path"])
    documents = {d["document_id"]: d for d in read_rows(config["dataset"]["document_path"])}
    old_config = load_and_validate_config(BASE_CONFIG)
    old_sections = defaultdict(list)
    for chunk in read_rows(old_config["chunking"]["chunk_path"]):
        old_sections[chunk["document_id"]].append(chunk)
    mapping, qrels = remap(config, questions, facts, chunks, documents, old_sections)
    write_rows(config["evaluation"]["chunk_qrels_path"], qrels)
    write_rows(config["evaluation"]["context_metrics"]["chunk_fact_map_path"], mapping)
    info = build_chunks(config, dataset)  # Registers reviewed qrels/meta; no embeddings.
    ev = validate_evaluation_inputs(config, dataset, info)
    ctx = load_context_inputs(config)
    if info["chunk_qrels_status"] != "ready" or ev["question_count"] != 200:
        raise ValueError("Pre-index review is not ready")
    gold_pairs = {(r["query_id"], r["document_id"]) for r in read_rows(config["evaluation"]["document_qrels_path"])}
    covered = {(r["query_id"], r["document_id"]) for r in qrels}
    original_lengths = [len(d["retrieval_text"]) for d in documents.values()]
    split_sections = Counter((c["document_id"], c.get("section_index")) for c in chunks)
    report = {"plan_id": plan_id, "experiment_id": run_id, "requested": {"strategy": strategy, "size": size, "overlap": overlap},
              "configuration_differences": changes, "unexpected_configuration_changes": [],
              "question_count": 200, "document_gold_pair_count": len(gold_pairs), "covered_gold_pairs": len(covered),
              "gold_pairs_without_single_fact_chunk": sorted(gold_pairs-covered), "chunk_count": len(chunks), "chunk_qrels_count": len(qrels),
              "fact_count": len(facts), "fact_map_count": len(mapping), "facts_without_single_complete_chunk": sum(r["chunk_id"] is None for r in mapping),
              "fact_sha256": sha(config["evaluation"]["context_metrics"]["required_facts_path"]),
              "chunk_qrels_sha256": sha(config["evaluation"]["chunk_qrels_path"]),
              "chunk_sha256": sha(info["chunk_path"]), "max_final_chunk_length": max(len(c["text"]) for c in chunks),
              "mean_final_chunk_length": sum(len(c["text"]) for c in chunks)/len(chunks),
              "multi_part_section_count": sum(v>1 for v in split_sections.values()) if strategy == "section" else None,
              "document_count": len(documents), "context_recall_ready_queries": sum(all(f["review_status"] == "approved" for f in fs.values()) for fs in ctx["facts"].values()),
              "status": "READY_FOR_INDEX", "gold_rule": "A complete approved required fact with source and role/conditional scope; Gold document alone is insufficient.",
              "baseline_gold_rule_difference": "Baseline retains its prior 211 whole-answer-reviewed positives; 2 additional fact-bearing baseline chunks exist. Precision/chunk-Gold comparisons to baseline require this limitation; document metrics and fixed fact Recall remain controlled."}
    AUDIT.mkdir(exist_ok=True)
    write_json(AUDIT / f"{plan_id}_preflight.json", report)
    write_csv(AUDIT / f"{plan_id}_chunk_review.csv", [{"query_id": r["query_id"], "document_id": r["document_id"],
              "chunk_id": r["chunk_id"], "fact_ids": json.dumps(r["source_fact_ids"]), "evidence_text": r["evidence_text"],
              "reviewed_by": REVIEWER} for r in qrels])
    print(json.dumps({k:v for k,v in report.items() if k != "configuration_differences"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_id", choices=list(CONDITIONS))
    prepare(parser.parse_args().plan_id)
