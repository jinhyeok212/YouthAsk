#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${1:-configs/experiments/exp_full_kure_v4_team.yaml}"
cd "$ROOT"
python -m pytest -q
python scripts/doctor.py --config "$CONFIG"
python -m src.experiments.runner --config "$CONFIG" --validate-only
python -m src.experiments.runner --config "$CONFIG" --dry-run
