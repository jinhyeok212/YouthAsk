# PR #26 리뷰 반영 안내 - 청킹 자동화, 무엇이 바뀌었나

> 대상: 실험 설정(YAML)을 쓰거나 qrels를 검수하는 팀원
> 한 줄 요약: **기존 팀 YAML은 그대로 쓰면 되고, 새 청킹 조건을 실험할 때만 `mode: generate`를 쓴다. 사람이 검수한 정답 파일은 이제 자동화가 절대 덮어쓰지 않는다.**

---

## 1. 왜 고쳤나

PR #26(조건별 청크 자동 생성)을 리뷰해 보니, 실제 팀 설정으로 실행하면 이런 문제가 있었습니다.

| # | 문제 | 쉽게 말하면 |
|---|---|---|
| 1 | 팀 YAML로 실행하면 `KeyError: 'chunk_path'` | 코드가 설정 파일의 엉뚱한 위치에서 경로를 찾았음 |
| 2 | 새로 만든 정답(qrels) 파일을 평가 단계가 안 읽음 | 청킹은 A 폴더에 저장하고, 평가는 B 폴더를 읽음. 옛날 정답으로 채점될 위험 |
| 3 | 다시 실행하면 사람이 검수한 정답이 사라짐 | 실행할 때마다 정답 파일을 새로 만들어 덮어썼음 |
| 4 | `strategy: fixed`를 YAML에 쓰면 거부됨 | 코드는 지원하는데 설정 검사기가 막았음 |
| 5 | 한 번 실패하면 입력을 고쳐도 재실행이 안 됨 | 실패 도중 반쯤 만들어진 파일이 남아 다음 실행을 막았음 |
| 6 | 새 section 청킹이 기존 C2와 같은 이름으로 만들어질 위험 | 섹션 나누는 방식과 청크 ID 형식이 C2와 완전히 다른데 버전 이름이 같았음 |

모두 고쳤고, 테스트로 확인했습니다(아래 6장).

---

## 2. 내가 해야 할 일이 바뀌었나?

### 기존 팀 YAML(`exp_full_kure_v4_team.yaml`)을 쓰는 경우 → **바뀐 것 없음**

- YAML을 고칠 필요가 없습니다.
- 동작은 main과 같습니다. 이미 만들어 둔(검수된) C2 청크와 정답 파일을 **검사만 하고 그대로 사용**합니다. 새로 만들지 않습니다.
- 처음 실행하면 정답 파일 옆에 `qrels_chunk.meta.json`이 하나 생깁니다. 정답 파일이 어떤 청크 기준인지 적어 두는 기록 파일이고, 정답 파일 자체는 건드리지 않습니다.

### 새 청킹 조건(크기, 겹침, 방식)으로 실험하는 경우 → **`mode: generate` 사용**

예시 YAML 두 개를 복사해서 쓰면 됩니다.

- `configs/experiments/exp_chunk_generate_fixed_example.yaml` — 글자 수 기준(fixed)
- `configs/experiments/exp_chunk_generate_section_example.yaml` — 정책 항목 제목 기준(section)

바꿀 곳은 보통 아래 정도입니다.

```yaml
experiment_id: exp_내_실험_이름          # 실험마다 새 이름

chunking:
  version: fixed_500_ov50_v1            # 조건이 바뀌면 버전 이름도 새로
  mode: generate
  strategy: fixed                       # fixed 또는 section
  size: 500
  overlap: 50
  chunk_path: data/processed/ontong_youth_full_v1/chunks/{chunking_version}/chunks.jsonl
  manifest_path: data/processed/ontong_youth_full_v1/chunks/{chunking_version}/chunk_manifest.json

evaluation:
  chunk_qrels_path: data/evaluation/eval_full_v1/chunk_qrels/{chunking_version}/qrels_chunk.jsonl

index:                                  # 청크가 바뀌면 인덱스도 새 이름으로
  version: index_full_kure_v4_fixed_500
  db_path: indexes/chroma/index_full_kure_v4_fixed_500
  collection_name: ontong_youth_full_kure_v4_fixed_500
```

