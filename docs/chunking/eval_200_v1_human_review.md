# eval_200_v1 Chunk Qrels 검수와 승인 반영

기준: `configs/experiments/exp_full_kure_200_v1.yaml`, `section_heading_800_ov120_v1`.
상태: 검수 후보 준비 완료, 사용자 승인 0건, 최종 `qrels_chunk.jsonl` 미생성.

## 계약 확인

`src/chunking/build_chunk_qrels.py`와 `docs/chunking/build_chunk_qrels.md`를 확인했다.
Runner의 확정 파일 계약은 query_id/document_id/chunk_id/relevance 행이며, chunking_version을 추가할 수 있다.
기존 자동 매핑은 근거 span 또는 텍스트가 있는 문서 qrels를 청크에 매핑한다. 현재 문서 qrels는 근거가 없어서 Runner 후보 0건, 검수 대상 207건인 상태다.

이 작업은 기존 Runner 후보 및 검수 대상 파일을 입력으로만 읽는다. 그 파일이나 기존 확정본을 덮어쓰지 않는다.
별도 `human_review_v1` 폴더의 CSV는 검수자가 편집하는 파일이며, `candidates.snapshot.jsonl`은 원본 후보 검증용이다.
사용자 승인 전에 Runner의 `approve` 명령을 실행하거나 후보를 최종 경로로 복사하면 안 된다.

## 산출물과 검증 범위

경로: `data/evaluation/eval_200_v1/chunk_qrels/section_heading_800_ov120_v1/human_review_v1/`

| 파일 | 용도 |
| --- | --- |
| `chunk_qrels_review.csv` | 전체 Gold 문서 하위 청크를 포함한 사람이 검수할 CSV; UTF-8 BOM |
| `query_candidate_summary.csv` | 질문별 Gold 문서·추천 chunk_id·검수/제외 건수 및 승인 대기 상태 |
| `review_needed_report.md` | APPROVE 추천이 없는 Gold 연결 53건의 질문·답변·검수 이유·상위 후보 |
| `review_needed_details.json` | 같은 53건의 청크 본문·직접 일치 부분·관련 raw_record 포함 상세 자료 |
| `validation_report.json` | 200문항/207 Gold 연결의 범위 및 구조 검증 결과 |
| `review_manifest.json` | 원본 CSV·질문·문서 qrels·문서·청크·청크 manifest·Runner 후보/검수 대상 및 생성 파일의 SHA256 |
| `candidates.snapshot.jsonl` | 전체 후보의 변경 불가 기준값; 승인 CSV의 ID/본문/추천 변조 검사에 사용 |

- 원본 최종 CSV의 SHA256을 확인하고 질문과 reference_answer 200개 전체를 입력 JSONL과 비교했다. 원본 문서·질문·qrels·청크의 해시도 각 Manifest와 대조했다.
- 원본 청크 25,829개 중 Gold 문서에 속한 후보 **2,548개**, 질문 **200/200개**, Gold 연결 **207/207건**을 포함한다.
- 추천: **APPROVE 155개**, **REVIEW 287개**, **REJECT 2,106개**. 단위는 질문-문서-청크 후보다.
- APPROVE 추천은 질문 153개 / Gold 연결 154건을 포함한다. 하나의 연결에 복수 추천 청크가 있을 수 있다.
- APPROVE 추천이 없는 질문은 **47개**, Gold 연결은 **53건**이다. 후보가 누락된 것이 아니며 모두 검수 자료에 있다.
- 사용자 승인 0건이므로 현재 최종 정답 청크 누락은 질문 **200개**, Gold 연결 **207건**이다. 추천을 승인으로 집계하지 않는다.
- 없는 chunk_id, chunk-document 불일치, 버전 불일치, 중복 후보 매핑은 각각 **0건**이다.

## 추천 판단의 범위와 한계

