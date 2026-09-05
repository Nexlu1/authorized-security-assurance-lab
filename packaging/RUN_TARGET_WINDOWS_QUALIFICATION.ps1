[CmdletBinding()]
param(
    [string]$QualificationLabel = 'target'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$Root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$ManifestPath = Join-Path $Root 'control\PAYLOAD_SHA256.csv'
$ResultsDir = Join-Path $Root ('results_' + $QualificationLabel)
$Timestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd_HHmmss')
$ResultZip = Join-Path $Root ("MCR_R8_TARGET_WINDOWS_RESULTS_TO_UPLOAD_{0}_{1}.zip" -f $QualificationLabel,$Timestamp)

function Get-Sha256Lower([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Invoke-NativeCaptured(
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$StdoutPath,
    [string]$StderrPath
) {
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
    return [int]$process.ExitCode
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'This qualification package must run on Windows.'
    }
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "Missing payload manifest: $ManifestPath"
    }

    if (Test-Path -LiteralPath $ResultsDir) {
        Remove-Item -LiteralPath $ResultsDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null

    $manifestRows = @(Import-Csv -LiteralPath $ManifestPath)
    if ($manifestRows.Count -lt 4) {
        throw "Payload manifest is unexpectedly small: $($manifestRows.Count) rows"
    }

    $hashFailures = New-Object System.Collections.ArrayList
    foreach ($row in $manifestRows) {
        $relative = [string]$row.path
        $expectedBytes = [int64]$row.bytes
        $expectedHash = ([string]$row.sha256).ToLowerInvariant()
        $fullPath = Join-Path $Root ($relative -replace '/', '\')
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            [void]$hashFailures.Add([pscustomobject]@{ path=$relative; problem='missing'; expected=$expectedHash; actual=$null })
            continue
        }
        $item = Get-Item -LiteralPath $fullPath
        if ([int64]$item.Length -ne $expectedBytes) {
            [void]$hashFailures.Add([pscustomobject]@{ path=$relative; problem='size'; expected=$expectedBytes; actual=[int64]$item.Length })
            continue
        }
        $actualHash = Get-Sha256Lower $fullPath
        if ($actualHash -ne $expectedHash) {
            [void]$hashFailures.Add([pscustomobject]@{ path=$relative; problem='sha256'; expected=$expectedHash; actual=$actualHash })
        }
    }
    if ($hashFailures.Count -gt 0) {
        $hashFailures | Export-Csv -LiteralPath (Join-Path $ResultsDir 'PAYLOAD_HASH_FAILURES.csv') -NoTypeInformation -Encoding UTF8
        throw "Payload integrity failed: $($hashFailures.Count) problem(s)"
    }

    $MainExe = Join-Path $Root 'bin\mcr-ingest.exe'
    $testFiles = @(Get-ChildItem -LiteralPath (Join-Path $Root 'tests') -Filter 'adversarial-*.exe' -File)
    if ($testFiles.Count -ne 1) {
        throw "Expected exactly one adversarial test executable; found $($testFiles.Count)"
    }
    $TestExe = $testFiles[0].FullName

    $TestStdout = Join-Path $ResultsDir 'adversarial_tests_stdout.txt'
    $TestStderr = Join-Path $ResultsDir 'adversarial_tests_stderr.txt'
    $testExit = Invoke-NativeCaptured $TestExe @('--test-threads=1','--nocapture') $TestStdout $TestStderr
    $testText = ''
    if (Test-Path -LiteralPath $TestStdout) { $testText += [System.IO.File]::ReadAllText($TestStdout) }
    if (Test-Path -LiteralPath $TestStderr) { $testText += "`r`n" + [System.IO.File]::ReadAllText($TestStderr) }
    $testSummaryMatch = [regex]::Match($testText, 'test result:\s+ok\.\s+57 passed;\s+0 failed;', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if ($testExit -ne 0 -or -not $testSummaryMatch.Success) {
        throw "Adversarial suite failed or did not prove 57/57: exit=$testExit"
    }

    $SmokeRoot = Join-Path $ResultsDir 'smoke_input'
    $SmokeManifest = Join-Path $ResultsDir 'smoke_manifest.json'
    $SmokeReport = Join-Path $ResultsDir 'smoke_report.md'
    New-Item -ItemType Directory -Path $SmokeRoot -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $SmokeRoot 'safe.txt'), 'synthetic safe evidence', (New-Object System.Text.UTF8Encoding($false)))

    $ScanStdout = Join-Path $ResultsDir 'scan_stdout.txt'
    $ScanStderr = Join-Path $ResultsDir 'scan_stderr.txt'
    $scanExit = Invoke-NativeCaptured $MainExe @('scan',$SmokeRoot,'--output',$SmokeManifest,'--report',$SmokeReport) $ScanStdout $ScanStderr
    if ($scanExit -ne 0 -or -not (Test-Path -LiteralPath $SmokeManifest -PathType Leaf)) {
        throw "mcr-ingest scan smoke test failed: exit=$scanExit"
    }

    $VerifyStdout = Join-Path $ResultsDir 'verify_stdout.txt'
    $VerifyStderr = Join-Path $ResultsDir 'verify_stderr.txt'
    $verifyExit = Invoke-NativeCaptured $MainExe @('verify',$SmokeManifest) $VerifyStdout $VerifyStderr
    if ($verifyExit -ne 0) {
        throw "mcr-ingest manifest verification failed: exit=$verifyExit"
    }

    $record = [ordered]@{
        schema = 'mcr-r8-target-windows-qualification-result-v2'
        status = 'PASS_57_OF_57_AND_RUNTIME_SMOKE'
        generated_utc = (Get-Date).ToUniversalTime().ToString('o')
        qualification_label = $QualificationLabel
        computer_name = $env:COMPUTERNAME
        os_version = [Environment]::OSVersion.VersionString
        os_is_64_bit = [Environment]::Is64BitOperatingSystem
        process_is_64_bit = [Environment]::Is64BitProcess
        powershell = $PSVersionTable.PSVersion.ToString()
        payload_manifest_rows = $manifestRows.Count
        payload_integrity = 'PASS'
        adversarial_test_executable = (Split-Path -Leaf $TestExe)
        adversarial_test_executable_sha256 = Get-Sha256Lower $TestExe
        adversarial_test_exit_code = $testExit
        adversarial_tests = 'PASS_57_OF_57'
        main_executable_sha256 = Get-Sha256Lower $MainExe
        scan_exit_code = $scanExit
        verify_exit_code = $verifyExit
        runtime_smoke = 'PASS'
        network_required = $false
        administrator_required = $false
    }
    $ResultJson = Join-Path $ResultsDir 'MCR_R8_TARGET_WINDOWS_QUALIFICATION_RESULT.json'
    $json = $record | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($ResultJson, $json, (New-Object System.Text.UTF8Encoding($false)))

    $resultFiles = @(Get-ChildItem -LiteralPath $ResultsDir -Recurse -File)
    $resultManifest = foreach ($file in $resultFiles) {
        [pscustomobject]@{
            path = $file.FullName.Substring($ResultsDir.Length + 1).Replace('\','/')
            bytes = [int64]$file.Length
            sha256 = Get-Sha256Lower $file.FullName
        }
    }
    $resultManifest | Sort-Object path | Export-Csv -LiteralPath (Join-Path $ResultsDir 'RESULT_SHA256.csv') -NoTypeInformation -Encoding UTF8

    if (Test-Path -LiteralPath $ResultZip) { Remove-Item -LiteralPath $ResultZip -Force }
    Compress-Archive -Path (Join-Path $ResultsDir '*') -DestinationPath $ResultZip -CompressionLevel Optimal -Force

    Write-Host ''
    Write-Host 'PASS: 57/57 adversarial tests and runtime smoke tests passed.' -ForegroundColor Green
    Write-Host "Results ZIP: $ResultZip" -ForegroundColor Cyan
    exit 0
}
catch {
    $message = $_.Exception.Message
    try {
        if (-not (Test-Path -LiteralPath $ResultsDir)) { New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null }
        [System.IO.File]::WriteAllText((Join-Path $ResultsDir 'FAILURE.txt'), $message, (New-Object System.Text.UTF8Encoding($false)))
        $failureRecord = [ordered]@{
            schema = 'mcr-r8-target-windows-qualification-failure-v2'
            status = 'FAIL_REVIEW_REQUIRED'
            generated_utc = (Get-Date).ToUniversalTime().ToString('o')
            qualification_label = $QualificationLabel
            message = $message
            powershell = $PSVersionTable.PSVersion.ToString()
            os_version = [Environment]::OSVersion.VersionString
        }
        [System.IO.File]::WriteAllText((Join-Path $ResultsDir 'FAILURE.json'), ($failureRecord | ConvertTo-Json -Depth 8), (New-Object System.Text.UTF8Encoding($false)))
        if (Test-Path -LiteralPath $ResultZip) { Remove-Item -LiteralPath $ResultZip -Force }
        Compress-Archive -Path (Join-Path $ResultsDir '*') -DestinationPath $ResultZip -CompressionLevel Optimal -Force
    } catch {}
    Write-Host ''
    Write-Host "FAIL: $message" -ForegroundColor Red
    Write-Host "Results ZIP: $ResultZip" -ForegroundColor Yellow
    exit 1
}
