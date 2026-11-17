# 공용 실험 비교표

담당: 진혁. 계획 주차는 제외하고 실제 실행을 기준으로 관리한다.
동일 설정 재실행은 마지막 `_vN` 숫자만 증가시키고, 실제 실행마다 새 행을 추가한다. 기존 완료 실행 이름은 보존한다.

현재 Context 설정의 다음 실행 ID: **`exp_full_kure_200_context_v2`** (아직 실행하지 않음).

## 1. 실험 계획·실행 목록 — 진혁

| 계획 ID | 실제 실행 ID | 모델 | 청킹 방식/크기/겹침 | 반복 번호 | 실행 상태 | 설정·입력·결과 링크 |
| --- | --- | --- | --- | --- | --- | --- |
| B01 | exp_full_kure_200_v1 | KURE-v1 | section / 800 / 120 | 1 | 완료 — SUCCESS | [최초 실행 기입안](baseline_200_comparison_entry.md) / [결과](../experiments/exp_full_kure_200_v1/experiment_manifest.json) |
| B01 | exp_full_kure_200_context_v1 | KURE-v1 | section / 800 / 120 | 2 — Context 평가 활성화 | 완료 — SUCCESS | [추가 실행 기입안](context_eval_200_v1_comparison_entry.md) / [결과](../experiments/exp_full_kure_200_context_v1/experiment_manifest.json) |
| C01 | exp_full_kure_200_fixed_800_ov120_v1 | KURE-v1 | fixed / 800 / 120 | 1 | 완료 — SUCCESS | [설정](../configs/experiments/exp_full_kure_200_fixed_800_ov120_v1.yaml) / [결과](../experiments/exp_full_kure_200_fixed_800_ov120_v1/experiment_manifest.json) |
| C02 | exp_full_kure_200_section_500_ov120_v1 | KURE-v1 | section / 500 / 120 | 1 | 완료 — SUCCESS | [설정](../configs/experiments/exp_full_kure_200_section_500_ov120_v1.yaml) / [결과](../experiments/exp_full_kure_200_section_500_ov120_v1/experiment_manifest.json) |
| C03 | exp_full_kure_200_section_800_ov0_v1 | KURE-v1 | section / 800 / 0 | 1 | 완료 — SUCCESS | [설정](../configs/experiments/exp_full_kure_200_section_800_ov0_v1.yaml) / [결과](../experiments/exp_full_kure_200_section_800_ov0_v1/experiment_manifest.json) |
| M01 | exp_full_kure_200_fixed_800_ov120_v2 | KURE-v1 | fixed / 800 / 120 | 2 | 완료 — SUCCESS | [설정](../configs/experiments/exp_full_kure_200_fixed_800_ov120_v2.yaml) / [결과](../experiments/exp_full_kure_200_fixed_800_ov120_v2/experiment_manifest.json) |

두 번째 행은 첫 번째 행과 별개의 실제 실행이다. 검색 설정은 동일하며 Context 평가를 활성화했다. 두 실행 모두 2026-11-17에 완료했다. 임의의 v2 별칭으로 이미 완료된 실행을 재명명하지 않는다.

## 2. 비교 가능 여부 — 진혁·관련 담당자

