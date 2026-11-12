# 의미 기반 Context Precision / Recall

기존 청크·인덱스·검색 결과를 그대로 사용한다. 새 청킹은 필요 없다.
이 구현은 프로젝트 자체 LLM 평가이며 RAGAS 패키지의 점수와 같다고 보장하지 않는다.
기존 qrels 지표는 유지하고 `semantic_context_*` 키로 구분한다.

## 1. 기준 데이터 검수

47개 질문의 기존 `reference_answer`를 복사한 검수 파일:
`data/evaluation/semantic_context_v1/references.review.jsonl`

각 행의 `query_id`, `query`를 유지하고, `reference_answer`가 실제 원문과 일치하는지
확인한다. `required_facts`에는 **질문에 답하기 위해 꼭 필요한 사실**을 문장으로
나누어 작성한다. 문서 전체 내용이나 답변에 불필요한 세부 조건을 모두 넣으면
Recall 기준이 과도해진다. 각 사실은 독립적으로 판단 가능한 하나의 주장으로 쓴다.
정책 식별 질문이면 정책명 및 질문에서 요구하는 식별 조건을 기준으로 삼는다.
검수 완료 후 `review_status`를 `approved`로 바꾼다. 기준 데이터의 검수는 질문과
문서를 이해하는 담당자가 진행한다. 템플릿은 자동 승인하지 않는다.

예시(형식 설명용 가상 정책):

```json
{"query_id":"q1","query":"서울 거주 19세 청년이 A 지원을 신청할 수 있나요?","reference_answer":"A 지원은 서울 거주 만 19세 이상 청년이 신청할 수 있다.","required_facts":["A 지원의 거주 요건은 서울이다.","A 지원의 최소 신청 연령은 만 19세이다."],"review_status":"approved"}
```

다른 질문셋용 템플릿 생성:

```powershell
python -m src.evaluation.semantic_context prepare --questions path/to/questions.jsonl --output path/to/references.review.jsonl
```

기존 파일을 덮어쓰지 않는다. 기존 질문 파일이나 qrels도 수정하지 않는다.

## 2. Baseline 재평가

선택 의존성을 설치한다. `OPENAI_API_KEY`는 환경 변수로 설정하고 저장소에 기록하지 않는다.
모델은 Structured Outputs를 지원하는, 팀에서 선택한 동일 모델을 사용한다.

```powershell
python -m pip install -r requirements-semantic.txt
python -m src.evaluation.semantic_context evaluate --retrieval-results experiments/exp_baseline_kure_v1/retrieval_results.jsonl --references data/evaluation/semantic_context_v1/references.review.jsonl --model YOUR_JUDGE_MODEL --top-k 3 --output-dir experiments/exp_baseline_semantic_v1 --validate-only
```

`--validate-only`는 API 호출 없이 질문 ID, 질문 본문, 검수 상태, 필수 사실,
검색 본문을 검증한다. 미검수 파일이면 오류로 중단하는 것이 정상이다.
검증이 통과하면 같은 명령에서 `--validate-only`를 제거해 실행한다.
실행은 질문·기준 답변·필수 사실·검색 본문을 OpenAI API로 전송하며 비용이 발생한다.
빈 검색 결과는 호출 없이 두 지표를 0으로 계산한다.

본문이 없는 검색 결과에는 `--chunks path/to/existing/chunks.jsonl`을 추가한다.
본문은 `text` 또는 `retrieval_text`에서 읽고, 자동으로 잘라내지 않는다.
컨텍스트 한도 오류가 발생하면 실패로 중단하므로 동일한 모델·Top-k 기준으로
입력을 조정하고 다시 실행한다.

파이썬 Baseline 평가도 지원한다:

```python
from src.evaluation.evaluator import run_chunk_evaluation

config = {"evaluation": {"semantic_context": {
    "enabled": True,
    "references_path": "data/evaluation/semantic_context_v1/references.review.jsonl",
    "model": "YOUR_JUDGE_MODEL",
    "top_k": 3,
}}}
run_chunk_evaluation("retrieval_results.jsonl", "qrels_chunk.jsonl",
                     "new_evaluation_output", semantic_config=config)
```

## 3. Runner 연결

기존 v4 실험 YAML의 `evaluation` 아래에 추가한다. 실행할 때 새 experiment_id를 쓴다.

```yaml
evaluation:
  # 기존 version, questions_path, document_qrels_path, chunk_qrels_path, ks 유지
  semantic_context:
    enabled: true
    references_path: data/evaluation/semantic_context_v1/references.review.jsonl
    model: YOUR_JUDGE_MODEL
    top_k: 3
```

설정을 생략하거나 `enabled: false`로 두면 추가 의존성·LLM 호출 없이 기존 평가만 한다.
Runner는 인덱스 처리 전에 기준 데이터의 검수 상태와 질문 정합성을 확인한다.
Runner 결과에 본문이 없으면 설정의 기존 `chunking.chunk_path`를 조회한다.
Baseline과 runner는 동일한 `evaluate_semantic_context`를 호출한다.
두 실험을 비교할 때는 같은 질문, 기준 데이터, 본문, 모델 및 Top-k를 사용한다.
`semantic_context.top_k`는 검색된 결과의 앞에서부터 적용하며
`retrieval.context_top_k`와 별도로 지정한다. `evaluation_max_k`보다 클 수 없다.

## 4. 점수와 산출물

- `semantic_context_precision`: 관련 청크 순위의 Precision@rank 합을 검색된 관련
  청크 수로 나눈 값. 관련 청크가 없으면 0. 중복 chunk_id는 순위를 차지하지만
  첫 등장만 적중으로 인정한다.
- `semantic_context_recall`: 검색된 청크들을 함께 읽었을 때 완전히 뒷받침되는
  필수 사실 수 / 전체 필수 사실 수. 부분 지원은 0으로 판단한다.
- 전체 점수는 질문별 점수의 산술 평균이다. 검색 실패·빈 결과도 분모에 포함한다.
- Judge의 거절, 형식 오류, 누락, 존재하지 않는 인용은 낮은 점수로 바꾸지 않고
  실행 오류로 처리한다. API 오류가 나면 해당 평가 실행은 완료되지 않는다.

Runner의 `metrics_summary.json`, `metrics_by_query.jsonl`에 점수를 합치고,
Baseline 및 runner 모두 다음 상세 산출물을 저장한다:

| 파일 | 내용 |
| --- | --- |
| `semantic_context_summary.json` | 전체 평균 |
| `semantic_context_metrics.jsonl` | 질문별 점수 |
| `semantic_context_judgments.jsonl` | 입력, 입력 해시, 청크별 판정, 사실별 판정, 인용, 응답 ID, 모델 및 사용량 |
| `semantic_context_manifest.json` | 프롬프트 버전·본문, 모델 설정, Top-k, 기준 파일 해시 |

인용문이 실제 본문에 존재하는지는 코드가 검사한다. 그 인용이 사실을 정말
뒷받침하는지는 LLM 판정이므로 표본을 사람이 다시 확인해야 한다.
모델 판단에는 변동이 있을 수 있어 점수만이 아니라 판정 근거도 함께 비교한다.
자동 승인, 기준 답변 자동 생성, RAGAS 결과와의 수치 동등성 검증은 포함하지 않는다.

API 구현 근거: [OpenAI 공식 Structured Outputs 문서](https://developers.openai.com/api/docs/guides/structured-outputs).
Responses API의 엄격한 JSON Schema 출력으로 판정 형식을 고정한다.
