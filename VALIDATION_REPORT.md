# Validation Report — v4 Team Ready

## 확인 완료

- `python -m compileall` 성공
- 순수 로직/계약 테스트: **22 passed**
- 프로젝트 루트가 아닌 `/tmp`에서 `run_experiment.py --validate-only` 성공
- 프로젝트 루트가 아닌 `/tmp`에서 `--dry-run`이 프로젝트 기준 data 경로를 정상 판정
- 동적 Hit@10 단위 테스트 통과
- `index.version` 변경 시 Index signature 불일치 테스트 통과
- Embedding `revision` 변경 시 Index signature 불일치 테스트 통과
- Top-k만 변경할 때 Index signature 유지 테스트 통과
- 기존 Chunk 누락 시 자동 재청킹하지 않고 명확히 실패하는 테스트 통과

## 실제로 이미 확인된 E2E 기반

이 v4는 앞선 v3 구조에서 사용자가 Windows CPU 환경에서 실제로 확인한 다음 흐름을 기반으로 보강했습니다.

- KURE-v1 모델 로드
- 2,875 Chunk Chroma Index 생성
- 47개 평가 질문 Retrieval/Evaluation
- Artifact 저장 SUCCESS
- 동일 Index 재실행 `index_reused=true`

## 아직 환경별 실제 E2E가 필요한 범위

다음 환경은 코드상 지원 경로가 있지만 이 패키지 제작 환경에서 실제 KURE/Chroma 전체 실행까지 직접 검증하지 않았습니다.

- Windows + NVIDIA CUDA
- macOS + MPS
- Linux + KURE-v1 + Chroma 실제 Index Build

따라서 팀원은 반드시 `tests → doctor → validate-only → dry-run → run` 순서로 확인해야 합니다.
