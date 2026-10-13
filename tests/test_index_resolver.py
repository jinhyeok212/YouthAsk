from src.indexing.build_index_manifest import build_index_signature, manifest_matches


def _config():
    return {
        "dataset": {"version": "d1", "preprocessing_version": "p1"},
        "chunking": {
            "version": "c1",
            "size": 800,
            "overlap": 120,
            "target_field": "retrieval_text",
        },
        "embedding": {
            "model": "m1",
            "revision": "rev1",
            "dimension": 1024,
            "normalize": True,
        },
        "index": {"version": "i1", "distance_metric": "cosine"},
        "retrieval": {"evaluation_max_k": 5},
    }


def _chunk_info():
    return {
        "chunk_count": 100,
        "dataset_sha256": "dataset-hash",
        "chunk_sha256": "chunk-hash",
    }


def test_top_k_change_does_not_change_index_signature():
    cfg1 = _config()
    cfg2 = _config()
    cfg2["retrieval"]["evaluation_max_k"] = 10
    assert build_index_signature(cfg1, _chunk_info()) == build_index_signature(
        cfg2, _chunk_info()
    )


def test_embedding_model_change_requires_new_index():
    cfg1 = _config()
    cfg2 = _config()
    cfg2["embedding"]["model"] = "m2"
    manifest = {"signature": build_index_signature(cfg1, _chunk_info())}
    assert manifest_matches(manifest, cfg2, _chunk_info()) is False


def test_embedding_revision_change_requires_new_index():
    cfg1 = _config()
    cfg2 = _config()
    cfg2["embedding"]["revision"] = "rev2"
    manifest = {"signature": build_index_signature(cfg1, _chunk_info())}
    assert manifest_matches(manifest, cfg2, _chunk_info()) is False


def test_index_version_change_requires_new_index():
    cfg1 = _config()
    cfg2 = _config()
    cfg2["index"]["version"] = "i2"
    manifest = {"signature": build_index_signature(cfg1, _chunk_info())}
    assert manifest_matches(manifest, cfg2, _chunk_info()) is False


def test_chunk_size_change_requires_new_index():
    cfg1 = _config()
    cfg2 = _config()
    cfg2["chunking"]["size"] = 1000
    manifest = {"signature": build_index_signature(cfg1, _chunk_info())}
    assert manifest_matches(manifest, cfg2, _chunk_info()) is False


def test_chunk_content_change_requires_new_index():
    cfg = _config()
    original = _chunk_info()
    changed = dict(original)
    changed["chunk_sha256"] = "different-hash"
    manifest = {"signature": build_index_signature(cfg, original)}
    assert manifest_matches(manifest, cfg, changed) is False
