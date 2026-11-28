$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$evalDir = Join-Path $root "data\evaluation\eval_200_v1"
$chunkDir = Join-Path $root "data\processed\ontong_youth_full_v1\chunks\eval_200_v1\fixed_800_ov120_v1"

$required = @(
    (Join-Path $evalDir "eval_questions.jsonl"),
    (Join-Path $evalDir "qrels.jsonl"),
    (Join-Path $evalDir "context_eval_200_v1\fixed_800_ov120_v1\qrels_chunk.jsonl"),
    (Join-Path $evalDir "context_eval_200_v1\required_facts.jsonl"),
    (Join-Path $evalDir "context_eval_200_v1\fixed_800_ov120_v1\chunk_fact_map.jsonl"),
    (Join-Path $chunkDir "chunks.jsonl"),
    (Join-Path $chunkDir "chunk_manifest.json")
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "GitHub의 200문항 입력 파일이 없습니다. git pull 후 다시 실행하세요: $path"
    }
}

$questions = Get-Content (Join-Path $evalDir "eval_questions.jsonl") -Encoding UTF8 |
    Where-Object { $_.Trim() } |
    ForEach-Object { $_ | ConvertFrom-Json }
$questionIds = @($questions | ForEach-Object { $_.query_id })
$uniqueIds = @($questionIds | Sort-Object -Unique)

if ($questions.Count -ne 200 -or $uniqueIds.Count -ne 200) {
    throw "평가 질문은 고유 ID 200개여야 합니다. rows=$($questions.Count), unique=$($uniqueIds.Count)"
}

Write-Host "GitHub eval_200_v1 확인 완료: 질문 200개, fixed/800/120 청크 및 qrels 준비됨"
