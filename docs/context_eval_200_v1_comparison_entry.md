# Context 기능 활성화 Baseline 재실행 — 공용표 추가 행

**실제 재실행 완료: SUCCESS.** 기존 `exp_full_kure_200_v1`의 결과·입력·검수자료 38개 파일은 SHA256이 그대로이며, 원본 YAML도 false 상태로 보존했다.

새 YAML: `configs/experiments/exp_full_kure_200_context_v1.yaml`.
새 결과: `experiments/exp_full_kure_200_context_v1/`.
실행 시간: 2026-11-17 19:15:42~19:16:04 KST.

## 1번 표: 실험 계획·실행 목록에 추가

| 계획 ID | 실제 실행 ID | 모델 | 청킹 방식/크기/겹침 | 반복 번호 | 실행 상태 | 설정·입력·결과 링크 |
| --- | --- | --- | --- | --- | --- | --- |
| B01 | exp_full_kure_200_context_v1 | KURE-v1 | section / 800 / 120 | 2 — Context 평가 활성화 | 완료 — SUCCESS | 새 YAML / context_eval_200_v1 입력 / 새 결과 폴더 |

이는 같은 검색 설정의 재실행에 Context 평가를 추가한 행이다. 청킹·모델 성능을 바꾼 비교 후보로 해석하지 않는다. 원본 실행 ID는 `exp_full_kure_200_v1`, 새 YAML의 base_experiment_id도 그 ID다.

## 3번 표: 검색 품질

| 실제 실행 ID | N | 문서 Hit@1 | Hit@3 | Hit@5 | Hit@5 성공 수/N | 문서 MRR@5 | 청크 Hit@1 | Hit@3 | Hit@5 | Hit@5 성공 수/N | 청크 MRR@5 | 실행 오류 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 200 | 0.900 | 0.955 | 0.960 | 192/200 | 0.925417 | 0.690 | 0.820 | 0.885 | 177/200 | 0.763667 | 0 |
| exp_full_kure_200_context_v1 | 200 | 0.900 | 0.955 | 0.960 | 192/200 | 0.925417 | 0.690 | 0.820 | 0.885 | 177/200 | 0.763667 | 0 |

질문200개 각각의 Top-5 chunk_id·document_id·rank가 기존 실행과 모두 동일함을 확인했다. Context 기능을 켜서 검색 품질이 개선된 것이 아니라 기존 검색 결과의 근거 지표를 추가 측정한 것이다.

### 3-3번 표: Context 근거 품질

| 실제 실행 ID | Context Precision@5 | Precision 평가 질문 수/N | Context Recall@5 | Recall 평가 질문 수/N | 평가 버전·검수 입력 | 질문별 결과·미평가 사유 |
| --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 미평가 | 0/200 | 미평가 | 0/200 | 비활성 | 기존 검색 결과 유지 |
| exp_full_kure_200_context_v1 | 0.762000 | 200/200 | 0.883249 **부분 평가** | **197/200** | context_eval_200_v1 / required_facts.jsonl / chunk_fact_map.jsonl / 승인 상태를 추가한 동일211개 Chunk qrels | 새 metrics_by_query.jsonl 및 아래3건 사유 |

Context Recall은 평가 가능한197문항의 산술평균이다. 이를 전체200문항의 공식 Recall로 쓰거나 미평가3문항을0점으로 바꾸면 안 된다. 같은3문항을 제외한 공통 질문 집합과 같은 사실 버전에서 후속 후보를 비교하거나, 원문을 확인해 새 버전으로 정정한 뒤 모든 후보를 같은 기준으로 재평가한다.

| 미평가 질문 ID | 원문에 확인된 문제 | 이번 처리 |
| --- | --- | --- |
| oy_eval200_new_0021 | ‘상반기64명(상반기32명, 하반기32명)’으로 인원 표기가 모순 | 해당 인원 사실 pending; 질문 전체 Recall 미평가 |
| oy_eval200_new_0025 | raw_record와 retrieval_text 모두 ‘관심있는 사’에서 자격 문구가 절단 | 누락 문구를 추정하지 않고 pending |
| oy_eval200_new_0120 | 주택 조건이 ‘인천시 소재 건축물 대’에서 절단 | 건축물의 추가 조건을 만들어내지 않고 pending |

기존 질문·참고답변·Gold를 수정하지 않았다. source가 불완전한 질문의 다른 승인된 사실만 골라 분모를 줄이지도 않았다. 해당 질문 전체를 Recall 집계에서 제외하는 기존 구현의 미검수 처리 규칙을 사용했다. Precision은 고정된 기존211개 정답 청크 집합 기준이며200문항 평가됐다.

## 4번 표: 실행 효율

