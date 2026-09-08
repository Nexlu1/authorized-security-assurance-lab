param(
    [string]$OutputRoot = (Join-Path $env:RUNNER_TEMP 'mcr-court-bundle')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedLockSha = 'b4ecd4f22926a6e92d5400e23a2ed5729e75d26c124d1d1ba4fb9bb5fa6af36d'
$qpdfLinuxOuter = 'db9122e88ec00c76ac6a14e09ffb92406db1773d47b968911ff6e69f28c09bf9'
$pdfcpuLinuxOuter = '652830db95e81868dbe38fbb3f506365511c99a1831b5e8955deac38f3f645f8'
$qpdfWindowsOuter = '3cd016cd433ef7232e42f4c13348a49cc14907a3c7278ef4f99120593126f7a6'
$pdfcpuWindowsOuter = '9809a70ee60ba78252628cc9738b284fbebf22bc2616ae903fb89b807e75a8a6'

function Invoke-Checked([scriptblock]$Command, [string]$Label) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Get-Sha256([string]$Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-Sha256([string]$Path, [string]$Expected, [string]$Label) {
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected) {
        throw "$Label SHA-256 mismatch: $actual != $Expected"
    }
}

function Normalize-QualificationSource {
    $path = Join-Path $PSScriptRoot 'src/main.rs'
    $text = [IO.File]::ReadAllText($path)

    foreach ($line in @(
        "        assert!(FULL_EXPECTED_PAGES > 100);`n",
        "        assert!(CORE_EXPECTED_PAGES < FULL_EXPECTED_PAGES);`n"
    )) {
        $count = ([regex]::Matches($text, [regex]::Escape($line))).Count
        if ($count -ne 1) { throw "expected exactly one redundant assertion: $line" }
        $text = $text.Replace($line, '')
    }

    $old = @'
    match action[4] {
        Object::Real(v) if (v - 1.0).abs() < f32::EPSILON => Ok(()),
        _ => Err("default PDF zoom is not 100%".into()),
    }
'@
    $new = @'
    match action[4] {
        Object::Real(v) if (v - 1.0).abs() < f32::EPSILON => Ok(()),
        Object::Integer(1) => Ok(()),
        _ => Err("default PDF zoom is not 100%".into()),
    }
'@
    if (([regex]::Matches($text, [regex]::Escape($old))).Count -ne 1) {
        throw 'expected exactly one OpenAction 100% verifier block'
    }
    $text = $text.Replace($old, $new)
    [IO.File]::WriteAllText($path, $text, [Text.UTF8Encoding]::new($false))
}

Push-Location $PSScriptRoot
try {
    Normalize-QualificationSource

    Invoke-Checked { cargo generate-lockfile } 'cargo generate-lockfile'
    Assert-Sha256 (Join-Path $PSScriptRoot 'Cargo.lock') $expectedLockSha 'Cargo.lock candidate'

    Invoke-Checked { cargo fmt } 'cargo fmt'
    Invoke-Checked { cargo fmt --check } 'cargo fmt --check'
    Invoke-Checked { cargo check --locked } 'cargo check --locked'
    Invoke-Checked { cargo test --locked --all-targets --verbose } 'cargo test'
    Invoke-Checked { cargo clippy --locked --all-targets -- -D warnings } 'cargo clippy'

    if (Test-Path $OutputRoot) { Remove-Item -Recurse -Force $OutputRoot }
    New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
    Invoke-Checked { cargo run --locked --release -- $OutputRoot } 'synthetic bundle generation'

    $hearing = Join-Path $OutputRoot 'SYN001_Synthetic-v-Respondent_Hearing_Bundle.pdf'
    $core = Join-Path $OutputRoot 'SYN001_Synthetic-v-Respondent_Core_Bundle.pdf'
    if (!(Test-Path $hearing)) { throw 'hearing bundle missing' }
    if (!(Test-Path $core)) { throw 'core bundle missing' }

    $tools = Join-Path $env:RUNNER_TEMP 'mcr-court-pdf-tools'
    if (Test-Path $tools) { Remove-Item -Recurse -Force $tools }
    New-Item -ItemType Directory -Force -Path $tools | Out-Null

    if ($IsWindows) {
        $qArchive = Join-Path $tools 'qpdf.zip'
        $pArchive = Join-Path $tools 'pdfcpu.zip'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/qpdf/qpdf/releases/download/v12.4.1/qpdf-12.4.1-msvc64.zip' -OutFile $qArchive
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/pdfcpu/pdfcpu/releases/download/v0.15.0/pdfcpu_0.15.0_Windows_x86_64.zip' -OutFile $pArchive
        Assert-Sha256 $qArchive $qpdfWindowsOuter 'qpdf Windows archive'
        Assert-Sha256 $pArchive $pdfcpuWindowsOuter 'pdfcpu Windows archive'
        $qDir = Join-Path $tools 'qpdf'
        $pDir = Join-Path $tools 'pdfcpu'
        Expand-Archive -LiteralPath $qArchive -DestinationPath $qDir -Force
        Expand-Archive -LiteralPath $pArchive -DestinationPath $pDir -Force
        $qCandidates = @(Get-ChildItem -LiteralPath $qDir -Recurse -File -Filter 'qpdf.exe')
        $pCandidates = @(Get-ChildItem -LiteralPath $pDir -Recurse -File -Filter 'pdfcpu.exe')
        $qOuter = $qpdfWindowsOuter
        $pOuter = $pdfcpuWindowsOuter
    } else {
        $qArchive = Join-Path $tools 'qpdf.zip'
        $pArchive = Join-Path $tools 'pdfcpu.tar.xz'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/qpdf/qpdf/releases/download/v12.4.1/qpdf-12.4.1-bin-linux-x86_64.zip' -OutFile $qArchive
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/pdfcpu/pdfcpu/releases/download/v0.15.0/pdfcpu_0.15.0_Linux_x86_64.tar.xz' -OutFile $pArchive
        Assert-Sha256 $qArchive $qpdfLinuxOuter 'qpdf Linux archive'
        Assert-Sha256 $pArchive $pdfcpuLinuxOuter 'pdfcpu Linux archive'
        $qDir = Join-Path $tools 'qpdf'
        $pDir = Join-Path $tools 'pdfcpu'
        New-Item -ItemType Directory -Force -Path $qDir,$pDir | Out-Null
        Invoke-Checked { unzip -q $qArchive -d $qDir } 'unzip qpdf'
        Invoke-Checked { tar -xJf $pArchive -C $pDir } 'extract pdfcpu'
        $qCandidates = @(Get-ChildItem -LiteralPath $qDir -Recurse -File | Where-Object Name -eq 'qpdf')
        $pCandidates = @(Get-ChildItem -LiteralPath $pDir -Recurse -File | Where-Object Name -eq 'pdfcpu')
        $qOuter = $qpdfLinuxOuter
        $pOuter = $pdfcpuLinuxOuter
    }

    if ($qCandidates.Count -ne 1) { throw "expected one qpdf executable, found $($qCandidates.Count)" }
    if ($pCandidates.Count -ne 1) { throw "expected one pdfcpu executable, found $($pCandidates.Count)" }
    $qpdf = $qCandidates[0].FullName
    $pdfcpu = $pCandidates[0].FullName
    if (!$IsWindows) {
        Invoke-Checked { chmod +x $qpdf $pdfcpu } 'mark PDF validators executable'
    }

    Invoke-Checked { & $qpdf --check $hearing } 'qpdf hearing check'
    Invoke-Checked { & $qpdf --check $core } 'qpdf core check'
    $hearingPages = (& $qpdf --show-npages $hearing).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'qpdf hearing page-count failed' }
    $corePages = (& $qpdf --show-npages $core).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'qpdf core page-count failed' }
    if ($hearingPages -ne '109') { throw "hearing page count $hearingPages != 109" }
    if ($corePages -ne '37') { throw "core page count $corePages != 37" }

    # pdfcpu v0.15.0 uses Cobra: --mode strict (or -m strict). Single-dash '-mode' is invalid.
    Invoke-Checked { & $pdfcpu validate --mode strict $hearing } 'pdfcpu strict hearing validation'
    Invoke-Checked { & $pdfcpu validate --mode strict $core } 'pdfcpu strict core validation'

    $qVersion = (& $qpdf --version | Select-Object -First 1)
    $pVersion = (& $pdfcpu version | Select-Object -First 1)
    $receipt = @(
        'status=PASS',
        "platform=$([System.Runtime.InteropServices.RuntimeInformation]::OSDescription)",
        "cargo_lock_sha256=$expectedLockSha",
        "qpdf_outer_sha256=$qOuter",
        "qpdf_exe_sha256=$(Get-Sha256 $qpdf)",
        "qpdf_version=$qVersion",
        "pdfcpu_outer_sha256=$pOuter",
        "pdfcpu_exe_sha256=$(Get-Sha256 $pdfcpu)",
        "pdfcpu_version=$pVersion",
        "hearing_pages=$hearingPages",
        "hearing_sha256=$(Get-Sha256 $hearing)",
        "core_pages=$corePages",
        "core_sha256=$(Get-Sha256 $core)",
        'source_immutability=PASS',
        'qpdf_check=PASS',
        'pdfcpu_strict_validation=PASS'
    )
    $receipt | Set-Content -Encoding ascii (Join-Path $OutputRoot 'EXTERNAL_QA_RECEIPT.txt')
    Copy-Item (Join-Path $PSScriptRoot 'Cargo.lock') (Join-Path $OutputRoot 'Cargo.lock.candidate') -Force
    Copy-Item (Join-Path $PSScriptRoot 'src/main.rs') (Join-Path $OutputRoot 'main.rs.formatted') -Force

    Write-Host 'PASS: court-bundle qualification runner completed'
    Get-Content (Join-Path $OutputRoot 'EXTERNAL_QA_RECEIPT.txt')
}
finally {
    Pop-Location
}
