# Full Dataset Baseline: eval_200_v1 준비 및 검증

검증일: 2026-11-17 (Asia/Seoul). 기준: 로컬 main, `7897b1b`.
상태: **데이터 변환 및 설정 검증 PASS / 전체 실험 미실행 / Chunk Qrels 별도 검수 대기**.

## 입력 및 코드 확인

- 입력 CSV: `C:\Users\LeeJH\Downloads\YouthAsk_eval_200_source_verified_FINAL.csv` (실제 제공 파일 사용).
- 원본 문서: `data/processed/ontong_youth_full_v1/documents.jsonl` (2,728개).
- 확인: `src/experiments/runner.py`, `config_validator.py`, `schemas/experiment_v4.schema.json`, `schemas/question.schema.json`, `schemas/qrels.schema.json`, `src/evaluation/validate_inputs.py`, `qrels.py`, `src/chunking/build_chunks.py`, `build_chunk_qrels.py` 및 기존 예시 설정.
- 질문/qrels JSON Schema는 object 수준의 느슨한 스키마이므로, 변환기의 엄격한 검증과 실제 document qrels loader로 추가 확인했다.
- Runner는 추가 `evaluation_manifest.json`을 필수 입력으로 읽지 않는다. 이 파일은 출처·해시·검증 결과 기록용이다.
- 기존 설정이 참조하는 `data/evaluation/eval_full_v1`은 현재 체크아웃에 없었다. 기존 47개 데이터는 `data/processed/ontong_youth_eval_questions_v2_final_47`에서 확인했으며 수정하지 않았다.

## 데이터 검증 결과

| 검사 | 결과 |
| --- | --- |
| 질문 수 / 고유 query_id | 200 / 200 |
| Document Gold 연결 수 / 고유 Gold 문서 | 207 / 205 |
| 질문별 Gold 수 | 1개: 193문항, 2개: 7문항 |
| 빈 query_id / query / reference_answer / Gold ID | 모두 0 |
| 중복 query_id / 중복 질문-문서 쌍 | 모두 0 |
| 원본 documents.jsonl에 없는 Gold ID | 0 |
| 모든 질문의 Document Gold 연결 | PASS |
| 원본 CSV와 전체 행 비교 | PASS: 순서·값·승인 내용 유지 |
| 실제 document qrels loader | PASS: 200개 질문, 207개 연결 |
| 원본 CSV 승인 라벨 | `human_review_label=1`: 200개, 원문 그대로 보존 |

`eval_questions.jsonl`은 CSV의 모든 컬럼을 보존하고 `ground_truth_document_ids`만 JSON 배열로 디코딩했다. 질문·답변의 공백을 포함한 원문을 변경하지 않았다. `qrels.jsonl`에는 각 배열 원소를 `query_id`, `document_id`, `relevance: 1`로 순서대로 펼쳤다. 중복 제거로 수를 맞추거나 질문을 생성하지 않았다.

`reference_answer`를 evidence_text, answer_text, 위치/offset으로 자동 변환하지 않았다. 청크와 Chunk Qrels 파일은 생성하지 않았다. 현재 qrels에는 청크 매핑 근거가 없으므로 향후 Runner 실행 시 청크를 생성한 뒤 검수 필요 상태로 Index/Embedding 전에 중단하도록 기존 동작을 유지한다. 실제 청크 생성 및 그 결과의 검증은 이번 작업에서 수행하지 않았다.

## SHA256

| 대상 | SHA256 |
| --- | --- |
| 원본 CSV | `21be26fedce3d06e26f73ae82f2ec890cb0fe03ea800e834191c9c3de7f4dd1a` |
| 원본 documents.jsonl | `99ac3eba5a1f79ad62842a5aff973cb69dd236d8dac63974ef87c70f8240e044` |
| eval_questions.jsonl | `4715106dd98d9541df9adfcf492a1f5177796700809f1ebe68eb2eeb10660a4f` |
| qrels.jsonl | `7bbbeb3cfbb0e322ec7253a5fb80d4b7ee1c3fcd5f56ee2a7db6da5fe018f117` |

동일 값이 `evaluation_manifest.json`에 기록되어 있으며, 생성된 JSONL의 해시를 다시 계산해 확인했다. Manifest 자체의 해시는 자기 참조를 피하기 위해 그 안에 기록하지 않는다. 입력 CSV 원본은 복사하거나 수정하지 않았다.

## 독립 설정

`configs/experiments/exp_chunk_generate_section_example.yaml`을 복사하여 `configs/experiments/exp_full_kure_200_v1.yaml`을 만들었다. 원본 예시는 그대로 보존했다.

- experiment_id: `exp_full_kure_200_v1`
- 평가 버전 및 경로: `eval_200_v1`, `data/evaluation/eval_200_v1/`
- 청킹: `generate`, `section`, 800 characters, overlap 120, `retrieval_text`, `section_heading_800_ov120_v1`
- 청크 출력: `data/processed/ontong_youth_full_v1/chunks/eval_200_v1/{chunking_version}/`
- 향후 검수된 Chunk Qrels 위치: `data/evaluation/eval_200_v1/chunk_qrels/{chunking_version}/qrels_chunk.jsonl` (현재 미생성)
- 임베딩: `nlpai-lab/KURE-v1`, revision `8b418a58414668e75532ed045c22d9ca018ae2b2`; 나머지 embedding 설정도 예시와 동일함을 비교 확인
- index.version: `index_full_kure_200_v1`
- index.db_path: `indexes/chroma/index_full_kure_200_v1`
- index.collection_name: `ontong_youth_full_kure_200_v1`
- evaluation_max_k: 5, ks: [1, 3, 5], context_metrics.enabled: false

