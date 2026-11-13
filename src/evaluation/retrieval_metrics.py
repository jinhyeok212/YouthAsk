"""검색 결과의 순위를 이용해 검색 성능을 계산한다."""


# Context Precision / Recall 계산
def calculate_context_metrics(
    retrieved_ids: list[str],
    gold_ids: set[str],
    required_fact_ids: set[str] | None = None,
    chunk_fact_map: dict[str, set[str]] | None = None,
) -> dict[str, float | None]:
    """Rank-based precision and unique required-fact coverage.

    Missing fact annotations are unevaluated (None), never gold-ID recall.
    A mapping associates each chunk with facts it fully supports.
    """
    seen: set[str] = set()
    hits = 0
    precision_sum = 0.0
    for rank, item_id in enumerate(retrieved_ids, start=1):
        if item_id in gold_ids and item_id not in seen:
            hits += 1
            precision_sum += hits / rank
        seen.add(item_id)
    return {
        "context_precision": precision_sum / hits if hits else 0.0,
        "context_recall": (
            len(set().union(*(chunk_fact_map.get(cid, set()) for cid in retrieved_ids))
                & required_fact_ids) / len(required_fact_ids)
            if required_fact_ids and chunk_fact_map is not None else None
        ),
    }


# First Relevant Rank 계산
def find_first_relevant_rank(
    retrieved_ids: list[str],
    gold_ids: set[str],
) -> int | None:
    """검색 결과에서 정답 ID의 First Relevant Rank를 찾는다.

    Document 평가에서는 document_id, Chunk 평가에서는 chunk_id를 받는다.
    정답 ID가 검색 결과에 있으면 First Relevant Rank를 반환하고,
    검색 결과에 없으면 None을 반환한다.
    """
    # 검색 결과를 1위부터 순서대로 확인한다.
    for rank, retrieved_id in enumerate(retrieved_ids, start=1):
        if retrieved_id in gold_ids:
            return rank

    # 모든 검색 결과를 확인해도 정답 ID가 없으면 None을 반환한다.
    return None


# Hit@k 계산
def calculate_hit_at_k(first_relevant_rank: int | None, k: int) -> int:
    """정답 ID가 Top-k 안에 있으면 Hit@k 1, 없으면 0을 반환한다."""
    if k < 1:
        raise ValueError("k는 1 이상의 정수여야 합니다.")

    if first_relevant_rank is None:
        return 0

    return int(first_relevant_rank <= k)


# RR 계산
def calculate_reciprocal_rank(first_relevant_rank: int | None) -> float:
    """First Relevant Rank의 역수인 RR을 계산한다."""
    if first_relevant_rank is None:
        return 0.0

    if first_relevant_rank < 1:
        raise ValueError("최초 정답 순위는 1 이상이어야 합니다.")

    return 1.0 / first_relevant_rank


# 전체 Hit@k 계산
def calculate_mean_hit_at_k(hit_values: list[int]) -> float:
    """질문별 Hit@k의 평균을 계산한다."""
    if not hit_values:
        raise ValueError("평균을 계산할 Hit@k 값이 없습니다.")

    return sum(hit_values) / len(hit_values)


# MRR 계산
def calculate_mrr(reciprocal_ranks: list[float]) -> float:
    """질문별 RR의 평균인 MRR을 계산한다."""
    if not reciprocal_ranks:
        raise ValueError("MRR을 계산할 RR 값이 없습니다.")

    return sum(reciprocal_ranks) / len(reciprocal_ranks)
