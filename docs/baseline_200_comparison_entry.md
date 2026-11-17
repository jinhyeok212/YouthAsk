# B01 Baseline 공용 비교표 기입안

후속 실행 안내: 이 문서는 최초 Baseline 실행 당시의 기록이다. Context를 활성화한 새 실행은 완료됐으며, 추가할 행은 [context_eval_200_v1_comparison_entry.md](context_eval_200_v1_comparison_entry.md)를 참고한다. 최초 실행의 Context 미평가 기록은 그대로 보존한다.

근거: `experiments/exp_full_kure_200_v1/`의 완료 산출물 및 질문별 결과 200행 대조.
계획 주차는 제외한다. 아래 `실행 ID`는 모두 **exp_full_kure_200_v1**이다.
`B01-20261117-R1`은 필요할 경우 사람이 읽는 별칭으로만 사용하고 실제 파일 ID를 바꾸지 않는다.

## 1. 진혁: 실험 계획·실행 목록

| 계획 ID | 실제 실행 ID | 모델 | 청킹 방식/크기/겹침 | 반복 번호 | 실행 상태 | 설정·입력·결과 링크 |
| --- | --- | --- | --- | --- | --- | --- |
| B01 | exp_full_kure_200_v1 | nlpai-lab/KURE-v1 | section / 본문800자 / overlap120자 | 1 (첫 정상 완료) | 완료 — SUCCESS | 아래 실행 자료 묶음 연결 |

실제 정상 실행 시작: 2026-11-17 18:33:36 KST. 결과 Manifest 생성: 18:38:42 KST.
이전 같은 ID의 입력 검증 실패 로그는 보존되어 있다. 이를 정상 반복 실행으로 세지 않는다.

### 설정·입력·결과 링크에 붙일 실행 자료 묶음

- 실행 설정 사본: `experiments/exp_full_kure_200_v1/experiment_config.yaml`
- 실행 요약/상태/코드/입력 연결: `experiments/exp_full_kure_200_v1/experiment_manifest.json`
- 실행 환경: `experiments/exp_full_kure_200_v1/environment.json`
- 결과 폴더: `experiments/exp_full_kure_200_v1/`
- 데이터: `ontong_youth_full_v1`, 전처리 `prep_v1`, 문서 2,728개
- 평가셋: `eval_200_v1`, 질문 200개, Document Gold 207연결, Chunk Gold 211매핑
- 청킹 버전: `section_heading_800_ov120_v1`, 청크 25,829개
- 청킹 원본 필드: `retrieval_text`; 실제 임베딩 청크 필드: `text`
- 모델 revision: `8b418a58414668e75532ed045c22d9ca018ae2b2`
- 임베딩: 1,024차원 / normalize=true / batch_size=32
- 검색: Chroma / cosine / evaluation_max_k=5 / ks=[1,3,5]
- `context_top_k=3`은 이번 검색평가의 검색 수를 줄이지 않는다. 답변 생성은 실행하지 않았다.
- 실행 Manifest의 git_commit: `7897b1bbd22c2c23eb7ff196e8a5730d6338250b`
- 실제 코드 기준은 계획서의 `acc959fc`와 다르므로 위 실제 커밋을 기록한다. 신규 설정·입력·스크립트 중 Git 미추적 파일이 있어 커밋 해시만으로 이번 실행을 복원할 수 없다. 공유 시 사용 파일도 커밋/별도 보존해야 한다.

| 입력 | 버전/경로 | SHA256 |
| --- | --- | --- |
| 문서 | data/processed/ontong_youth_full_v1/documents.jsonl | 99ac3eba5a1f79ad62842a5aff973cb69dd236d8dac63974ef87c70f8240e044 |
| 질문 | data/evaluation/eval_200_v1/eval_questions.jsonl | 4715106dd98d9541df9adfcf492a1f5177796700809f1ebe68eb2eeb10660a4f |
| Document qrels | data/evaluation/eval_200_v1/qrels.jsonl | 7bbbeb3cfbb0e322ec7253a5fb80d4b7ee1c3fcd5f56ee2a7db6da5fe018f117 |
| 청크 | data/processed/ontong_youth_full_v1/chunks/eval_200_v1/section_heading_800_ov120_v1/chunks.jsonl | f63102c3774ceb8130949bfd2f7ad27a46e6fd792de532410e84007d298d689e |
| Chunk qrels | data/evaluation/eval_200_v1/chunk_qrels/section_heading_800_ov120_v1/qrels_chunk.jsonl | 1c90b9bdb74791ed1b366b5f87efe8b366aa29f0c6f6e7322e176e4c0eaf7522 |

