[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bin = Join-Path $Root 'bin'
$Models = Join-Path $Root 'models'
$Runtime = Join-Path $Root 'runtime'
$Server = Join-Path $Bin 'llama-server.exe'
$Model = Join-Path $Models 'qwen2.5-0.5b-instruct-q4_k_m.gguf'
$ModelTemp = "$Model.partial"
$ModelUrl = 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/df5bf01389a39c743ab467d734bf501681e041c5/qwen2.5-0.5b-instruct-q4_k_m.gguf?download=true'
$ModelSha256 = '74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db'

function Write-Heading([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 70) -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ('=' * 70) -ForegroundColor Cyan
}

function Get-FreePort {
    foreach ($port in 8080..8090) {
        $busy = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if (-not $busy) { return $port }
    }
    throw 'No free local demo port was found between 8080 and 8090.'
}

function Download-Model {
    New-Item -ItemType Directory -Path $Models -Force | Out-Null
    if (Test-Path -LiteralPath $ModelTemp) { Remove-Item -LiteralPath $ModelTemp -Force }

    Write-Heading 'FIRST RUN: downloading the official Qwen demo model (~491 MB)'
    Write-Host 'This happens once. The file is verified with SHA-256 before use.'

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & $curl.Source -L --fail --retry 3 --output $ModelTemp $ModelUrl
        if ($LASTEXITCODE -ne 0) { throw "Model download failed with curl exit code $LASTEXITCODE." }
    }
    else {
        Invoke-WebRequest -Uri $ModelUrl -OutFile $ModelTemp -UseBasicParsing
    }

    $hash = (Get-FileHash -LiteralPath $ModelTemp -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $ModelSha256) {
        Remove-Item -LiteralPath $ModelTemp -Force -ErrorAction SilentlyContinue
        throw "Downloaded model failed SHA-256 verification. Expected $ModelSha256 but got $hash."
    }
    Move-Item -LiteralPath $ModelTemp -Destination $Model -Force
    Write-Host 'Model download and SHA-256 verification passed.' -ForegroundColor Green
}

Write-Heading 'RIG WORKER - LOCAL AI DEMO'
Write-Host 'Portable Windows x64 demonstration. No cloud AI service is used.'

if (-not (Test-Path -LiteralPath $Server -PathType Leaf)) {
    throw "llama-server.exe is missing from the package: $Server"
}

if (-not (Test-Path -LiteralPath $Model -PathType Leaf)) {
    Download-Model
}
else {
    $existingHash = (Get-FileHash -LiteralPath $Model -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($existingHash -ne $ModelSha256) {
        throw 'The existing demo model does not match the pinned verified model. Delete the models folder and run again.'
    }
}

New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
$Port = Get-FreePort
$Url = "http://127.0.0.1:$Port"

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $Server
$psi.WorkingDirectory = $Bin
$psi.UseShellExecute = $false
foreach ($arg in @(
    '--model', $Model,
    '--host', '127.0.0.1',
    '--port', $Port.ToString(),
    '--ctx-size', '4096',
    '--offline',
    '--alias', 'Rig-Worker-Demo'
)) {
    [void]$psi.ArgumentList.Add($arg)
}

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $psi
if (-not $process.Start()) { throw 'llama-server did not start.' }

try {
    $ready = $false
    foreach ($attempt in 1..60) {
        Start-Sleep -Milliseconds 500
        if ($process.HasExited) {
            throw "llama-server exited before becoming ready (exit code $($process.ExitCode))."
        }
        try {
            $response = Invoke-WebRequest -Uri "$Url/health" -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        }
        catch { }
    }
    if (-not $ready) { throw "llama-server did not become ready at $Url within 30 seconds." }

    Write-Heading 'READY'
    Write-Host "Local AI is running at: $Url" -ForegroundColor Green
    Write-Host 'The server is bound to this PC only (127.0.0.1) and is running offline.'
    Write-Host 'Your browser will open now.'
    Write-Host ''
    Write-Host 'Press ENTER in this window when you want to stop the demo.' -ForegroundColor Yellow
    Start-Process $Url
    [void](Read-Host)
}
finally {
    if (-not $process.HasExited) {
        try { $process.Kill($true) } catch { }
        try { $process.WaitForExit(5000) } catch { }
    }
}

Write-Host 'Rig Worker demo stopped.' -ForegroundColor Green