각 후보에 질문, 원본 reference_answer, Gold 문서의 retrieval_text 전체, 질문/절 관련 raw_record 필드, 실제 chunk_text, 직접 일치 인용, 추천 이유를 넣었다.
APPROVE 추천은 참고답변 전체가 실제 청크와 원본에 문자 그대로 포함될 때만 부여한다. 정책 식별 질문에서는 정책명 접두어가 반복된 모든 하위 청크를 추천하지 않고 title 청크만 대상으로 삼는다.

공백·기호 제거 및 문자 trigram 점수는 후보 검색/정렬에만 사용한다. 정규화만 일치하면 REVIEW다. `exact_excerpt_for_review`는 실제 부분 문자열이지만 완결된 문장이나 충분한 사실이라고 자동 판정한 것이 아니다. REVIEW/REJECT도 사용자가 직접 근거를 확인한 뒤 승인할 수 있다.

이는 보수적인 자동 추천으로, 200개 질문의 의미를 사람이 승인한 결과가 아니다. 질문의 지역·기간·대상·조건·부정·예외·필요 사실을 사람이 확인해야 한다. 특히 복수 청크가 답변을 나누어 지지할 때는 각 청크의 필요한 사실 및 전체 사실의 합집합을 검수한다. 구조 검증만으로 의미상 사실 완전성을 보증하지 않는다.

검수 우선 항목을 직접 원문과 대조해 별도 보고서에도 기록했다.

- `oy_eval_repair_q0077`: 질문은 장애인 신청방법이지만 question_type은 specific_policy_search이다. 기존 질문·답변·승인은 수정하지 않고 실제 질문 의미로 검수한다.
- `oy_eval_v2r_q0015`: 창업 자격의 연령/관내 조건과 사업자등록/단체 대표 조건이 서로 다른 청크에 있다.
- `oy_eval200_new_0030`의 청송 Gold: 참고답변의 인정 주체 `시·군·구청장`과 원문의 `청송군`을 구분해서 검수한다.
- `oy_eval200_new_0070`, `oy_eval200_new_0100`의 인천 시 단위 Gold: 소득·재산·전입 사실은 있으나 생략/문구 차이 및 질문의 구 단위 범위를 확인해야 한다.
- `oy_eval_repair_q0037`의 두 번째 Gold: 원문은 `20만원 상당`을 명시하며 참고답변의 `1인당 연간 최대` 표현을 같은 방식으로 명시하지 않는다.

## CSV 검수 방법

1. `chunk_qrels_review.csv`를 열어 **다른 이름으로 저장**한다. 예: 같은 폴더의 `chunk_qrels_review.user.csv` (CSV UTF-8).
2. query_id 및 document_id로 묶고 recommendation을 검토한다. APPROVE 추천부터 확인하되, 53개 미추천 연결과 복수 Gold를 빠뜨리지 않는다.
3. 아래 네 컬럼만 입력한다. 나머지 컬럼이나 행을 삭제·변경하지 않는다. 정렬 순서는 변경할 수 있다.

| 사용자 컬럼 | 입력 |
| --- | --- |
| `human_decision` | `APPROVE`, `REVIEW`, `REJECT` 또는 빈칸 |
| `reviewer` | APPROVE한 사람의 이름/식별자 |
| `human_evidence_quote` | 실제 chunk_text와 원문에 모두 존재하는 근거를 그대로 인용 (최소 8자) |
| `human_note` | 해당 근거가 질문의 어느 사실·조건을 충족하는지 검수 의견 |

`exact_excerpt_for_review`를 기계적으로 승인란에 일괄 복사하지 않는다. 필요한 사실이 완전히 지지되는지 먼저 확인한다. 원문이나 청크에 없는 인용문·위치를 새로 만들지 않는다. 여러 필요한 사실을 각각 다른 청크가 지지하면 여러 행을 승인하고 의견에 지지 범위를 쓴다.

