# KURE-v3 / Snowflake Arctic KO 모델 비교 최종안

## 확정 기준

성공합시다의 11/12·11/17 회의 및 실험 운영 문서를 기준으로 다음을 적용한다.

- 평가 질문: 47개가 아니라 정확히 200개
- 전체 정책 문서: 2,728개
- 청킹: 모델 비교 잠정 기준 fixed / 800자 / overlap 120
- 검색: Chroma / cosine / Top-5
- 모델 외 조건: device=auto, float32, normalize=true, embedding batch 32, Chroma batch 256
- 비교 모델: 기존 KURE-v1과 신규 KURE-v3, Snowflake Arctic L v2.0 KO

두 신규 YAML에는 `evaluation.expected_question_count: 200`이 설정되어 있다. Runner는
질문 수가 200이 아니거나 질문·document qrels·chunk qrels의 query ID 집합이 다르면
임베딩을 시작하기 전에 중단한다.

## 모델별 입력 계약

| 모델 | 고정 revision | 차원 | 질문 | 문서 |
|---|---|---:|---|---|
| KURE-v3 | `5b0494e801cd5cc21234012df1b83cfdb42b2065` | 2048 | `encode_query` | `encode_document` |
| Snowflake Arctic L v2.0 KO | `55ec6e9358a56d56af759bc8372e970caf8c305f` | 1024 | `query: ` + `encode` | 원문 + `encode` |

KURE-v3의 `encode_query`와 `encode_document`가 각각 모델 카드의 query/passage
prompt를 적용한다. Snowflake KO는 질문에만 `query: `를 붙인다. 저장 vector는 두
모델 모두 L2 정규화된 float32이다.

## GitHub 데이터 확인 결과

2026-11-23 재확인 결과 `origin/main`의 `ab13913`에 `eval_200_v1` 최종본이 추가됐다.
질문 200개, document qrels 207행, fixed/800/120 chunk qrels 240행이며 모든 질문 ID와
정답 문서·청크 연결을 확인했다. 모델 비교 설정은 다음 GitHub 추적 파일을 직접 쓴다.

```text
data/evaluation/eval_200_v1/
  eval_questions.jsonl
  qrels.jsonl
  context_eval_200_v1/required_facts.jsonl
  context_eval_200_v1/fixed_800_ov120_v1/
    qrels_chunk.jsonl
    chunk_fact_map.jsonl

data/processed/ontong_youth_full_v1/chunks/eval_200_v1/fixed_800_ov120_v1/
  chunks.jsonl
  chunk_manifest.json
```

KURE-v1 완료 실행 `exp_full_kure_200_fixed_800_ov120_v2`를 기준으로 삼고,
KURE-v3와 Snowflake는 같은 평가·청크·context gold를 사용한다.

## Windows 10/11 권장 실행

Python 3.11 x64와 Git을 설치한다. PowerShell에서 저장소를 최신화한 뒤 입력을 확인한다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
git pull
.\scripts\prepare_eval200_windows.ps1
```

검증만 먼저 실행한다. 이 단계는 가상환경 생성, 패키지 설치, 전체 테스트,
환경 점검, YAML 검증, dry-run을 수행한다.

```powershell
.\scripts\run_embedding_model_windows.ps1 -Model snowflake
.\scripts\run_embedding_model_windows.ps1 -Model kure-v3
```

모두 통과한 뒤 실제로 인덱스와 검색 평가를 실행한다.

```powershell
.\scripts\run_embedding_model_windows.ps1 -Model snowflake -Run
.\scripts\run_embedding_model_windows.ps1 -Model kure-v3 -Run
```

KURE-v3는 모델과 2048차원 index가 커서 CPU 실행 시간이 Snowflake보다 길고 메모리
요구량도 높다. Windows에서 먼저 Snowflake를 실행해 전체 파이프라인을 확인한 뒤
KURE-v3를 실행하는 순서를 권장한다.

## macOS 검증

YAML은 기존 KURE-v1 실험과 같은 `device: auto`를 사용한다. Intel Mac은 CPU, Apple
Silicon은 설치된 PyTorch가 지원하면 MPS를 선택한다. Python 3.11 가상환경에서 확인한다.

```bash
python3.11 -m venv .venv-embedding
source .venv-embedding/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-experiments.txt
python -m pytest -q tests
python scripts/doctor.py --config configs/experiments/exp_model_snowflake_arctic_l_v2_ko_eval200.yaml
python -m src.experiments.runner \
  --config configs/experiments/exp_model_snowflake_arctic_l_v2_ko_eval200.yaml \
  --validate-only
```

## Index 생성·재사용 규칙

기존 Runner 규칙을 그대로 사용한다.

1. 모델별로 DB 경로·collection·index version을 분리한다.
2. 먼저 임시 collection에 저장하고 record 수와 vector를 검증한 뒤 최종 이름으로 바꾼다.
3. 실패하면 임시 collection만 정리하고 기존 완성 index는 삭제하지 않는다.
4. dataset/chunk SHA256, 청킹, 모델명/revision/dimension/normalize, 거리 척도가 manifest와 모두 같을 때만 재사용한다.
5. 200문항은 index 입력이 아니므로 동일한 모델·청크 index는 재사용할 수 있다. 모델이 달라지면 반드시 별도 index를 만든다.

## 최종 확인 항목

- validate-only에서 질문 수 `200` 확인
- 200개 query ID가 document/chunk qrels에 모두 존재
- Chroma record 수와 chunk manifest 수 일치
- embedding shape: KURE-v3 `(N, 2048)`, Snowflake `(N, 1024)`
- NaN/Inf 및 zero vector 없음
- vector norm 약 1.0
- 두 번째 동일 실행에서 `index_reused: true`
- 결과 폴더와 manifest에 모델 revision, 데이터/청크 SHA256 기록