| 실제 실행 ID | 청크/Index 레코드 수 | Index 생성 시간 | 재사용 | 최초 생성 실행 ID | 검색 평균(ms) | p95(ms) | 최대(ms) | 측정 조건 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 25,829 / 25,829 | 249.3048초 | 아니오 | exp_full_kure_200_v1 | 23.5478 | 30.1256 | 60.4364 | 별도 워밍업 없는 첫 정상 실행 |
| exp_full_kure_200_context_v1 | 25,829 / 25,829 | **재사용** | 예 | exp_full_kure_200_v1 | 25.3207 | 29.9328 | 149.9605 | 동일 GPU·모델revision, 별도 워밍업 없음, 캐시된 모델을 offline로 로드 |

Index 새 생성이 아니므로 0초의 생성 성능으로 해석하지 않는다. 저장된 index_manifest.json의 reused=false/build_time249.3048은 최초생성 Index의 원본 정보다. 이번 재사용 여부는 **새 experiment_manifest.json의 index.reused=true**와 run.log로 확인한다.

검색 시간 범위는 질문 임베딩~DB응답까지이며 Context 계산 시간은 포함하지 않는다. 새 평균 증가나 p95 감소로 Context 기능의 성능 영향을 단정할 수 없다. 두 실행 모두 별도 워밍업이 없고 정식속도비교의 정상3회 조건도 미충족이다. 모델로딩 최대토큰길이는 이번 콘솔에서8192로 확인했지만 실제 잘림 통계는 수집하지 않았다.

## 동일하게 유지한 것과 추가한 것

- 문서2728·질문200·문서Gold207·청크25829, 같은입력 SHA256.
- KURE-v1 revision `8b418a58414668e75532ed045c22d9ca018ae2b2`, 1024차원·정규화·batch32·CUDA/RTX4060.
- section800/overlap120, 같은청크버전, Chroma cosine Top-5, 같은Index버전/DB/Collection.
- Chunk qrels의 query_id/document_id/chunk_id/relevance **211개 매핑은 완전히 동일**. 별도 사본에 review_status/context_version 메타데이터만 추가했다.
- 새 실행 ID·결과 폴더 및 Context 설정/입력 경로를 추가했다. 원본 Baseline YAML과 결과는 수정하지 않았다.
- 사실691개 중688개 승인,3개 pending. 매핑716건. 목록 제목은 사실 분모에서 제외하고, 서류 조건/지원 제외/영어성적 택1 같은 의미를 보존했다. 표기 기호를 제외한 실제 원문 인용으로 연결하며 유사도만으로 승인하지 않았다.
- 같은 사실의 복수Gold 근거는 source_evidence에 연결하므로 사실 ID와 Recall 분모를 중복 생성하지 않는다.
- 검수자는 사용자위임을 받은Codex이며 사람직접검수라고 표기하지 않았다. 외부현행공고 검증이 아니라 수집원문 기준이다.

## 팀원별 확인 파일

| 담당 | 지금 볼 자료와 할 일 |
| --- | --- |
| 진혁 | 이 문서의B01 새행, 새YAML, experiment_manifest.json을 공용표에 연결. Context외 검색조건동일·Index재사용·Recall부분평가를 명시 |
| 종선 | data/evaluation/eval_200_v1/context_eval_200_v1/required_facts.jsonl 및 fact_review.csv에서 원문조건·필수사실 확인. 위3문항은 원문/승인절차를 거쳐 새버전으로 해결 |
| 상준 | 같은폴더 chunk_fact_map.jsonl의 fact_id–chunk_id와 실제본문 대조. 새청킹에서는 사실목록을고정하고 청크매핑만 새로검수 |
| 예지 | 새결과 metrics_by_query.jsonl의 context_*_status·required/supported/missing_fact_ids와 summary의200/197 집계범위 확인. 미평가를0점처리하지 않음 |
| 찬진 | 새 experiment_manifest.json의index.reused=true 확인. 모델/Index조건은동일. 새생성시간을비교하지 않음 |
| 현수 | 새 retrieval_results.jsonl의latency를확인. 전체200개 순위일치·시간변동을구분하고 추후워밍업/반복측정조건확립 |

검증 파일: `experiments/context_comparison_eval_200_v1/verification_report.json`.
독립 계산으로 Precision/Recall을 재계산해 저장 결과와 일치함을 확인했고, 전체 테스트170개가 통과했다.

## 다음 실행 시 주의

이번 새 YAML은 이미 실제 실행을 마쳐 결과 폴더가 있다. 같은 ID로 다시 실행하면 보호장치가 중단한다. 추가 반복에는 새 experiment_id를 사용한다. 이 실행은 Recall197/200의 부분평가이므로 ‘Context 전체200문항 검수완료’로 표시하지 않는다.