데이터 Manifest는 `data/evaluation/eval_200_v1/dataset_manifest.json`, 평가 출처 Manifest는 같은 폴더의 `evaluation_manifest.json`을 연결한다. Windows CRLF 파일 기준 SHA256을 사용했으며 기존 LF 기준 Dataset Manifest는 보존했다.

## 2. 진혁: 비교 가능 여부

Baseline 자체는 후보와의 비교가 아직 없으므로 비교 가능성을 확정하지 않는다.

| 비교 그룹 | 기준 실제 실행 ID | 후보 실제 실행 ID | 변경 변수 | 품질 비교 가능 여부 | 시간 비교 가능 여부 | 조건 차이·제약 |
| --- | --- | --- | --- | --- | --- | --- |
| chunk-v1 | exp_full_kure_200_v1 | — | 청킹 방식/크기/겹침 (각 후보별 별도 행) | 미확인 — 후보 실행 후 판단 | 미확인 — 후보 실행 후 판단 | B01은 문서/청크 Hit·MRR만 산출. Context 미평가. 별도 워밍업 없는 정상 실행1회 |

model-v1/combo-v1/answer-v1의 기준은 해당 단계의 선택 청킹/조합이 확정된 뒤 연결한다. 현재 B01을 모든 그룹의 확정 기준으로 미리 채우지 않는다.

## 3. 예지: 검색 품질 기입값

### 3-1. 문서 검색 품질

| 실제 실행 ID | 평가셋 버전 | N | Hit@1 | Hit@3 | Hit@5 | Hit@5 성공 수/N | MRR@5 | 질문별 실행 오류 수 | 결과·실패 사례 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | eval_200_v1 | 200 | 0.900 | 0.955 | 0.960 | 192/200 | 0.925417 | 0 | metrics_summary.json / metrics_by_query.jsonl / failure_cases.csv |

### 3-2. 청크 검색 품질

| 실제 실행 ID | 청크 qrels 버전 | N | Hit@1 | Hit@3 | Hit@5 | Hit@5 성공 수/N | MRR@5 | 결과·실패 사례 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | eval_200_v1 / section_heading_800_ov120_v1 / 위 Chunk qrels SHA256 | 200 | 0.690 | 0.820 | 0.885 | 177/200 | 0.763667 | metrics_summary.json / metrics_by_query.jsonl / failure_cases.csv |

지표 파일은 위 결과 폴더에 있다. 질문별 결과를 대조해 문서 Hit@1/3/5는180/191/192, 청크는138/164/177임을 확인했다. 모든 질문은 고유하며 Top-5 결과가 각각5개 있다.

실패 분류: 문서 Top-5 누락8건, 문서는 찾았지만 정답 청크 Top-5 누락15건, 정답 청크가4~5위인 진단 사례13건. failure_cases.csv의 총36행은 실행 오류36건이 아니다. 실제 질문별 실행 오류는0이다.

### 3-3. 검색 근거 품질

| 실제 실행 ID | Context Precision@5 | Precision 평가 질문 수/N | Context Recall@5 | Recall 평가 질문 수/N | 평가 버전·검수 입력 | 미평가 사유 |
| --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 미평가 | 0/200 | 미평가 | 0/200 | 이번 실행에서 Context 평가 버전 미지정 | context_metrics.enabled=false. eval_200_v1의 required_facts 및 fact–chunk 매핑 미준비 |

