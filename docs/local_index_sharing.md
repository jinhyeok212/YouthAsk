# 실험 결과와 로컬 DB 분리

## Git으로 공유하는 것

- `src/`, `scripts/`, `tests/`, `schemas/`: 코드·검증·실행 스크립트
- `configs/experiments/`: 모델과 실험 조건을 지정하는 YAML
- `docs/`: 실험 설명과 비교 문서
- `experiments/`: 지표, 검색 결과, trace, 환경 기록, 설정, 실험 manifest
- 기존 공통 문서·청크·평가 입력: `data/processed/`, `data/evaluation/`

이번 변경은 코드·평가 입력·완료된 실험 기록을 수정하지 않습니다.
`experiments/`의 `index_manifest.json`은 실험 근거로 Git에 남습니다.

## Git에서 제외하는 것

- `indexes/chroma/` 전체 (`.gitkeep` 제외): SQLite, 벡터 인덱스, 런타임 manifest
- `.venv-*/`: `.venv-embedding/` 등을 포함한 로컬 가상환경
- `db-exports/`: 별도 전달용 압축 파일을 만들 때 사용할 로컬 폴더

기존 추적 DB도 `git rm --cached`로 추적만 해제하고 실제 로컬 파일은 유지합니다.
이후 `git add .`를 실행해도 이 경로들은 포함되지 않습니다. `git add -f`로 강제 추가하지 마세요.
새 DB도 YAML의 `index.db_path`를 `indexes/chroma/` 아래에 지정합니다.
코드는 이 폴더가 아닌 `src/`나 `scripts/`에 보관하세요.
다른 경로에 생성하는 DB에는 별도의 ignore 규칙이 필요합니다.

## 이번 신규 실험: 별도로 전달할 폴더

2026-11-28 확인한 압축 전 용량입니다. 두 폴더 모두 청크 3,462개의 인덱스입니다.

| 모델 | 저장소 루트 기준 폴더 (= 받는 사람의 복원 경로) | 파일 수 | 용량 |
|---|---|---:|---:|
| KURE-v3 | `indexes/chroma/index_full_kure_v3_200_fixed_800_ov120_v1/` | 7 | 84,540,482 bytes (약 80.6 MiB) |
| Snowflake Arctic L v2.0 KO | `indexes/chroma/index_full_snowflake_arctic_l_v2_ko_200_fixed_800_ov120_v1/` | 7 | 68,373,662 bytes (약 65.2 MiB) |

각 **폴더 전체**를 압축해 별도 저장소에 업로드하세요. 포함해야 할 파일은 다음과 같습니다.

```text
index_full_<모델>_200_fixed_800_ov120_v1/
├── chroma.sqlite3
├── <collection 이름>__manifest.json
└── <UUID>/
    ├── data_level0.bin
    ├── header.bin
    ├── index_metadata.pickle
    ├── length.bin
    └── link_lists.bin
```

SQLite 하나만 공유하면 안 됩니다. 추가 보조 파일이 생겨도 폴더 전체에 포함하세요.
DB 옆 `__manifest.json`은 런타임 재사용 검사에 필요합니다. DB와 이것 중 하나만
있으면 현재 runner는 불완전한 인덱스로 판단해 중단합니다.

실험과 Chroma를 사용하는 프로그램이 종료된 상태에서 압축·복원하세요.
저장소 루트 PowerShell에서 아래 명령으로 두 ZIP을 만들 수 있습니다.

```powershell
New-Item -ItemType Directory -Path .\db-exports -Force | Out-Null
Compress-Archive -LiteralPath .\indexes\chroma\index_full_kure_v3_200_fixed_800_ov120_v1 -DestinationPath .\db-exports\kure-v3-eval200-v1.zip
Compress-Archive -LiteralPath .\indexes\chroma\index_full_snowflake_arctic_l_v2_ko_200_fixed_800_ov120_v1 -DestinationPath .\db-exports\snowflake-ko-eval200-v1.zip
Get-ChildItem .\db-exports -Filter '*.zip' | Get-FileHash -Algorithm SHA256
```

