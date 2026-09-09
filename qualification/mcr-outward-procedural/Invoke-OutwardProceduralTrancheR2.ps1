param(
    [string]$OutputRoot = 'F:\MCR_OUTWARD_REHEARSAL_R2',
    [string]$ToolsRoot = 'E:\MCR_GITHUB_DONORS',
    [string]$ResultsRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PackageRoot)
if (!$ResultsRoot) {
    $ResultsRoot = if (Test-Path 'G:\') { 'G:\MCR_OUTWARD_REHEARSAL_RESULTS' } else { 'E:\MCR_OUTWARD_REHEARSAL_RESULTS' }
}

function Get-Sha256([string]$Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-NotC([string]$Path, [string]$Label) {
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    if ($root -and $root.TrimEnd('\') -ieq 'C:') {
        throw "$Label resolves to prohibited project storage on C: $full"
    }
}

function Assert-Drive([string]$Path, [string[]]$AllowedDrives, [string]$Label) {
    $full = [IO.Path]::GetFullPath($Path)
    $drive = [IO.Path]::GetPathRoot($full).TrimEnd('\').ToUpperInvariant()
    if ($drive -notin $AllowedDrives) {
        throw "$Label must use $($AllowedDrives -join ' or '): $full"
    }
}

function Assert-Sha256([string]$Path, [string]$Expected, [string]$Label) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label missing: $Path" }
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "$Label SHA-256 mismatch: $actual != $Expected"
    }
}

function Invoke-NativeChecked(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$Label
) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
}

function Invoke-NativeText(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$Label
) {
    $text = (& $FilePath @Arguments 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE`n$text" }
    $text
}

function Download-Exact(
    [string]$Url,
    [string]$Destination,
    [string]$ExpectedSha256,
    [string]$Label
) {
    if (Test-Path -LiteralPath $Destination) {
        if ((Get-Sha256 $Destination) -eq $ExpectedSha256) { return }
        Remove-Item -Force -LiteralPath $Destination
    }
    Invoke-NativeChecked 'curl.exe' @(
        '--location', '--fail', '--retry', '5', '--retry-delay', '2',
        '--output', $Destination, $Url
    ) "download $Label"
    Assert-Sha256 $Destination $ExpectedSha256 "$Label archive"
}

function Get-ExactExeFromZip(
    [string]$Archive,
    [string]$Destination,
    [string]$ExeName,
    [string]$ExpectedSha256
) {
    $candidate = @(Get-ChildItem -LiteralPath $Destination -Recurse -File -Filter $ExeName -ErrorAction SilentlyContinue)
    if ($candidate.Count -eq 1 -and (Get-Sha256 $candidate[0].FullName) -eq $ExpectedSha256) {
        return $candidate[0].FullName
    }
    if (Test-Path -LiteralPath $Destination) { Remove-Item -Recurse -Force -LiteralPath $Destination }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $Destination -Force
    $candidate = @(Get-ChildItem -LiteralPath $Destination -Recurse -File -Filter $ExeName)
    if ($candidate.Count -ne 1) { throw "Expected one $ExeName, found $($candidate.Count)" }
    Assert-Sha256 $candidate[0].FullName $ExpectedSha256 $ExeName
    $candidate[0].FullName
}

function Get-FileIdentity([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [ordered]@{ path = $Path; exists = $false }
    }
    $item = Get-Item -LiteralPath $Path
    [ordered]@{
        path = $item.FullName
        exists = $true
        bytes = $item.Length
        last_write_utc = $item.LastWriteTimeUtc.ToString('o')
        sha256 = Get-Sha256 $item.FullName
    }
}

function Test-SameFileIdentity($Before, $After) {
    if ($Before.exists -ne $After.exists) { return $false }
    if (!$Before.exists) { return $true }
    $Before.bytes -eq $After.bytes -and
        $Before.last_write_utc -eq $After.last_write_utc -and
        $Before.sha256 -eq $After.sha256
}

function Get-OutlineCount($Items) {
    $count = 0
    foreach ($item in @($Items)) {
        $count++
        if ($item.kids) { $count += Get-OutlineCount $item.kids }
    }
    $count
}

function Assert-OutlinePage($Items, [int]$ExpectedPage, [string]$Label) {
    foreach ($item in @($Items)) {
        if ($item.destpageposfrom1 -ne $ExpectedPage) { throw "$Label bookmark destination is not local page $ExpectedPage" }
        if ($item.kids) { Assert-OutlinePage $item.kids $ExpectedPage $Label }
    }
}

function Get-Donor($Manifest, [string]$Repository) {
    $matches = @($Manifest.donors | Where-Object { $_.repo -eq $Repository })
    if ($matches.Count -ne 1) { throw "Expected exactly one donor manifest entry for $Repository" }
    $matches[0]
}

function Get-PdfInventory(
    [string]$PdfInfo,
    [string]$Pdf,
    [int]$ExpectedPages,
    [int]$ExpectedLandscape,
    [string]$Label
) {
    $info = Invoke-NativeText $PdfInfo @('-f', '1', '-l', "$ExpectedPages", '-box', $Pdf) "$Label pdfinfo"
    $pageLine = [regex]::Match($info, '(?m)^Pages:\s+(\d+)\s*$')
    if (!$pageLine.Success -or [int]$pageLine.Groups[1].Value -ne $ExpectedPages) {
        throw "$Label pdfinfo page count mismatch"
    }
    $sizes = [regex]::Matches($info, '(?m)^Page\s+\d+ size:\s+([0-9.]+) x ([0-9.]+) pts')
    if ($sizes.Count -ne $ExpectedPages) { throw "$Label orientation inventory is incomplete" }
    $landscape = 0
    foreach ($size in $sizes) {
        if ([double]$size.Groups[1].Value -gt [double]$size.Groups[2].Value) { $landscape++ }
    }
    if ($landscape -ne $ExpectedLandscape) {
        throw "$Label landscape page mismatch: $landscape != $ExpectedLandscape"
    }
    $rotations = [regex]::Matches($info, '(?m)^Page\s+\d+ rot:\s+(-?\d+)\s*$')
    if ($rotations.Count -ne $ExpectedPages) { throw "$Label rotation inventory is incomplete" }
    foreach ($rotation in $rotations) {
        if ([int]$rotation.Groups[1].Value -ne 0) { throw "$Label contains a rotated page" }
    }
    [ordered]@{ pages = $ExpectedPages; landscape_pages = $landscape; rotated_pages = 0 }
}

function Assert-SearchableText(
    [string]$PdfToText,
    [string]$Pdf,
    [string]$TextPath,
    [string[]]$RequiredText,
    [string]$Label
) {
    Invoke-NativeChecked $PdfToText @('-layout', $Pdf, $TextPath) "$Label text extraction"
    $text = Get-Content -Raw -LiteralPath $TextPath
    foreach ($required in $RequiredText) {
        if (!$text.Contains($required)) { throw "$Label searchable text missing: $required" }
    }
    $text
}

function Assert-PdfValidators(
    [string]$Qpdf,
    [string]$Pdfcpu,
    [string]$Pdf,
    [string]$Label,
    [string]$EvidenceDirectory
) {
    $qpdfOutput = Invoke-NativeText $Qpdf @('--check', $Pdf) "$Label qpdf check"
    # pdfcpu 0.15.0 uses the standard long-form global flag for config isolation.
    $pdfcpuOutput = Invoke-NativeText $Pdfcpu @('--conf', 'disable', 'validate', '--mode', 'strict', $Pdf) "$Label pdfcpu strict validation"
    @(
        "COMMAND: qpdf --check `"$Pdf`"",
        'EXIT: 0',
        $qpdfOutput,
        '',
        "COMMAND: pdfcpu --conf disable validate --mode strict `"$Pdf`"",
        'EXIT: 0',
        $pdfcpuOutput
    ) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $EvidenceDirectory "$Label.validators.log")
}

Assert-NotC $PackageRoot 'Package root'
Assert-NotC $RepoRoot 'Repository root'
Assert-NotC $OutputRoot 'Output root'
Assert-NotC $ToolsRoot 'Tools root'
Assert-NotC $ResultsRoot 'Results root'
Assert-Drive $PackageRoot @('E:') 'Package root'
Assert-Drive $RepoRoot @('E:') 'Repository root'
Assert-Drive $ToolsRoot @('E:') 'Tools root'
Assert-Drive $OutputRoot @('F:') 'Output root'
Assert-Drive $ResultsRoot @('E:', 'G:') 'Results root'
if (!(Test-Path 'E:\')) { throw 'Required E: drive is missing' }
if (!(Test-Path 'F:\')) { throw 'Required F: drive is missing' }

$run = "$(Get-Date -Format 'yyyyMMdd_HHmmss_fff')_$([guid]::NewGuid().ToString('N').Substring(0,8))"
$work = Join-Path $OutputRoot "runs\$run"
$output = Join-Path $work 'output'
$evidence = Join-Path $work 'evidence'
$controls = Join-Path $work 'controls'
$cache = Join-Path $OutputRoot 'cache'
$temp = Join-Path $OutputRoot 'temp'
$homeRoot = Join-Path $OutputRoot 'home'
$appData = Join-Path $OutputRoot 'appdata'
$localAppData = Join-Path $OutputRoot 'localappdata'
$cargoHome = Join-Path $OutputRoot 'cargo-home'
$cargoTarget = Join-Path $OutputRoot 'cargo-target'
$builderWork = Join-Path $work 'qualified-court-builder'
$bundleOutput = Join-Path $output 'court-bundle-derivative'

if (Test-Path -LiteralPath $work) { throw "R2 work directory already exists: $work" }
foreach ($path in @($work, $output, $evidence, $controls, $cache, $temp, $homeRoot, $appData, $localAppData, $cargoHome, $cargoTarget, $builderWork, $ResultsRoot)) {
    Assert-NotC $path 'R2 writable path'
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}

$originalPdfcpuConfig = Join-Path $env:APPDATA 'pdfcpu\config.yml'
$pdfcpuConfigBefore = Get-FileIdentity $originalPdfcpuConfig

$env:TEMP = $temp
$env:TMP = $temp
$env:HOME = $homeRoot
$env:XDG_CACHE_HOME = $cache
$env:APPDATA = $appData
$env:LOCALAPPDATA = $localAppData
$env:CARGO_HOME = $cargoHome
$env:CARGO_TARGET_DIR = $cargoTarget

$receipt = [ordered]@{
    schema = 'mcr-outward-procedural-tranche-r2'
    status = 'STARTED'
    run = $run
    branch = ''
    git_commit = ''
    storage = [ordered]@{
        repository = $RepoRoot
        tools = $ToolsRoot
        work = $work
        results = $ResultsRoot
        c_drive_policy = 'NO_INTENTIONAL_PROJECT_WRITES'
    }
    checks = [ordered]@{}
}

$finalReceiptPath = Join-Path $ResultsRoot "MCR_OUTWARD_PROCEDURAL_TRANCHE_R2_${run}_RECEIPT.json"
$zipPath = $null
$zipSha = $null

try {
    $receipt.branch = Invoke-NativeText 'git.exe' @('-C', $RepoRoot, 'branch', '--show-current') 'Git branch identity'
    $receipt.git_commit = Invoke-NativeText 'git.exe' @('-C', $RepoRoot, 'rev-parse', 'HEAD') 'Git commit identity'
    if (!$receipt.branch.StartsWith('local/')) { throw "R2 must run from a local tranche branch: $($receipt.branch)" }
    $upstream = Invoke-NativeText 'git.exe' @('-C', $RepoRoot, 'for-each-ref', '--format=%(upstream:short)', "refs/heads/$($receipt.branch)") 'Git upstream identity'
    if ($upstream) { throw "R2 local tranche branch must not have an upstream: $upstream" }
    $receipt.checks.local_branch = 'PASS'

    $qualifiedRoot = Join-Path $PackageRoot 'qualified-court-builder'
    $qualifiedReceiptPath = Join-Path $qualifiedRoot 'QUALIFIED_SOURCE_RECEIPT.json'
    $donorManifestPath = Join-Path $PackageRoot 'GITHUB_DONOR_MANIFEST_R1.json'
    $adverseManifestPath = Join-Path $PackageRoot 'OUTWARD_PROCEDURAL_ADVERSE_GATE_R2.json'
    $packTemplatePath = Join-Path $PackageRoot 'synthetic_procedural_pack.typ'
    $standaloneTemplatePath = Join-Path $PackageRoot 'synthetic_procedural_standalone.typ'
    $qualifiedReceipt = Get-Content -Raw -LiteralPath $qualifiedReceiptPath | ConvertFrom-Json
    $mainPath = Join-Path $qualifiedRoot 'src\main.rs'
    $lockPath = Join-Path $qualifiedRoot 'Cargo.lock'
    $tomlPath = Join-Path $qualifiedRoot 'Cargo.toml'
    Assert-Sha256 $mainPath 'e369cd07d421e579ef65d843c11f0d04e093dbe652ddeea3f43923ab13eed875' 'qualified main.rs'
    Assert-Sha256 $lockPath 'b4ecd4f22926a6e92d5400e23a2ed5729e75d26c124d1d1ba4fb9bb5fa6af36d' 'qualified Cargo.lock'
    Assert-Sha256 $tomlPath 'ec7ef4857b0ed709d842f89574cefb99d548990000a121399d27e071c0725c6a' 'qualified Cargo.toml'
    if ($qualifiedReceipt.lopdf_commit -ne 'a62854e1bbea308cd7db6e34492c0b3873711471') { throw 'qualified lopdf pin mismatch' }
    $receipt.source = [ordered]@{
        main_rs_sha256 = Get-Sha256 $mainPath
        cargo_lock_sha256 = Get-Sha256 $lockPath
        cargo_toml_sha256 = Get-Sha256 $tomlPath
        qualified_source_receipt_sha256 = Get-Sha256 $qualifiedReceiptPath
        donor_manifest_sha256 = Get-Sha256 $donorManifestPath
        typst_pack_source_sha256 = Get-Sha256 $packTemplatePath
        typst_standalone_source_sha256 = Get-Sha256 $standaloneTemplatePath
        adverse_gate_manifest_sha256 = Get-Sha256 $adverseManifestPath
        r2_runner_sha256 = Get-Sha256 $MyInvocation.MyCommand.Path
    }
    if ($receipt.source.typst_pack_source_sha256 -ne 'b923b24e186aa325ea8232467dc522d2ba53e9e681830810bffebc0c36765bac') {
        throw 'synthetic procedural pack Typst source hash mismatch'
    }
    if ($receipt.source.typst_standalone_source_sha256 -ne '13dc93a3d17e96911337ba4e66d0b9ee8f9e971a0c8ac5caa2ede5baf3b9c391') {
        throw 'synthetic procedural standalone Typst source hash mismatch'
    }
    $receipt.checks.source_hashes = 'PASS'

    foreach ($control in @($MyInvocation.MyCommand.Path, $adverseManifestPath, $packTemplatePath, $standaloneTemplatePath, $donorManifestPath, $qualifiedReceiptPath)) {
        Copy-Item -LiteralPath $control -Destination (Join-Path $controls ([IO.Path]::GetFileName($control)))
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $builderWork 'src') | Out-Null
    Copy-Item -LiteralPath $mainPath -Destination (Join-Path $builderWork 'src\main.rs')
    Copy-Item -LiteralPath $lockPath -Destination (Join-Path $builderWork 'Cargo.lock')
    Copy-Item -LiteralPath $tomlPath -Destination (Join-Path $builderWork 'Cargo.toml')
    Assert-Sha256 (Join-Path $builderWork 'src\main.rs') $receipt.source.main_rs_sha256 'staged main.rs'
    Assert-Sha256 (Join-Path $builderWork 'Cargo.lock') $receipt.source.cargo_lock_sha256 'staged Cargo.lock'
    Assert-Sha256 (Join-Path $builderWork 'Cargo.toml') $receipt.source.cargo_toml_sha256 'staged Cargo.toml'

    $donorManifest = Get-Content -Raw -LiteralPath $donorManifestPath | ConvertFrom-Json
    if ($donorManifest.schema -ne 'mcr-outward-procedural-github-donors-r1') { throw 'donor manifest schema mismatch' }
    $typstDonor = Get-Donor $donorManifest 'typst/typst'
    $qpdfDonor = Get-Donor $donorManifest 'qpdf/qpdf'
    $pdfcpuDonor = Get-Donor $donorManifest 'pdfcpu/pdfcpu'
    $lopdfDonor = Get-Donor $donorManifest 'J-F-Liu/lopdf'
    $emStitchingDonor = Get-Donor $donorManifest 'hmcts/em-stitching-api'
    $sscsDonor = Get-Donor $donorManifest 'hmcts/sscs-case-loader'
    if ($typstDonor.tag -ne 'v0.15.1' -or $typstDonor.commit -ne '9dfd3a08500b7896045f907433cf7b4b02434fad') { throw 'Typst donor manifest pin mismatch' }
    if ($qpdfDonor.tag -ne 'v12.4.1' -or $qpdfDonor.commit -ne 'c37f83ae468abb6cc741f43b2f6fdeb66e550ffb') { throw 'qpdf donor manifest pin mismatch' }
    if ($pdfcpuDonor.tag -ne 'v0.15.0' -or $pdfcpuDonor.commit -ne 'f2686555086a2e76dc19f602ea1897f6e3baae4d') { throw 'pdfcpu donor manifest pin mismatch' }
    if ($lopdfDonor.commit -ne 'a62854e1bbea308cd7db6e34492c0b3873711471') { throw 'lopdf donor manifest pin mismatch' }
    if ($emStitchingDonor.commit -ne 'bdb2c306b523ad962298af9c198462d9a42017f4') { throw 'HMCTS em-stitching donor manifest pin mismatch' }
    if ($sscsDonor.commit -ne '660995ee2666bec627e4363b2ac7ffa63fc4789e') { throw 'HMCTS SSCS donor manifest pin mismatch' }

    $typstRoot = Join-Path $ToolsRoot 'typst-0.15.1'
    $qpdfRoot = Join-Path $ToolsRoot 'qpdf-12.4.1'
    $pdfcpuRoot = Join-Path $ToolsRoot 'pdfcpu-0.15.0'
    New-Item -ItemType Directory -Force -Path $typstRoot, $qpdfRoot, $pdfcpuRoot | Out-Null
    $typstArchive = Join-Path $typstRoot 'typst-x86_64-pc-windows-msvc.zip'
    $qpdfArchive = Join-Path $qpdfRoot 'qpdf-12.4.1-msvc64.zip'
    $pdfcpuArchive = Join-Path $pdfcpuRoot 'pdfcpu_0.15.0_Windows_x86_64.zip'
    Download-Exact $typstDonor.download $typstArchive $typstDonor.windows_x86_64_asset_sha256 'Typst'
    Download-Exact "https://github.com/qpdf/qpdf/releases/download/$($qpdfDonor.tag)/$($qpdfDonor.windows_archive)" $qpdfArchive $qpdfDonor.windows_archive_sha256 'qpdf'
    Download-Exact "https://github.com/pdfcpu/pdfcpu/releases/download/$($pdfcpuDonor.tag)/$($pdfcpuDonor.windows_archive)" $pdfcpuArchive $pdfcpuDonor.windows_archive_sha256 'pdfcpu'
    $typst = Get-ExactExeFromZip $typstArchive (Join-Path $typstRoot 'extracted') 'typst.exe' $typstDonor.qualified_windows_exe_sha256
    $qpdf = Get-ExactExeFromZip $qpdfArchive (Join-Path $qpdfRoot 'extracted') 'qpdf.exe' $qpdfDonor.qualified_windows_exe_sha256
    $pdfcpu = Get-ExactExeFromZip $pdfcpuArchive (Join-Path $pdfcpuRoot 'extracted') 'pdfcpu.exe' $pdfcpuDonor.qualified_windows_exe_sha256
    $pdfToText = 'E:\RIG_WORKER\TOOLS\Poppler\poppler-26.02.0\Library\bin\pdftotext.exe'
    $pdfInfo = 'E:\RIG_WORKER\TOOLS\Poppler\poppler-26.02.0\Library\bin\pdfinfo.exe'
    Assert-NotC $pdfToText 'pdftotext executable'
    Assert-NotC $pdfInfo 'pdfinfo executable'
    Assert-Sha256 $pdfToText $donorManifest.local_r2_validation_tools.poppler.pdftotext_exe_sha256 'pdftotext executable'
    Assert-Sha256 $pdfInfo $donorManifest.local_r2_validation_tools.poppler.pdfinfo_exe_sha256 'pdfinfo executable'
    $pdfToTextVersion = Invoke-NativeText $pdfToText @('-v') 'pdftotext version'
    $pdfInfoVersion = Invoke-NativeText $pdfInfo @('-v') 'pdfinfo version'
    if ($pdfToTextVersion -notmatch 'version 26\.02\.0' -or $pdfInfoVersion -notmatch 'version 26\.02\.0') { throw 'Poppler version mismatch' }
    $receipt.tools = [ordered]@{
        typst = [ordered]@{ version = Invoke-NativeText $typst @('--version') 'Typst version'; archive_sha256 = Get-Sha256 $typstArchive; exe_sha256 = Get-Sha256 $typst }
        qpdf = [ordered]@{ version = Invoke-NativeText $qpdf @('--version') 'qpdf version'; archive_sha256 = Get-Sha256 $qpdfArchive; exe_sha256 = Get-Sha256 $qpdf }
        pdfcpu = [ordered]@{ version = Invoke-NativeText $pdfcpu @('--conf', 'disable', 'version') 'pdfcpu version'; archive_sha256 = Get-Sha256 $pdfcpuArchive; exe_sha256 = Get-Sha256 $pdfcpu; validation_command = 'pdfcpu --conf disable validate --mode strict' }
        pdftotext = [ordered]@{ version = '26.02.0'; path = $pdfToText; exe_sha256 = Get-Sha256 $pdfToText }
        pdfinfo = [ordered]@{ version = '26.02.0'; path = $pdfInfo; exe_sha256 = Get-Sha256 $pdfInfo }
        hmcts_em_stitching_reference = 'bdb2c306b523ad962298af9c198462d9a42017f4'
        hmcts_sscs_case_loader_reference = '660995ee2666bec627e4363b2ac7ffa63fc4789e'
        lopdf_commit = 'a62854e1bbea308cd7db6e34492c0b3873711471'
    }
    $receipt.checks.donor_identity = 'PASS'

    $rustup = (Get-Command 'rustup.exe' -ErrorAction Stop).Source
    Assert-NotC $rustup 'rustup executable'
    $rustupHome = 'E:\MCR_RIG_ACCEPTANCE\tools\rustup-gnu'
    $dlltool = 'E:\SERVATI\TOOLS\llvm-mingw-20260826-ucrt-x86_64\bin\x86_64-w64-mingw32-dlltool.exe'
    Assert-NotC $rustupHome 'Rust toolchain home'
    Assert-NotC $dlltool 'GNU import-library tool'
    if (!(Test-Path -LiteralPath $rustupHome -PathType Container)) { throw 'HOLD: non-C Rust 1.88 toolchain home is missing' }
    if (!(Test-Path -LiteralPath $dlltool -PathType Leaf)) { throw 'HOLD: non-C GNU dlltool is missing' }
    Assert-Sha256 $dlltool $donorManifest.local_r2_validation_tools.llvm_mingw.dlltool_exe_sha256 'GNU dlltool'
    $env:RUSTUP_HOME = $rustupHome
    $env:RUSTFLAGS = "-C link-self-contained=yes -C dlltool=$dlltool"
    $rustVersion = Invoke-NativeText $rustup @('run', '1.88.0', 'rustc', '--version') 'Rust 1.88 identity'
    if ($rustVersion -notmatch '^rustc 1\.88\.0') { throw "HOLD: exact Rust 1.88.0 is unavailable: $rustVersion" }
    $receipt.tools.rust = [ordered]@{ version = $rustVersion; rustup_path = $rustup; rustup_home = $rustupHome; dlltool_sha256 = Get-Sha256 $dlltool }

    Push-Location $builderWork
    try {
        Invoke-NativeChecked $rustup @('run', '1.88.0', 'cargo', 'check', '--locked') 'qualified builder cargo check'
        Invoke-NativeChecked $rustup @('run', '1.88.0', 'cargo', 'test', '--locked', '--all-targets') 'qualified builder cargo test'
        Invoke-NativeChecked $rustup @('run', '1.88.0', 'cargo', 'run', '--locked', '--release', '--', $bundleOutput) 'qualified builder release run'
    } finally {
        Pop-Location
    }
    Assert-Sha256 (Join-Path $builderWork 'src\main.rs') $receipt.source.main_rs_sha256 'post-build staged main.rs'
    Assert-Sha256 (Join-Path $builderWork 'Cargo.lock') $receipt.source.cargo_lock_sha256 'post-build staged Cargo.lock'
    Assert-Sha256 (Join-Path $builderWork 'Cargo.toml') $receipt.source.cargo_toml_sha256 'post-build staged Cargo.toml'
    $receipt.checks.qualified_builder_build_and_source_immutability = 'PASS'

    $proceduralPack = Join-Path $output 'synthetic_procedural_pack.pdf'
    Invoke-NativeChecked $typst @('compile', $packTemplatePath, $proceduralPack, '--pdf-standard', '1.7') 'Typst procedural pack compile'
    $proceduralDocuments = @(
        [ordered]@{ key = 'witness_statement'; file = 'synthetic_witness_statement.pdf'; expected_pages = 1; expected_bookmarks = 1; text = @('Witness Statement', 'SIGNING GATE NOT ACTIVATED') },
        [ordered]@{ key = 'exhibit_and_index_material'; file = 'synthetic_exhibit_and_index_material.pdf'; expected_pages = 1; expected_bookmarks = 3; text = @('Exhibit and Index Material', 'Contents', 'Exhibit Register', 'Synthetic adverse note') },
        [ordered]@{ key = 'participation_and_adjustment_request'; file = 'synthetic_participation_and_adjustment_request.pdf'; expected_pages = 1; expected_bookmarks = 1; text = @('Participation / Adjustments Request', 'Synthetic communication-processing barrier') },
        [ordered]@{ key = 'authorities_sheet'; file = 'synthetic_authorities_sheet.pdf'; expected_pages = 1; expected_bookmarks = 1; text = @('Authorities / Currentness Sheet', 'Recheck official source before filing') },
        [ordered]@{ key = 'filing_and_service_receipt'; file = 'synthetic_filing_and_service_receipt.pdf'; expected_pages = 1; expected_bookmarks = 2; text = @('Filing / Service Receipt', 'NOT FILED / NOT SERVED', 'Hostile / Adverse Gate') }
    )
    foreach ($document in $proceduralDocuments) {
        $document.path = Join-Path $output $document.file
        Invoke-NativeChecked $typst @('compile', $standaloneTemplatePath, $document.path, '--input', "kind=$($document.key)", '--pdf-standard', '1.7') "compile $($document.key)"
    }

    $hearing = Join-Path $bundleOutput 'SYN001_Synthetic-v-Respondent_Hearing_Bundle.pdf'
    $core = Join-Path $bundleOutput 'SYN001_Synthetic-v-Respondent_Core_Bundle.pdf'
    Assert-Sha256 $hearing 'f7022f3271cd1b566d4bebfe06a79733496cbae58caa28ae866b46d3cc88133b' 'hearing bundle derivative'
    Assert-Sha256 $core 'e0334d0b8ae43dd4366908f448f72326ccf51a35e21e3f8c4fb3201a1a83db31' 'core bundle derivative'

    $outputInventory = [ordered]@{}
    $allProcedural = @([ordered]@{ key = 'procedural_pack'; path = $proceduralPack; expected_pages = 6; expected_bookmarks = 6; text = @('SYNTHETIC OUTWARD PROCEDURAL PACK', 'Witness Statement', 'Exhibit Register', 'Participation / Adjustments Request', 'Authorities / Currentness Index', 'Filing / Service Receipt', 'Hostile / Adverse Gate') }) + $proceduralDocuments
    foreach ($document in $allProcedural) {
        Assert-PdfValidators $qpdf $pdfcpu $document.path $document.key $evidence
        $pages = [int](Invoke-NativeText $qpdf @('--show-npages', $document.path) "$($document.key) page count")
        if ($pages -ne $document.expected_pages) { throw "$($document.key) page mismatch: $pages != $($document.expected_pages)" }
        $textPath = Join-Path $evidence "$($document.key).txt"
        $documentText = Assert-SearchableText $pdfToText $document.path $textPath $document.text $document.key
        $inventory = Get-PdfInventory $pdfInfo $document.path $document.expected_pages 0 $document.key
        $outline = (Invoke-NativeText $qpdf @('--json', '--json-key=outlines', $document.path) "$($document.key) outline inventory") | ConvertFrom-Json
        if ((Get-OutlineCount $outline.outlines) -ne $document.expected_bookmarks) { throw "$($document.key) bookmark count mismatch" }
        if ($document.key -ne 'procedural_pack') {
            Assert-OutlinePage $outline.outlines 1 $document.key
            if (!$documentText.Contains('Page 1') -or $documentText -match 'Page\s+[2-9]\d*') { throw "$($document.key) visible pagination was not reset" }
        }
        $acroform = (Invoke-NativeText $qpdf @('--json', '--json-key=acroform', $document.path) "$($document.key) signature-field inventory") | ConvertFrom-Json
        if ($acroform.acroform.hasacroform -or @($acroform.acroform.fields).Count -ne 0) { throw "$($document.key) contains an AcroForm/signature field" }
        $outputInventory[$document.key] = [ordered]@{ file = $document.path; pages = $inventory.pages; landscape_pages = $inventory.landscape_pages; bookmarks = $document.expected_bookmarks; sha256 = Get-Sha256 $document.path; qpdf = 'PASS'; pdfcpu_strict_config_disabled = 'PASS'; searchable_text = 'PASS'; orientation = 'PASS'; visible_pagination = 'PASS'; signature_fields_absent = 'PASS' }
    }

    $proceduralOutline = (Invoke-NativeText $qpdf @('--json', '--json-key=outlines', $proceduralPack) 'procedural outline inventory') | ConvertFrom-Json
    $expectedOutlineTitles = @('1. Witness Statement', '2. Exhibit Register', '3. Participation / Adjustments Request', '4. Authorities / Currentness Index', '5. Filing / Service Receipt', '6. Hostile / Adverse Gate')
    if ((Get-OutlineCount $proceduralOutline.outlines) -ne $expectedOutlineTitles.Count) { throw 'procedural bookmark count mismatch' }
    for ($i = 0; $i -lt $expectedOutlineTitles.Count; $i++) {
        if ($proceduralOutline.outlines[$i].title -ne $expectedOutlineTitles[$i]) { throw "procedural bookmark title mismatch at $i" }
        $expectedPage = if ($i -lt 5) { $i + 2 } else { 6 }
        if ($proceduralOutline.outlines[$i].destpageposfrom1 -ne $expectedPage) { throw "procedural bookmark destination mismatch at $i" }
    }
    $receipt.checks.procedural_index_and_bookmarks = 'PASS'

    $bundleReceiptPath = Join-Path $bundleOutput 'COURT_BUNDLE_QUALIFICATION_RECEIPT.json'
    $bundleReceipt = Get-Content -Raw -LiteralPath $bundleReceiptPath | ConvertFrom-Json
    if ($bundleReceipt.status -ne 'PASS' -or $bundleReceipt.hearing_bundle.pages -ne 109 -or $bundleReceipt.core_bundle.pages -ne 37) { throw 'qualified builder receipt status/page gate failed' }
    if ($bundleReceipt.hearing_bundle.index_links -ne 12 -or $bundleReceipt.core_bundle.index_links -ne 4) { throw 'qualified builder index-link gate failed' }
    foreach ($field in @('source_immutability', 'default_view_100_percent', 'searchable_text_preserved', 'continuous_visible_page_numbers', 'clickable_index_targets', 'nested_bookmarks')) {
        if ($bundleReceipt.$field -ne 'PASS') { throw "qualified builder receipt gate failed: $field" }
    }
    if ($bundleReceipt.malformed_input -ne 'REJECTED' -or $bundleReceipt.encrypted_input -ne 'REJECTED') { throw 'qualified builder hostile-input rejection gate failed' }

    foreach ($bundle in @(
        [ordered]@{ key = 'hearing_bundle_derivative'; path = $hearing; pages = 109; landscape = 1; bookmarks = 15 },
        [ordered]@{ key = 'core_bundle_derivative'; path = $core; pages = 37; landscape = 1; bookmarks = 7 }
    )) {
        Assert-PdfValidators $qpdf $pdfcpu $bundle.path $bundle.key $evidence
        $pages = [int](Invoke-NativeText $qpdf @('--show-npages', $bundle.path) "$($bundle.key) page count")
        if ($pages -ne $bundle.pages) { throw "$($bundle.key) page mismatch" }
        Assert-SearchableText $pdfToText $bundle.path (Join-Path $evidence "$($bundle.key).txt") @('SYNTHETIC COURT BUNDLE INDEX', 'SYNTHETIC DOCUMENT') $bundle.key | Out-Null
        $inventory = Get-PdfInventory $pdfInfo $bundle.path $bundle.pages $bundle.landscape $bundle.key
        $outline = (Invoke-NativeText $qpdf @('--json', '--json-key=outlines', $bundle.path) "$($bundle.key) outline inventory") | ConvertFrom-Json
        if ((Get-OutlineCount $outline.outlines) -ne $bundle.bookmarks) { throw "$($bundle.key) bookmark count mismatch" }
        $outputInventory[$bundle.key] = [ordered]@{ file = $bundle.path; pages = $inventory.pages; landscape_pages = $inventory.landscape_pages; bookmarks = $bundle.bookmarks; sha256 = Get-Sha256 $bundle.path; qpdf = 'PASS'; pdfcpu_strict_config_disabled = 'PASS'; searchable_text = 'PASS'; orientation = 'PASS'; index_links = 'PASS'; visible_pagination = 'PASS' }
    }
    $receipt.checks.page_count_index_bookmark_searchability_orientation = 'PASS'

    $adverseManifest = Get-Content -Raw -LiteralPath $adverseManifestPath | ConvertFrom-Json
    if ($adverseManifest.schema -ne 'mcr-outward-procedural-adverse-gate-r2') { throw 'adverse manifest schema mismatch' }
    foreach ($field in @('synthetic_only', 'r59_accessed', 'live_evidence_used', 'signed_statement_of_truth', 'filing_or_service_claimed', 'adverse_material_identified', 'adverse_material_included_in_index', 'information_and_belief_source_identified')) {
        if ($adverseManifest.$field -isnot [bool]) { throw "adverse manifest field is not Boolean: $field" }
    }
    if (!$adverseManifest.synthetic_only -or $adverseManifest.r59_accessed -or $adverseManifest.live_evidence_used -or $adverseManifest.signed_statement_of_truth -or $adverseManifest.filing_or_service_claimed) { throw 'adverse manifest privacy/signing boundary failed' }
    if (!$adverseManifest.adverse_material_identified -or !$adverseManifest.adverse_material_included_in_index -or !$adverseManifest.information_and_belief_source_identified) { throw 'hostile/adverse evidence manifest failed closed' }
    $expectedFamilies = @('witness_statement', 'exhibit_and_index_material', 'participation_and_adjustment_request', 'authorities_sheet', 'filing_and_service_receipt', 'hearing_and_core_bundle_derivative')
    $familyDifference = @(Compare-Object @($adverseManifest.required_document_families) $expectedFamilies)
    if ($familyDifference.Count -ne 0) { throw 'adverse manifest required-document inventory mismatch' }
    foreach ($family in $expectedFamilies | Where-Object { $_ -ne 'hearing_and_core_bundle_derivative' }) {
        if (!$outputInventory.Contains($family)) { throw "required procedural family was not generated: $family" }
    }
    if (!$outputInventory.Contains('hearing_bundle_derivative') -or !$outputInventory.Contains('core_bundle_derivative')) { throw 'required hearing/core derivatives were not generated' }
    $packText = Get-Content -Raw -LiteralPath (Join-Path $evidence 'procedural_pack.txt')
    foreach ($required in @('Synthetic adverse note', 'SIGNING GATE NOT ACTIVATED', 'NOT FILED / NOT SERVED', 'No private or live source is included')) {
        if (!$packText.Contains($required)) { throw "hostile/adverse output gate missing: $required" }
    }
    $receipt.checks.hostile_adverse_evidence_gate = 'PASS'
    $receipt.checks.no_signed_statement_of_truth = 'PASS'
    $receipt.checks.r59_not_accessed = [ordered]@{ status = 'PASS'; basis = 'Runner accepts no R59 path and used only generated synthetic inputs.' }
    $receipt.checks.live_evidence_not_used = [ordered]@{ status = 'PASS'; basis = 'Frozen templates, manifest and generated synthetic builder fixtures were the only content inputs.' }

    $pdfcpuConfigAfter = Get-FileIdentity $originalPdfcpuConfig
    $receipt.pdfcpu_config_isolation = [ordered]@{ command = 'pdfcpu --conf disable validate --mode strict'; before = $pdfcpuConfigBefore; after = $pdfcpuConfigAfter; unchanged = Test-SameFileIdentity $pdfcpuConfigBefore $pdfcpuConfigAfter }
    if (!$receipt.pdfcpu_config_isolation.unchanged) { throw 'existing pdfcpu config was modified' }
    $receipt.checks.pdfcpu_config_isolation = 'PASS'
    $receipt.checks.c_drive_path_isolation = 'PASS'

    $receipt.output = $outputInventory
    $receipt.output.qualified_builder_receipt_sha256 = Get-Sha256 $bundleReceiptPath
    $receipt.status = 'PASS'
} catch {
    if ($_.Exception.Message.StartsWith('HOLD:')) {
        $receipt.status = 'HOLD'
    } else {
        $receipt.status = 'FAIL'
    }
    $receipt.error = $_.Exception.Message
}

if (!$receipt.Contains('pdfcpu_config_isolation')) {
    $pdfcpuConfigAfter = Get-FileIdentity $originalPdfcpuConfig
    $unchanged = Test-SameFileIdentity $pdfcpuConfigBefore $pdfcpuConfigAfter
    $receipt.pdfcpu_config_isolation = [ordered]@{ command = 'pdfcpu --conf disable validate --mode strict'; before = $pdfcpuConfigBefore; after = $pdfcpuConfigAfter; unchanged = $unchanged }
    if (!$unchanged) {
        $receipt.status = 'FAIL'
        $receipt.error = 'existing pdfcpu config was modified'
    }
}

if ($receipt.status -eq 'PASS') {
    $partialId = [guid]::NewGuid().ToString('N')
    $partialZip = Join-Path $ResultsRoot ".$run.$partialId.partial.zip"
    $partialReceipt = Join-Path $ResultsRoot ".$run.$partialId.partial.json"
    $partialSidecar = Join-Path $ResultsRoot ".$run.$partialId.partial.sha256.txt"
    $zipPath = Join-Path $ResultsRoot "MCR_OUTWARD_PROCEDURAL_TRANCHE_R2_${run}_PASS.zip"
    try {
        Compress-Archive -Path $output, $evidence, $controls, $builderWork -DestinationPath $partialZip -CompressionLevel Optimal
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [IO.Compression.ZipFile]::OpenRead($partialZip)
        try {
            $entries = @($archive.Entries | ForEach-Object { $_.FullName })
            foreach ($requiredEntry in @(
                'controls/Invoke-OutwardProceduralTrancheR2.ps1',
                'controls/OUTWARD_PROCEDURAL_ADVERSE_GATE_R2.json',
                'controls/GITHUB_DONOR_MANIFEST_R1.json',
                'controls/QUALIFIED_SOURCE_RECEIPT.json',
                'controls/synthetic_procedural_pack.typ',
                'controls/synthetic_procedural_standalone.typ',
                'output/synthetic_procedural_pack.pdf',
                'output/synthetic_witness_statement.pdf',
                'output/synthetic_exhibit_and_index_material.pdf',
                'output/synthetic_participation_and_adjustment_request.pdf',
                'output/synthetic_authorities_sheet.pdf',
                'output/synthetic_filing_and_service_receipt.pdf',
                'output/court-bundle-derivative/SYN001_Synthetic-v-Respondent_Hearing_Bundle.pdf',
                'output/court-bundle-derivative/SYN001_Synthetic-v-Respondent_Core_Bundle.pdf'
            )) {
                if ($requiredEntry -notin $entries) { throw "result archive is missing: $requiredEntry" }
            }
        } finally {
            $archive.Dispose()
        }
        $zipSha = Get-Sha256 $partialZip
        $receipt.archive = [ordered]@{
            path = $zipPath
            bytes = (Get-Item -LiteralPath $partialZip).Length
            entries = $entries.Count
            sha256 = $zipSha
            reopen_check = 'PASS'
            receipt_is_standalone_to_avoid_a_circular_archive_hash = $true
        }
        $receipt | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 -LiteralPath $partialReceipt
        Set-Content -Encoding ASCII -LiteralPath $partialSidecar -Value "$zipSha  $([IO.Path]::GetFileName($zipPath))"
        Move-Item -LiteralPath $partialZip -Destination $zipPath
        Move-Item -LiteralPath $partialSidecar -Destination "$zipPath.sha256.txt"
        Move-Item -LiteralPath $partialReceipt -Destination $finalReceiptPath
    } catch {
        foreach ($path in @($partialZip, $partialReceipt, $partialSidecar, $zipPath, "$zipPath.sha256.txt")) {
            if (Test-Path -LiteralPath $path) { Remove-Item -Force -LiteralPath $path }
        }
        $receipt.status = 'FAIL'
        $receipt.error = "result finalization failed: $($_.Exception.Message)"
        $receipt | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 -LiteralPath $finalReceiptPath
        $zipPath = $null
        $zipSha = $null
    }
} else {
    $receipt | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 -LiteralPath $finalReceiptPath
}

Write-Host "MCR OUTWARD PROCEDURAL TRANCHE R2 — LOCAL END-TO-END: $($receipt.status)"
Write-Host "Qualification receipt: $finalReceiptPath"
if ($zipPath) {
    Write-Host "Final result ZIP: $zipPath"
    Write-Host "Final result ZIP SHA-256: $zipSha"
}
if ($receipt.status -eq 'PASS') { exit 0 }
if ($receipt.status -eq 'HOLD') { exit 2 }
exit 1
