# build_chunks.py 설명서 - 청크 준비(재사용/생성)

## 파일 목적

`src/chunking/build_chunks.py`는 Experiment Runner가 호출하는 청킹 단계의 진입점이다. 검수된 기존 청크를 등록하거나(reuse), 조건별 청크를 생성한다(generate). 두 경우 모두 chunk qrels 상태를 함께 확인해 `ChunkInfo`로 반환한다.

```python
build_chunks(config: dict, dataset_info: dict) -> dict
```

## Runner에서의 위치

```text
validate_documents
  -> build_chunks
  -> (경로 일치 확인, chunk qrels 검수 상태 확인)   # review_required면 여기서 중단
  -> validate_evaluation_inputs
  -> resolve_index
  -> run_batch_retrieval
  -> evaluate_experiment
```

## 설정 계약

경로는 YAML·v4 스키마 위치를 그대로 쓴다. `build_chunks`는 경로를 바꾸지 않으므로 반환 경로와 후속 단계가 읽는 `config` 경로가 항상 같다.

| 필드 | 의미 |
|---|---|
| `chunking.mode` | `reuse`(기본) 또는 `generate` |
| `chunking.strategy` | `section` 또는 `fixed` (별칭은 YAML에서 허용하지 않음) |
| `chunking.chunk_path` | `chunks.jsonl` 경로 |
| `chunking.manifest_path` | `chunk_manifest.json` 경로 |
| `evaluation.chunk_qrels_path` | 확정(검수 완료) chunk qrels 경로 |
| `evaluation.document_qrels_path` | generate 모드에서 자동 매핑에 쓰는 문서 qrels |

조건마다 다른 경로가 필요하면 경로에 `{chunking_version}`을 쓴다. 설정 로더(`load_and_validate_config`)가 한 번 치환하고, 이후 모든 단계가 같은 경로를 쓴다. 예시는 `configs/experiments/exp_chunk_generate_fixed_example.yaml`과 `exp_chunk_generate_section_example.yaml`에 있다.

## mode: reuse (기본, 팀 YAML)

기존 C2처럼 사람이 검수한 청크와 qrels를 검증하고 등록한다. 청크를 생성하지 않는다.

1. `chunk_path`가 없으면 `FileNotFoundError`로 중단한다.
2. 청크를 검증한다. ID 중복, 문서 참조, `chunk_index` 순서를 본다.
3. manifest가 있으면 signature와 SHA256을 비교한다. 없으면 bootstrap manifest를 만든다. 기존 manifest는 다시 쓰지 않는다.
4. 확정 qrels가 없으면 `FileNotFoundError`로 중단한다. 있으면 검증만 하고, 메타가 없으면 `legacy_bootstrap` 메타를 만든다.

## mode: generate

1. `chunking.version`이 `c2_`로 시작하면 거부한다. 새 생성기는 C2와 chunk_id·section 체계가 다르기 때문이다.
2. 같은 조건(signature: 데이터 SHA, 버전, 전략, size, overlap, `chunk_id_scheme`)의 manifest가 있으면 기존 청크를 재사용한다. 조건이 다르면 덮어쓰지 않고 중단한다.
3. 새로 만들 때는 아래 순서를 따른다.
   - 문서 qrels 형식(`query_id`)을 먼저 검증한다.
   - 청크를 생성해 임시 파일에 쓰고 검증한다.
   - chunk qrels를 처리한다(`build_chunk_qrels.md` 참고).
   - 모든 검증이 끝나면 청크, qrels 파일, manifest 순서로 최종 경로에 반영한다. manifest가 마지막이다.
   - 도중에 실패하면 이번 실행이 만든 임시 파일만 지운다. 입력을 고쳐 다시 실행하면 그대로 진행된다.

## 반환값

필수 필드(`chunk_path`, `manifest_path`, `chunk_count`, `chunk_qrels_path`)에 다음 필드를 더한다.

- `chunk_qrels_status`: `ready` / `review_required`
- `chunk_qrels_review_status`: `legacy_bootstrap` / `reviewed` / `auto_ready` / `review_required`
- `chunk_qrels_candidates_path`, `chunk_qrels_review_required_path`, `chunk_qrels_meta_path`
- `chunk_sha256`, `dataset_sha256`, `chunking_mode`, `chunks_reused`

## 남은 제약

- 최종 경로로 옮기는 도중(파일 교체 사이)에 프로세스가 강제 종료되면 manifest 없는 청크가 남을 수 있다. 이 경우 보호 규칙이 실행을 막으므로, 남은 파일을 확인한 뒤 정리해야 한다.
- 문서 단위로만 평가하는 모드는 아직 없다. `review_required`이면 실행 전체가 중단된다.