| 비교 대상 | 기준 실제 실행 ID | 후보 실제 실행 ID | 변경 변수 | 품질 비교 가능 여부 | 시간 비교 가능 여부 | 조건 차이·제약 |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline 재실행 확인 | exp_full_kure_200_v1 | exp_full_kure_200_context_v1 | Context 평가 활성화 | 문서·청크 Hit/MRR 직접 비교 가능. Context는 원본 미평가로 증감 비교 불가 | 제한적 비교 가능 | 전체200문항 Top-5 순위 동일. Context Recall은197문항 부분 평가. 별도 워밍업 없음 |
| C01 청킹 비교 | exp_full_kure_200_context_v1 | exp_full_kure_200_fixed_800_ov120_v1 | 청킹 fixed/800/120  | 문서 지표 직접 비교; 청크·Precision은 공통 사실 기준 보조 Baseline 참조 | 제한적 | 동일 모델·질문·207 Gold 연결·691 사실. Recall197/200. 헤더 구성 차이 포함 |
| C02 청킹 비교 | exp_full_kure_200_context_v1 | exp_full_kure_200_section_500_ov120_v1 | 청킹 section/500/120  | 문서 지표 직접 비교; 청크·Precision은 공통 사실 기준 보조 Baseline 참조 | 제한적 | 동일 모델·질문·207 Gold 연결·691 사실. Recall197/200. 헤더 구성 차이 포함 |
| C03 청킹 비교 | exp_full_kure_200_context_v1 | exp_full_kure_200_section_800_ov0_v1 | 청킹 section/800/0  | 문서 지표 직접 비교; 청크·Precision은 공통 사실 기준 보조 Baseline 참조 | 제한적 | 동일 모델·질문·207 Gold 연결·691 사실. Recall197/200. 헤더 구성 차이 포함 |
| M01 청킹 비교 | exp_full_kure_200_context_v1 | exp_full_kure_200_fixed_800_ov120_v2 | 청킹 fixed/800/120 선택 조건 재실행 | 문서 지표 직접 비교; 청크·Precision은 공통 사실 기준 보조 Baseline 참조 | 제한적 | 동일 모델·질문·207 Gold 연결·691 사실. Recall197/200. 헤더 구성 차이 포함 |

청킹3조건과 선택 조건 확인 실행을 추가했다. 모델 비교는 이후 진행한다.

## 3-1. 문서 검색 품질 — 예지

| 실제 실행 ID | 평가셋 | N | Hit@1 | Hit@3 | Hit@5 | Hit@5 성공 수/N | MRR@5 | 실행 오류 수 | 결과·실패 사례 링크 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | eval_200_v1 | 200 | 0.900 | 0.955 | 0.960 | 192/200 | 0.925417 | 0 | [요약](../experiments/exp_full_kure_200_v1/metrics_summary.json) / [실패](../experiments/exp_full_kure_200_v1/failure_cases.csv) |
| exp_full_kure_200_context_v1 | eval_200_v1 | 200 | 0.900 | 0.955 | 0.960 | 192/200 | 0.925417 | 0 | [요약](../experiments/exp_full_kure_200_context_v1/metrics_summary.json) / [실패](../experiments/exp_full_kure_200_context_v1/failure_cases.csv) |
| exp_full_kure_200_fixed_800_ov120_v1 | eval_200_v1 | 200 | 0.895 | 0.955 | 0.965 | 193/200 | 0.923667 | 0 | [요약](../experiments/exp_full_kure_200_fixed_800_ov120_v1/metrics_summary.json) / [실패](../experiments/exp_full_kure_200_fixed_800_ov120_v1/failure_cases.csv) |
| exp_full_kure_200_section_500_ov120_v1 | eval_200_v1 | 200 | 0.905 | 0.955 | 0.960 | 192/200 | 0.927917 | 0 | [요약](../experiments/exp_full_kure_200_section_500_ov120_v1/metrics_summary.json) / [실패](../experiments/exp_full_kure_200_section_500_ov120_v1/failure_cases.csv) |
| exp_full_kure_200_section_800_ov0_v1 | eval_200_v1 | 200 | 0.900 | 0.955 | 0.960 | 192/200 | 0.925417 | 0 | [요약](../experiments/exp_full_kure_200_section_800_ov0_v1/metrics_summary.json) / [실패](../experiments/exp_full_kure_200_section_800_ov0_v1/failure_cases.csv) |
| exp_full_kure_200_fixed_800_ov120_v2 | eval_200_v1 | 200 | 0.895 | 0.955 | 0.965 | 193/200 | 0.923667 | 0 | [요약](../experiments/exp_full_kure_200_fixed_800_ov120_v2/metrics_summary.json) / [실패](../experiments/exp_full_kure_200_fixed_800_ov120_v2/failure_cases.csv) |

