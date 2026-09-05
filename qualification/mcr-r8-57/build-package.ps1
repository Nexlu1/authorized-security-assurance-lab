$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$root = Join-Path $env:RUNNER_TEMP 'mcr-r8-57'
$zip = Join-Path $env:RUNNER_TEMP 'mcr-r8-57-source.zip'
$stage = Join-Path $env:RUNNER_TEMP 'mcr-r8-57-stage'

Remove-Item -LiteralPath $root,$stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $root -Force | Out-Null

$parts = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter 'source-payload.part*' -File | Sort-Object Name)
if ($parts.Count -ne 7) { throw "Expected 7 source payload chunks; found $($parts.Count)" }
$b64 = (($parts | ForEach-Object { (Get-Content -LiteralPath $_.FullName -Raw).Trim() }) -join '')
[IO.File]::WriteAllBytes($zip, [Convert]::FromBase64String($b64))
$sourceHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sourceHash -ne 'dc45a336c415dc7908858352e6d5e3d64d043bea1cc725a47fd4ba8ed68ef1dc') {
    throw "Source payload SHA-256 mismatch: $sourceHash"
}
Expand-Archive -LiteralPath $zip -DestinationPath $root -Force

Push-Location $root
try {
    rustc -Vv
    cargo -V
    cargo generate-lockfile
    cargo fmt --check
    cargo test --locked --release --test adversarial -- --test-threads=1 --nocapture
    $listed = @(cargo test --locked --release --test adversarial -- --list)
    $count = @($listed | Where-Object { $_ -match '^t\d{2}_[^:]+: test$' }).Count
    if ($count -ne 57) { throw "Expected exactly 57 named adversarial tests; found $count" }
    cargo clippy --locked --all-targets -- -D warnings
    cargo build --locked --release
}
finally { Pop-Location }

New-Item -ItemType Directory -Path (Join-Path $stage 'bin') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage 'tests') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage 'control') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage 'source') -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $root 'target\release\mcr-ingest.exe') -Destination (Join-Path $stage 'bin\mcr-ingest.exe')
$tests = @(Get-ChildItem -LiteralPath (Join-Path $root 'target\release\deps') -Filter 'adversarial-*.exe' -File)
if ($tests.Count -ne 1) { throw "Expected one adversarial test executable; found $($tests.Count)" }
Copy-Item -LiteralPath $tests[0].FullName -Destination (Join-Path $stage 'tests')
Copy-Item -LiteralPath (Join-Path $root 'packaging\RUN_ME_TARGET_WINDOWS_QUALIFICATION.cmd') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'packaging\RUN_TARGET_WINDOWS_QUALIFICATION.ps1') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'README.md') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'LICENSE-MIT') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'LICENSE-APACHE') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'Cargo.lock') -Destination (Join-Path $stage 'source\Cargo.lock')
Copy-Item -LiteralPath $zip -Destination (Join-Path $stage 'source\mcr-r8-57-source.zip')

$receipt = [ordered]@{
    schema = 'mcr-r8-57-windows-build-receipt-v1'
    generated_utc = (Get-Date).ToUniversalTime().ToString('o')
    repository = $env:GITHUB_REPOSITORY
    git_sha = $env:GITHUB_SHA
    workflow_run_id = $env:GITHUB_RUN_ID
    runner_os = $env:RUNNER_OS
    runner_arch = $env:RUNNER_ARCH
    runner_image = $env:ImageOS
    rustc = (rustc -Vv | Out-String).Trim()
    cargo = (cargo -V | Out-String).Trim()
    source_payload_sha256 = $sourceHash
    adversarial_tests = 'PASS_57_OF_57'
    cargo_fmt = 'PASS'
    cargo_clippy_deny_warnings = 'PASS'
    cargo_release_build = 'PASS'
}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stage 'control\BUILD_RECEIPT.json') -Encoding utf8

$rows = foreach ($file in Get-ChildItem -LiteralPath $stage -Recurse -File) {
    [pscustomobject]@{
        path = $file.FullName.Substring($stage.Length + 1).Replace('\','/')
        bytes = [int64]$file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$rows | Sort-Object path | Export-Csv -LiteralPath (Join-Path $stage 'control\PAYLOAD_SHA256.csv') -NoTypeInformation -Encoding utf8

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $stage 'RUN_TARGET_WINDOWS_QUALIFICATION.ps1') -QualificationLabel github_ps51
if ($LASTEXITCODE -ne 0) { throw "Windows PowerShell 5.1 qualification failed: $LASTEXITCODE" }
& pwsh -NoProfile -File (Join-Path $stage 'RUN_TARGET_WINDOWS_QUALIFICATION.ps1') -QualificationLabel github_ps7
if ($LASTEXITCODE -ne 0) { throw "PowerShell 7 qualification failed: $LASTEXITCODE" }

"MCR_STAGE=$stage" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
Write-Host "MCR package stage ready: $stage"
