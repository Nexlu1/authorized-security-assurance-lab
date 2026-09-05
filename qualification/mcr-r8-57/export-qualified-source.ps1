$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function Get-Sha256Lower {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$root = Join-Path $env:RUNNER_TEMP 'mcr-r8-57'
if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "Qualified source root not found: $root" }
if (-not $env:MCR_STAGE) { throw 'MCR_STAGE is not set.' }
$dest = Join-Path $env:MCR_STAGE 'source\qualified'
Remove-Item -LiteralPath $dest -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $dest -Force | Out-Null

$topFiles = @('Cargo.toml','Cargo.lock','README.md','LICENSE-MIT','LICENSE-APACHE')
foreach ($name in $topFiles) {
    $src = Join-Path $root $name
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw "Required qualified source file missing: $src" }
    Copy-Item -LiteralPath $src -Destination (Join-Path $dest $name)
}
foreach ($dir in @('src','tests','packaging')) {
    $src = Join-Path $root $dir
    if (-not (Test-Path -LiteralPath $src -PathType Container)) { throw "Required qualified source directory missing: $src" }
    Copy-Item -LiteralPath $src -Destination $dest -Recurse
}

$rows = foreach ($file in Get-ChildItem -LiteralPath $dest -Recurse -File) {
    [pscustomobject]@{
        path = $file.FullName.Substring($dest.Length + 1).Replace('\','/')
        bytes = [int64]$file.Length
        sha256 = Get-Sha256Lower -Path $file.FullName
    }
}
$rows = @($rows | Sort-Object path)
if ($rows.Count -lt 10) { throw "Unexpectedly small qualified source export: $($rows.Count) files" }
$rows | Export-Csv -LiteralPath (Join-Path $env:MCR_STAGE 'control\QUALIFIED_SOURCE_SHA256.csv') -NoTypeInformation -Encoding utf8

$receipt = [ordered]@{
    schema = 'mcr-r8-57-qualified-source-export-v1'
    generated_utc = (Get-Date).ToUniversalTime().ToString('o')
    git_sha = $env:GITHUB_SHA
    workflow_run_id = $env:GITHUB_RUN_ID
    qualified_source_files = $rows.Count
    source_root = 'source/qualified'
    exact_build_receipt = 'control/BUILD_RECEIPT.json'
    exact_patch_receipt = 'control/PATCH_RECEIPT.json'
    manifest = 'control/QUALIFIED_SOURCE_SHA256.csv'
}
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $env:MCR_STAGE 'control\QUALIFIED_SOURCE_EXPORT.json') -Encoding utf8
Write-Host "Exported $($rows.Count) exact qualified source files to $dest"
