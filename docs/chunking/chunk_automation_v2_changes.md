# 청킹 자동화 변경 보고서

## 1. 변경 목적

기존 청킹 자동화 코드는 현재 범위에서는 정상 동작했다. 다만 팀의 최종 목표는 단순히 준비된 청크를 검증하는 것이 아니라, 다음 조건을 바꿔가며 실험하는 것이다.

```text
chunk size
overlap
chunking strategy
embedding model
retrieval 조건
```

따라서 청킹 조건이 바뀌면 해당 조건으로 청크를 새로 생성하거나, 동일 조건의 기존 청크를 안전하게 재사용할 수 있어야 한다.

이번 변경은 기존 구현을 다음 목표에 맞게 확장한 것이다.

```text
YAML 청킹 조건
-> 조건별 청크 생성 또는 재사용
-> Manifest signature 검증
-> 조건별 qrels_chunk 준비 또는 검수 필요 표시
-> 임베딩/인덱싱 단계로 전달
```

## 1.1 이전 구현과 비교한 핵심 변경 요약

```text
1. 청킹 조건별 생성

이전:
준비된 청크를 검증하거나 단순 청킹을 수행하는 수준이었다.

변경:
YAML의 strategy, size, overlap, target_field를 읽어
해당 조건에 맞는 청크를 생성할 수 있게 했다.
```

```text
2. 조건별 결과 분리

이전:
하나의 chunks.jsonl 경로를 그대로 사용할 수 있어
조건이 다른 청크가 기존 결과를 덮어쓸 위험이 있었다.

변경:
fixed_500_ov50_v1, section_800_ov120_v1처럼
청킹 조건별로 다른 경로에 저장하고 기존 청크를 덮어쓰지 않게 했다.
```

```text
3. Manifest signature 검증

이전:
청크 재사용 여부를 데이터 버전, 전처리 버전, 데이터 해시,
청킹 조건까지 포함해 엄격하게 판단하지 못했다.

변경:
데이터 버전, 전처리 버전, 데이터 해시, 청킹 버전,
strategy, size, overlap, unit, target_field가 모두 같을 때만
기존 청크를 재사용하도록 했다.
```

```text
4. qrels 안전 처리

이전:
정답 문서에 속한 모든 chunk를 정답 chunk로 처리할 수 있었다.

변경:
정답 문서의 모든 chunk를 무조건 정답 처리하지 않고,
근거 span/text가 있는 경우만 qrels_chunk로 확정한다.
근거가 없으면 qrels_chunk_review_required.jsonl로 분리해
검수 필요 상태로 남긴다.
```

## 2. 이전 구현의 범위

이전 구현은 다음 역할에 가까웠다.

```text
documents.jsonl을 읽음
단순 chunk 생성
chunks.jsonl 저장
문서 qrels를 chunk qrels로 변환
기본 검증 수행
```

초기 구현은 청킹 모듈 단독 테스트에는 충분했지만, 조건별 비교 실험 관점에서는 부족한 점이 있었다.

부족했던 점:

```text
1. 기존 청크 생성 전략을 명확히 재사용하지 않음
2. strategy, target_field, preprocessing_version 등을 signature로 관리하지 않음
3. 조건이 다른 청크를 별도 경로로 강제 분리하지 않음
4. 동일 입력·동일 조건 재실행 시 재사용 판단이 약함
5. 문서 정답의 모든 chunk를 정답으로 보는 방식이 가능했음
6. 근거가 없는 qrels를 검수 필요로 분리하지 않음
```

## 3. 변경 후 전체 흐름

변경 후 `build_chunks(config, dataset_info)`의 흐름은 다음과 같다.

```text
1. YAML에서 chunking 조건을 읽는다.
2. _chunk_signature 규칙에 맞춰 현재 조건의 signature를 만든다.
3. 조건별 chunk_path와 manifest_path를 결정한다.
4. 기존 Manifest와 chunk가 현재 signature와 일치하면 재사용한다.
5. 기존 결과가 없으면 YAML 조건으로 청크를 새로 생성한다.
6. chunks.jsonl을 검증한다.
7. qrels를 chunk에 연결할 수 있는지 확인한다.
8. 근거가 있는 qrels만 qrels_chunk.jsonl로 확정한다.
9. 근거가 불확실한 qrels는 qrels_chunk_review_required.jsonl로 분리한다.
10. chunk_manifest.json을 저장한다.
11. Runner에 ChunkInfo를 반환한다.
```

## 4. 변경 파일

### 수정된 파일

```text
src/chunking/build_chunks.py
src/chunking/build_chunk_qrels.py
src/chunking/validate_chunks.py
tests/test_chunk_validation.py
```

