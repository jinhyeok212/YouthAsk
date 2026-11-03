# build_chunk_qrels.py 설명서 - chunk qrels 생명주기

## 원칙

- **확정 qrels(`evaluation.chunk_qrels_path`)는 자동화의 입력이다.** 파일이 있으면 자동화는 그 파일을 절대 쓰지 않고 검증만 한다.
- 자동 매핑 결과는 후보로만 저장한다. 근거가 부족하면 확정본을 만들지 않는다.

## 파일 구성 (같은 폴더)

| 파일 | 작성 주체 | 설명 |
|---|---|---|
| `qrels_chunk.jsonl` | 사람(검수) 또는 자동(전부 근거 매핑 시) | 평가가 읽는 확정본 |
| `qrels_chunk.candidates.jsonl` | 자동 | 근거 기반 매핑 후보. 실행할 때마다 다시 만든다 |
| `qrels_chunk_review_required.jsonl` | 자동 | 사람이 검수해야 할 항목과 이유. 실행할 때마다 다시 만든다 |
| `qrels_chunk.meta.json` | 자동 | 확정본과 청크 버전을 연결하는 메타데이터 |

후보 파일과 검수 파일은 다시 만들어지므로 그 파일을 직접 수정하면 안 된다. 검수 결과는 반드시 `qrels_chunk.jsonl`로 저장한다.

`qrels_chunk.meta.json`에는 다음 필드가 들어간다: `status`, `chunking_version`, `chunk_sha256`, `qrels_sha256`, `source_document_qrels_sha256`, `updated_at_utc`.

## 상황별 동작 (`resolve_chunk_qrels`)

| 상황 | 동작 |
|---|---|
| 확정본 있음 + 메타 있음 | 메타의 `chunking_version`·`chunk_sha256`이 현재 청크와 다르면 파일을 그대로 두고 중단한다. 같으면 ID를 검증하고 사용한다. 확정본 해시가 메타와 다르면(사람이 수정함) 메타만 `reviewed`로 갱신한다. |
| 확정본 있음 + 메타의 원본 qrels 해시가 현재와 다름 | 정답 근거가 바뀐 것이다. 확정본과 메타를 그대로 두고 `review_required`(`review_status=source_changed`)를 반환한다. 검수 파일에 질문별 `confirmed_chunk_ids`와 `candidate_chunk_ids`를 나란히 기록한다. 예외: 사람이 고치지 않은 `auto_ready` 확정본을 다시 매핑한 결과가 완전히 같으면 메타의 원본 해시만 갱신하고 진행한다. |
| 확정본 있음 + 메타에 원본 해시가 있는데 원본 qrels 파일이 없음 | 변경 여부를 확인할 수 없으므로 중단한다. |
| 확정본 있음 + 메타 없음 | 검증을 통과하면 메타만 만든다. reuse 모드는 `legacy_bootstrap`, generate 모드는 `reviewed`로 기록한다. generate 모드는 이때의 원본 qrels 해시도 기록한다. |
| 확정본이 비어 있음 | 중단한다. 비어 있는 확정본으로 평가하지 않는다. |
| 확정본 없음 + reuse 모드 | `FileNotFoundError` |
| 확정본 없음 + generate + 전부 근거 매핑 | 확정본과 메타(`auto_ready`)를 만든다. |
| 확정본 없음 + generate + 검수 필요 항목 있음 | 후보와 검수 파일만 만들고 `review_required`를 반환한다. Runner는 Index 생성 전에 중단한다. |

## 자동 매핑 규칙 (`map_chunk_qrels`)

파일을 읽거나 쓰지 않는 순수 함수다.

1. 문서 qrels 행에 `chunk_id`가 있으면 그대로 사용한다. 그 청크가 없으면 검수 대상으로 보낸다.
2. 근거 span이 있으면(`evidence_start_char`/`evidence_end_char` 등) 그 범위와 겹치는 청크를 매핑한다.
3. 근거 텍스트가 있으면(`evidence_text` 등) 그 텍스트를 포함하는 청크를 매핑한다.
4. 근거가 없으면 매핑하지 않고 검수 대상으로 보낸다(`missing_evidence_for_chunk_mapping`).

저장소의 `ontong_youth_eval_questions_v2_final_47/qrels.jsonl`(47문항, 50행)에는 근거 필드가 없다. 그래서 새 청크 조건으로 generate하면 50행이 모두 검수 대상이 된다. 이것이 정상 동작이다.

## 검수 절차

1. `qrels_chunk_review_required.jsonl`과 `qrels_chunk.candidates.jsonl`을 확인한다.
2. 정답 청크를 정해 `qrels_chunk.jsonl`에 저장한다. 행 형식은 `query_id`, `document_id`, `chunk_id`, `relevance`이고, 필요하면 `matched_section`과 `chunking_version`도 넣는다.
3. 같은 설정으로 다시 실행한다. 메타가 `reviewed`로 기록되고, 이후 재실행에서도 파일은 바뀌지 않는다.
4. 원본 문서 qrels가 바뀌어 `source_changed`로 멈췄다면, 검수 파일을 보고 `qrels_chunk.jsonl`을 필요한 만큼 고친 뒤 승인을 기록한다. 확정본 내용은 바꾸지 않고 메타만 현재 청크·원본 qrels 기준 `reviewed`로 갱신한다.

   ```
   python -m src.chunking.build_chunk_qrels approve --config configs/experiments/<실험>.yaml
   ```

5. 자동 결과로 다시 시작하려면 새 `chunking.version` 또는 새 경로를 쓴다. 기존 확정본을 덮어쓰는 옵션은 없다.

## 단독 실행 함수

`build_chunk_qrels(document_qrels_path, chunks_path, output_path, review_required_path=None, overwrite=False)`는 매핑 결과를 파일로 저장한다. `output_path`가 이미 있으면 `FileExistsError`로 중단한다.
