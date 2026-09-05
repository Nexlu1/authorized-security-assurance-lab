$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function Get-Sha256Lower {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )
    & $FilePath @ArgumentList
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Native command failed with exit code ${exitCode}: $FilePath $($ArgumentList -join ' ')"
    }
}

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$root = Join-Path $env:RUNNER_TEMP 'mcr-r8-57'
$zip = Join-Path $env:RUNNER_TEMP 'mcr-r8-57-source.zip'
$stage = Join-Path $env:RUNNER_TEMP 'mcr-r8-57-stage'

Remove-Item -LiteralPath $root, $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $root -Force | Out-Null

$parts = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter 'source-payload.part*' -File | Sort-Object Name)
if ($parts.Count -ne 7) { throw "Expected 7 source payload chunks; found $($parts.Count)" }
$b64 = (($parts | ForEach-Object { (Get-Content -LiteralPath $_.FullName -Raw).Trim() }) -join '')
[IO.File]::WriteAllBytes($zip, [Convert]::FromBase64String($b64))
$sourceHash = Get-Sha256Lower -Path $zip
if ($sourceHash -ne 'dc45a336c415dc7908858352e6d5e3d64d043bea1cc725a47fd4ba8ed68ef1dc') {
    throw "Source payload SHA-256 mismatch: $sourceHash"
}
Expand-Archive -LiteralPath $zip -DestinationPath $root -Force

# Apply two bounded, reviewable source repairs before formatting and compilation.
# The original immutable source ZIP is retained in the output package.
$patches = @()

$pathChecks = Join-Path $root 'src\path_checks.rs'
$pathChecksBefore = Get-Sha256Lower -Path $pathChecks
$pathText = [IO.File]::ReadAllText($pathChecks)
$oldBorrow = "    for seg in normalise_slashes(raw).split('/') {"
$borrowCount = ([regex]::Matches($pathText, [regex]::Escape($oldBorrow))).Count
if ($borrowCount -ne 1) { throw "Expected exactly one Rust E0716 target; found $borrowCount" }
$newLine = if ($pathText.Contains("`r`n")) { "`r`n" } else { "`n" }
$newBorrow = "    let normalized = normalise_slashes(raw);${newLine}    for seg in normalized.split('/') {"
$pathText = $pathText.Replace($oldBorrow, $newBorrow)
[IO.File]::WriteAllText($pathChecks, $pathText, [Text.UTF8Encoding]::new($false))
$pathChecksAfterTargeted = Get-Sha256Lower -Path $pathChecks
$patches += [pscustomobject]@{
    file = 'src/path_checks.rs'
    purpose = 'Fix Rust E0716 by extending the normalized String lifetime while preserving path semantics.'
    occurrences = $borrowCount
    before_sha256 = $pathChecksBefore
    after_targeted_patch_sha256 = $pathChecksAfterTargeted
}

$magic = Join-Path $root 'src\magic.rs'
$magicBefore = Get-Sha256Lower -Path $magic
$magicText = [IO.File]::ReadAllText($magic)
$oldSeverity = '    let severity = if expected == "text" && detected == "html" { Severity::High } else { Severity::High };'
$severityCount = ([regex]::Matches($magicText, [regex]::Escape($oldSeverity))).Count
if ($severityCount -ne 1) { throw "Expected exactly one identical-branches severity target; found $severityCount" }
$magicText = $magicText.Replace($oldSeverity, '    let severity = Severity::High;')
[IO.File]::WriteAllText($magic, $magicText, [Text.UTF8Encoding]::new($false))
$magicAfterTargeted = Get-Sha256Lower -Path $magic
$patches += [pscustomobject]@{
    file = 'src/magic.rs'
    purpose = 'Collapse identical branches without changing severity or behavior.'
    occurrences = $severityCount
    before_sha256 = $magicBefore
    after_targeted_patch_sha256 = $magicAfterTargeted
}

