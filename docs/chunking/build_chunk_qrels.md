# build_chunk_qrels.py 설명서 - 문서 qrels를 chunk qrels로 변환

## 파일 목적

`src/chunking/build_chunk_qrels.py`는 평가 담당자가 만든 문서 단위 qrels를 chunk 단위 qrels로 변환한다. 검색 평가는 chunk 검색 결과를 기준으로 수행되기 때문에 문서 정답을 chunk 정답 후보로 연결해야 한다.

## 입력

```python
build_chunk_qrels(
    document_qrels_path,
    chunks_path,
    output_path,
)
```

지원하는 문서 qrels 형식은 두 가지다.

```json
{"query_id": "q001", "ground_truth_document_ids": ["policy_001"]}
```

```json
{"query_id": "q001", "document_id": "policy_001", "relevance": 1}
```

## 출력

`qrels_chunk.jsonl`은 다음 형태로 저장된다.

```json
{
  "query_id": "q001",
  "ground_truth_document_ids": ["policy_001"],
  "ground_truth_chunk_ids": ["policy_001__chunk_000", "policy_001__chunk_001"]
}
```

함수는 생성 요약을 반환한다.

```python
{
    "chunk_qrels_path": ".../qrels_chunk.jsonl",
    "query_count": 47,
    "mapped_query_count": 47,
    "missing_document_count": 0,
}
```

## 실패 조건

- qrels 파일이 없음
- chunks 파일이 없음
- qrels 행에 `query_id`가 없음
- 정답 문서에 해당하는 chunk가 없음
- 존재하지 않는 chunk id가 출력에 포함됨

