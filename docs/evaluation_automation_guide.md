# 6번 평가 자동화: 코드 읽기와 발표 준비

## 읽는 순서

1. `src/experiments/runner.py`: 검색 결과가 평가 함수로 들어가고, 전체 실행 context가 저장 함수로 들어가는 부분.
2. `src/evaluation/evaluate_experiment.py`: 질문 ID 검증 → qrels 연결 → 기존 계산 함수 호출 → 집계.
3. `src/evaluation/retrieval_metrics.py`: 최초 정답 순위, Hit@k, RR, 평균.
4. `src/evaluation/failure_analyzer.py`: 관측 가능한 실패 유형 분류.
5. `src/experiments/artifact_writer.py`: 결과 파일과 Manifest 저장, 덮어쓰기 방지.
6. `tests/test_experiment_metrics.py`, `tests/test_artifact_writer.py`: 정답을 아는 작은 입력과 Runner 연결 검증.

## 계산 기준

- 문서·청크 Hit@1/3/5를 각각 계산한다. 정답 여러 개 중 하나라도 발견하면 Hit이다.
- 문서 평가는 기존 코드와 동일하게 청크 검색 순위를 유지한다. 동일 문서가 여러 번 나와도 순위를 압축하지 않는다.
- MRR은 evaluation_max_k까지 검색한 결과에서 최초 정답의 역순위를 평균한다. 기본 설정에서는 MRR@5에 해당한다.
- Hit@5를 보고하므로 evaluation_max_k가 5보다 작으면 거부한다.
- p95는 정렬한 지연시간의 ceil(0.95*N)번째 값(nearest rank)이다.
- 모든 질문에 문서·청크 정답이 있어야 한다. 현재 부분 청크 평가를 위한 대상 표시 규격은 없으므로 누락은 오류다.
- 실제 저장소의 행 단위 qrels와 초기 안내의 ground_truth_*_ids 배열을 모두 읽는다. relevance가 0 이하인 항목은 정답에서 제외한다.
- Runtime 오류는 빈 결과와 오류 문자열로 받아 0점으로 포함하되 정상 검색 실패와 별도로 집계한다.

## 실패 분석

자동 분류: runtime_error, document_not_in_top_5, chunk_not_in_top_5.
검색 실패 수는 실행 오류를 제외한 청크 Top-5 실패 질문 수이다. 문서 실패 수도 별도 제공한다.
낮은 순위는 질문별 first_relevant_rank로 확인한다. 합의되지 않은 순위 임계값을 추가하지 않았다.
표현 차이·유사 정책 혼동 등 의미적 원인은 사람이 원문과 검색 결과를 검토해야 한다.

## 저장 책임

- 저장 함수: 실험 Manifest, 지표 요약, 질문별 지표, 검색 결과, 실패 CSV.
- Index Manifest: 인덱스 담당자가 만든 파일을 보존하거나 원문 그대로 복사한다.
- Trace: 검색 담당자가 이미 생성했다면 질문 ID 범위를 확인하고 보존한다. 없으면 전달받은 검색 결과로 생성한다.
- run.log: Runner가 생성한다. 저장 함수 단독 호출은 Runner 로그를 만들지 않는다.
- 기존 대상 파일이 있으면 쓰기 전에 중단한다. 새 experiment_id로 재실행한다.
- Runtime 오류가 있으면 FAILED Manifest와 실패 CSV를 남긴 뒤 예외를 발생시켜 Runner 성공 처리를 방지한다.

## 검증 명령

```powershell
python -m unittest discover -s tests -p 'test_experiment_metrics.py'
python -m unittest discover -s tests -p 'test_artifact_writer.py'
python -m src.experiments.runner --dry-run
```

고정 Fixture 예제: 정답 순위 1위, 3위, 없음인 질문 3개.
문서·청크 Hit@1=1/3, Hit@3=Hit@5=2/3, MRR=4/9.
이는 계산 검증용 예시이며 실제 KURE-v1 성능이 아니다.

## 발표 흐름 (약 3분)

1. 기존 문서·청크 평가 코드를 Runner가 호출할 수 있게 연결했다.
2. config와 검색 결과를 받아 qrels와 질문 ID를 검증하고 지표를 계산한다.
3. 문서 검색 실패, 청크 검색 실패, 실행 오류를 분리해 CSV로 저장한다.
4. 고정 Fixture로 수작업 계산과 일치하는지 검증했고 실제 Runner 연결도 앞 단계를 가짜 입력으로 대체해 테스트했다.
5. 전체 데이터 실측은 데이터·청킹·인덱싱·검색 모듈과 입력 파일이 준비된 뒤 진행한다. 개별 기능 검증과 전체 Baseline 완료를 구분한다.

## PM에게 공유할 구현 결정

공통 함수명, 인자, YAML 및 Runner는 변경하지 않았다.
실제 계약 문서는 `docs/config_experiments_contract.md`에 있다.
현재 Runner는 평가 결과의 status를 확인하지 않고 COMPLETED를 지정하므로,
검색 Runtime 오류 시 저장 함수가 진단 산출물을 남긴 후 예외를 발생시킨다.
향후 PM이 실패 상태 및 진단 저장을 Runner에서 직접 관리하도록 확장할 수 있다.
부분 청크 평가가 필요하면 대상 질문과 집계 분모의 공통 규격을 먼저 정해야 한다.

## Context Precision / Recall (PM 운영 기준 반영)

