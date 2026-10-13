"""Prepare a gold-closed sample, run the real experiment, and verify its artifacts."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.io import read_jsonl, sha256_file, write_json, write_jsonl
from src.data.validate_documents import validate_documents
from src.chunking.build_chunks import build_chunks
from src.evaluation.validate_inputs import validate_evaluation_inputs
from src.evaluation.qrels import load_document_qrels, load_chunk_qrels
from src.experiments.config_validator import load_and_validate_config
from scripts.verify_smoke import input_paths, require, verify_smoke
import yaml


def select_questions(questions: list[dict], document_qrels: dict,
                     chunk_qrels: dict, count: int) -> list[dict]:
    require(1 <= count <= len(questions), f'question-count must be 1..{len(questions)}')
    selected: list[dict] = []

    def add(row: dict) -> None:
        if len(selected) < count and row not in selected:
            selected.append(row)

    # Exercise multiple golds and question types when the requested size allows it.
    for qrels in (document_qrels, chunk_qrels):
        candidate = next((q for q in questions if len(qrels[q['query_id']]) > 1), None)
        if candidate is not None:
            add(candidate)
    for kind in sorted({str(q.get('question_type', '')) for q in questions}):
        if not any(str(q.get('question_type', '')) == kind for q in selected):
            add(next(q for q in questions if str(q.get('question_type', '')) == kind))
    for row in questions:
        add(row)
    chosen = {q['query_id'] for q in selected}
    return [q for q in questions if q['query_id'] in chosen]


def prepare_smoke(source_config: str | Path, run_id: str, count: int = 8,
                  device: str | None = None) -> Path:
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', run_id) is not None,
            'run-id must be 1..64 ASCII letters/digits/underscores/hyphens, starting with a letter/digit')
    source = load_and_validate_config(source_config)
    paths = input_paths(source)
    # Read all inputs before reserving output; missing sources never get invented.
    rows = {name: read_jsonl(path) for name, path in paths.items()}
    require(1 <= count <= len(rows['questions']), f"question-count must be 1..{len(rows['questions'])}")
    base = ROOT / 'smoke_checks' / run_id
    base.mkdir(parents=True, exist_ok=False)
    config_path = base / 'config.yaml'
    # Validate the complete source bundle, but write any bootstrap manifests only
    # into this new run. Never pass original manifest paths to mutating stages.
    validation_config = deepcopy(source)
    validation_config['dataset']['manifest_path'] = str(base / 'source_validation/dataset_manifest.json')
    validation_config['chunking']['manifest_path'] = str(base / 'source_validation/chunk_manifest.json')
    dataset = validate_documents(validation_config)
    chunks = build_chunks(validation_config, dataset)
    source_validation = validate_evaluation_inputs(validation_config, dataset, chunks)
    dq = load_document_qrels(paths['document_qrels'])
    cq = load_chunk_qrels(paths['chunk_qrels'])
    for question in rows['questions']:
        if 'ground_truth_document_ids' in question:
            require(set(question['ground_truth_document_ids']) == dq[question['query_id']],
                    f"Question gold array differs from qrels: {question['query_id']}")
    selected = select_questions(rows['questions'], dq, cq, count)
    chosen = {q['query_id'] for q in selected}
    doc_qrels = [r for r in rows['document_qrels'] if r['query_id'] in chosen]
    chunk_qrels = [r for r in rows['chunk_qrels'] if r['query_id'] in chosen]
    # Include even explicit non-relevant qrel references to preserve original rows.
    document_ids = {r['document_id'] for r in doc_qrels + chunk_qrels}
    subset = {
        'documents': [r for r in rows['documents'] if r['document_id'] in document_ids],
        'chunks': [r for r in rows['chunks'] if r['document_id'] in document_ids],
        'questions': selected, 'document_qrels': doc_qrels, 'chunk_qrels': chunk_qrels,
    }
    filenames = {'documents': 'documents.jsonl', 'chunks': 'chunks.jsonl',
                 'questions': 'eval_questions.jsonl', 'document_qrels': 'qrels.jsonl',
                 'chunk_qrels': 'qrels_chunk.jsonl'}
    for name, filename in filenames.items():
        write_jsonl(base / 'inputs' / filename, subset[name])
    # Retain source dataset/chunk versions and row IDs. The new hash distinguishes
    # the subset; experiment/index/evaluation namespaces are unique per run.
    config = yaml.safe_load(Path(source['_runtime']['config_path']).read_text(encoding='utf-8'))
    relative = base.relative_to(ROOT).as_posix()
    config['experiment_id'] = run_id
    config['experiment_name'] = f'Smoke test with {count} reviewed questions'
    config['dataset'].update(document_path=f'{relative}/inputs/documents.jsonl',
                             manifest_path=f'{relative}/inputs/dataset_manifest.json')
    config['chunking'].update(chunk_path=f'{relative}/inputs/chunks.jsonl',
                              manifest_path=f'{relative}/inputs/chunk_manifest.json')
    config['evaluation'].update(version=f'eval_{run_id}',
        questions_path=f'{relative}/inputs/eval_questions.jsonl',
        document_qrels_path=f'{relative}/inputs/qrels.jsonl',
        chunk_qrels_path=f'{relative}/inputs/qrels_chunk.jsonl')
    config['index'].update(version=f'index_{run_id}', db_path=f'{relative}/index',
                           collection_name=f'index_{run_id}')
    config['index'].pop('manifest_path', None)
    config['output']['root'] = f'{relative}/results'
    config['execution']['retrieval_error_policy'] = 'fail'
    if device:
        config['embedding']['device'] = device
    with config_path.open('x', encoding='utf-8') as stream:
        yaml.safe_dump(config, stream, allow_unicode=True, sort_keys=False)
    runtime = load_and_validate_config(config_path)
    di = validate_documents(runtime)
    ci = build_chunks(runtime, di)
    ei = validate_evaluation_inputs(runtime, di, ci)
    write_json(base / 'preparation_audit.json', {
        'source_config': source['_runtime']['config_path'],
        'sources': {n: {'path': p, 'rows': len(rows[n]), 'sha256': sha256_file(p)} for n, p in paths.items()},
        'source_validation': source_validation, 'sample_validation': ei,
        'selection_rule': 'multi-gold questions, distinct question types, then source order; retain all qrels and all chunks of selected documents',
        'selected_query_ids': [q['query_id'] for q in selected],
        'sample_counts': {n: len(r) for n, r in subset.items()},
        'sample_hashes': {n: sha256_file(base / 'inputs' / f) for n, f in filenames.items()},
    })
    return config_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-config', default=str(ROOT / 'configs/smoke/mvp400_c2.yaml'))
    parser.add_argument('--question-count', type=int, default=8)
    parser.add_argument('--run-id', help='Optional unique name; existing run folders are rejected')
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda', 'mps'])
    parser.add_argument('--prepare-only', action='store_true', help='Prepare/validate files without indexing or retrieval')
    parser.add_argument('--offline', action='store_true', help='Use only the existing Hugging Face model cache')
    args = parser.parse_args()
    if args.offline:
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
    run_id = args.run_id or ('smoke_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8])
    config_path = prepare_smoke(args.source_config, run_id, args.question_count, args.device)
    print(f'Prepared config: {config_path}', flush=True)
    if args.prepare_only:
        print('PREPARED: actual indexing/retrieval/evaluation was not executed.')
        return
    doctor = subprocess.run([sys.executable, str(ROOT / 'scripts/doctor.py'), '--config', str(config_path)],
                            cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                            env={**os.environ, 'PYTHONUTF8': '1'})
    (config_path.parent / 'doctor.json').write_text(doctor.stdout, encoding='utf-8')
    if doctor.returncode:
        raise RuntimeError(f'Environment/readiness check failed.\n{doctor.stdout}\n{doctor.stderr}')
    from src.experiments.runner import run_pipeline

    result = run_pipeline(load_and_validate_config(config_path))
    write_json(config_path.parent / 'run_result.json', result)
    report = verify_smoke(config_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
