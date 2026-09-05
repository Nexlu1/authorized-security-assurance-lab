[CmdletBinding()]
param([switch]$SelfTest)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if ($SelfTest) {
    $rows = @()
    $rows += [pscustomobject]@{name='alpha'; exit_code=0}
    $rows += [pscustomobject]@{name='beta'; exit_code=0}
    $receipt = [ordered]@{schema='mcr-windows-runner-self-test-v1'; status='PASS'; rows=$rows}
    $json = $receipt | ConvertTo-Json -Depth 8
    $parsed = $json | ConvertFrom-Json
    if ($parsed.rows.Count -ne 2) { throw 'Self-test array serialization failed.' }
    Write-Host 'PASS_SELF_TEST'
    exit 0
}

$Root = $PSScriptRoot
$Manifest = Join-Path $Root 'PAYLOAD_SHA256.csv'
if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) { throw 'PAYLOAD_SHA256.csv missing.' }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Results = Join-Path $Root ('results_' + $stamp)
New-Item -ItemType Directory -Path $Results -Force | Out-Null
$log = Join-Path $Results 'RUN.log'
function Log([string]$Message) {
    $line = ('[{0}] {1}' -f (Get-Date -Format s), $Message)
    $line | Tee-Object -FilePath $log -Append | Write-Host
}

$failures = @()
$manifestRows = Import-Csv -LiteralPath $Manifest
Log ('Verifying {0} package files.' -f $manifestRows.Count)
foreach ($row in $manifestRows) {
    $path = Join-Path $Root ($row.path -replace '/', [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $failures += [pscustomobject]@{stage='hash'; item=$row.path; error='missing'}
        continue
    }
    $actualLength = (Get-Item -LiteralPath $path).Length
    if ([int64]$row.bytes -ne $actualLength) {
        $failures += [pscustomobject]@{stage='hash'; item=$row.path; error=('size {0} != {1}' -f $actualLength,$row.bytes)}
        continue
    }
    $actualHash = Get-FileSha256 $path
    if ($actualHash -ne $row.sha256.ToLowerInvariant()) {
        $failures += [pscustomobject]@{stage='hash'; item=$row.path; error=('sha256 {0} != {1}' -f $actualHash,$row.sha256)}
    }
}
if ($failures.Count -gt 0) {
    $failures | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath (Join-Path $Results 'FAILURES.csv')
    throw ('Package verification failed: {0} error(s).' -f $failures.Count)
}
Log 'Package hashes PASS.'

$toolConfig = Get-Content -LiteralPath (Join-Path $Root 'controls\TOOL_ENTRYPOINTS.json') -Raw | ConvertFrom-Json
$qpdf = Join-Path $Root ($toolConfig.'qpdf.exe'.path -replace '/', [IO.Path]::DirectorySeparatorChar)
$pdfcpu = Join-Path $Root ($toolConfig.'pdfcpu.exe'.path -replace '/', [IO.Path]::DirectorySeparatorChar)
$env:MCR_QPDF_EXE = $qpdf
$env:MCR_QPDF_SHA256 = Get-FileSha256 $qpdf
$env:MCR_PDFCPU_EXE = $pdfcpu
$env:MCR_PDFCPU_SHA256 = Get-FileSha256 $pdfcpu

$testFiles = @(Get-ChildItem -LiteralPath (Join-Path $Root 'tests') -File -Filter '*.exe' | Sort-Object Name)
if ($testFiles.Count -lt 1) { throw 'No Windows Rust test executables found.' }
$testResults = @()
$totalPassed = 0
$totalFailed = 0
foreach ($test in $testFiles) {
    $stdout = Join-Path $Results ($test.BaseName + '.stdout.txt')
    $stderr = Join-Path $Results ($test.BaseName + '.stderr.txt')
    Log ('Running {0}' -f $test.Name)
    $process = Start-Process -FilePath $test.FullName -ArgumentList '--test-threads=1','--nocapture' -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $text = ''
    if (Test-Path -LiteralPath $stdout) { $text += Get-Content -LiteralPath $stdout -Raw }
    if (Test-Path -LiteralPath $stderr) { $text += "`n" + (Get-Content -LiteralPath $stderr -Raw) }
    $passed = 0
    $failed = 0
    if ($text -match 'test result:\s+\w+\.\s+(\d+) passed;\s+(\d+) failed') {
        $passed = [int]$Matches[1]
        $failed = [int]$Matches[2]
    }
    $totalPassed += $passed
    $totalFailed += $failed
    $testResults += [pscustomobject]@{name=$test.Name; exit_code=$process.ExitCode; passed=$passed; failed=$failed; stdout=(Split-Path $stdout -Leaf); stderr=(Split-Path $stderr -Leaf)}
    if ($process.ExitCode -ne 0) { $failures += [pscustomobject]@{stage='rust-test'; item=$test.Name; error=('exit ' + $process.ExitCode)} }
}

$runtimePlan = Get-Content -LiteralPath (Join-Path $Root 'controls\RUNTIME_PLAN.json') -Raw | ConvertFrom-Json
$smokeResult = $null
if ($runtimePlan.smoke_command) {
    $main = Join-Path $Root 'bin\mcr-ingest.exe'
    $smokeOut = Join-Path $Results 'mcr-ingest-smoke.stdout.txt'
    $smokeErr = Join-Path $Results 'mcr-ingest-smoke.stderr.txt'
    $process = Start-Process -FilePath $main -ArgumentList ([string]$runtimePlan.smoke_command) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $smokeOut -RedirectStandardError $smokeErr
    $smokeResult = [pscustomobject]@{command=$runtimePlan.smoke_command; exit_code=$process.ExitCode; stdout=(Split-Path $smokeOut -Leaf); stderr=(Split-Path $smokeErr -Leaf)}
    if ($process.ExitCode -ne 0) { $failures += [pscustomobject]@{stage='smoke'; item='mcr-ingest.exe'; error=('exit ' + $process.ExitCode)} }
}

$status = if ($failures.Count -eq 0 -and $totalFailed -eq 0) { 'PASS_TARGET_WINDOWS_RUNTIME' } else { 'FAIL_TARGET_WINDOWS_RUNTIME' }
$receipt = [ordered]@{
    schema='mcr-r8-target-windows-qualification-receipt-v1'
    status=$status
    generated=(Get-Date).ToUniversalTime().ToString('o')
    computer_name=$env:COMPUTERNAME
    os=[Environment]::OSVersion.VersionString
    powershell=$PSVersionTable.PSVersion.ToString()
    package_manifest_sha256=(Get-FileSha256 $Manifest)
    test_executable_count=$testFiles.Count
    rust_tests_passed=$totalPassed
    rust_tests_failed=$totalFailed
    tests=$testResults
    smoke=$smokeResult
    failures=$failures
}
$receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $Results 'TARGET_WINDOWS_QUALIFICATION.json') -Encoding UTF8
$testResults | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath (Join-Path $Results 'TEST_RESULTS.csv')
if ($failures.Count -gt 0) { $failures | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath (Join-Path $Results 'FAILURES.csv') }
$resultsZip = Join-Path $Root ('MCR_R8_TARGET_WINDOWS_RESULTS_TO_UPLOAD_' + $stamp + '.zip')
Compress-Archive -LiteralPath (Join-Path $Results '*') -DestinationPath $resultsZip -Force
Log ('Final status: {0}' -f $status)
Log ('Results ZIP: {0}' -f $resultsZip)
if ($status -ne 'PASS_TARGET_WINDOWS_RUNTIME') { exit 1 }
exit 0
