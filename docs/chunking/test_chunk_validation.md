# test_chunk_validation.py 설명서 - 청킹 자동화 테스트

## 파일 목적

`tests/test_chunk_validation.py`는 청킹 담당 모듈만 독립적으로 검증하는 단위 테스트다. 전 단계 데이터 검증 코드나 다음 단계 임베딩 코드는 사용하지 않는다.

## 테스트 방식

테스트마다 임시 폴더를 만들고 작은 샘플 파일을 생성한다.

- `documents.jsonl`
- `qrels.jsonl`

그 다음 `build_chunks`, `validate_chunks`, `build_chunk_qrels`를 직접 호출한다.

## 검증 항목

- `build_chunks`가 `chunks.jsonl`을 생성하는지
- `build_chunks`가 `chunk_manifest.json`을 생성하는지
- `build_chunks`가 `qrels_chunk.jsonl`을 생성하는지
- `build_chunks` 반환값이 Runner의 `ChunkInfo` 계약을 만족하는지
- 정상 chunk는 `validate_chunks`를 통과하는지
- 중복 `chunk_id`는 검증 실패하는지
- 원본에 없는 `document_id`는 검증 실패하는지
- 문서 qrels가 chunk qrels로 변환되는지

## 실행 명령

```powershell
py -m unittest tests.test_chunk_validation -v
```

