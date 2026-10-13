param(
    [string]$Config = "configs\experiments\exp_full_kure_v4_team.yaml"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python -m pytest -q
    python scripts\doctor.py --config $Config
    python -m src.experiments.runner --config $Config --validate-only
    python -m src.experiments.runner --config $Config --dry-run
} finally {
    Pop-Location
}