REJECT는 청크 후보에 대한 추천이며 문서 Gold 또는 원본 질문을 폐기한다는 의미가 아니다. 의미상 정답 청크가 없는 Gold 연결은 REVIEW로 남긴다. 현재 승인 생성기는 부분 승인을 전체 평가 정답으로 사용하지 못하도록 완전한 200/207 연결을 요구한다.

## 승인 후 생성

가상환경을 활성화한 프로젝트 루트에서 실행한다. 이 명령은 사용자가 편집한 승인 CSV를 읽어 사용자 `APPROVE` 행만 반영한다. recommendation 컬럼을 APPROVE로 바꾸는 것은 승인이 아니며 원본 후보 변조로 거부된다.

```powershell
python scripts/review_chunk_qrels_200.py export-approved `
  --review-dir data/evaluation/eval_200_v1/chunk_qrels/section_heading_800_ov120_v1/human_review_v1 `
  --review-csv data/evaluation/eval_200_v1/chunk_qrels/section_heading_800_ov120_v1/human_review_v1/chunk_qrels_review.user.csv
```

출력은 설정의 `evaluation.chunk_qrels_path`인 `qrels_chunk.jsonl`과 별도 `qrels_chunk.human_approval.json` 감사 기록이다. 사용자 승인이 없거나 질문/Gold 연결이 누락되면 파일을 생성하지 않는다. 기존 출력 또는 승인 기록이 있으면 덮어쓰지 않고 실패한다.

생성 전 검증:

- 검수 당시 모든 입력 SHA256과 현재 파일 비교; 입력이 달라졌으면 새 검수 필요.
- 후보 원본 스냅샷 및 CSV의 ID/본문/추천 등 변경 불가 컬럼 대조.
- 사용자 승인 상태, 검수자, 검수 의견 및 실제 청크/원문에 존재하는 인용문 확인.
- 모든 query_id 및 Gold 연결 커버리지, 실제 chunk_id, 청크-문서 연결, chunking.version, 중복 매핑 및 relevance 검사.
- relevance=1은 사용자가 명시적으로 승인한 출력 행에만 부여.

구조 재검증:

```powershell
python scripts/review_chunk_qrels_200.py validate-final `
  --qrels data/evaluation/eval_200_v1/chunk_qrels/section_heading_800_ov120_v1/qrels_chunk.jsonl
```

`validate-final`은 구조 및 범위를 검사한다. 사용자 승인 이력은 export-approved가 생성한 감사 기록으로 별도 추적한다. 이후 사용자가 실험을 재개하면 Runner가 기존 계약대로 확정본을 검증하고 meta를 만든다. 이번 준비 작업은 Runner를 재실행하지 않았으며 임베딩/Index/검색 평가도 수행하지 않았다.

## 검수 자료 재생성

원본이 달라져 다시 만들 때는 새 디렉터리를 사용한다. 기존 파일을 덮어쓰는 옵션은 없다.

```powershell
python scripts/review_chunk_qrels_200.py prepare `
  --output-dir data/evaluation/eval_200_v1/chunk_qrels/section_heading_800_ov120_v1/human_review_v2
```

## 테스트

```powershell
python -m pytest tests -q
```

새 테스트는 정규화 단독 승인 금지, 정책명 접두어만 있는 하위 청크 제외, 사용자 승인만 반영, 무승인/불완전 승인 거부, 근거 인용·검수자·의견 필수, 입력 변경 및 후보 변조 거부, 잘못된 연결/버전/중복/relevance 거부, 최종 파일 덮어쓰기 차단을 검사한다.

실행 결과: 전체 **158개 통과** (기존 141개 + 새 17개). 실제 원본 검수 CSV의 무승인 상태로 export-approved를 호출해 승인 누락 200문항/207 Gold 연결로 실패하고 최종 파일이 생성되지 않음을 확인했다. 새 자료를 독립 경로에 재생성해 모든 검수 산출물의 바이트 일치를 확인했다. 기존 평가 입력·Runner 후보/검수 파일·청크·청크 Manifest·설정 등 작업 전 보호 대상 9개 파일의 SHA256은 모두 보존했다.
