param(
    [string]$OutputRoot = 'F:\MCR_OUTWARD_REHEARSAL'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Sha256([string]$Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}
function Assert-NotC([string]$Path,[string]$Label) {
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    if ($root -and $root.TrimEnd('\') -ieq 'C:') { throw "$Label resolves to C: : $full" }
}
function Invoke-Checked([scriptblock]$Command,[string]$Label) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
}
function Download-Exact([string]$Url,[string]$Dest,[string]$Expected,[string]$Label) {
    if (Test-Path $Dest) {
        if ((Sha256 $Dest) -eq $Expected) { return }
        Remove-Item -Force $Dest
    }
    Invoke-Checked { curl.exe --location --fail --retry 5 --retry-delay 2 --output $Dest $Url } "download $Label"
    $actual = Sha256 $Dest
    if ($actual -ne $Expected) { throw "$Label archive hash mismatch: $actual" }
}

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolsRoot = 'E:\MCR_GITHUB_DONORS'
$ResultsRoot = if (Test-Path 'G:\') { 'G:\MCR_OUTWARD_REHEARSAL_RESULTS' } else { 'E:\MCR_OUTWARD_REHEARSAL_RESULTS' }

foreach ($p in @($PackageRoot,$OutputRoot,$ToolsRoot,$ResultsRoot)) { Assert-NotC $p 'Writable/project path' }
if (!(Test-Path 'E:\')) { throw 'E: drive missing' }
if (!(Test-Path 'F:\')) { throw 'F: drive missing' }

$run = Get-Date -Format 'yyyyMMdd_HHmmss'
$work = Join-Path $OutputRoot $run
$out = Join-Path $work 'output'
$receipts = Join-Path $work 'receipts'
New-Item -ItemType Directory -Force -Path $work,$out,$receipts,$ToolsRoot,$ResultsRoot | Out-Null

# Exact GitHub donor pins.
$typstUrl = 'https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-pc-windows-msvc.zip'
$typstArchiveSha = '19ce3551153c2fe7ee9fa2f95208310c8f4d3209fedb699e0333faf8913f6736'
$qpdfUrl = 'https://github.com/qpdf/qpdf/releases/download/v12.4.1/qpdf-12.4.1-msvc64.zip'
$qpdfArchiveSha = '3cd016cd433ef7232e42f4c13348a49cc14907a3c7278ef4f99120593126f7a6'
$qpdfExeSha = '57c003e868fb66cd343fd5afb91be8c2277f56434eea8635762499731bf9f60d'
$pdfcpuUrl = 'https://github.com/pdfcpu/pdfcpu/releases/download/v0.15.0/pdfcpu_0.15.0_Windows_x86_64.zip'
$pdfcpuArchiveSha = '9809a70ee60ba78252628cc9738b284fbebf22bc2616ae903fb89b807e75a8a6'
$pdfcpuExeSha = '94cafb66b508c2eb8648dffbb17fddb74b7a117fdc38846e36f9ec6322bdd05e'

$typstRoot = Join-Path $ToolsRoot 'typst-0.15.1'
$qpdfRoot = Join-Path $ToolsRoot 'qpdf-12.4.1'
$pdfcpuRoot = Join-Path $ToolsRoot 'pdfcpu-0.15.0'
New-Item -ItemType Directory -Force -Path $typstRoot,$qpdfRoot,$pdfcpuRoot | Out-Null

$typstZip = Join-Path $typstRoot 'typst-x86_64-pc-windows-msvc.zip'
$qpdfZip = Join-Path $qpdfRoot 'qpdf-12.4.1-msvc64.zip'
$pdfcpuZip = Join-Path $pdfcpuRoot 'pdfcpu_0.15.0_Windows_x86_64.zip'
Download-Exact $typstUrl $typstZip $typstArchiveSha 'Typst'
Download-Exact $qpdfUrl $qpdfZip $qpdfArchiveSha 'qpdf'
Download-Exact $pdfcpuUrl $pdfcpuZip $pdfcpuArchiveSha 'pdfcpu'

function ExactExeFromZip([string]$Archive,[string]$Dest,[string]$ExeName,[string]$ExpectedSha='') {
    $candidate = @(Get-ChildItem -LiteralPath $Dest -Recurse -File -Filter $ExeName -ErrorAction SilentlyContinue)
    if ($candidate.Count -eq 1 -and (!$ExpectedSha -or (Sha256 $candidate[0].FullName) -eq $ExpectedSha)) { return $candidate[0].FullName }
    if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $Dest -Force
    $candidate = @(Get-ChildItem -LiteralPath $Dest -Recurse -File -Filter $ExeName)
    if ($candidate.Count -ne 1) { throw "Expected one $ExeName, found $($candidate.Count)" }
    if ($ExpectedSha -and (Sha256 $candidate[0].FullName) -ne $ExpectedSha) { throw "$ExeName hash mismatch" }
    return $candidate[0].FullName
}

$typst = ExactExeFromZip $typstZip (Join-Path $typstRoot 'extracted') 'typst.exe'
$qpdf = ExactExeFromZip $qpdfZip (Join-Path $qpdfRoot 'extracted') 'qpdf.exe' $qpdfExeSha
$pdfcpu = ExactExeFromZip $pdfcpuZip (Join-Path $pdfcpuRoot 'extracted') 'pdfcpu.exe' $pdfcpuExeSha

$template = Join-Path $PackageRoot 'synthetic_procedural_pack.typ'
$pdf = Join-Path $out 'synthetic_procedural_pack.pdf'
Invoke-Checked { & $typst compile $template $pdf --pdf-standard 1.7 } 'Typst compile'
Invoke-Checked { & $qpdf --check $pdf } 'qpdf check'
Invoke-Checked { & $pdfcpu validate --mode strict $pdf } 'pdfcpu strict validation'
$pages = (& $qpdf --show-npages $pdf).Trim()
if ($LASTEXITCODE -ne 0) { throw 'qpdf page count failed' }
if ([int]$pages -lt 4) { throw "Synthetic procedural pack unexpectedly short: $pages pages" }

$receipt = [ordered]@{
    schema = 'mcr-outward-procedural-rehearsal-r1'
    status = 'PASS'
    run = $run
    storage = [ordered]@{ tools = $ToolsRoot; work = $work; results = $ResultsRoot; c_drive = 'NO_INTENTIONAL_PROJECT_WRITES' }
    github_donors = [ordered]@{
        typst = [ordered]@{ version='0.15.1'; tag_commit='9dfd3a08500b7896045f907433cf7b4b02434fad'; archive_sha256=$typstArchiveSha; exe_sha256=(Sha256 $typst) }
        qpdf = [ordered]@{ version='12.4.1'; tag_commit='c37f83ae468abb6cc741f43b2f6fdeb66e550ffb'; archive_sha256=$qpdfArchiveSha; exe_sha256=(Sha256 $qpdf) }
        pdfcpu = [ordered]@{ version='0.15.0'; tag_commit='f2686555086a2e76dc19f602ea1897f6e3baae4d'; archive_sha256=$pdfcpuArchiveSha; exe_sha256=(Sha256 $pdfcpu) }
        hmcts_em_stitching_reference = 'bdb2c306b523ad962298af9c198462d9a42017f4'
        hmcts_sscs_case_loader_reference = '660995ee2666bec627e4363b2ac7ffa63fc4789e'
        lopdf_qualified_commit = 'a62854e1bbea308cd7db6e34492c0b3873711471'
    }
    output = [ordered]@{
        file = $pdf
        pages = [int]$pages
        sha256 = (Sha256 $pdf)
        qpdf = 'PASS'
        pdfcpu_strict = 'PASS'
        statement_of_truth_signed = $false
        live_case_data = $false
        r59_accessed = $false
    }
}
$receiptPath = Join-Path $receipts 'OUTWARD_PROCEDURAL_REHEARSAL_RECEIPT.json'
$receipt | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $receiptPath

$zip = Join-Path $ResultsRoot "MCR_OUTWARD_REHEARSAL_${run}_PASS.zip"
Compress-Archive -Path (Join-Path $work '*') -DestinationPath $zip -CompressionLevel Optimal
$zipSha = Sha256 $zip
Set-Content -Encoding ASCII -Path "$zip.sha256.txt" -Value "$zipSha  $([IO.Path]::GetFileName($zip))"

Write-Host 'OUTWARD PROCEDURAL LAYER SYNTHETIC REHEARSAL: PASS'
Write-Host "PDF: $pdf"
Write-Host "PDF SHA-256: $($receipt.output.sha256)"
Write-Host "Result ZIP: $zip"
Write-Host "Result ZIP SHA-256: $zipSha"
