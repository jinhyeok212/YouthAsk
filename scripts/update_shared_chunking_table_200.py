"""Append completed chunking runs to the shared Markdown tables, preserving old rows."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "experiments/chunking_comparison_eval_200_v1"


def main():
    rows = json.loads((AUDIT / "comparison_rows.json").read_text(encoding="utf-8"))[1:]
    decision = json.loads((AUDIT / "selection_decision.json").read_text(encoding="utf-8"))
    path = ROOT / "docs/shared_experiment_comparison.md"
    text = path.read_text(encoding="utf-8")
    if any(f"| {r['plan_id']} | {r['run_id']} |" in text for r in rows):
        raise ValueError("Completed run rows already present; refusing duplicate append")

    def append_table(heading, additions):
        nonlocal text
        start = text.index(heading)
        end = text.find("\n## ", start + len(heading))
        end = len(text) if end < 0 else end
        section = text[start:end]
        table_end = section.rfind("\n| ")
        table_end = section.find("\n", table_end + 1)
        section = section[:table_end] + "\n" + "\n".join(additions) + section[table_end:]
        text = text[:start] + section + text[end:]

    append_table("## 1.", [f"| {r['plan_id']} | {r['run_id']} | KURE-v1 | {r['strategy']} / {r['size']} / {r['overlap']} | {2 if r['plan_id']=='M01' else 1} | 완료 — {r['status']} | [설정](../configs/experiments/{r['run_id']}.yaml) / [결과](../{r['result_path']}/experiment_manifest.json) |" for r in rows])
    append_table("## 2.", [f"| {r['plan_id']} 청킹 비교 | exp_full_kure_200_context_v1 | {r['run_id']} | 청킹 {r['strategy']}/{r['size']}/{r['overlap']} {'선택 조건 재실행' if r['plan_id']=='M01' else ''} | 문서 지표 직접 비교; 청크·Precision은 공통 사실 기준 보조 Baseline 참조 | 제한적 | 동일 모델·질문·207 Gold 연결·691 사실. Recall197/200. 헤더 구성 차이 포함 |" for r in rows])
    append_table("## 3-1.", [f"| {r['run_id']} | eval_200_v1 | 200 | {r['document_hit_at_1']:.3f} | {r['document_hit_at_3']:.3f} | {r['document_hit_at_5']:.3f} | {r['document_success_count']}/200 | {r['document_mrr_at_5']:.6f} | {r['runtime_errors']} | [요약](../{r['result_path']}/metrics_summary.json) / [실패](../{r['result_path']}/failure_cases.csv) |" for r in rows])
    append_table("## 3-2.", [f"| {r['run_id']} | 200 | {r['chunk_hit_at_1']:.3f} | {r['chunk_hit_at_3']:.3f} | {r['chunk_hit_at_5']:.3f} | {r['chunk_success_count']}/200 | {r['chunk_mrr_at_5']:.6f} | [질문별 결과](../{r['result_path']}/metrics_by_query.jsonl) |" for r in rows])
    append_table("## 3-3.", [f"| {r['run_id']} | {r['context_precision_at_5']:.6f} | 200/200 | {r['context_recall_at_5']:.6f} **부분 평가** | **197/200** | context_eval_200_v1 공통 사실·조건별 매핑 | 동일한 원문 문제3문항 |" for r in rows])
    append_table("## 4-1.", [f"| {r['run_id']} | {r['chunk_count']:,} | {r['index_count']:,} | {r['index_build_seconds']} | {r['index_MiB_current']:.4f} — 이번 측정 | {'예' if r['index_reused'] else '아니오'} | {decision['source_run'] if r['plan_id']=='M01' else r['run_id']} | [Manifest](../{r['result_path']}/experiment_manifest.json) |" for r in rows])
    append_table("## 4-2.", [f"| {r['run_id']} | 200 | 별도 워밍업 없음 | {r['latency_mean_ms']:.4f} | {r['latency_p95_ms']:.4f} | {r['latency_max_ms']:.4f} | RTX4060 / CUDA | [원본](../{r['result_path']}/retrieval_results.jsonl) |" for r in rows])
    append_table("## 5.", [f"| C01·M01 / KURE fixed800/120 | {decision['source_run']}, {decision['confirmation_run']} | 2 | 미확정 | 미확정 | 200문항 Top-5 및 품질 지표 동일 여부는 검증 보고서 참조 | 별도 워밍업·동일조건3회 속도측정 필요 |"])
    text = text.replace("청킹·모델 후보의 우열 비교 행은 해당 후보 실행 후 추가한다.", "청킹3조건과 선택 조건 확인 실행을 추가했다. 모델 비교는 이후 진행한다.")
    text = text.replace("6번 질문별 개선·악화는 다른 검색 후보가 생긴 뒤 작성한다. 7번 답변 품질은 미평가, 8번 최종 후보 판정과9번 최종 선택은 미확정이다.", "6번 질문별 개선·악화는 아래 CSV에 작성했다. 7번 답변 품질은 미평가다. 8·9번은 fixed/800/120을 다음 모델 비교용 잠정 기준으로 선택했으며, 답변 품질까지 반영한 최종 채택은 미확정이다.")
    text += "\n## 청킹 비교 추가 근거 — 진혁·팀원\n\n"
    text += "[상세 비교·선정 이유·팀원별 확인 자료](chunking_200_comparison_results.md), [비교 CSV](../experiments/chunking_comparison_eval_200_v1/comparison_rows.csv), [질문별 개선·악화 CSV](../experiments/chunking_comparison_eval_200_v1/query_improvement_decline.csv).\n\n"
    text += "기존 B01은 211개 정답 매핑과 원래 결과를 그대로 보존했다. 새 조건과 동일한 전체 사실 포함 기준으로 원래 검색 순위만 보조 재평가한 B01은213매핑이며 Precision@5=0.761167이다(원래 기록0.762000). 두 매핑 추가 이유와 원문은 상세 보고서·baseline_common_gold_evaluation에 있다. 보조 재평가는 새 검색 실행 행으로 세지 않는다.\n\n"
    text += "진혁은1·2·8·9번의 실행ID·조건·비교 제약·잠정 선정 이유를 사용한다. 예지는3번의 metrics_summary와6번 질문별 CSV/실패 사례를 확인한다. 상준은조건별 C*_chunk_review.csv·qrels·chunk_fact_map과 청크Manifest를 확인한다. 종선은동일 required_facts와 보류3문항을 확인한다. 찬진은4-1번 Index Manifest·용량, 현수는4-2·5번 retrieval_results의 질문별 시간을 확인한다. 각 담당자는 실제 실행ID로 같은 행에 연결한다.\n\n"
    text += f"선택 조건의 다음 동일 설정 재실행 ID는 `{decision['confirmation_run'].rsplit('_v',1)[0]}_v3`이다. 모델·청킹·Index 버전은 실행 번호와 별개로 유지한다.\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
