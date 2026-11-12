# Context Precision / Recall (qrels 기반)

Baseline(`evaluator.py`)과 experiment runner(`evaluate_experiment.py`)는
`retrieval_metrics.calculate_context_metrics`의 동일한 계산을 사용한다.
추가 API 호출이나 LLM 비용 없이 기존 검색 결과와 qrels로 계산한다.

- Context Precision: 각 관련 ID 순위의 Precision@rank 합 / 검색된 고유 관련 ID 수.
  관련 근거가 앞에 있을수록 높다. 관련 ID를 하나도 찾지 못하면 0.
- Context Recall: 검색된 고유 관련 ID 수 / 전체 gold ID 수.
- 중복 ID는 순위를 차지하지만 정답 적중을 추가로 인정하지 않는다.
- 빈 검색 결과는 두 지표 모두 0이며, 빈 gold 집합은 오류로 처리한다.
- 질문별 지표를 산술 평균하여 전체 지표를 계산한다.

문서와 청크를 각각 계산한다. Baseline은 전달된 검색 결과 전체에 대해
`context_precision`, `context_recall`을 질문별로 저장하고, 요약 키에
`document_` 또는 `chunk_`를 붙인다. Runner도 같은 요약 키를 저장하며
설정의 `evaluation.ks`별로 `chunk_context_precision_at_5` 같은 지표를 추가한다.
비교 실험은 같은 검색 개수, qrels, 청크 버전을 사용해야 한다.
기존 결과 파일은 자동으로 갱신되지 않으므로 새 지표는 재평가해야 한다.

이 지표는 **ID 관련성 및 gold 근거 검색 비율**을 측정한다.
특히 문서 ID가 맞더라도 검색된 청크에 답변 내용이 없을 수 있어 청크 지표를
함께 확인해야 한다. qrels에 대체 가능한 근거가 여러 개 등록된 경우에도
Recall은 그 ID들의 검색 비율이며 답변 가능 여부와 같지는 않다.

RAGAS/LLM 기반 의미 평가를 구현한 것은 아니다. 답변에 필요한 사실이
검색 근거에 충분히 포함됐는지를 직접 평가하려면 기준 답변 또는 필수 사실,
검색된 청크 본문, 의미적 관련성/사실 커버리지 판정이 별도로 필요하다.

선택적으로 실행 가능한 의미 평가가 추가되었다. 설정 및 검수 순서는
[semantic_context_guide.md](semantic_context_guide.md)를 참고한다.