### 추가된 파일

```text
src/chunking/generators.py
src/chunking/manifest.py
docs/chunking/chunk_automation_v2_changes.md
```

## 5. 파일별 변경 내용

## 5.1 build_chunks.py

### 이전

초기 버전의 `build_chunks.py`는 청크를 만들고 검증한 뒤 qrels를 생성하는 단순 흐름이었다.

```text
documents.jsonl
-> chunks.jsonl
-> qrels_chunk.jsonl
```

### 변경 후

현재는 Runner의 청킹 준비 단계 역할을 한다.

주요 변경:

```text
YAML의 strategy, size, overlap, unit, target_field를 읽음
조건별 chunk_path를 자동 분리
signature가 같으면 기존 청크 재사용
signature가 다르면 덮어쓰지 않고 중단
Manifest에 chunk_sha256, dataset_sha256, generator 정보를 기록
qrels_chunk_status와 review_required_path를 반환
```

반환값에는 기존 필수 필드를 유지하면서 추가 정보를 붙였다.

```python
{
    "chunk_path": "...",
    "manifest_path": "...",
    "chunk_count": 1234,
    "chunk_qrels_path": "...",
    "chunk_qrels_status": "ready 또는 review_required",
    "chunk_qrels_review_required_path": "...",
    "chunk_sha256": "...",
    "dataset_sha256": "..."
}
```

이전 Runner 계약의 필수 필드는 유지했다.

```text
chunk_path
manifest_path
chunk_count
chunk_qrels_path
```

## 5.2 generators.py

새로 추가된 파일이다.

역할:

```text
실제 청크 생성 전략을 담당한다.
```

현재 지원하는 전략:

```text
fixed
section
```

`fixed` 전략:

```text
target_field의 텍스트를 size 단위로 자른다.
overlap만큼 앞뒤 chunk가 겹친다.
size는 최종 chunk text 길이 제한을 의미한다.
```

`section` 전략:

```text
정책명, 지원 내용, 신청 방법 같은 section을 먼저 찾는다.
각 section body를 size 기준으로 나눈다.
필요하면 제목 prefix를 붙인다.
size는 최종 text 전체 길이가 아니라 section body 분할 기준이다.
```

이 차이는 Manifest의 `generator.size_meaning`에 기록된다.

## 5.3 manifest.py

새로 추가된 파일이다.

역할:

```text
청킹 조건 signature 생성
조건별 출력 경로 결정
기존 청크 재사용 가능 여부 판단
chunk_sha256 계산
Manifest 생성
```

현재 signature는 다음 값을 기준으로 한다.

```text
dataset_version
preprocessing_version
dataset_sha256
chunking_version
strategy
size
overlap
unit
target_field
```

이 값이 모두 일치할 때만 기존 청크를 재사용한다.

## 5.4 validate_chunks.py

### 이전

기본적으로 다음을 검증했다.

```text
빈 chunk
중복 chunk_id
잘못된 document_id
char_length 불일치
```

### 변경 후

추가로 다음을 확인한다.

```text
document_id별 chunk_index 순서
fixed 전략에서 chunk_size 초과 여부
section 전략에서는 title prefix 때문에 최종 text가 size를 넘을 수 있음을 허용
```

즉, 청킹 전략에 따라 size의 의미가 다르다는 점을 검증에 반영했다.

## 5.5 build_chunk_qrels.py

### 이전

문서 qrels를 chunk qrels로 바꿀 때 정답 문서에 속한 모든 chunk를 정답 후보로 볼 수 있었다.

예:

```text
정답 문서: policy_001
정답 chunk: policy_001의 모든 chunk
```

이 방식은 검색 평가를 느슨하게 만들 수 있다.

### 변경 후

이제 근거가 있는 qrels만 chunk qrels로 확정한다.

지원하는 자동 연결 방식:

```text
1. qrels에 chunk_id가 이미 있는 경우
2. evidence_start_char / evidence_end_char 같은 근거 span이 있는 경우
3. evidence_text / answer_text 같은 근거 텍스트가 있는 경우
```

근거가 없는 경우에는 chunk qrels를 임의로 만들지 않는다.

대신 다음 파일에 검수 필요 상태로 기록한다.

```text
qrels_chunk_review_required.jsonl
```

즉, 변경 후 정책은 다음과 같다.

```text
정답 문서의 모든 chunk를 정답으로 처리하지 않는다.
근거 없이 qrels_chunk를 만들지 않는다.
자동 연결이 불확실하면 review_required로 분리한다.
```

## 6. 조건별 출력 경로

이전에는 설정상 하나의 `chunks.jsonl` 경로를 그대로 사용할 수 있었다.

