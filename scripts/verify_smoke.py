"""Verify a generated smoke run without modifying source data or its results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.io import load_json, read_jsonl, sha256_file, write_json
from src.experiments.config_validator import load_and_validate_config


def require(condition: bool, message: str) -> None:
    # Do not use assert for input/artifact validation: python -O disables it.
    if not condition:
        raise ValueError(message)


def input_paths(config: dict) -> dict[str, str]:
    return {
        'documents': config['dataset']['document_path'],
        'chunks': config['chunking']['chunk_path'],
        'questions': config['evaluation']['questions_path'],
        'document_qrels': config['evaluation']['document_qrels_path'],
        'chunk_qrels': config['evaluation']['chunk_qrels_path'],
    }


def verify_smoke(config_path: str | Path) -> dict:
    import chromadb

    config = load_and_validate_config(config_path)
    base = Path(config['_runtime']['config_path']).parent
    audit = load_json(base / 'preparation_audit.json')
    for source in audit['sources'].values():
        require(sha256_file(source['path']) == source['sha256'],
                f"Source file changed: {source['path']}")
    paths = input_paths(config)
    data = {name: read_jsonl(path) for name, path in paths.items()}
    require({name: len(rows) for name, rows in data.items()} == audit['sample_counts'],
            'Sample counts changed')
    require({name: sha256_file(path) for name, path in paths.items()} == audit['sample_hashes'],
            'Sample hashes changed')
    out = Path(config['output']['root']) / config['experiment_id']
    manifest = load_json(out / 'experiment_manifest.json')
    metrics = load_json(out / 'metrics_summary.json')
    retrieval = read_jsonl(out / 'retrieval_results.jsonl')
    evaluated = read_jsonl(out / 'metrics_by_query.jsonl')
    traces = read_jsonl(out / 'traces.jsonl')
    expected = {row['query_id'] for row in data['questions']}
    for name, rows in [('retrieval', retrieval), ('evaluation', evaluated), ('trace', traces)]:
        require(len(rows) == len(expected) and {r['query_id'] for r in rows} == expected,
                f'{name}: question IDs/count do not match')
    require(manifest['status'] == 'SUCCESS', 'Runner status is not SUCCESS')
    require(metrics['evaluation_query_count'] == len(expected), 'Evaluation denominator mismatch')
    require(metrics['retrieval_failure_count'] == 0 and
            not any(r.get('error') for r in retrieval) and
            not any(r.get('runtime_error') for r in evaluated), 'Retrieval runtime errors found')
    require(manifest['dataset']['document_count'] == len(data['documents']), 'Document count mismatch')
    for section, key in [('chunking', 'chunk_count'), ('index', 'index_count')]:
        require(manifest[section][key] == len(data['chunks']), f'{section} count mismatch')
    require(manifest['index']['reused'] is False, 'Expected a new smoke index')
    require(manifest['evaluation']['validation']['question_count'] == len(expected),
            'Input-validation question count mismatch')
    chunk_map = {r['chunk_id']: r['document_id'] for r in data['chunks']}
    k = min(int(config['retrieval']['evaluation_max_k']), len(chunk_map))
    for row in retrieval:
        require(len(row['results']) == k, f"Incomplete results: {row['query_id']}")
        require([r['rank'] for r in row['results']] == list(range(1, k + 1)), 'Invalid ranks')
        require(all(chunk_map.get(r['chunk_id']) == r['document_id'] for r in row['results']),
                'Result chunk/document IDs do not match sample')
    client = chromadb.PersistentClient(path=config['index']['db_path'])
    collection = client.get_collection(config['index']['collection_name'])
    records = collection.get(include=['metadatas'])
    require(collection.count() == len(chunk_map) and set(records['ids']) == set(chunk_map),
            'Indexed IDs/count do not match sample')
    require(all(chunk_map[cid] == meta['document_id']
                for cid, meta in zip(records['ids'], records['metadatas'])),
            'Index parent-document metadata mismatch')
    require(load_json(out / 'index_manifest.json') == load_json(manifest['index']['manifest_path']),
            'Saved index manifest mismatch')
    report = {
        'status': 'PASS', 'experiment_id': config['experiment_id'], 'runner_status': 'SUCCESS',
        'counts': audit['sample_counts'], 'index_records': collection.count(),
        'retrieval_queries': len(retrieval), 'evaluation_queries': len(evaluated),
        'trace_queries': len(traces), 'runtime_errors': 0,
        'source_and_sample_hashes_unchanged': True, 'indexed_chunk_ids_exact_match': True,
        'metrics': metrics, 'output_dir': str(out),
    }
    write_json(base / 'verification.json', report)
    # Keep a local checksum ledger for binary artifacts and logs as well.
    inventory = [{'path': p.relative_to(base).as_posix(), 'bytes': p.stat().st_size,
                  'sha256': sha256_file(p)}
                 for p in sorted(base.rglob('*')) if p.is_file() and p.name != 'artifact_inventory.json']
    write_json(base / 'artifact_inventory.json', inventory)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Generated smoke config.yaml')
    args = parser.parse_args()
    print(json.dumps(verify_smoke(args.config), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
