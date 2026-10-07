# 🔎 YouthAsk — RAG Retrieval System

> 청년정책 데이터를 기반으로 검색 파이프라인을 구현하고, 검색 성능을 정량적으로 평가·개선하는 프로젝트

## 📌 Project Overview

YouthAsk는 온통청년 청년정책 Open API 데이터를 활용하는 RAG 검색 시스템 프로젝트입니다.

데이터 수집 → 전처리 → Chunking → Embedding → Vector DB → Retrieval → Evaluation의 흐름을 구성하고, 설정에 따른 검색 성능 차이를 분석하는 것을 목표로 합니다.

Baseline 표본 데이터로 설정을 비교하고 전체 정책 데이터로 확장하는 방향을 유지하며, 현재 `main`에는 YAML 기반 experiment runner, batch retrieval, 평가 단계 연결 구조와 Full Dataset용 KURE-v1·Chroma 설정이 포함되어 있습니다.

**이 문서의 구현 상태는 코드와 설정의 존재를 기준으로 합니다. 전체 실험 실행 완료, 테스트 통과, 검색 성능 검증 완료를 의미하지 않습니다.**

## 🎯 Goals

- 청년정책 데이터 수집·전처리 및 공통 스키마 관리
- Baseline과 Full Dataset의 검색 설정 비교
- Chunking·Embedding·Top-k에 따른 성능 분석
- Hit@k·MRR 기반 검색 평가
- 실험 설정과 결과를 추적할 수 있는 실행 구조 구축

## 🏗️ RAG Pipeline

데이터 준비 흐름과 실험 runner의 실행 범위는 다음과 같습니다.

```text
온통청년 Open API
        ↓
원본 데이터 수집·전처리
        ↓
Baseline / Full Dataset 및 평가 데이터 준비
        ↓
YAML 기반 Experiment Runner
        ├── 문서·Dataset Manifest 검증
        ├── 청킹·Chunk qrels 검증
        ├── Chroma 인덱스 생성 또는 재사용
        ├── 전체 평가 질문 Top-k 검색
        ├── Hit@k·MRR 및 실패 사례 평가
        └── 실험 결과 저장
```

