# 소량 표본 실제 실행과 Git 관리

Smoke test는 전체 실험을 시작하기 전에 소량 입력으로 핵심 흐름이 끝까지 작동하는지 확인하는 검사입니다. 이 도구는 **준비된 검수 문서·청크·질문·qrels에서 표본을 만들고 실제 실험을 실행**합니다. 청크나 정답을 새로 생성하는 기능은 아닙니다.

## 한 번에 실행하기

저장소 루트에서 실행합니다. Python 3.10–3.13과 `requirements-experiments.txt`의 의존성이 필요합니다. 모델이 처음에는 없으면 Hugging Face에서 설정에 고정된 KURE-v1 revision을 다운로드합니다.

이미 준비된 환경에서는 다음 한 명령으로 표본 준비 → 입력·Manifest 검증 → 환경 점검 → 새 인덱스 생성 → 검색 → 평가 → 저장 → 독립 결과 검증까지 실행합니다.

```powershell
python scripts/run_smoke.py
```

현재 로컬 검증 환경 `.venv-smoke`를 사용하는 경우에는 다음을 실행합니다.

```powershell
$env:PYTHONUTF8 = "1"
$env:HF_HOME = "$PWD\.venv-smoke\hf_cache"
& .\.venv-smoke\Scripts\python.exe scripts/run_smoke.py --offline
```

`--offline`은 캐시에 이미 모델이 있을 때 사용합니다. 이 컴퓨터의 `.venv-smoke`는 기존 환경의 torch 등 일부 패키지를 읽어 재사용하므로 다른 컴퓨터에 그대로 복사해서 사용하지 마세요. 팀원은 자체 환경을 준비합니다.

새 Windows 환경의 준비 예시:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-experiments.txt
& .\.venv\Scripts\python.exe scripts/run_smoke.py
```

## 원본과 실험 조건

공유하는 기본 소스 설정은 `configs/smoke/mvp400_c2.yaml`입니다. 기본으로 아래 기존 검수 자료를 사용합니다.

| 자료 | 위치 |
| --- | --- |
| 문서 | data/processed/chunking2/01.document/documents.jsonl |
| 질문 | data/processed/chunking2/02.eval_question_qrels/eval_questions.jsonl |
| 문서 qrels | data/processed/chunking2/02.eval_question_qrels/qrels.jsonl |
| 청크 | data/processed/chunking2/05.chunks/c2_section_800/c2_section_800_chunks.jsonl |
| 청크 qrels | data/processed/chunking2/05.chunks/c2_section_800/qrels_chunk.jsonl |

소스 설정은 표본 준비 도구에 전달하는 설정입니다. `src.experiments.runner`에 직접 실행 설정으로 전달하지 마세요. 도구가 생성한 `smoke_checks/<run_id>/config.yaml`이 실제 실행 설정입니다.

기본 표본은 질문 8개입니다. 복수 정답 질문과 질문 유형을 우선 포함하고 나머지는 원본 순서로 선택합니다. 선택 질문에 연결된 qrels 행과 정답 문서의 전체 청크를 보존하며 원본 ID·본문·순서를 바꾸지 않습니다. 현재 기본 자료에서 문서 9개, 청크 67개, 문서·청크 qrels 각 9행입니다. 이 개수는 하드코딩하지 않고 실제 선택 자료에서 계산합니다.

원본 전체의 문서·청크·qrels 연결을 먼저 검증합니다. 원본 Manifest 경로에는 쓰지 않고 실행 폴더 안에서 검증용 Manifest를 생성합니다. 표본 Manifest도 현행 러너가 사용하는 signature와 파일 SHA256 규칙으로 생성합니다.

## 실행 옵션

```powershell
# 표본 파일과 Manifest만 준비·검증. 실제 실행 성공을 의미하지 않습니다.
python scripts/run_smoke.py --prepare-only

# 표본 질문 수 변경 (기본 자료에서는 1~47)
python scripts/run_smoke.py --question-count 4

