# 2번 데이터셋/전처리 담당 전달 메모

## 핵심 상태

- 온통청년 전체 정책 2,728건을 RAG 문서 형식으로 변환 완료
- Runner 호출용 `validate_documents(config)` 대응 완료
- 전체 데이터 검증 통과
- 테스트 결과: `13 passed, 1 skipped`

## 전체 데이터 위치

```text
data/processed/ontong_youth_full_v1/documents.jsonl
data/processed/ontong_youth_full_v1/dataset_manifest.json
data/processed/ontong_youth_full_v1/data_quality_report.csv
```

## 청킹 담당자 사용 규칙

- 청킹 대상 필드: `retrieval_text`
- 문서 단위: `one policy = one document`
- 다음으로 생성해야 할 파일:

```text
data/processed/ontong_youth_full_v1/chunks.jsonl
data/processed/ontong_youth_full_v1/chunk_manifest.json
```

## Runner 데이터 검증 함수

```python
from src.data.validate_documents import validate_documents

dataset_info = validate_documents(config)
```

필수 반환 필드:

```text
document_path
manifest_path
document_count
sha256
```

현재 실제 반환 예:

```json
{
  "document_path": "data/processed/ontong_youth_full_v1/documents.jsonl",
  "manifest_path": "data/processed/ontong_youth_full_v1/dataset_manifest.json",
  "quality_report_path": "data/processed/ontong_youth_full_v1/data_quality_report.csv",
  "document_count": 2728,
  "sha256": "8688055b4553c79e9390e31831b5fefbef00925f24fb20af983a7ca552914a48",
  "dataset_version": "ontong_youth_full_v1",
  "preprocessing_version": "prep_v1"
}
```

## 기존 평가셋 참고

기존 MVP 평가 질문/문서 qrels는 아래에 있음.

```text
data/processed/ontong_youth_eval_questions_v2_final_47/
```

- 평가 질문: 47개
- 문서 단위 qrels: 50행
- 아직 `data/evaluation/eval_full_v1/` 표준 경로로 옮긴 것은 아님
- 아직 `qrels_chunk.jsonl` 없음
- `qrels_chunk.jsonl`은 `chunks.jsonl` 생성 이후 만들어야 함

## 아직 남은 후속 작업

```text
chunks.jsonl 생성
chunk_manifest.json 생성
qrels_chunk.jsonl 생성
KURE-v1 embedding
Chroma index
batch retrieval
Hit@k / MRR 자동 평가
Experiment Runner 통합
```
