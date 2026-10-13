$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    python -m pip freeze | Out-File -Encoding utf8 requirements-lock.txt
    Write-Host "Created: $root\requirements-lock.txt"
} finally {
    Pop-Location
}