- `{chunking_version}`은 실행할 때 위의 `version` 값으로 자동으로 바뀝니다. 조건마다 폴더가 따로 생겨서 서로 덮어쓰지 않습니다.
- 같은 조건으로 다시 실행하면 청크를 새로 만들지 않고 재사용합니다.

### 이렇게 쓰면 거부됩니다 (의도된 동작)

| 설정 | 이유 |
|---|---|
| `mode: generate` + `version: c2_...` | C2는 사람이 검수한 별도 산출물입니다. 새 생성기로 C2 이름의 청크를 만들면 정답 연결이 깨집니다 |
| `strategy: char`, `c2_section` 같은 별칭 | YAML에는 `fixed`, `section`만 씁니다 |
| 같은 경로에 다른 조건으로 실행 | 기존 청크를 덮어쓰지 않으려고 중단합니다. 새 `version`을 쓰세요 |

---

## 3. 정답(qrels) 파일은 어떻게 관리되나

정답 파일 폴더에는 아래 파일들이 생깁니다.

| 파일 | 누가 만드나 | 설명 |
|---|---|---|
| `qrels_chunk.jsonl` | **사람(검수)** 또는 자동 | 평가에 쓰는 **확정 정답**. 있으면 자동화가 절대 덮어쓰지 않음 |
| `qrels_chunk.candidates.jsonl` | 자동 | 자동으로 찾은 정답 후보 |
| `qrels_chunk_review_required.jsonl` | 자동 | 사람이 확인해야 할 질문 목록과 이유 |
| `qrels_chunk.meta.json` | 자동 | 확정 정답이 어떤 청크 기준인지 기록 |

> 주의: `candidates`와 `review_required` 파일은 실행할 때마다 다시 만들어집니다. **이 두 파일을 직접 고치지 말고**, 검수 결과는 반드시 `qrels_chunk.jsonl`에 저장하세요.

### 자동으로 정답을 못 찾으면?

자동화는 문서 qrels에 **근거(정답이 있는 위치나 문장)** 가 있을 때만 정답 청크를 찾을 수 있습니다. 현재 47문항 qrels에는 근거가 없어서, 새 청킹 조건으로 실행하면 **50행 모두 검수 대상**이 됩니다. 이것은 정상입니다.

이때 실행은 **임베딩·인덱스를 만들기 전에 멈추고**, 이런 메시지를 보여줍니다.

```text
Chunk qrels 검수가 필요합니다. chunk 평가를 진행하지 않고 Index 생성 전에 중단합니다.
- 검수 대상: .../qrels_chunk_review_required.jsonl (50건)
- 자동 매핑 후보: .../qrels_chunk.candidates.jsonl (0건)
- 검수 완료 후 저장 위치: .../qrels_chunk.jsonl
```

시간이 오래 걸리는 임베딩 전에 멈추므로 비용이 낭비되지 않고, 잘못된 정답으로 채점되지도 않습니다.

### 검수 순서

1. `qrels_chunk_review_required.jsonl`에서 확인할 질문을 봅니다.
2. 생성된 `chunks.jsonl`에서 정답 청크를 찾습니다.
3. `qrels_chunk.jsonl`에 한 줄씩 저장합니다.
   ```json
   {"query_id": "q001", "document_id": "policy_001", "chunk_id": "policy_001__sec_01_application_method__chunk_000", "relevance": 1}
   ```
4. 같은 YAML로 다시 실행합니다. 이번에는 검수한 정답으로 평가가 진행되고, 이후 몇 번을 다시 실행해도 파일은 바뀌지 않습니다.

### 청크가 바뀌었는데 예전 정답 파일이 있으면?

