import pytest

from src.experiments.config_validator import validate_config_dict


def _schema():
    return {
        "type": "object",
        "required": ["chunking", "retrieval"],
        "properties": {
            "chunking": {"type": "object"},
            "retrieval": {"type": "object"},
        },
    }


def test_overlap_must_be_smaller_than_size():
    config = {
        "chunking": {"size": 100, "overlap": 100},
        "retrieval": {"evaluation_max_k": 5, "context_top_k": 3},
    }
    with pytest.raises(ValueError):
        validate_config_dict(config, _schema())
