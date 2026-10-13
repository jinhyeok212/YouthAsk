#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python -m pip freeze > requirements-lock.txt
echo "Created: $ROOT/requirements-lock.txt"
