param(
    [Parameter(Mandatory=$true)] [string]$Documents,
    [string]$DatasetManifest = "",
    [Parameter(Mandatory=$true)] [string]$Chunks,
    [Parameter(Mandatory=$true)] [string]$Questions,
    [Parameter(Mandatory=$true)] [string]$DocumentQrels,
    [Parameter(Mandatory=$true)] [string]$ChunkQrels
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$datasetDir = Join-Path $root "data\processed\ontong_youth_full_v1"
$evalDir = Join-Path $root "data\evaluation\eval_full_v1"

New-Item -ItemType Directory -Force -Path $datasetDir | Out-Null
New-Item -ItemType Directory -Force -Path $evalDir | Out-Null

Copy-Item $Documents (Join-Path $datasetDir "documents.jsonl") -Force
if ($DatasetManifest -and (Test-Path $DatasetManifest)) {
    Copy-Item $DatasetManifest (Join-Path $datasetDir "dataset_manifest.json") -Force
}
Copy-Item $Chunks (Join-Path $datasetDir "chunks.jsonl") -Force
Copy-Item $Questions (Join-Path $evalDir "eval_questions.jsonl") -Force
Copy-Item $DocumentQrels (Join-Path $evalDir "qrels.jsonl") -Force
Copy-Item $ChunkQrels (Join-Path $evalDir "qrels_chunk.jsonl") -Force

Write-Host "Input files copied under: $root\data"
Write-Host "Next: .\scripts\run_checks.ps1"
