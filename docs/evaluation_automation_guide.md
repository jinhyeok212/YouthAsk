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