이미 같은 ZIP 이름이 있다면 새 이름을 사용하세요. 공유 링크와 SHA-256을 팀원에게
전달하고, 실제 업로드 위치가 정해지면 이 문서에 링크를 기록할 수 있습니다.
가상환경과 Hugging Face 모델 캐시는 전달 대상이 아닙니다. 팀원은 의존성 목록과
모델 revision에 맞춰 환경과 모델을 준비합니다.

## 받는 팀원: 첫 변경 적용 전

**기존 DB를 유지하려면 추적 해제 커밋을 pull하거나 해당 변경이 있는 브랜치로
전환하기 전에 백업하세요.** Git이 기존 추적 DB 파일을 삭제할 수 있습니다.
DB 프로그램을 종료하고 `indexes/chroma/` 전체를 저장소 밖에 복사한 후 변경을
받으세요. 성공 후 백업한 폴더를 같은 경로에 복원하면 이제 로컬 전용 파일로 유지됩니다.
로컬 변경이 있어 Git이 중단하면 먼저 그 변경을 보관하고 진행하며 강제로 덮어쓰지 않습니다.

백업을 놓쳤다면 이전 LFS 커밋의 별도 clone에서 복구하거나 DB를 다시 전달받거나
재생성할 수 있습니다. 과거 Git/LFS 객체는 이번 변경에서 삭제하지 않습니다.

## 받는 팀원: 신규 DB 복원

코드·설정·결과 변경을 받은 뒤 ZIP의 모델별 폴더를 `indexes/chroma/` 바로 아래에 풉니다.
아래처럼 폴더가 중복 중첩되지 않아야 합니다.

```text
indexes/chroma/index_full_kure_v3_200_fixed_800_ov120_v1/chroma.sqlite3
indexes/chroma/index_full_snowflake_arctic_l_v2_ko_200_fixed_800_ov120_v1/chroma.sqlite3
```

YAML 연결은 각각 다음과 같습니다.

- KURE-v3: `configs/experiments/exp_model_kure_v3_eval200.yaml`
- Snowflake KO: `configs/experiments/exp_model_snowflake_arctic_l_v2_ko_eval200.yaml`

YAML의 상대 경로 `index.db_path`와 `collection_name`을 사용합니다.
완료된 `experiments/` 기록의 절대 경로를 팀원 PC에 맞추려고 수정하지 않습니다.
Chroma/Python 등 환경 버전은 해당 실험의 `environment.json`과 의존성 목록을 확인하세요.
새 평가 실행에는 별도 `experiment_id`를 쓰고 완료된 결과 폴더를 덮어쓰지 않습니다.

결과 문서·지표만 보는 팀원은 DB를 받지 않아도 됩니다.
기존 벡터로 직접 검색하거나 임베딩 재생성 없이 평가하려는 팀원은 해당 모델 DB를 받습니다.
DB를 받지 않고 직접 재생성할 수도 있으며, 이때 모델 다운로드와 임베딩 실행이 필요합니다.

## 기존 기준 DB가 필요한 경우

이번 신규 모델 두 개만 공유할 경우 이전 DB까지 모두 전달할 필요는 없습니다.
KURE-v1 기준 검색도 필요한 팀원에게는 다음 폴더를 추가로 전달합니다.

- `indexes/chroma/index_full_kure_200_fixed_800_ov120_v1/` (약 65.2 MiB)

이전 청킹 실험을 직접 재사용할 때만 아래 폴더들을 필요에 따라 전달합니다.

- `indexes/chroma/index_full_kure_200_v1/`
- `indexes/chroma/index_full_kure_200_section_500_ov120_v1/`
- `indexes/chroma/index_full_kure_200_section_800_ov0_v1/`
- `indexes/chroma/chroma_db/` (이전 파이프라인)

## Git에 올리기 전 확인

```powershell
git status --short
git add .
git diff --cached --stat
```

최초 전환에는 기존 DB가 Git상 삭제(`D`)로 표시되는 것이 정상입니다.
로컬 파일 삭제를 뜻하지 않습니다. 이후 새 DB는 변경 목록에 나타나지 않습니다.
코드·설정·결과와 추적 해제 변경을 검토한 뒤 현재 작업 브랜치에 커밋·push하세요.
이 설정은 과거 커밋의 LFS 사용량을 회수하거나 이전 커밋에 이미 포함된 큰 파일을
제거하지는 않습니다.
