$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

if (-not $env:MCR_STAGE) { throw 'MCR_STAGE is not set.' }
if (-not $env:GITHUB_TOKEN) { throw 'GITHUB_TOKEN is not set.' }
if (-not $env:GITHUB_REPOSITORY) { throw 'GITHUB_REPOSITORY is not set.' }

$source = Join-Path $env:MCR_STAGE 'source\qualified'
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Qualified source is missing: $source" }
$publish = Join-Path $env:RUNNER_TEMP 'mcr-r8-57-qualified-publish'
Remove-Item -LiteralPath $publish -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $publish -Force | Out-Null

Push-Location $publish
try {
    git init
    git config user.name 'github-actions[bot]'
    git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

    Copy-Item -LiteralPath (Join-Path $source 'Cargo.toml') -Destination $publish
    Copy-Item -LiteralPath (Join-Path $source 'Cargo.lock') -Destination $publish
    Copy-Item -LiteralPath (Join-Path $source 'README.md') -Destination $publish
    Copy-Item -LiteralPath (Join-Path $source 'LICENSE-MIT') -Destination $publish
    Copy-Item -LiteralPath (Join-Path $source 'LICENSE-APACHE') -Destination $publish
    Copy-Item -LiteralPath (Join-Path $source 'src') -Destination $publish -Recurse
    Copy-Item -LiteralPath (Join-Path $source 'tests') -Destination $publish -Recurse
    Copy-Item -LiteralPath (Join-Path $source 'packaging') -Destination $publish -Recurse
    New-Item -ItemType Directory -Path (Join-Path $publish 'qualification') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $env:MCR_STAGE 'control\BUILD_RECEIPT.json') -Destination (Join-Path $publish 'qualification\BUILD_RECEIPT.json')
    Copy-Item -LiteralPath (Join-Path $env:MCR_STAGE 'control\PATCH_RECEIPT.json') -Destination (Join-Path $publish 'qualification\PATCH_RECEIPT.json')
    Copy-Item -LiteralPath (Join-Path $env:MCR_STAGE 'control\QUALIFIED_SOURCE_SHA256.csv') -Destination (Join-Path $publish 'qualification\QUALIFIED_SOURCE_SHA256.csv')
    Copy-Item -LiteralPath (Join-Path $env:MCR_STAGE 'control\QUALIFIED_SOURCE_EXPORT.json') -Destination (Join-Path $publish 'qualification\QUALIFIED_SOURCE_EXPORT.json')

    @"
# Qualified MCR R8 57-test safety-core source

This branch contains the exact patched and rustfmt-normalized source bytes used by the passing Windows Server 2025 qualification for workflow run $env:GITHUB_RUN_ID.

It is synthetic-only future tooling. It is **not** the frozen MCR R59 record and it is **not** a complete R2 PDF/OOXML/MBOX/SQLite qualification.

Source provenance and hashes are under `qualification/`.
"@ | Set-Content -LiteralPath (Join-Path $publish 'QUALIFIED_SOURCE_README.md') -Encoding utf8

    git add --all
    git commit -m "qualified: exact 57-test safety-core source from run $env:GITHUB_RUN_ID"
    $auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("x-access-token:$env:GITHUB_TOKEN"))
    git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $auth" push --force "https://github.com/$env:GITHUB_REPOSITORY.git" HEAD:refs/heads/qualified/mcr-r8-57-safety-core-v1
    if ($LASTEXITCODE -ne 0) { throw "git push failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}
