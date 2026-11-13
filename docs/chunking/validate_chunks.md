# validate_chunks.py 설명서 - 청킹 결과 검증 자동화

## 파일 목적

`src/chunking/validate_chunks.py`는 생성된 `chunks.jsonl`이 임베딩과 인덱싱 단계로 넘어가도 되는지 검사한다.

## 입력

```python
validate_chunks(
    documents_path,
    chunks_path,
    chunk_size=800,
    overlap=120,
)
```

## 출력

검증 성공 시 다음 형태의 요약 정보를 반환한다.

```python
{
    "valid": True,
    "document_count": 400,
    "chunk_count": 2875,
    "duplicate_chunk_id_count": 0,
    "blank_chunk_count": 0,
    "missing_document_id_count": 0,
}
```

검증 실패 시 `ValueError`를 발생시킨다.

## 검증 항목

- `overlap < chunk_size`
- `documents.jsonl` 존재
- `chunks.jsonl` 존재
- `chunk_id` 누락 없음
- `chunk_id` 중복 없음
- `document_id` 누락 없음
- chunk의 `document_id`가 원본 문서에 존재
- `text`가 비어 있지 않음
- `char_length`가 실제 `text` 길이와 일치
- 모든 문서에 최소 1개 이상의 chunk 존재

## Runner와의 관계

이 파일은 Runner가 직접 호출하지 않고 `build_chunks.py` 내부에서 호출한다. 검증 실패가 발생하면 예외가 Runner까지 전달되어 다음 단계로 넘어가지 않는다.