## 3-2. 청크 검색 품질 — 예지·상준

청크 qrels는 두 실행 모두 동일한211개 query-document-chunk-relevance 매핑이며, 두 번째 입력에 Context 검수 메타데이터만 추가했다. 청킹 버전은 section_heading_800_ov120_v1이다.

| 실제 실행 ID | N | Hit@1 | Hit@3 | Hit@5 | Hit@5 성공 수/N | MRR@5 | 결과 링크 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 200 | 0.690 | 0.820 | 0.885 | 177/200 | 0.763667 | [질문별 결과](../experiments/exp_full_kure_200_v1/metrics_by_query.jsonl) |
| exp_full_kure_200_context_v1 | 200 | 0.690 | 0.820 | 0.885 | 177/200 | 0.763667 | [질문별 결과](../experiments/exp_full_kure_200_context_v1/metrics_by_query.jsonl) |
| exp_full_kure_200_fixed_800_ov120_v1 | 200 | 0.820 | 0.910 | 0.930 | 186/200 | 0.864833 | [질문별 결과](../experiments/exp_full_kure_200_fixed_800_ov120_v1/metrics_by_query.jsonl) |
| exp_full_kure_200_section_500_ov120_v1 | 200 | 0.690 | 0.810 | 0.870 | 174/200 | 0.759583 | [질문별 결과](../experiments/exp_full_kure_200_section_500_ov120_v1/metrics_by_query.jsonl) |
| exp_full_kure_200_section_800_ov0_v1 | 200 | 0.690 | 0.815 | 0.880 | 176/200 | 0.761750 | [질문별 결과](../experiments/exp_full_kure_200_section_800_ov0_v1/metrics_by_query.jsonl) |
| exp_full_kure_200_fixed_800_ov120_v2 | 200 | 0.820 | 0.910 | 0.930 | 186/200 | 0.864833 | [질문별 결과](../experiments/exp_full_kure_200_fixed_800_ov120_v2/metrics_by_query.jsonl) |

## 3-3. 검색 근거 품질 — 예지·종선·상준

| 실제 실행 ID | Context Precision@5 | Precision 평가 질문 수/N | Context Recall@5 | Recall 평가 질문 수/N | 평가 버전·검수 입력 | 미평가 사유 |
| --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 미평가 | 0/200 | 미평가 | 0/200 | Context 비활성 | 최초 실행에서 미산출 |
| exp_full_kure_200_context_v1 | 0.762000 | 200/200 | 0.883249 **부분 평가** | **197/200** | [context_eval_200_v1](../data/evaluation/eval_200_v1/context_eval_200_v1/preparation_manifest.json) | 원문 인원 모순0021, 문구 절단0025·0120 |
| exp_full_kure_200_fixed_800_ov120_v1 | 0.860417 | 200/200 | 0.914842 **부분 평가** | **197/200** | context_eval_200_v1 공통 사실·조건별 매핑 | 동일한 원문 문제3문항 |
| exp_full_kure_200_section_500_ov120_v1 | 0.757917 | 200/200 | 0.859137 **부분 평가** | **197/200** | context_eval_200_v1 공통 사실·조건별 매핑 | 동일한 원문 문제3문항 |
| exp_full_kure_200_section_800_ov0_v1 | 0.760083 | 200/200 | 0.878173 **부분 평가** | **197/200** | context_eval_200_v1 공통 사실·조건별 매핑 | 동일한 원문 문제3문항 |
| exp_full_kure_200_fixed_800_ov120_v2 | 0.860417 | 200/200 | 0.914842 **부분 평가** | **197/200** | context_eval_200_v1 공통 사실·조건별 매핑 | 동일한 원문 문제3문항 |

