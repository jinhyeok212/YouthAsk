param(
    [ValidateSet("kure-v3", "snowflake")]
    [string]$Model = "snowflake",
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv-embedding"
$config = if ($Model -eq "kure-v3") {
    "configs\experiments\exp_model_kure_v3_eval200.yaml"
} else {
    "configs\experiments\exp_model_snowflake_arctic_l_v2_ko_eval200.yaml"
}

Push-Location $root
try {
    if (-not (Test-Path $venv)) {
        py -3.11 -m venv $venv
    }
    $python = Join-Path $venv "Scripts\python.exe"
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements-experiments.txt
    & $python -m pytest -q tests
    & $python scripts\doctor.py --config $config
    & $python -m src.experiments.runner --config $config --validate-only
    & $python -m src.experiments.runner --config $config --dry-run
    if ($Run) {
        & $python run_experiment.py --config $config
    } else {
        Write-Host "검증 완료. 실제 실행은 -Run 옵션을 추가하세요."
    }
} finally {
    Pop-Location
}
