# Ontong Youth Full RAG Document Schema v1

## 목적

온통청년 전체 정책 데이터를 RAG 실험 파이프라인에 넣기 위한 공통 문서 구조다.
정책 1개를 문서 1개로 본다.

## 레코드 단위

`one policy = one document`

## 후속 Chunking 대상 필드

`retrieval_text`

`content`와 `raw_record`는 보존/검사용이고, 실제 검색 청킹은 `retrieval_text`를 기준으로 진행한다.

## 주요 필드

- `document_id`: 문서 고유 ID. 기본 형식은 `ontong_youth_{plcyNo}`
- `title`: 정책명
- `source`: `ontong_youth`
- `url`: 대표 URL
- `content`: 주요 정책 필드를 구조화 텍스트로 결합한 본문
- `retrieval_text`: 검색/청킹 대상 텍스트
- `metadata`: 분류, 기관, 기간, 조건, URL, 정규화 상태, 품질점수
- `raw_record`: 온통청년 API 원본 주요 필드

## 아직 하지 않은 작업

- Chunking
- Chunk ID 생성
- Chunk 단위 qrels 생성
- Embedding
- Chroma index 구축
- Retrieval 평가
