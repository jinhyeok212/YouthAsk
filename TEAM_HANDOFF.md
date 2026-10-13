# 팀원에게 넘길 때 체크리스트

1. 압축 해제
2. Python 3.10~3.13 환경 준비
3. 가상환경 생성
4. `requirements-experiments.txt` 설치
5. 입력 5개 파일 배치
   - documents.jsonl
   - chunks.jsonl
   - eval_questions.jsonl
   - qrels.jsonl
   - qrels_chunk.jsonl
6. `scripts/run_checks.ps1` 또는 `run_checks.sh` 통과
7. 새 실험이면 `experiment_id` 변경
8. Index 영향 설정을 바꿨다면 index version/db_path/collection_name도 새 값 사용
9. 실행 후 `status`, `index_reused`, `environment.json`, `metrics_summary.json` 확인
10. 한 환경에서 E2E 성공 후 `capture_lock`으로 exact package lock 생성·공유

현재 기준 자동화의 책임 경계는 **검수된 Dataset/Chunk/qrels를 받아 Indexing → Retrieval → Evaluation → Artifact를 재현 가능하게 반복 실행하는 것**입니다.