Chunk Hit@5=0.885를 Context Recall 값으로 옮기면 안 된다. 계획서는 Baseline부터 Context 평가를 요구하지만 실제 실행은 해당 항목이 빠져 있다. 종선·상준·예지가 필수 사실/사실–청크 연결과 관련 청크 검수 범위를 준비하고, 진혁이 별도 재평가 설정·결과 연결을 관리해야 한다. 저장된 retrieval_results.jsonl의 순위/청크 ID로 재평가할 수 있으므로 검색을 다시 해야만 하는 것은 아니다. 원본 결과를 덮어쓰지 말고 원본 검색 실행 ID에 재평가 버전·결과를 추가 연결한다.

## 4. 찬진·현수: 실행 효율 기입값

### 4-1. 인덱스 생성·용량

| 실제 실행 ID | 청크 수 | 인덱스 레코드 수 | 인덱스 생성 시간(초) | 인덱스 용량(MiB) | 인덱스 재사용 | 최초 생성 실행 ID | 측정 정보 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 25,829 | 25,829 | 249.3048 | 332.3969 | 아니오 | exp_full_kure_200_v1 | index_manifest.json; 용량은 실행 후 현재 DB디렉터리 측정 |

용량 측정 범위: `indexes/chroma/index_full_kure_200_v1/` 전체7개 파일, 348,543,419bytes÷1,048,576. 결과 폴더 전체 용량이나 공용 Chroma DB 용량이 아니다. 실행 후 측정값이며 원래 실행 산출물에 저장된 값은 아니다.

249.3048초의 코드상 측정 범위는 모델 로딩 이후 문서 임베딩·DB적재·개수검증·Collection이름확정까지다. 모델 다운로드/로딩이나 전체 Runner 실행 시간을 포함하지 않는다. 청크는 기존 파일을 재사용했지만 Index는 새로 생성했다.

### 4-2. 검색 시간

| 실제 실행 ID | 측정 질문 수 | 워밍업 조건 | 검색 평균(ms) | 검색 p95(ms) | 검색 최대(ms) | device·장비 | 환경·질문별 시간 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| exp_full_kure_200_v1 | 200 | 별도 워밍업 단계 없음 — 잠정값 | 23.5478 | 30.1256 | 60.4364 | auto→CUDA (코드·기록 기준), NVIDIA GeForce RTX4060 | environment.json / metrics_by_query.jsonl |

측정 범위는 질문 임베딩+DB검색 응답까지이며 평가/파일저장은 제외한다. p95는 사전 기준인 ceil(0.95×200)=190번째 값과 일치한다. 장비 기록은 Python3.12.10, Windows10, torch2.11.0+cu128, chromadb1.5.9, sentence-transformers6.1.0이다.

별도 워밍업 및 반복3회 기준을 아직 충족하지 않으므로 이 값으로 모델 간 속도 우열을 확정하지 않는다. 최대토큰길이/실제잘림통계는 이번 결과파일에 없어 미기록으로 적고, 찬진이 향후 실행에서 보강한다.

## 5~9. 지금 적을 것과 남겨 둘 것

- 5 반복 요약: 정상 반복 수1, 연결 ID는현재ID. 대표값은 확정하지 않고 추가 반복 대기. 인덱스 재사용·품질일관성도 아직 재실행 확인 전이다.
- 6 개선·악화: 비교 후보 결과가 없으므로 아직 작성할 비교 행이 없다. 현재 실패 사례를 후보 비교의 출발점으로 보존한다.
- 7 답변: 생성하지 않았으므로 미평가. context_top_k=3은 답변을 생성해3개를 전달했다는 기록이 아니다.
- 8-1 Baseline 성능 행: 위 문서/청크 Hit@5·MRR@5만 옮긴다. Context/대표p95/답변점수는 각각 미평가/대표값미확정/미평가로 표시한다.
- 8-2 진혁의 후보 판정: 후보가 없으므로 미판정. Baseline 실행완료를 최종설정 채택으로 적지 않는다.
- 9 진혁의 최종선택설정: 비교 및 답변평가 후 작성한다. 현재는 ‘미확정—Baseline 완료’로 둘 수 있다.

## 팀원별 무엇을 보고 작성하는가

공통 결과 폴더: `experiments/exp_full_kure_200_v1/`.

