# build_chunks.py 설명서 - 문서 청킹 생성 자동화

## 파일 목적

`src/chunking/build_chunks.py`는 Experiment Runner가 호출하는 청킹 단계의 메인 진입점이다. `documents.jsonl`과 실험 설정을 입력받아 `chunks.jsonl`, `chunk_manifest.json`, `qrels_chunk.jsonl`을 생성하고 Runner 계약에 맞는 `ChunkInfo`를 반환한다.

## Runner에서의 위치

```text
validate_documents
  -> build_chunks
  -> resolve_index
```

Runner는 다음 함수를 호출한다.

```python
build_chunks(config: dict, dataset_info: dict) -> dict
```

## 입력

- `config["chunking"]`: `version`, `size`, `overlap`, `unit`
- `dataset_info["document_path"]`: 데이터 담당자가 넘긴 문서 파일 경로
- `config["dataset"]["chunk_path"]`: 생성할 `chunks.jsonl` 경로
- `config["evaluation"]["document_qrels_path"]`: 문서 단위 qrels 경로
- `config["evaluation"]["chunk_qrels_path"]`: 생성할 chunk qrels 경로

본문 필드는 `retrieval_text`, `content`, `text` 순서로 찾는다.

## 출력

```python
{
    "chunk_path": ".../chunks.jsonl",
    "manifest_path": ".../chunk_manifest.json",
    "chunk_count": 1234,
    "chunk_qrels_path": ".../qrels_chunk.jsonl",
}
```

## 처리 흐름

1. YAML 설정에서 chunk size, overlap, version을 읽는다.
2. `documents.jsonl`을 읽는다.
3. 문서마다 `{document_id}__chunk_{chunk_index:03d}` 규칙으로 chunk를 만든다.
4. `chunks.jsonl`을 저장한다.
5. `validate_chunks.py`로 결과를 검증한다.
6. `build_chunk_qrels.py`로 `qrels_chunk.jsonl`을 만든다.
7. `chunk_manifest.json`을 저장한다.
8. Runner 계약에 맞는 `ChunkInfo`를 반환한다.

## 실패 조건

- `chunking.overlap >= chunking.size`
- 문서에 `document_id`가 없음
- 문서에 청킹할 본문이 없음
- 지원하지 않는 `chunking.unit`
- chunk 검증 실패
- qrels를 chunk로 매핑할 수 없음