기존 Hit@k·MRR은 유지하고, 근거 지표는 검수 입력으로 활성화한다.
LLM·API·재청킹은 필요 없다. 이전 정답 청크 ID 검색 비율을 Context Recall로
저장하던 계산은 제거했다. 이전 점수와 새 점수는 같은 지표로 비교하지 않는다.

- Precision@k: 관련 청크가 나온 각 순위의 Precision@rank 평균.
- Recall@k: 상위 k개 청크가 뒷받침하는 고유 필수 정보 수 / 전체 필수 정보 수.
- 동일 사실이 여러 청크에 있어도 한 번만 센다. 연결 하나는 그 사실 전체를
  지원한다는 뜻이며, 부분 정보만 있는 청크는 완전한 지원으로 등록하지 않는다.
- MRR은 Top-5 첫 정답의 역수이며 검색 깊이가 커져도 6위부터는 0이다.

### YAML과 검수 입력

기존 `evaluation`에 추가한다. 경로는 프로젝트 기준이며 `{chunking_version}`도
지원한다. `1 ≤ k ≤ retrieval.evaluation_max_k`를 검증하며 운영표 비교에는 k=5를 쓴다.
실제 검수 입력이 준비되기 전 기본 설정은 비활성 상태다.

```yaml
context_metrics:
  enabled: true
  version: context_eval_v1
  k: 5
  required_facts_path: data/evaluation/eval_full_v1/required_facts.jsonl
  chunk_fact_map_path: data/evaluation/eval_full_v1/c2_section_800/chunk_fact_map.jsonl
```

`required_facts.jsonl`은 모든 청킹·모델에서 동일 버전을 쓴다(한 행에 한 사실).

```json
{"query_id":"q1","fact_id":"age","fact_text":"A 정책은 만 19세 이상 신청 가능하다.","document_id":"d1","source_location":"eligibility","review_status":"approved"}
{"query_id":"q1","fact_id":"period","fact_text":"신청 마감일은 11월 30일이다.","document_id":"d1","source_location":"application_period","review_status":"approved"}
```

`chunk_fact_map.jsonl`은 청킹별로 검수한다. 같은 사실을 지원하는 청크가 여러 개면
행을 추가한다. 모델만 변경하는 비교에는 같은 연결표를 사용한다.

```json
{"query_id":"q1","fact_id":"age","chunk_id":"c1","chunking_version":"c2_section_800_v1","review_status":"approved"}
{"query_id":"q1","fact_id":"period","chunk_id":"c3","chunking_version":"c2_section_800_v1","review_status":"approved"}
```

검수한 결과 지원 청크가 전혀 없으면 해당 사실의 연결에 `chunk_id: null`을 기록한다.
연결 행 누락은 '지원 없음'이 아니라 '검수 부족'이다. null 행과 실제 청크 연결을
같은 사실에 함께 등록하면 오류다. 청크 qrels에도 `review_status`를 기록한다.
해당 질문의 관련 청크 목록을 충분히 검수해 목록 밖을 비관련으로 판정할 수 있을 때만
모든 행을 approved로 바꾼다. 기존 정답 청크가 있다는 이유로 자동 승인하지 않는다.

검수 상태는 pending/approved/rejected이고 필드 생략은 pending이다.
입력에 `context_version`이 있으면 YAML의 version과 일치해야 한다.
연결표의 `chunking_version`은 필수다. 질문·사실·청크·문서 참조, 중복·버전·원문 위치
오류와 파일 누락은 실행 전에 오류로 중단한다. 승인된 사실 일부만 분모로 골라 쓰지 않는다.
문서 담당은 필수 정보를, 청킹 담당은 청크 연결표를 작성하고 평가 담당이 검수한다.

### 집계와 저장

| 구분 | 처리 |
| --- | --- |
| 검수 후 정상 검색 | 정의대로 계산. 빈 결과·근거 미검색은 0 |
| 질문별 검색 오류 | 검수 가능한 지표를 0점으로 포함. execution_error 및 사유 저장 |
| 검수 부족 | null 및 사유 저장. 해당 지표의 평가 질문 수에서 제외 |
| 질문 누락·중복·입력 오류 | 공식 집계 중단 후 수정·재실행 |

질문별 오류도 검수 자체가 부족한 지표는 미평가로 남긴다. 오류 행의 충족·누락 정보는
판정하지 않고 null로 남긴다. 일부만 검수한 평균은 부분 평가이며 전체 공식 평가가 아니다.

기존 `metrics_by_query.jsonl`에 `context_precision_at_5`, `context_recall_at_5`,
`context_*_status`, `context_*_reason`, `required_fact_ids`, `supported_fact_ids`,
`missing_fact_ids`를 저장한다. `metrics_summary.json`에는 평균, 평가/미평가 질문 수,
전체 질문 수, complete/partial/unevaluated 상태와 기준 버전을 저장한다.
`experiment_manifest.json`의 `evaluation.context_metrics`에는 경로·SHA256·청킹 버전·k를 남긴다.

Runner는 인덱스 처리 전 입력을 검증한다. Baseline도
`run_chunk_evaluation(..., context_config=config)`로 같은 계산을 사용하고 기존
`chunk_metrics.jsonl`, `chunk_summary.json`, `chunk_evaluation_manifest.json`에 저장한다.
원본 검색을 재평가할 때 원본 실행 ID를 유지하고 새 평가 결과는 별도 폴더에 저장한다.
테스트는 기존 `tests/test_retrieval_metrics.py`에 통합했다.