runner는 준비된 데이터와 YAML 설정을 입력으로 각 단계의 entrypoint를 호출하고 반환값을 검증하는 구조입니다. Open API 수집과 표본 추출은 위 runner의 직접 실행 단계에 포함되지 않습니다. 구현 근거: [Experiment Runner](https://github.com/jinhyeok212/YouthAsk/blob/main/src/experiments/runner.py).

## 🗂️ Dataset

### 온통청년 청년정책 데이터

온통청년 Open API에서 얻은 정책 데이터를 전처리하여 검색 입력으로 활용합니다.

### Baseline Dataset

카테고리별 층화 표본을 활용하여 설정 비교와 평가 환경 점검을 수행하기 위한 데이터셋입니다. 카테고리와 추출 비율은 데이터 및 설정을 기준으로 관리합니다.

### Full Dataset

전체 정책 데이터를 대상으로 검색·평가를 수행하기 위한 설정이 있습니다. 해당 설정의 존재만으로 데이터 수집 완료, 인덱스 구축 완료 또는 Baseline 설정 확정을 판단하지 않습니다.

Full Dataset 설정의 입력 경로는 다음과 같습니다.

```text
data/processed/ontong_youth_full_v1/
├── documents.jsonl
├── chunks.jsonl
└── dataset_manifest.json

data/evaluation/eval_full_v1/
├── eval_questions.jsonl
├── qrels.jsonl
├── qrels_chunk.jsonl
└── evaluation_manifest.json
```

위 목록은 YAML에 지정된 경로입니다. 실행 환경에서 각 파일의 준비 여부와 내용의 유효성을 별도로 확인해야 합니다. 설정 근거: [Full Dataset YAML](https://github.com/jinhyeok212/YouthAsk/blob/main/configs/experiments/exp_full_kure_v1.yaml).

## 🧩 Common Data Schema

정책 문서, 검색 청크, 평가 질문과 정답 연결 정보(qrels)를 구분하여 관리합니다.

batch retrieval이 사용하는 평가 질문의 최소 입력 예시는 다음과 같습니다.

```json
{
  "query_id": "query_001",
  "query": "청년이 받을 수 있는 주거 지원 정책은?"
}
```

질문 파일은 JSONL 형식이며, batch retrieval에는 빈 질문·중복 `query_id` 등을 검사하는 코드가 있습니다. 검색 결과에는 질문 식별자와 청크별 순위, `chunk_id`, `document_id`를 확인하는 검증 로직이 포함되어 있습니다. 구현 근거: [Batch Retriever](https://github.com/jinhyeok212/YouthAsk/blob/main/src/retrieval/batch_retriever.py).

## 🔍 Batch Retrieval

`src/retrieval/batch_retriever.py`는 평가 질문을 입력 순서대로 처리하고, 기존 Chroma 컬렉션을 읽어 질문별 검색 결과를 반환하도록 구현되어 있습니다.

- 질문 임베딩 모델과 장치를 실험 설정에서 읽습니다.
- 검색 개수는 `retrieval.evaluation_max_k`를 사용합니다.
- batch retrieval 단계 자체는 인덱스를 생성하지 않습니다.
- 현재 구현은 cosine 거리 기반 검색 결과 처리를 지원합니다.
- 질문 처리 중 오류가 발생하면 해당 `query_id`를 포함한 예외를 발생시킵니다.
- 전체 질문 수와 결과 수의 일치 여부를 검사합니다.

여기서 batch retrieval은 **평가 질문 전체를 일괄 처리하는 단계**를 뜻합니다. 질문을 병렬로 검색한다는 의미는 아닙니다. 구현 근거: [Batch Retriever](https://github.com/jinhyeok212/YouthAsk/blob/main/src/retrieval/batch_retriever.py).

## 📊 Evaluation

검색 결과와 Ground Truth를 연결하여 Retriever 성능을 평가하는 방향입니다.

| 지표 | 의미 |
| --- | --- |
| Hit@k | 상위 k개 결과에 정답이 하나 이상 포함된 질문의 비율 |
| MRR | 질문별 첫 정답 순위의 역수를 평균한 값 |

검색 범위에 정답이 없으면 해당 질문의 Reciprocal Rank는 0입니다. 결과를 비교할 때는 평가 질문, qrels, 데이터·인덱스 버전과 검색 범위를 함께 기록해야 합니다.

runner에는 `evaluate_experiment` 단계와 그 반환값을 검증하는 연결 구조가 있으며, 이후 결과 저장 단계를 호출합니다. **평가 구조가 코드에 있다는 사실과 실제 점수가 측정·검증되었다는 사실은 구분합니다.** 연결 근거: [Experiment Runner](https://github.com/jinhyeok212/YouthAsk/blob/main/src/experiments/runner.py).

## 🧪 Experiment Runner

실험 설정은 YAML로 전달합니다. 다음 명령은 저장소 루트에서 사용하는 CLI 예시이며, 실행 성공을 확인한 기록은 아닙니다.

### 설정 검증

```bash
python -m src.experiments.runner --config configs/experiments/exp_full_kure_v1.yaml --validate-only
```

설정 검증 후 종료합니다. 입력 파일의 준비 상태나 모델·인덱스의 정상 동작까지 확인하는 모드는 아닙니다.

### 준비 상태 점검

```bash
python -m src.experiments.runner --config configs/experiments/exp_full_kure_v1.yaml --dry-run
```

설정된 입력 파일의 존재 여부와 단계별 entrypoint의 import 가능 여부를 출력합니다. 실제 검색·평가는 수행하지 않으며, 출력 내용도 함께 확인해야 합니다.

### 실험 실행

```bash
python -m src.experiments.runner --config configs/experiments/exp_full_kure_v1.yaml
```

입력 데이터, 의존성, 모델과 실행 장치를 준비한 환경에서 사용합니다. runner는 `experiments/<experiment_id>/`를 출력 경로로 사용하고 `run.log`를 기록하며, 내용이 있는 동일 결과 폴더의 덮어쓰기를 거부하도록 구현되어 있습니다. CLI 근거: [Experiment Runner](https://github.com/jinhyeok212/YouthAsk/blob/main/src/experiments/runner.py).

## ⚙️ Full Dataset Configuration

`configs/experiments/exp_full_kure_v1.yaml`의 주요 설정입니다.

| 항목 | 설정값 |
| --- | --- |
| Experiment ID | `exp_full_kure_v1` |
| Dataset Version | `ontong_youth_full_v1` |
| Evaluation Version | `eval_full_v1` |
| Chunking | `section`, 800 characters, overlap 120 |
| Chunking 대상 | `retrieval_text` |
| Embedding Model | `nlpai-lab/KURE-v1` |
| Embedding Dimension | `1024` |
| Normalization | `true` |
| Embedding Batch Size | `32` |
| Device | `auto` |
| Index Version | `index_full_kure_v1` |
| Chroma 경로 | `indexes/chroma/index_full_kure_v1` |
| Collection | `ontong_youth_full_kure_v1` |
| Distance Metric | `cosine` |
| Evaluation Max-k | `5` |
| Context Top-k | `3` |
| Output Root | `experiments` |
| Registry Path | `registry/experiments` |
| Fail Fast | `true` |

`evaluation_max_k`는 평가 검색 수이고, `context_top_k`는 별도의 컨텍스트 설정입니다. 이 값들이 최적 설정으로 검증되었거나 답변 생성까지 실행되었다는 의미는 아닙니다. 설정 근거: [Full Dataset YAML](https://github.com/jinhyeok212/YouthAsk/blob/main/configs/experiments/exp_full_kure_v1.yaml).

## 📁 Project Structure

검색 실험 관련 주요 경로를 중심으로 정리했습니다.

```text
.
├── configs/
│   └── experiments/
│       └── exp_full_kure_v1.yaml
├── data/
├── src/
│   ├── experiments/
│   │   └── runner.py
│   └── retrieval/
│       └── batch_retriever.py
├── experiments/
├── indexes/
│   └── chroma/
├── schemas/
├── scripts/
├── tests/
├── docs/
├── learning/
├── backend/
├── frontend/
├── dashboard/
├── requirements-experiments.txt
└── README.md
```

전체 파일 목록과 각 디렉터리의 내용은 [저장소 main](https://github.com/jinhyeok212/YouthAsk)에서 확인할 수 있습니다. 디렉터리의 존재만으로 해당 기능의 실행·검증 완료를 의미하지 않습니다.

## 🧪 Experiment Strategy

비교 대상은 Chunk Size·Overlap, Embedding Model·Normalization, Top-k 등입니다.

실험 결과를 비교할 때는 동일한 평가 데이터 사용 여부와 데이터·청킹·인덱스 버전을 확인합니다. 인덱스에 영향을 주는 설정을 바꾼 경우에는 기존 인덱스의 재사용 적합성을 점검합니다.

현재 batch retrieval의 거리 처리는 cosine으로 제한되므로, 다른 거리 지표의 실험에는 구현 지원 여부를 먼저 확인해야 합니다. 구현 근거: [Batch Retriever](https://github.com/jinhyeok212/YouthAsk/blob/main/src/retrieval/batch_retriever.py).

## 🛠️ Tech Stack

- Python
- Sentence Transformers / KURE-v1
- ChromaDB
- YAML 기반 실험 설정
- JSON / JSONL 데이터
- Hit@k / MRR 평가 지표
- Git / GitHub

## 🚀 Development Roadmap

다음은 개발·검증의 진행 방향이며 완료 목록이 아닙니다.

1. 데이터 수집·전처리 및 버전 관리
2. Baseline·Full Dataset과 Ground Truth 정합성 확인
3. runner의 단계별 실행 및 통합 동작 확인
4. 테스트 결과와 실행 환경 기록
5. 검색 성능 측정 및 실패 사례 분석
6. 설정 비교와 개선 결과 문서화

## 🔬 What We Focus On

정책 문서의 전처리와 청킹 방식이 검색에 미치는 영향, 모델·Top-k별 성능 차이, 표본에서 얻은 결과가 전체 데이터에서도 유지되는지를 탐구합니다.

## 👥 Team

데이터 준비, 검색 파이프라인, 평가, 실험 분석을 역할별로 분담하여 진행합니다.

## 📌 Current Status

**기준일: 2026년 10월 7일 · 대상 브랜치: `main`**

| 구분 | 확인된 상태 |
| --- | --- |
| Experiment runner | YAML 기반 단계 실행·검증 코드 존재 |
| Batch retrieval | 전체 평가 질문 검색 코드 존재 |
| 평가 파이프라인 | Hit@k·MRR 평가 단계 연결 구조 확인 |
| Full Dataset | KURE-v1·Chroma 실험 설정 존재 |
| 전체 실험 실행 완료 | 저장소 확인만으로 확정할 수 없음 |
| 테스트 성공 | 저장소 확인만으로 확정할 수 없음 |
| 검색 성능·최적 설정 | 실행 결과와 검증 근거 확인 필요 |

구현 근거: [Runner](https://github.com/jinhyeok212/YouthAsk/blob/main/src/experiments/runner.py), [Batch Retrieval](https://github.com/jinhyeok212/YouthAsk/blob/main/src/retrieval/batch_retriever.py), [Full Dataset 설정](https://github.com/jinhyeok212/YouthAsk/blob/main/configs/experiments/exp_full_kure_v1.yaml).

기준일에 GitHub의 **열린 Issue는 0개, 열린 Pull Request는 0개**입니다. 이는 해당 시점의 열린 항목 수이며, 결함이 없거나 개발·검증이 완료되었다는 뜻은 아닙니다. 확인 링크: [Issues](https://github.com/jinhyeok212/YouthAsk/issues), [Pull Requests](https://github.com/jinhyeok212/YouthAsk/pulls).

실행 완료 여부와 테스트 상태는 코드·설정의 구현 상태와 별도로 관리하고, 확인된 실행 로그·결과·테스트 근거가 있을 때 갱신합니다.
