"""Select the next KURE reference and write the shared table from real artifacts."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yaml
from scripts.review_chunk_qrels_200 import read_rows, sha, write_csv, write_json
from scripts.prepare_chunking_comparison_200 import CONDITIONS, AUDIT

BASELINE = "exp_full_kure_200_context_v1"


def runs():
    return {"B01": BASELINE} | {p: f"exp_full_kure_200_{s}_{n}_ov{o}_v1" for p,(s,n,o,_) in CONDITIONS.items()}


def quality_key(summary):
    # Declared plan: document Hit@5 -> MRR@5 -> Hit@1; common-fact Recall tie break.
    # Do not use speed (no warmup) or baseline Precision (Gold review scope differs).
    return tuple(summary[k] for k in ("document_hit_at_5", "document_mrr", "document_hit_at_1", "context_recall_at_5"))


def select():
    values = {}
    for plan, run in runs().items():
        folder = ROOT / "experiments" / run
        manifest = json.loads((folder/"experiment_manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((folder/"metrics_summary.json").read_text(encoding="utf-8"))
        if manifest["status"] != "SUCCESS" or summary["retrieval_failure_count"] or summary["evaluation_query_count"] != 200:
            raise ValueError(f"Cannot select from incomplete/error run: {run}")
        values[plan] = summary
    plan = max(values, key=lambda p: quality_key(values[p]))
    source_run = runs()[plan]
    original = yaml.safe_load((ROOT/f"configs/experiments/{source_run}.yaml").read_text(encoding="utf-8"))
    stem = re.sub(r"_v\d+$", "", source_run)
    names = [p.stem for p in (ROOT/"configs/experiments").glob(stem+"_v*.yaml")]
    names += [p.name for p in (ROOT/"experiments").glob(stem+"_v*") if p.is_dir()]
    versions = [int(match.group(1)) for name in names
                if (match := re.fullmatch(re.escape(stem)+r"_v(\d+)", name))]
    next_run = f"{stem}_v{max(versions)+1}"
    cfg = copy.deepcopy(original)
    cfg.update(experiment_id=next_run, experiment_name=next_run.replace("_", "-"), base_experiment_id=source_run)
    if any(cfg[k] != original[k] for k in cfg if k not in {"experiment_id", "experiment_name", "base_experiment_id"}):
        raise AssertionError("Selected-condition confirmation changed parameters")
    with (ROOT/f"configs/experiments/{next_run}.yaml").open("x",encoding="utf-8",newline="\n") as handle:
        yaml.safe_dump(cfg,handle,allow_unicode=True,sort_keys=False)
    decision = {"plan_id":"M01", "selected_from_plan":plan, "source_run":source_run, "confirmation_run":next_run,
                "selected_chunking":cfg["chunking"], "selection_order":["document_hit_at_5","document_mrr","document_hit_at_1","context_recall_at_5"],
                "all_candidates":{p:{"run_id":runs()[p], **v} for p,v in values.items()},
                "reason":"Use the declared document-quality priority; fixed facts on the same197 questions break ties. No speed claim from un-warmed single runs. This is a working reference for model comparison, not a final answer-quality choice.",
                "settings_unchanged_for_confirmation":True}
    write_json(AUDIT/"selection_decision.json",decision)
    print(json.dumps({k:v for k,v in decision.items() if k not in {"all_candidates","selected_chunking"}},ensure_ascii=False,indent=2))


def report():
    decision = json.loads((AUDIT/"selection_decision.json").read_text(encoding="utf-8"))
    all_runs = runs() | {"M01":decision["confirmation_run"]}
    rows = []
    for plan, run in all_runs.items():
        folder = ROOT/"experiments"/run
        m = json.loads((folder/"experiment_manifest.json").read_text(encoding="utf-8"))
        s = json.loads((folder/"metrics_summary.json").read_text(encoding="utf-8"))
        cfg = yaml.safe_load((folder/"experiment_config.yaml").read_text(encoding="utf-8"))
        qs = read_rows(folder/"metrics_by_query.jsonl")
        index = Path(m["index"]["db_path"])
        size = sum(p.stat().st_size for p in index.rglob("*") if p.is_file())/1048576
        rows.append({"plan_id":plan,"run_id":run,"status":m["status"],
                     "strategy":cfg["chunking"]["strategy"],"size":cfg["chunking"]["size"],"overlap":cfg["chunking"]["overlap"],
                     "questions":s["evaluation_query_count"],"document_hit_at_1":s["document_hit_at_1"],
                     "document_hit_at_3":s["document_hit_at_3"],"document_hit_at_5":s["document_hit_at_5"],
                     "document_success_count":sum(r["document_hit_at_5"] for r in qs),"document_mrr_at_5":s["document_mrr"],
                     "chunk_hit_at_1":s["chunk_hit_at_1"],"chunk_hit_at_3":s["chunk_hit_at_3"],"chunk_hit_at_5":s["chunk_hit_at_5"],
                     "chunk_success_count":sum(r["chunk_hit_at_5"] for r in qs),"chunk_mrr_at_5":s["chunk_mrr"],
                     "context_precision_at_5":s["context_precision_at_5"],"precision_count":s["context_precision_evaluated_query_count"],
                     "context_recall_at_5":s["context_recall_at_5"],"recall_count":s["context_recall_evaluated_query_count"],
                     "runtime_errors":s["retrieval_failure_count"],"chunk_count":m["chunking"]["chunk_count"],
                     "index_count":m["index"]["index_count"],"index_reused":m["index"]["reused"],
                     "index_build_seconds":"재사용" if m["index"]["reused"] else m["index"]["build_time_seconds"],
                     "index_MiB_current":size,"latency_mean_ms":s["average_retrieval_latency_ms"],
                     "latency_p95_ms":s["p95_retrieval_latency_ms"],"latency_max_ms":max(r["retrieval_latency_ms"] for r in qs),
                     "result_path":folder.relative_to(ROOT).as_posix()})
    write_csv(AUDIT/"comparison_rows.csv",rows)
    write_json(AUDIT/"comparison_rows.json",rows)
    lines=["# KURE-v1 청킹 비교와 선택 청킹 확인", "", "실제 결과에서 작성. 모든 실행은 별도 행이며 기존 Baseline은 보존했다.", "",
           "## 1. 실행 목록 — 진혁", "", "| 계획 ID | 실제 실행 ID | 모델 | 방식/크기/겹침 | 실행 상태 |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['plan_id']} | {r['run_id']} | KURE-v1 | {r['strategy']}/{r['size']}/{r['overlap']} | {r['status']} |")
    lines += ["", "## 3. 검색 품질 — 예지", "", "| 계획 | 문서 Hit@1/3/5 | 문서 성공/N | 문서 MRR@5 | 청크 Hit@1/3/5 | 청크 성공/N | 청크 MRR@5 | 오류 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['plan_id']} | {r['document_hit_at_1']:.3f}/{r['document_hit_at_3']:.3f}/{r['document_hit_at_5']:.3f} | {r['document_success_count']}/200 | {r['document_mrr_at_5']:.6f} | {r['chunk_hit_at_1']:.3f}/{r['chunk_hit_at_3']:.3f}/{r['chunk_hit_at_5']:.3f} | {r['chunk_success_count']}/200 | {r['chunk_mrr_at_5']:.6f} | {r['runtime_errors']} |")
    lines += ["", "| 계획 | Context Precision@5 | 평가 수 | Context Recall@5 | 평가 수 |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['plan_id']} | {r['context_precision_at_5']:.6f} | {r['precision_count']}/200 | {r['context_recall_at_5']:.6f} 부분 평가 | {r['recall_count']}/200 |")
    common = json.loads((AUDIT/"baseline_common_gold_evaluation/metrics_summary.json").read_text(encoding="utf-8"))
    lines += ["", f"B01의 위 값은 원본 실행 기록이다. 동일한 필수사실 정답 규칙으로 저장 순위를 별도 재평가한 B01의 Context Precision은 **{common['context_precision_at_5']:.6f}**다. 이 보조 평가에서는 정답집합이211→213개이며 문서/청크Hit·MRR과Recall은 변하지 않았다. C01/C02/C03과의Precision 비교에는 이 공통규칙 보조값을 사용한다. 이는 새 검색실행이 아니며 원본 B01값을 덮어쓰지 않았다.", ""]
    lines += ["", "## 4. 효율 — 찬진·현수", "", "| 계획 | 청크/Index 수 | Index 생성 초 | 재사용 | 현재 용량MiB | 검색 평균/p95/최대 ms |", "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['plan_id']} | {r['chunk_count']}/{r['index_count']} | {r['index_build_seconds']} | {r['index_reused']} | {r['index_MiB_current']:.4f} | {r['latency_mean_ms']:.4f}/{r['latency_p95_ms']:.4f}/{r['latency_max_ms']:.4f} |")
    lines += ["", "## 선택한 청킹 — M01", "", f"선정 원본: **{decision['selected_from_plan']} / {decision['source_run']}**. 확인 실행: **{decision['confirmation_run']}**.", "",
              "선정 순서: 문서 Hit@5 → 문서 MRR@5 → 문서 Hit@1 → 같은197문항/필수사실의 Context Recall. 속도나 Baseline과 검수범위가 조금 다른 Context Precision으로 선택하지 않았다.", "",
              "이 설정은 모델 비교 단계의 기준 후보이며, 답변 품질까지 확인한 최종 설정 채택이 아니다. 성공1문항 차이(0.005)는 작은 차이로 해석한다.", "",
              "## 비교 시 반드시 기록할 제약", "",
              "- 문서·질문·Document qrels·691개 필수사실·KURE revision·임베딩차원/정규화/batch·Top5/cosine·오류정책은 고정했다. 변경된 설정 필드는 C01/C02/C03_preflight.json에 기록했다.",
              "- 청킹마다 ID가 달라 qrels와 사실–청크 연결은 별도로 검수했다. Gold 문서 소속이라는 이유만으로 모든 청크를 정답 처리하지 않았다.",
              "- C01/C02/C03은 같은 '완전한 필수사실 포함' 규칙을 쓴다. B01의과거211개검수본은보존했고, 빠진2개를보완한213개공통규칙정답으로원본검색순위를보조재평가했다. 새실험조건을바꾸거나검색을재실행한것은아니다. 원본값과보조평가값을구분해기록한다.",
              "- fixed는 원문 전체를800자로 나누고 section은 본문제한 뒤 정책명 접두어를 붙인다. 이를 변경하지 않았으므로 헤더/입력구성까지 포함한 청킹 비교다.",
              "- Recall은 원문문제로197/200 부분 평가다. 해당3문항/미검수 사실을0점으로 바꾸거나 승인된부분만 분모로 삼지 않았다.",
              "- 온전한 사실을 담는 단일 청크가 없으면 null로 기록하고 분모를 유지했다. C02의0121근로계약/근무/급여조건은 경계에서 나뉘어 이 경우에 해당한다.",
              "- 별도 워밍업없는1회측정이므로 시간은 참고값이며 속도우열을 확정하지 않는다. Index생성은 모델로딩이후 임베딩/DB적재/검증시간이다.", "",
              "## 팀원 확인 자료", "",
              "진혁은1번 실행목록과2번비교제약·8-2임시선정근거를 기입한다. 예지는각결과 metrics_summary.json/metrics_by_query.jsonl/failure_cases.csv로3번과6번을 확인한다. 상준은청크Manifest와조건별chunk_fact_map/qrels 및C*_chunk_review.csv, 종선은고정required_facts와3개보류원문을 확인한다. 찬진은experiment_manifest의Index생성/재사용과실제DB용량, 현수는retrieval_results의시간원본을 확인한다.", ""]
    path=ROOT/"docs/chunking_200_comparison_results.md"
    with path.open("x",encoding="utf-8",newline="\n") as handle:
        handle.write("\n".join(lines))
    base_rows={r["query_id"]:r for r in read_rows(AUDIT/"baseline_common_gold_evaluation/metrics_by_query.jsonl")}
    query_text={q["query_id"]:q["query"] for q in read_rows(ROOT/"data/evaluation/eval_200_v1/eval_questions.jsonl")}
    changes=[]
    counts={}
    for plan in CONDITIONS:
        counts[plan]={}
        candidate=read_rows(ROOT/"experiments"/all_runs[plan]/"metrics_by_query.jsonl")
        for metric in ("document","chunk","context_precision","context_recall"):
            category_counts={}
            for r in candidate:
                b=base_rows[r["query_id"]]
                if metric in {"document","chunk"}:
                    before,after=b[metric+"_first_relevant_rank"],r[metric+"_first_relevant_rank"]
                    category=("성공 전환" if before is None and after is not None else
                              "신규 실패" if before is not None and after is None else
                              "순위 개선" if before is not None and after is not None and after<before else
                              "순위 하락" if before is not None and after is not None and after>before else "동일")
                else:
                    before,after=b[metric+"_at_5"],r[metric+"_at_5"]
                    category=("미평가" if before is None or after is None else "점수 개선" if after>before+1e-12 else "점수 하락" if after<before-1e-12 else "동일")
                category_counts[category]=category_counts.get(category,0)+1
                changes.append({"plan_id":plan,"query_id":r["query_id"],"query":query_text[r["query_id"]],
                                "metric":metric,"baseline_search_run_id":BASELINE,
                                "baseline_evaluation_id":"baseline_common_fact_gold_v1", "candidate_run_id":all_runs[plan],
                                "baseline_rank_or_score":before,"candidate_rank_or_score":after,"change":category,
                                "baseline_missing_fact_ids":json.dumps(b.get("missing_fact_ids")),
                                "candidate_missing_fact_ids":json.dumps(r.get("missing_fact_ids"))})
            counts[plan][metric]=category_counts
    write_csv(AUDIT/"query_improvement_decline.csv",changes)
    write_json(AUDIT/"query_change_counts.json",counts)
    print(json.dumps(rows,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["select","report"])
    args=parser.parse_args()
    select() if args.command=="select" else report()
