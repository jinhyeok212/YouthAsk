"""비용이 큰 Embedding/Indexing 전에 평가셋과 qrels 정합성을 선검증한다."""

from __future__ import annotations

from collections import defaultdict
from src.common.io import read_jsonl, sha256_file
from src.evaluation.qrels import load_chunk_qrels, load_document_qrels


def validate_context_config(config: dict) -> None:
    settings = config.get("evaluation", {}).get("context_metrics", {})
    if not settings.get("enabled", False):
        return
    k = settings.get("k")
    if type(k) is not int or not 1 <= k <= config.get("retrieval", {}).get("evaluation_max_k", 5):
        raise ValueError("context_metrics.k must satisfy 1 <= k <= evaluation_max_k")
    for field in ("version", "required_facts_path", "chunk_fact_map_path"):
        if not isinstance(settings.get(field), str) or not settings[field].strip():
            raise ValueError(f"context_metrics.{field} is required")


def load_context_inputs(config: dict, *, questions=None, documents=None, chunks=None) -> dict | None:
    """Validate references and review state before indexing; pending != zero.

    Facts are row-based (query_id, fact_id, fact_text, document_id,
    source_location, review_status). Map rows link a fact to a fully supporting
    chunk; approved chunk_id=null explicitly records no supporting chunk.
    """
    validate_context_config(config)
    settings = config.get("evaluation", {}).get("context_metrics", {})
    if not settings.get("enabled", False):
        return None
    evaluation = config["evaluation"]
    questions = questions if questions is not None else read_jsonl(evaluation["questions_path"])
    documents = documents if documents is not None else read_jsonl(config["dataset"]["document_path"])
    chunks = chunks if chunks is not None else read_jsonl(config["chunking"]["chunk_path"])
    question_ids = [r["query_id"] for r in questions]
    if not question_ids or len(question_ids) != len(set(question_ids)):
        raise ValueError("Context evaluation requires non-empty unique question IDs")
    question_set = set(question_ids)
    document_ids = {r["document_id"] for r in documents}
    document_qrels = load_document_qrels(evaluation["document_qrels_path"])
    chunk_by_id = {r["chunk_id"]: r for r in chunks}
    if len(chunk_by_id) != len(chunks):
        raise ValueError("Duplicate chunk IDs in context inputs")
    facts: dict = defaultdict(dict)
    mapping: dict = defaultdict(list)
    qrels: dict = defaultdict(list)
    chunk_version = config["chunking"]["version"]

    def check_row(row, label):
        qid = row.get("query_id")
        if qid not in question_set:
            raise ValueError(f"Unknown query_id in {label}: {qid}")
        if row.get("review_status", "pending") not in {"pending", "approved", "rejected"}:
            raise ValueError(f"Invalid review_status in {label}: {qid}")
        if row.get("context_version", settings["version"]) != settings["version"]:
            raise ValueError(f"Context version mismatch in {label}: {qid}")
        return qid

    for row in read_jsonl(settings["required_facts_path"]):
        qid = check_row(row, "required_facts")
        for field in ("fact_id", "fact_text", "document_id", "source_location"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Invalid required fact {field}: {qid}")
        fid = row["fact_id"]
        if fid in facts[qid]:
            raise ValueError(f"Duplicate required fact: {qid}/{fid}")
        if row["document_id"] not in document_ids:
            raise ValueError(f"Unknown fact document: {qid}/{fid}")
        if row["document_id"] not in document_qrels.get(qid, set()):
            raise ValueError(f"Fact document is not gold for this question: {qid}/{fid}")
        facts[qid][fid] = row
    seen_map = set()
    for row in read_jsonl(settings["chunk_fact_map_path"]):
        qid = check_row(row, "chunk_fact_map")
        fid, cid = row.get("fact_id"), row.get("chunk_id")
        if fid not in facts[qid]:
            raise ValueError(f"Unknown mapped fact: {qid}/{fid}")
        if "chunk_id" not in row or (cid is not None and cid not in chunk_by_id):
            raise ValueError(f"Unknown mapped chunk: {qid}/{fid}/{cid}")
        if row.get("chunking_version") != chunk_version:
            raise ValueError(f"Chunk fact map version mismatch: {qid}/{fid}")
        key = (qid, fid, cid)
        if key in seen_map:
            raise ValueError(f"Duplicate fact mapping: {key}")
        seen_map.add(key)
        if cid is not None and chunk_by_id[cid]["document_id"] != facts[qid][fid]["document_id"]:
            raise ValueError(f"Fact/chunk document mismatch: {qid}/{fid}/{cid}")
        mapping[qid].append(row)
    for qid, rows in mapping.items():
        for fid in facts[qid]:
            links = [r["chunk_id"] for r in rows if r["fact_id"] == fid]
            if None in links and len(links) > 1:
                raise ValueError(f"Conflicting no-support and chunk mapping: {qid}/{fid}")
    seen_qrels = set()
    for row in read_jsonl(evaluation["chunk_qrels_path"]):
        qid = check_row(row, "chunk_qrels")
        cid = row.get("chunk_id")
        if cid not in chunk_by_id or (qid, cid) in seen_qrels:
            raise ValueError(f"Unknown/duplicate context qrel: {qid}/{cid}")
        seen_qrels.add((qid, cid))
        if row.get("chunking_version", chunk_version) != chunk_version:
            raise ValueError(f"Context qrels chunking version mismatch: {qid}")
        if row.get("document_id", chunk_by_id[cid]["document_id"]) != chunk_by_id[cid]["document_id"]:
            raise ValueError(f"Context qrels document mismatch: {qid}/{cid}")
        if type(row.get("relevance", 1)) not in (int, float) or row.get("relevance", 1) not in (0, 1):
            raise ValueError(f"Context qrels require binary relevance: {qid}/{cid}")
        qrels[qid].append(row)
    paths = {name: evaluation[name] for name in ("questions_path", "document_qrels_path", "chunk_qrels_path")}
    paths.update({name: settings[name] for name in ("required_facts_path", "chunk_fact_map_path")})
    paths.update({"document_path": config["dataset"]["document_path"],
                  "chunk_path": config["chunking"]["chunk_path"]})
    return {"question_ids": question_ids, "chunk_ids": set(chunk_by_id),
            "facts": facts, "mapping": mapping, "qrels": qrels,
            "manifest": {"version": settings["version"], "k": settings["k"],
                "chunking_version": chunk_version, "recall_definition": "unique_required_fact_coverage",
                "inputs": {name: {"path": str(path), "sha256": sha256_file(path)}
                           for name, path in paths.items()}}}


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

    context = load_context_inputs(config, questions=questions, documents=documents, chunks=chunks)
    return {
        "question_count": len(questions),
        "document_qrels_query_count": len(doc_qrels),
        "chunk_qrels_query_count": len(chunk_qrels),
        "chunk_qrels_row_count": len(raw_chunk_qrels),
        "status": "VALID",
        **({"context_metrics": context["manifest"]} if context is not None else {}),
    }
