"""Model-load failures must clean only the builder's temporary collection."""
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys

import pytest
from src.indexing import build_index


def test_model_load_failure_deletes_only_new_temporary_collection(monkeypatch, tmp_path):
    client = MagicMock()
    client.list_collections.return_value = ['existing_collection']
    client.get_max_batch_size.return_value = 256
    monkeypatch.setitem(sys.modules, 'chromadb', SimpleNamespace(PersistentClient=lambda **kw: client))
    monkeypatch.setitem(sys.modules, 'src.rag.embedding', SimpleNamespace(
        load_chunks=lambda **kw: ([{'chunk_id': 'c1'}], {'chunk_count': 1}),
        build_chroma_metadata=lambda row: {}, batched=lambda rows, size: [rows],
    ))

    def fail_loading(config):
        raise RuntimeError('model download failed')

    monkeypatch.setattr(build_index, 'KUREAdapter', fail_loading)
    config = {'index': {'db_path': str(tmp_path / 'new_index'),
                       'collection_name': 'new_collection', 'distance_metric': 'cosine'}}
    with pytest.raises(RuntimeError, match='model download failed'):
        build_index.build_new_index(config, {'chunk_path': 'unused.jsonl', 'chunk_count': 1})
    temporary_name = client.create_collection.call_args.kwargs['name']
    assert temporary_name.startswith('new_collection__building__')
    client.delete_collection.assert_called_once_with(temporary_name)