## 실행한 검증

프로젝트 루트에서 `.venv-smoke/Scripts/python.exe`를 사용했다.

```powershell
.\.venv-smoke\Scripts\python.exe -m pytest tests -q
.\.venv-smoke\Scripts\python.exe run_experiment.py --config configs/experiments/exp_full_kure_200_v1.yaml --validate-only
.\.venv-smoke\Scripts\python.exe run_experiment.py --config configs/experiments/exp_full_kure_200_v1.yaml --dry-run
git diff --check
```

- 전체 테스트: **141 passed in 9.63s**, 그중 새 변환 테스트 13개.
- 새 테스트: 복수 Gold 및 모든 원문 컬럼 보존, 해시, 재실행 덮어쓰기 차단, CSV 부재, 질문/연결 수 불일치, 중복 query_id, 빈 질문/답변/Gold ID, 미존재 Gold, 빈 배열, 배열 아닌 값, JSON 오류, 중복 Gold 거부. 실패한 입력은 출력 디렉터리를 생성하지 않음을 확인.
- `--validate-only`: **VALID** (현행 v4 JSON Schema 및 의미 검증).
- `--dry-run`: input_files_ready / pipeline_modules_ready / output_available / ready_for_execution 모두 true. generate 모드의 입력 준비 상태이며, 청크 정답 검수 완료나 실험 성공을 의미하지 않는다. chunks 및 chunk_qrels 존재 여부는 false다.
- `git diff --check`: PASS.
- `data/evaluation`, `data/processed`, `indexes`, `experiments`, `configs/experiments`의 작업 전 기존 파일 **294개**를 SHA256으로 비교해 모두 보존 확인. 예시 설정, 기존 47개 데이터, 기존 청크·Index·실험 산출물을 포함한다.
- 새 설정의 청크·청크 manifest·Chunk Qrels·Index DB·실험 결과 경로가 생성되지 않았음을 확인.

변환 재현 명령 (출력 폴더가 이미 존재하면 의도적으로 실패하며 덮어쓰지 않음):

```powershell
.\.venv-smoke\Scripts\python.exe scripts/prepare_eval_200_v1.py --source 'C:\Users\LeeJH\Downloads\YouthAsk_eval_200_source_verified_FINAL.csv'
```

## 변경 파일 목록

모두 신규 파일이며 기존 추적 파일 수정은 없다.

1. `scripts/prepare_eval_200_v1.py`
2. `tests/test_prepare_eval_200_v1.py`
3. `configs/experiments/exp_full_kure_200_v1.yaml`
4. `data/evaluation/eval_200_v1/eval_questions.jsonl`
5. `data/evaluation/eval_200_v1/qrels.jsonl`
6. `data/evaluation/eval_200_v1/evaluation_manifest.json`
7. `docs/eval_200_v1_validation_report.md`
8. `data/evaluation/eval_200_v1/dataset_manifest.json` (아래 후속 수정에서 추가)

로컬 보존 비교용 작업 전 해시 목록은 기존 gitignore 대상인 `smoke_checks/eval_200_preservation_before.json`에 두었다. 임베딩·전체 실험·실험 결과 생성·커밋·푸시는 실행하지 않았다.

## 후속 수정: Windows 체크아웃의 Dataset Manifest 해시 불일치

사용자의 Runner 실행은 문서 검증 단계에서 중단되었다. 최초 `--validate-only`와 `doctor`는 설정 및 입력 존재를 확인하지만 실제 Dataset Manifest의 문서 해시까지 검증하지 않으므로 이 문제를 발견하지 못했다.

- 기존 Dataset Manifest의 문서 SHA256: `8688055b4553c79e9390e31831b5fefbef00925f24fb20af983a7ca552914a48`.
- 작업 폴더 문서의 SHA256: 위 표의 `99ac3e...e044`로, 평가셋 생성 당시와 동일하다.
- Git 저장본은 LF, Windows 작업 폴더는 CRLF이며 CRLF 2,728개를 LF로 치환한 바이트가 Git HEAD 저장본과 완전히 일치한다. LF 바이트의 SHA256도 기존 Manifest와 정확히 일치했다. 문서 내용 변경이 아니라 파일 줄바꿈 표현의 차이다.
- 기존 문서 및 기존 `data/processed/ontong_youth_full_v1/dataset_manifest.json`은 수정하지 않았다. 해시 검증 로직도 유지했다.
- 기존 `build_dataset_manifest(..., write=False)`로 현재 문서를 읽어 `data/evaluation/eval_200_v1/dataset_manifest.json`을 신규 생성했다. 현재 바이트 SHA256, 문서 품질 검사 결과, 원본 Manifest 경로·해시, LF 해시 및 Git 비교 결과를 기록했다.
- 새 실험 YAML의 `dataset.manifest_path`만 새 Dataset Manifest 경로로 변경했다. 추가 출처 기록용 `evaluation_manifest.json`과 달리 이 Dataset Manifest는 Runner가 실제로 읽는 파일이다.
- 실제 `validate_documents(config)` 직접 호출: PASS, 문서 2,728개 및 현재 SHA256 확인. 청킹·임베딩·Index·전체 실험은 실행하지 않았다.

후속 검증 결과: `python -m pytest tests -q`는 **141 passed in 5.25s**, Runner `--validate-only`는 VALID, `--dry-run`의 입력/출력 준비 상태는 true, `scripts/doctor.py`는 doctor_pass=true였다. 기존 보호 대상 파일 294개의 SHA256도 모두 변경 없음을 다시 확인했다. `python -m pytest -q`는 개인 연습·로컬 복사본 테스트를 수집하므로 공식 검증 명령은 `tests` 경로를 명시한다.
