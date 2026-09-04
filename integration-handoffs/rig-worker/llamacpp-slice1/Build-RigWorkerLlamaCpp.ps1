[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Workspace,

    [switch]$CleanBuild,

    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$DonorRepository = 'https://github.com/ggml-org/llama.cpp.git'
$DonorSha = '0ef4d560e12c1a46470265c1abd31dd47c777d23'
$SourceMarkerName = 'RIG_WORKER_LLAMA_SOURCE.json'

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required build tool '$Name' was not found in PATH."
    }
    return $command.Source
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
    }
}

$git = Require-Command 'git'
$cmake = Require-Command 'cmake'
$ninja = Require-Command 'ninja'
$clang = Require-Command 'clang'
$ctest = Require-Command 'ctest'

$workspacePath = [System.IO.Path]::GetFullPath($Workspace)
$sourcePath = Join-Path $workspacePath 'llama.cpp-source'
$buildPath = Join-Path $workspacePath 'llama.cpp-build'
$sourceMarker = Join-Path $sourcePath $SourceMarkerName
$receiptPath = Join-Path $workspacePath 'build-receipt.json'

New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null

if (-not (Test-Path -LiteralPath $sourcePath)) {
    New-Item -ItemType Directory -Path $sourcePath | Out-Null
    Invoke-Checked $git @('-C', $sourcePath, 'init')
    Invoke-Checked $git @('-C', $sourcePath, 'remote', 'add', 'origin', $DonorRepository)
    try {
        Invoke-Checked $git @('-C', $sourcePath, '-c', 'protocol.version=2', 'fetch', '--no-tags', '--depth=1', 'origin', $DonorSha)
        Invoke-Checked $git @('-C', $sourcePath, 'checkout', '--detach', 'FETCH_HEAD')
    }
    finally {
        $remote = (& $git -C $sourcePath remote 2>$null | Out-String).Trim()
        if ($remote -match '(^|\r?\n)origin($|\r?\n)') {
            & $git -C $sourcePath remote remove origin | Out-Null
        }
    }

    $marker = [ordered]@{
        schema_version = 1
        repository = 'ggml-org/llama.cpp'
        commit_sha = $DonorSha
        created_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    }
    $marker | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $sourceMarker -Encoding utf8
}
else {
    if (-not (Test-Path -LiteralPath $sourceMarker -PathType Leaf)) {
        throw "Refusing to use existing directory without Rig Worker ownership marker: $sourcePath"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $sourcePath '.git') -PathType Container)) {
        throw "Marked donor source directory is not a Git repository: $sourcePath"
    }
}

$actualSha = (& $git -C $sourcePath rev-parse HEAD | Out-String).Trim()
if ($actualSha -ne $DonorSha) {
    throw "Pinned donor SHA mismatch. Expected $DonorSha, found $actualSha."
}

$remainingRemotes = (& $git -C $sourcePath remote | Out-String).Trim()
if ($remainingRemotes) {
    throw "Donor source must not retain a Git remote after acquisition. Found: $remainingRemotes"
}

if ($CleanBuild -and (Test-Path -LiteralPath $buildPath)) {
    Remove-Item -LiteralPath $buildPath -Recurse -Force
}
New-Item -ItemType Directory -Path $buildPath -Force | Out-Null

$toolchain = Join-Path $sourcePath 'cmake\x64-windows-llvm.cmake'
if (-not (Test-Path -LiteralPath $toolchain -PathType Leaf)) {
    throw "Expected upstream Windows LLVM toolchain was not found: $toolchain"
}

$configureArgs = @(
    '-S', $sourcePath,
    '-B', $buildPath,
    '-G', 'Ninja Multi-Config',
    "-DCMAKE_TOOLCHAIN_FILE=$toolchain",
    '-DGGML_NATIVE=OFF',
    '-DGGML_OPENMP_FETCH=ON',
    '-DLLAMA_BUILD_SERVER=ON',
    '-DGGML_RPC=ON',
    '-DBUILD_SHARED_LIBS=OFF',
    '-DLLAMA_BUILD_BORINGSSL=ON'
)
Invoke-Checked $cmake $configureArgs

$parallelism = [Math]::Max(1, [Environment]::ProcessorCount)
Invoke-Checked $cmake @('--build', $buildPath, '--config', 'Release', '-j', $parallelism.ToString())

if (-not $SkipTests) {
    Push-Location $buildPath
    try {
        Invoke-Checked $ctest @('-L', 'main', '-C', 'Release', '--verbose', '--timeout', '900')
    }
    finally {
        Pop-Location
    }
}

$serverPath = Join-Path $buildPath 'bin\Release\llama-server.exe'
$cliPath = Join-Path $buildPath 'bin\Release\llama-cli.exe'
foreach ($path in @($serverPath, $cliPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Expected compiled executable is missing: $path"
    }
}

$outputs = @()
foreach ($path in @($serverPath, $cliPath)) {
    $item = Get-Item -LiteralPath $path
    $outputs += [ordered]@{
        path = $item.FullName
        size_bytes = $item.Length
        sha256 = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$receipt = [ordered]@{
    schema_version = 1
    target_project = 'Rig Worker'
    donor_repository = 'ggml-org/llama.cpp'
    donor_commit_sha = $DonorSha
    built_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    workspace = $workspacePath
    tests_run = (-not $SkipTests)
    configuration = [ordered]@{
        generator = 'Ninja Multi-Config'
        build_type = 'Release'
        ggml_native = $false
        ggml_openmp_fetch = $true
        llama_build_server = $true
        ggml_rpc = $true
        build_shared_libs = $false
        llama_build_boringssl = $true
    }
    tools = [ordered]@{
        git = (& $git --version | Out-String).Trim()
        cmake = ((& $cmake --version | Select-Object -First 1) | Out-String).Trim()
        ninja = (& $ninja --version | Out-String).Trim()
        clang = ((& $clang --version | Select-Object -First 1) | Out-String).Trim()
    }
    outputs = $outputs
}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding utf8

Write-Host 'Qualified llama.cpp donor source built successfully.'
Write-Host "Source SHA: $DonorSha"
Write-Host "Server: $serverPath"
Write-Host "Receipt: $receiptPath"