| 담당 | 작성/확인할 표 | 먼저 볼 파일 | 확인할 내용 |
| --- | --- | --- | --- |
| 진혁 | 1·2, 7의 설정취합, 8-2·9 | experiment_manifest.json / experiment_config.yaml / resolved_config.json / run.log | 실제ID·상태·날짜·모델revision·입력경로·코드버전. 현재는1/2를기입하고 최종판정은보류 |
| 종선 | 입력 검증, 3의 질문/정답 확인 | data/evaluation/eval_200_v1/evaluation_manifest.json / dataset_manifest.json / eval_questions.jsonl / qrels.jsonl | 질문200·문서2728·Gold207·유일ID·해시·0053참고답변 불일치. Context용 required_facts 정의 |
| 상준 | 청크/qrels, 3-2 입력, 4-1 청크수 | 청크폴더 chunks.jsonl / chunk_manifest.json; 평가폴더 qrels_chunk.jsonl / qrels_chunk.meta.json / delegated_review_v1/ | 청크25829·Gold211매핑·버전/문서연결·검수근거. 조건변경시 같은필수사실에 대한 새청크매핑 검수 |
| 찬진 | 4-1 및 모델/환경 확인 | index_manifest.json / experiment_manifest.json / environment.json; indexes/chroma/index_full_kure_200_v1/ | 레코드25829·249.3048초·재사용false·용량범위·revision/차원/device. 모델입력최대길이·잘림기록 보강 |
| 현수 | 4-2·5 | retrieval_results.jsonl / metrics_by_query.jsonl / environment.json | 질문별latency200개·평균/p95/최대·측정범위·워밍업없음·반복1회. 새ID반복의시간원본 보존 |
| 예지 | 3·6·7품질·8-1 | metrics_summary.json / metrics_by_query.jsonl / failure_cases.csv / retrieval_results.jsonl; 문서/청크qrels | Hit/MRR·성공수·오류0·실패유형·정답순위. Context는미평가 표기 후입력준비/재평가. 비교시query_id로연결 |

청크 기준 폴더는 `data/processed/ontong_youth_full_v1/chunks/eval_200_v1/section_heading_800_ov120_v1/`, 청크정답 기준 폴더는 `data/evaluation/eval_200_v1/chunk_qrels/section_heading_800_ov120_v1/`다.

팀 공유에는 로컬 D:경로 링크 대신 실제 팀원이 접근 가능한 Git/공용저장소 링크를 붙이고 위 저장소 상대경로를 함께 적는다. 최소한 결과폴더11개파일과 같은버전 입력/Manifest/청크정답/검수기록/신규코드를 보존해야 한다. run.log의 과거 SHA불일치/검수중단은 사전시도 기록이고 최종상태는 experiment_manifest.json의 SUCCESS로 확인한다.

## 그대로 붙일 Baseline 요약 메모

> B01 전체 데이터 Baseline을 exp_full_kure_200_v1로 완료했다. KURE-v1 고정revision, section800/overlap120, 문서2728개·청크25829개·질문200개로 Top-5 검색을 평가했다. 문서Hit@5=0.960(192/200), MRR@5=0.925417, 청크Hit@5=0.885(177/200), MRR@5=0.763667이며 실행오류는0건이다. 문서실패8건과 문서는찾았으나 청크실패15건을 분석대상으로 남겼다. Context 지표는이번실행에서비활성화되어미평가이며 필수사실/사실–청크매핑준비후 저장검색결과를 재평가할계획이다. 시간은워밍업없는1회측정으로평균23.5478ms·p95 30.1256ms이며속도비교확정값으로쓰지않는다. 재실행의Index재사용/품질일관성확인과후보비교가남아있다.

정상 재실행은 새 experiment_id와 결과경로를 사용해야 한다. 기존 완료ID로 같은 명령을 다시 실행하면 결과보호장치로 중단된다. 동일조건 재실행에서는 기존 Index 설정을 유지해 재사용을 검증하되, 청킹/모델을 바꾸는 비교실험은 해당조건의 별도 Index를 사용한다.