# GPU 없이 실행
python scripts/run_smoke.py --device cpu

# 원하는 이름 지정. 이미 존재하는 폴더는 거부합니다.
python scripts/run_smoke.py --run-id smoke_team_check

# 다른 준비된 자료의 소스 설정 사용
python scripts/run_smoke.py --source-config configs/smoke/mvp400_c2.yaml
```

이름을 지정하지 않으면 UTC 시각과 임의 식별자를 조합한 새 run_id를 생성합니다. 실행마다 experiment_id, 인덱스 버전·경로·컬렉션이 분리됩니다. 기존 결과는 덮어쓰지 않습니다. 다른 청킹 조건을 비교하려면 해당 조건의 검수 청크·chunk qrels와 맞는 소스 설정을 준비해야 합니다.

## 결과 확인

생성 자료는 모두 `smoke_checks/<run_id>/` 아래에 저장됩니다.

```text
smoke_checks/<run_id>/
├── config.yaml
├── inputs/                   # 표본 5파일 + Dataset/Chunk Manifest
├── source_validation/        # 원본을 수정하지 않고 만든 검증용 Manifest
├── preparation_audit.json    # 선정 규칙, ID, 개수, 원본·표본 해시
├── doctor.json
├── index/                    # 새 Chroma 인덱스와 Manifest
├── results/<run_id>/         # 러너의 검색·평가·Trace·로그 등
├── run_result.json
├── verification.json
└── artifact_inventory.json   # 실행 자료의 경로·크기·해시
```

`verification.json`의 `status=PASS`, `runner_status=SUCCESS`를 확인합니다. 검증은 실제 Chroma 개수·ID, 모든 질문의 검색·평가·Trace 누락/중복, 검색 runtime 오류, 결과의 부모 문서 연결, 원본·표본 해시 보존, 저장된 Index Manifest를 확인합니다. 낮은 Hit@k/MRR은 검색 품질 문제로 구분하며 이 검사에서 실패로 처리하지 않습니다.

기존 결과를 다시 확인하려면 다음 명령을 사용합니다. 인덱스를 새로 생성하거나 기존 결과 폴더를 덮어쓰지 않으며, 로컬 verification.json과 해시 목록만 갱신합니다.

```powershell
python scripts/verify_smoke.py --config smoke_checks/<run_id>/config.yaml
```

실패한 실행 폴더는 진단용으로 남깁니다. 원인을 해결한 후 새 run_id로 실행하세요. 모델 캐시 부족 시 다운로드 가능한 환경에서 `--offline` 없이 실행하고, 입력 파일·qrels·ID 오류는 원본 자료 담당자와 확인합니다. 정답을 임의로 생성하지 않습니다.

## GitHub에 남길 파일

- 기능 코드와 회귀 테스트
- 재사용 가능한 `scripts/run_smoke.py`, `scripts/verify_smoke.py`
- 소스 설정 `configs/smoke/mvp400_c2.yaml`
- 이 안내 문서와 README 링크

`/smoke_checks/` 전체와 `/.venv-smoke/`는 루트 `.gitignore`에서 제외합니다. 표본 복사본·생성 설정·모델 캐시·인덱스·결과·로그·개인 환경 정보는 GitHub에 추가하지 않습니다. 기존 검수 소스 자료는 기존 저장소 정책에 따라 유지합니다. 이전 날짜별 임시 도구·설정은 로컬 `smoke_checks/20261013_mvp400_c2/legacy_tools/`에 보관했습니다.

확인 명령:

```powershell
git status --short
git check-ignore smoke_checks/<run_id>/config.yaml
python -m pytest tests -q
```

루트 `pytest -q`는 개인 연습 프로젝트의 별도 테스트도 탐색하므로 현재 누락 모듈로 수집 오류가 발생할 수 있습니다. 실험 파이프라인 테스트는 `tests` 디렉터리를 명시해 실행합니다. 전체 데이터 실험의 입력 준비와 조건별 청크 생성 자동화는 이 도구의 범위에 포함되지 않습니다.