변경 후에는 chunking version별로 경로를 분리한다.

예:

```text
data/processed/ontong_youth_full_v1/chunks/fixed_500_ov50_v1/chunks.jsonl
data/processed/ontong_youth_full_v1/chunks/c2_section_800_ov120_v1/chunks.jsonl
```

qrels도 조건별로 분리한다.

```text
data/evaluation/eval_full_v1/chunk_qrels/fixed_500_ov50_v1/qrels_chunk.jsonl
data/evaluation/eval_full_v1/chunk_qrels/c2_section_800_ov120_v1/qrels_chunk.jsonl
```

이렇게 해야 서로 다른 조건의 청크와 평가 정답이 서로 덮어쓰이지 않는다.

## 7. fixed와 section 청킹 방식

이번 변경에서 청킹 방식은 크게 `fixed`와 `section`으로 나뉜다.

둘 중 하나가 항상 정답이라는 뜻은 아니다. 같은 데이터, 같은 평가 질문, 같은 embedding/search 조건에서 두 방식을 비교한 뒤 더 좋은 결과를 이후 실험의 기준으로 채택하기 위해 둘 다 지원한다.

## 7.1 fixed 청킹

`fixed`는 문서 본문을 단순히 글자 수 기준으로 자르는 방식이다.

예를 들어 다음 설정이면:

```yaml
chunking:
  strategy: fixed
  size: 500
  overlap: 50
  target_field: retrieval_text
```

`retrieval_text`를 500자 단위로 자르고, 앞뒤 청크는 50자씩 겹치게 만든다.

예시:

```text
chunk_000: 0~500자
chunk_001: 450~950자
chunk_002: 900~1400자
```

장점:

```text
구현이 단순하다.
항상 일정한 규칙으로 잘리기 때문에 재현성이 좋다.
문서 구조가 없어도 모든 문서에 적용할 수 있다.
청크 길이가 비교적 일정해서 embedding 비용과 검색 조건을 예측하기 쉽다.
```

단점:

```text
문장이나 항목 중간에서 끊길 수 있다.
신청 방법, 지원 내용, 제출 서류 같은 의미 단위가 나뉠 수 있다.
정책 문서의 구조 정보를 활용하지 못한다.
```

fixed 방식은 다음과 같은 상황에서 유리할 수 있다.

```text
문서 구조가 일정하지 않거나 section label이 잘 잡히지 않는 경우
간단한 baseline이 필요한 경우
청크 길이를 엄격하게 통제하고 싶은 경우
```

## 7.2 section 청킹

`section`은 문서를 먼저 의미 있는 구역으로 나누고, 각 구역이 너무 길 때만 다시 자르는 방식이다.

예를 들어 정책 문서에 다음과 같은 구역이 있다고 하자.

```text
정책명
정책 요약
지원 내용
참여 대상
신청 방법
제출 서류
```

`section` 방식은 이 구역들을 먼저 찾는다. 그리고 각 구역의 본문이 `size`보다 길면 그때만 overlap을 적용해 나눈다.

예:

```text
policy_001__sec_00_title__chunk_000
policy_001__sec_01_summary__chunk_000
policy_001__sec_02_support__chunk_000
policy_001__sec_03_application_method__chunk_000
```

중요한 점은 `section`에서의 `size` 의미다.

```text
fixed의 size:
최종 chunk text 전체 길이 제한

section의 size:
section body를 나누는 기준
```

section 방식에서는 제목 prefix가 붙을 수 있다.

예:

```text
정책명: 청년 월세 지원

신청 방법: 온라인 신청만 가능합니다.
```

그래서 section 방식의 최종 chunk text 길이는 `size`보다 조금 길어질 수 있다. 이 차이는 Manifest의 `generator.size_meaning`에 기록된다.

장점:

```text
정책 문서의 의미 구조를 유지할 수 있다.
신청 방법, 지원 내용, 제출 서류 같은 질문에 맞는 구역이 검색될 가능성이 높다.
청크가 의미 단위로 나뉘므로 검색 결과를 사람이 해석하기 쉽다.
```

단점:

```text
문서의 section label이 일정하지 않으면 잘 나누기 어렵다.
fixed보다 구현과 검증이 복잡하다.
section prefix 때문에 최종 chunk 길이가 일정하지 않을 수 있다.
```

section 방식은 다음과 같은 상황에서 유리할 수 있다.

```text
정책 문서가 일정한 항목 구조를 가지고 있는 경우
질문이 신청 방법, 지원 내용, 자격 조건처럼 특정 구역을 묻는 경우
검색 결과의 설명 가능성을 높이고 싶은 경우
```

## 7.3 왜 둘 다 지원하는가

