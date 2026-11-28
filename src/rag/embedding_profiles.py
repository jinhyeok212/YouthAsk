"""Reproducible embedding model profiles for YouthAsk experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class EmbeddingProfile:
    key: str
    model_name: str
    revision: str
    dimension: int
    max_seq_length: int
    query_method: str
    document_method: str
    query_prefix: str = ""
    document_prefix: str = ""
    normalize: bool = True


PROFILES: Dict[str, EmbeddingProfile] = {
    "kure_v3": EmbeddingProfile(
        key="kure_v3",
        model_name="nlpai-lab/KURE-v3",
        revision="5b0494e801cd5cc21234012df1b83cfdb42b2065",
        dimension=2048,
        max_seq_length=8192,
        query_method="encode_query",
        document_method="encode_document",
    ),
    "snowflake_arctic_l_v2_ko": EmbeddingProfile(
        key="snowflake_arctic_l_v2_ko",
        model_name="dragonkue/snowflake-arctic-embed-l-v2.0-ko",
        revision="55ec6e9358a56d56af759bc8372e970caf8c305f",
        dimension=1024,
        max_seq_length=8192,
        query_method="encode",
        document_method="encode",
        query_prefix="query: ",
    ),
}


def get_profile(key: str, revision: Optional[str] = None) -> EmbeddingProfile:
    """Return a known profile and optionally validate an explicit revision."""
    try:
        profile = PROFILES[key]
    except KeyError as exc:
        raise ValueError(
            f"지원하지 않는 embedding profile입니다: {key}. "
            f"가능한 값={sorted(PROFILES)}"
        ) from exc

    if revision is not None and revision != profile.revision:
        raise ValueError(
            f"YAML revision이 고정 profile과 다릅니다: "
            f"expected={profile.revision}, actual={revision}"
        )
    return profile


def get_profile_by_model(model_name: str) -> Optional[EmbeddingProfile]:
    """Return a profile for a model ID, leaving KURE-v1 on its legacy path."""
    for profile in PROFILES.values():
        if profile.model_name == model_name:
            return profile
    return None