미평가3문항을0점으로 바꾸거나197문항 평균을전체200문항의완료지표로 표시하지 않는다. [보류3건 검수표](../experiments/context_comparison_eval_200_v1/recall_pending_review.csv).

## 4-1. 인덱스 생성·용량 — 찬진·상준

| 실제 실행 ID | 청크 수 | Index 레코드 수 | Index 생성 시간(초) | 용량(MiB) | Index 재사용 | 최초 생성 실행 ID | 근거 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 25,829 | 25,829 | 249.3048 | 332.3969 — 최초 실행 후 측정 | 아니오 | exp_full_kure_200_v1 | [Manifest](../experiments/exp_full_kure_200_v1/experiment_manifest.json) |
| exp_full_kure_200_context_v1 | 25,829 | 25,829 | 재사용 | — 별도 재측정 안 함 | 예 | exp_full_kure_200_v1 | [Manifest](../experiments/exp_full_kure_200_context_v1/experiment_manifest.json) |
| exp_full_kure_200_fixed_800_ov120_v1 | 3,462 | 3,462 | 123.0483 | 65.2372 — 이번 측정 | 아니오 | exp_full_kure_200_fixed_800_ov120_v1 | [Manifest](../experiments/exp_full_kure_200_fixed_800_ov120_v1/experiment_manifest.json) |
| exp_full_kure_200_section_500_ov120_v1 | 26,059 | 26,059 | 236.0709 | 332.6118 — 이번 측정 | 아니오 | exp_full_kure_200_section_500_ov120_v1 | [Manifest](../experiments/exp_full_kure_200_section_500_ov120_v1/experiment_manifest.json) |
| exp_full_kure_200_section_800_ov0_v1 | 25,825 | 25,825 | 256.9587 | 331.9217 — 이번 측정 | 아니오 | exp_full_kure_200_section_800_ov0_v1 | [Manifest](../experiments/exp_full_kure_200_section_800_ov0_v1/experiment_manifest.json) |
| exp_full_kure_200_fixed_800_ov120_v2 | 3,462 | 3,462 | 재사용 | 65.2372 — 이번 측정 | 예 | exp_full_kure_200_fixed_800_ov120_v1 | [Manifest](../experiments/exp_full_kure_200_fixed_800_ov120_v2/experiment_manifest.json) |

같은 Index를 재사용했다. 이전 용량 측정값을 새로 측정한 값처럼 기록하지 않는다.

## 4-2. 검색 시간 — 현수

| 실제 실행 ID | 측정 질문 수 | 워밍업 | 평균(ms) | p95(ms) | 최대(ms) | 장비 | 질문별 원본 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 200 | 별도 워밍업 없음 | 23.5478 | 30.1256 | 60.4364 | RTX4060 / CUDA | [원본](../experiments/exp_full_kure_200_v1/retrieval_results.jsonl) |
| exp_full_kure_200_context_v1 | 200 | 별도 워밍업 없음 | 25.3207 | 29.9328 | 149.9605 | RTX4060 / CUDA | [원본](../experiments/exp_full_kure_200_context_v1/retrieval_results.jsonl) |
| exp_full_kure_200_fixed_800_ov120_v1 | 200 | 별도 워밍업 없음 | 16.3344 | 19.4267 | 41.3765 | RTX4060 / CUDA | [원본](../experiments/exp_full_kure_200_fixed_800_ov120_v1/retrieval_results.jsonl) |
| exp_full_kure_200_section_500_ov120_v1 | 200 | 별도 워밍업 없음 | 24.3752 | 29.0869 | 48.5228 | RTX4060 / CUDA | [원본](../experiments/exp_full_kure_200_section_500_ov120_v1/retrieval_results.jsonl) |
| exp_full_kure_200_section_800_ov0_v1 | 200 | 별도 워밍업 없음 | 19.6991 | 26.3949 | 33.4653 | RTX4060 / CUDA | [원본](../experiments/exp_full_kure_200_section_800_ov0_v1/retrieval_results.jsonl) |
| exp_full_kure_200_fixed_800_ov120_v2 | 200 | 별도 워밍업 없음 | 16.1796 | 17.0281 | 132.7094 | RTX4060 / CUDA | [원본](../experiments/exp_full_kure_200_fixed_800_ov120_v2/retrieval_results.jsonl) |