Push-Location $root
try {
    Invoke-NativeChecked -FilePath 'rustc' -ArgumentList @('-Vv')
    Invoke-NativeChecked -FilePath 'cargo' -ArgumentList @('-V')
    Invoke-NativeChecked -FilePath 'cargo' -ArgumentList @('generate-lockfile')

    # Normalize the recovered source once, then require a clean formatting gate.
    Invoke-NativeChecked -FilePath 'cargo' -ArgumentList @('fmt')
    Invoke-NativeChecked -FilePath 'cargo' -ArgumentList @('fmt', '--check')

    Invoke-NativeChecked -FilePath 'cargo' -ArgumentList @('test', '--locked', '--release', '--test', 'adversarial', '--', '--test-threads=1', '--nocapture')

    $listed = @(& cargo test --locked --release --test adversarial -- --list 2>&1)
    $listExit = $LASTEXITCODE
    if ($listExit -ne 0) { throw "Test-list command failed with exit code $listExit" }
    $count = @($listed | Where-Object { $_ -match '^t\d{2}_[^:]+: test$' }).Count
    if ($count -ne 57) { throw "Expected exactly 57 named adversarial tests; found $count" }

    Invoke-NativeChecked -FilePath 'cargo' -ArgumentList @('clippy', '--locked', '--all-targets', '--', '-D', 'warnings')
    Invoke-NativeChecked -FilePath 'cargo' -ArgumentList @('build', '--locked', '--release')
}
finally {
    Pop-Location
}

foreach ($patch in $patches) {
    $finalPath = Join-Path $root ($patch.file.Replace('/', '\'))
    $patch | Add-Member -NotePropertyName after_rustfmt_sha256 -NotePropertyValue (Get-Sha256Lower -Path $finalPath)
}

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
Copy-Item -LiteralPath $zip -Destination (Join-Path $stage 'source\mcr-r8-57-original-source.zip')
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $stage 'control\BUILD_PACKAGE_SCRIPT.ps1')

$patchReceipt = [ordered]@{
    schema = 'mcr-r8-57-source-patch-receipt-v1'
    generated_utc = (Get-Date).ToUniversalTime().ToString('o')
    original_source_zip_sha256 = $sourceHash
    policy = 'Original source ZIP retained; only the exact recorded bounded repairs and rustfmt normalization were applied before compilation.'
    patches = $patches
}
$patchReceipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $stage 'control\PATCH_RECEIPT.json') -Encoding utf8

$receipt = [ordered]@{
    schema = 'mcr-r8-57-windows-build-receipt-v2'
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
    bounded_source_repairs = $patches.Count
    adversarial_tests = 'PASS_57_OF_57'
    cargo_fmt = 'PASS_AFTER_RECORDED_NORMALIZATION'
    cargo_clippy_deny_warnings = 'PASS'
    cargo_release_build = 'PASS'
}
$receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $stage 'control\BUILD_RECEIPT.json') -Encoding utf8

$rows = foreach ($file in Get-ChildItem -LiteralPath $stage -Recurse -File) {
    [pscustomobject]@{
        path = $file.FullName.Substring($stage.Length + 1).Replace('\', '/')
        bytes = [int64]$file.Length
        sha256 = Get-Sha256Lower -Path $file.FullName
    }
}
$rows | Sort-Object path | Export-Csv -LiteralPath (Join-Path $stage 'control\PAYLOAD_SHA256.csv') -NoTypeInformation -Encoding utf8

# Exercise the exact packaged runner under both Windows shells before release.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $stage 'RUN_TARGET_WINDOWS_QUALIFICATION.ps1') -QualificationLabel github_ps51
if ($LASTEXITCODE -ne 0) { throw "Windows PowerShell 5.1 qualification failed: $LASTEXITCODE" }
& pwsh -NoProfile -File (Join-Path $stage 'RUN_TARGET_WINDOWS_QUALIFICATION.ps1') -QualificationLabel github_ps7
if ($LASTEXITCODE -ne 0) { throw "PowerShell 7 qualification failed: $LASTEXITCODE" }

"MCR_STAGE=$stage" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
Write-Host "MCR package stage ready: $stage"
