#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 5 ]]; then
  echo "Usage: $0 DOCUMENTS CHUNKS QUESTIONS DOCUMENT_QRELS CHUNK_QRELS [DATASET_MANIFEST]"
  exit 2
fi

DOCUMENTS="$1"
CHUNKS="$2"
QUESTIONS="$3"
DOCUMENT_QRELS="$4"
CHUNK_QRELS="$5"
DATASET_MANIFEST="${6:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATASET_DIR="$ROOT/data/processed/ontong_youth_full_v1"
EVAL_DIR="$ROOT/data/evaluation/eval_full_v1"

mkdir -p "$DATASET_DIR" "$EVAL_DIR"
cp "$DOCUMENTS" "$DATASET_DIR/documents.jsonl"
cp "$CHUNKS" "$DATASET_DIR/chunks.jsonl"
cp "$QUESTIONS" "$EVAL_DIR/eval_questions.jsonl"
cp "$DOCUMENT_QRELS" "$EVAL_DIR/qrels.jsonl"
cp "$CHUNK_QRELS" "$EVAL_DIR/qrels_chunk.jsonl"
if [[ -n "$DATASET_MANIFEST" && -f "$DATASET_MANIFEST" ]]; then
  cp "$DATASET_MANIFEST" "$DATASET_DIR/dataset_manifest.json"
fi

echo "Input files copied under: $ROOT/data"
echo "Next: ./scripts/run_checks.sh"
