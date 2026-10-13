"""비용이 큰 Embedding/Indexing 전에 평가셋과 qrels 정합성을 선검증한다."""

from __future__ import annotations

from src.common.io import read_jsonl
from src.evaluation.qrels import load_chunk_qrels, load_document_qrels


def validate_evaluation_inputs(
    config: dict,
    dataset_info: dict,
    chunk_info: dict,
) -> dict:
    """평가 질문, Document qrels, Chunk qrels 연결을 Index 생성 전에 확인한다.

    실제 프로젝트 qrels는 row 기반이다.
    - Document qrels: query_id + document_id + relevance
    - Chunk qrels: query_id + document_id + chunk_id + relevance

    한 질문에 여러 Gold Document/Chunk가 있으면 같은 query_id가 여러 행에
    등장하는 것이 정상이다.
    """
    questions = read_jsonl(config["evaluation"]["questions_path"])
    documents = read_jsonl(dataset_info["document_path"])
    chunks = read_jsonl(chunk_info["chunk_path"])
    raw_chunk_qrels = read_jsonl(config["evaluation"]["chunk_qrels_path"])

    if not questions:
        raise ValueError("평가 질문이 0건입니다.")

    # 1) 질문 자체 검증
    question_ids: list[str] = []
    for row in questions:
        query_id = str(row.get("query_id", "")).strip()
        query = str(row.get("query", "")).strip()
        if not query_id:
            raise ValueError("빈 query_id가 있습니다.")
        if not query:
            raise ValueError(f"빈 query: query_id={query_id}")
        question_ids.append(query_id)

    if len(question_ids) != len(set(question_ids)):
        raise ValueError("평가 질문에 중복 query_id가 있습니다.")

    # 2) 실제 row 기반 qrels 로드
    doc_qrels = load_document_qrels(
        config["evaluation"]["document_qrels_path"]
    )
    chunk_qrels = load_chunk_qrels(
        config["evaluation"]["chunk_qrels_path"]
    )

    question_set = set(question_ids)

    # 3) 모든 질문에 Document/Chunk qrels가 있는지 확인
    if set(doc_qrels) != question_set:
        missing = sorted(question_set - set(doc_qrels))
        extra = sorted(set(doc_qrels) - question_set)
        raise ValueError(
            "질문/document qrels 불일치: "
            f"missing={missing[:10]}, extra={extra[:10]}"
        )

    if set(chunk_qrels) != question_set:
        missing = sorted(question_set - set(chunk_qrels))
        extra = sorted(set(chunk_qrels) - question_set)
        raise ValueError(
            "질문/chunk qrels 불일치: "
            f"missing={missing[:10]}, extra={extra[:10]}"
        )

    # 4) 실제 데이터 ID Map
    valid_document_ids = {
        str(row["document_id"])
        for row in documents
    }
    chunk_map = {
        str(row["chunk_id"]): row
        for row in chunks
    }
    valid_chunk_ids = set(chunk_map)

    # 5) Document qrels의 정답 ID가 실제 documents에 존재하는지
    for query_id, ids in doc_qrels.items():
        missing = ids - valid_document_ids
        if missing:
            raise ValueError(
                "존재하지 않는 정답 document_id: "
                f"query_id={query_id}, ids={sorted(missing)[:10]}"
            )

    # 6) Chunk qrels의 정답 ID가 실제 chunks에 존재하는지
    for query_id, ids in chunk_qrels.items():
        missing = ids - valid_chunk_ids
        if missing:
            raise ValueError(
                "존재하지 않는 정답 chunk_id: "
                f"query_id={query_id}, ids={sorted(missing)[:10]}"
            )

    # 7) Chunk qrels의 document / section / version 정합성 확인
    configured_chunk_version = config["chunking"]["version"]

    for row in raw_chunk_qrels:
        relevance = row.get("relevance", 1)
        try:
            if float(relevance) <= 0:
                continue
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"잘못된 Chunk qrels relevance: {relevance}"
            ) from e

        query_id = str(row.get("query_id", "")).strip()
        chunk_id = str(row.get("chunk_id", "")).strip()
        document_id = str(row.get("document_id", "")).strip()

        if chunk_id not in chunk_map:
            # 위에서 이미 검증하지만 오류 메시지를 더 구체적으로 남긴다.
            raise ValueError(
                f"존재하지 않는 Chunk qrels chunk_id: query_id={query_id}, chunk_id={chunk_id}"
            )

        chunk = chunk_map[chunk_id]

        # qrels의 document_id와 실제 Chunk document_id가 같은가?
        actual_document_id = str(chunk.get("document_id", "")).strip()
        if actual_document_id != document_id:
            raise ValueError(
                "Chunk-document 연결 오류: "
                f"query_id={query_id}, chunk_id={chunk_id}, "
                f"qrels_document={document_id}, actual_document={actual_document_id}"
            )

        # Chunk qrels의 document_id가 Document qrels에도 Gold로 등록돼 있는가?
        if document_id not in doc_qrels[query_id]:
            raise ValueError(
                "Chunk qrels의 document_id가 Document qrels와 다릅니다: "
                f"query_id={query_id}, document_id={document_id}"
            )

        # matched_section 필드가 있으면 실제 Chunk section과 비교한다.
        matched_section = row.get("matched_section")
        if matched_section is not None:
            actual_section = chunk.get("section")
            if str(actual_section) != str(matched_section):
                raise ValueError(
                    "Chunk section 불일치: "
                    f"query_id={query_id}, chunk_id={chunk_id}, "
                    f"qrels={matched_section}, chunk={actual_section}"
                )

        # qrels에 chunking_version이 있으면 YAML 설정과 비교한다.
        qrels_version = row.get("chunking_version")
        if qrels_version and qrels_version != configured_chunk_version:
            raise ValueError(
                "Chunking Version 불일치: "
                f"query_id={query_id}, qrels={qrels_version}, "
                f"config={configured_chunk_version}"
            )

    return {
        "question_count": len(questions),
        "document_qrels_query_count": len(doc_qrels),
        "chunk_qrels_query_count": len(chunk_qrels),
        "chunk_qrels_row_count": len(raw_chunk_qrels),
        "status": "VALID",
    }