시간 측정 범위는 질문 임베딩~DB응답이다. Context 계산은 이 시간에 포함되지 않는다. 워밍업 없는 측정이므로 속도 우열과 Context 기능의 실행시간 영향을 단정하지 않는다.

## 5. 반복 측정 요약 — 현수·예지

| 계획 ID·조건 | 연결 실행 ID | 정상 검색 실행 수 | 대표 평균 | 대표 p95 | 품질 일관성 | 남은 조건 |
| --- | --- | --- | --- | --- | --- | --- |
| B01 / KURE section800/120 | exp_full_kure_200_v1, exp_full_kure_200_context_v1 | 2 | 미확정 | 미확정 | 200문항 Top-5 순위와 Hit/MRR 동일 | Context 설정은 다름. 워밍업 및 동일조건3회 속도측정 필요 |
| C01·M01 / KURE fixed800/120 | exp_full_kure_200_fixed_800_ov120_v1, exp_full_kure_200_fixed_800_ov120_v2 | 2 | 미확정 | 미확정 | 200문항 Top-5 및 품질 지표 동일 여부는 검증 보고서 참조 | 별도 워밍업·동일조건3회 속도측정 필요 |

## 이후 단계

6번 질문별 개선·악화는 아래 CSV에 작성했다. 7번 답변 품질은 미평가다. 8·9번은 fixed/800/120을 다음 모델 비교용 잠정 기준으로 선택했으며, 답변 품질까지 반영한 최종 채택은 미확정이다.

팀원별 상세 확인 파일은 [최초 실행 기입안](baseline_200_comparison_entry.md)과 [Context 추가 실행 기입안](context_eval_200_v1_comparison_entry.md)에 정리했다. [CSV 비교표2행](../experiments/context_comparison_eval_200_v1/comparison_rows.csv)도 함께 사용할 수 있다.

## 청킹 비교 추가 근거 — 진혁·팀원

[상세 비교·선정 이유·팀원별 확인 자료](chunking_200_comparison_results.md), [비교 CSV](../experiments/chunking_comparison_eval_200_v1/comparison_rows.csv), [질문별 개선·악화 CSV](../experiments/chunking_comparison_eval_200_v1/query_improvement_decline.csv).

기존 B01은 211개 정답 매핑과 원래 결과를 그대로 보존했다. 새 조건과 동일한 전체 사실 포함 기준으로 원래 검색 순위만 보조 재평가한 B01은213매핑이며 Precision@5=0.761167이다(원래 기록0.762000). 두 매핑 추가 이유와 원문은 상세 보고서·baseline_common_gold_evaluation에 있다. 보조 재평가는 새 검색 실행 행으로 세지 않는다.

진혁은1·2·8·9번의 실행ID·조건·비교 제약·잠정 선정 이유를 사용한다. 예지는3번의 metrics_summary와6번 질문별 CSV/실패 사례를 확인한다. 상준은조건별 C*_chunk_review.csv·qrels·chunk_fact_map과 청크Manifest를 확인한다. 종선은동일 required_facts와 보류3문항을 확인한다. 찬진은4-1번 Index Manifest·용량, 현수는4-2·5번 retrieval_results의 질문별 시간을 확인한다. 각 담당자는 실제 실행ID로 같은 행에 연결한다.

선택 조건의 다음 동일 설정 재실행 ID는 `exp_full_kure_200_fixed_800_ov120_v3`이다. 모델·청킹·Index 버전은 실행 번호와 별개로 유지한다.