청킹 방식은 검색 성능에 직접 영향을 준다.

너무 단순하게 자르면 의미가 끊길 수 있고, 너무 구조적으로 자르면 문서마다 구조 차이에 영향을 받을 수 있다.

그래서 현재 목표는 하나를 미리 정답으로 고르는 것이 아니라, 같은 조건에서 비교하는 것이다.

비교할 때 고정하는 조건:

```text
같은 documents.jsonl
같은 eval_questions.jsonl
같은 document qrels
같은 embedding model
같은 retrieval top-k
```

바꾸는 조건:

```text
chunking.strategy
chunking.size
chunking.overlap
```

비교 지표:

```text
document Hit@1/3/5
chunk Hit@1/3/5
document MRR
chunk MRR
검색 지연시간
실패 질문 유형
```

결론적으로:

```text
fixed와 section을 둘 다 실행해보고,
평가 지표와 실패 사례를 비교한 뒤,
더 안정적인 방식을 이후 실험의 기준으로 채택한다.
```

다만 chunk qrels가 준비되지 않은 조건은 chunk-level 평가를 바로 할 수 없다. 이 경우 document-level 평가는 가능하지만, chunk-level 평가는 `qrels_chunk_review_required.jsonl` 검수 후 진행해야 한다.

## 8. 왜 이제 조건별 실험이 가능해졌는가

이번 변경으로 가능해진 것:

```text
YAML의 strategy를 바꾸면 다른 방식으로 청크 생성
YAML의 size를 바꾸면 다른 크기로 청크 생성
YAML의 overlap을 바꾸면 다른 overlap으로 청크 생성
YAML의 target_field를 바꾸면 다른 본문 필드를 기준으로 청크 생성
동일 조건 재실행 시 기존 청크 재사용
다른 조건은 별도 경로에 저장
Manifest signature로 재사용 가능 여부 판단
근거 없는 qrels는 임의 생성하지 않고 검수 필요로 분리
```

즉 이전에는:

```text
준비된 청크를 검증하는 자동화
```

였다면, 이제는:

```text
조건별 청크 생성·재사용·검증을 수행하는 자동화
```

가 되었다.

## 9. 테스트 변경

`tests/test_chunk_validation.py`는 다음을 검증한다.

```text
조건별 경로에 chunks.jsonl과 Manifest가 생성되는지
동일 입력·동일 조건 재실행 시 chunk_id와 text가 동일한지
서로 다른 조건 2개가 별도 경로에 생성되는지
중복 chunk_id를 검출하는지
근거가 있는 qrels만 qrels_chunk로 생성되는지
근거가 없는 qrels는 review_required로 분리되는지
```

실행 명령:

```powershell
py -m unittest tests.test_chunk_validation -v
```

현재 결과:

```text
Ran 5 tests
OK
```

## 10. 실행 명령

문법 검사:

```powershell
py -m compileall src/chunking tests/test_chunk_validation.py
```

단위 테스트:

```powershell
py -m unittest tests.test_chunk_validation -v
```

Runner 연결 후 예상 실행:

```powershell
py -m src.experiments.runner --config configs/experiments/exp_full_kure_v1.yaml
```

단, 실제 인덱싱·검색·평가까지 완료하려면 평가/러너/인덱스 담당 모듈과 qrels 정책이 함께 맞아야 한다.

## 11. 추가 합의가 필요한 부분

청킹 담당 코드에서 검수 필요 상태를 표시할 수 있게 되었지만, Runner와 Evaluation 쪽에서 이 상태를 어떻게 처리할지는 팀 합의가 필요하다.

합의 필요:

```text
chunk_qrels_status가 review_required일 때 Runner를 중단할지
document-level 평가만 허용할지
chunk-level 평가는 qrels ready 조건에서만 실행할지
qrels_chunk_review_required.jsonl을 누가 검수할지
검수 완료 qrels를 어떤 형식으로 저장할지
```

현재 청킹 모듈은 qrels를 임의 생성하지 않고 상태를 명확히 분리하는 쪽으로 구현했다.

## 12. 최종 요약

이번 변경의 핵심은 다음이다.

```text
기존: 준비된 청크 검증 중심
변경: YAML 조건 기반 청크 생성·재사용 중심
```

그리고 qrels 정책은 다음으로 바뀌었다.

```text
기존: 정답 문서의 모든 chunk를 정답 후보로 처리 가능
변경: 근거가 있는 chunk만 정답으로 확정, 불확실하면 검수 필요
```

이 변경으로 청크 크기, overlap, 청킹 방식이 바뀌어도 조건별로 청크를 생성하고, 기존 결과를 덮어쓰지 않으면서 실험 비교를 진행할 수 있게 되었다.

