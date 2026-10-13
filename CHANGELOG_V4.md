# v4 Team Ready 변경사항

- CWD 의존 상대경로 제거: config 내부 경로를 프로젝트 루트 기준으로 resolve
- `run_experiment.py` 추가: 프로젝트 밖의 작업 폴더에서도 절대경로로 실행 가능
- 기존 검수 `chunks.jsonl`을 필수 입력으로 변경, Runner 내부 fallback 청킹 제거
- `index.version`을 재사용 Signature에 포함
- `embedding.revision`을 재사용 Signature에 포함
- KURE-v1 revision을 성공 Baseline에서 확인한 commit으로 고정
- SentenceTransformers embedding dimension API 신/구 버전 호환
- 명시적 CUDA/MPS 요청 시 unavailable device 조기 오류
- Chroma `get_max_batch_size()`가 있으면 DB batch 자동 제한
- `evaluation.ks` 동적 Hit@K 지원
- 질문 단위 Retrieval 오류 존재 시 `PARTIAL_SUCCESS`
- Artifact staging → rename 적용
- `environment.json`, `resolved_config.json`, 원본 YAML snapshot 저장
- 팀 환경 점검용 `doctor.py`, `run_checks` 추가
- Windows/macOS/Linux 입력 준비 스크립트 추가
- exact package lock 생성 스크립트 추가
- deprecated/unused indexing adapter 예시 파일 제거
- 테스트 22개 통과