예전 청크 기준의 정답으로 채점하지 않도록 **정답 파일을 그대로 둔 채 실행을 멈춥니다.** 새 `version`(새 폴더)으로 실행하거나, 정답을 다시 검수하세요.

---

## 4. 실패했을 때

- 입력 파일(문서 qrels 등)이 잘못돼 실패하면, **파일을 고치고 그대로 다시 실행하면 됩니다.** 반쯤 만든 파일을 손으로 지울 필요가 없습니다.
- 예외: 파일을 저장하는 그 순간에 프로그램이 강제 종료되면(전원 차단 등), `chunks.jsonl`만 남고 `chunk_manifest.json`이 없을 수 있습니다. 이때는 기존 파일 보호를 위해 실행이 막힙니다. 남은 `chunks.jsonl`을 확인한 뒤 지우고 다시 실행하세요.

---

## 5. 바뀐 파일

| 파일 | 내용 |
|---|---|
| `src/chunking/build_chunks.py` | reuse/generate 두 모드로 정리, 임시 파일에 먼저 저장 후 반영 |
| `src/chunking/build_chunk_qrels.py` | 확정 정답 보호, 후보/검수 파일 분리, 메타 기록 |
| `src/chunking/manifest.py` | 설정 경로를 그대로 사용, 경로 자동 변경 제거 |
| `src/chunking/generators.py` | 청크 ID 규칙 이름 추가, section 청크에 `section` 필드 추가 |
| `src/chunking/validate_chunks.py` | 기존 C2처럼 일부 문서만 청크가 있어도 등록 가능 |
| `src/experiments/config_validator.py` | `{chunking_version}` 치환, 잘못된 조합 거부 |
| `src/experiments/runner.py` | 검수 필요 시 인덱스 전에 중단, 경로 일치 확인 |
| `schemas/experiment_v4.schema.json` | `strategy: fixed` 허용, `mode` 추가 |
| `configs/experiments/exp_chunk_generate_*.yaml` | 새 예시 설정 2개 |
| `tests/test_chunk_automation_contract.py` | 리뷰 문제별 회귀 테스트 16개 |
| `tests/test_chunk_validation.py` | 실제 설정 위치(`chunking.*`)를 쓰도록 수정 |
| `docs/chunking/*.md` | 설명 문서 갱신 |

---

## 6. 확인한 것과 아직 확인하지 않은 것

**확인함**
- 전체 테스트 89개 통과(`python -m pytest tests`).
- 새 회귀 테스트는 실제 팀 YAML을 읽어 실행합니다. 수정 전 코드에서는 16개 중 13개가 실패했습니다. 나머지 3개는 원래 코드도 막던 잘못된 strategy 값을 검사하는 테스트입니다.
- 실제 C2 데이터 복사본으로 확인함(원본은 건드리지 않음):
  - 팀 YAML(reuse): 청크 2,875개, 47문항, 정답 50행 검증 통과. 정답 파일 변경 없음.
  - generate 모드 + 47문항 qrels: 검수 대상 50건으로 분류하고 인덱스 전에 중단.
- 팀 YAML과 예시 YAML 2개가 설정 검사(`--validate-only`)를 통과합니다.

**아직 안 함 / 팀 확인 필요**
- 임베딩·Chroma까지 포함한 전체 실행은 하지 않았습니다.
- 팀 YAML이 가리키는 `data/processed/ontong_youth_full_v1/chunks.jsonl`, `data/evaluation/eval_full_v1/`이 저장소에 없어서, 팀 YAML을 그대로 실행하면 "파일 없음"으로 멈춥니다. 이 파일들을 어디에 둘지 팀 확인이 필요합니다. (C2 산출물은 `data/processed/chunking2/05.chunks/c2_section_800/`에 있습니다.)
- 문서 단위로만 평가하는 모드는 이번에 넣지 않았습니다. 검수가 필요하면 실행 전체가 멈춥니다.
