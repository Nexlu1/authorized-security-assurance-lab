[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Start', 'Stop', 'Status')]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [string]$Workspace,

    [string]$ModelPath,

    [ValidateRange(1024, 65535)]
    [int]$Port = 8080,

    [string]$ServerPath,

    [ValidateRange(0, 1048576)]
    [int]$ContextSize = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$DonorSha = '0ef4d560e12c1a46470265c1abd31dd47c777d23'
$workspacePath = [System.IO.Path]::GetFullPath($Workspace)
$runtimePath = Join-Path $workspacePath 'runtime'
$statePath = Join-Path $runtimePath 'llama-server-state.json'
$logPath = Join-Path $runtimePath 'llama-server.log'

function Read-State {
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $statePath -Raw -Encoding utf8 | ConvertFrom-Json
    }
    catch {
        throw "Rig Worker runtime state is unreadable: $statePath. $($_.Exception.Message)"
    }
}

function Get-DefaultServerPath {
    return Join-Path $workspacePath 'llama.cpp-build\bin\Release\llama-server.exe'
}

function Get-ResolvedServerPath {
    $candidate = if ($ServerPath) { $ServerPath } else { Get-DefaultServerPath }
    return [System.IO.Path]::GetFullPath($candidate)
}

function Get-VerifiedStateProcess {
    param([Parameter(Mandatory = $true)]$State)

    $process = Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }

    try {
        $actualPath = [System.IO.Path]::GetFullPath($process.Path)
    }
    catch {
        throw "Process $($State.pid) exists but its executable path could not be verified. Refusing to manage it."
    }

    $expectedPath = [System.IO.Path]::GetFullPath([string]$State.server_path)
    if (-not [string]::Equals($actualPath, $expectedPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "PID $($State.pid) now belongs to a different executable. Expected '$expectedPath', found '$actualPath'. Refusing to manage it."
    }
    return $process
}

function Write-Status {
    param(
        [bool]$Running,
        $State,
        [string]$Reason = ''
    )

    $result = [ordered]@{
        running = $Running
        reason = $Reason
        state_file = $statePath
    }
    if ($State) {
        $result.pid = $State.pid
        $result.server_path = $State.server_path
        $result.model_path = $State.model_path
        $result.host = $State.host
        $result.port = $State.port
        $result.started_at_utc = $State.started_at_utc
        $result.log_path = $State.log_path
        $result.donor_commit_sha = $State.donor_commit_sha
    }
    $result | ConvertTo-Json -Depth 5
}

switch ($Action) {
    'Status' {
        $state = Read-State
        if (-not $state) {
            Write-Status -Running $false -State $null -Reason 'no runtime state exists'
            exit 0
        }
        $process = Get-VerifiedStateProcess -State $state
        if (-not $process) {
            Write-Status -Running $false -State $state -Reason 'state exists but process is not running'
            exit 0
        }
        Write-Status -Running $true -State $state -Reason 'verified process is running'
        exit 0
    }

    'Stop' {
        $state = Read-State
        if (-not $state) {
            Write-Host 'Rig Worker llama-server is not recorded as running.'
            exit 0
        }
        $process = Get-VerifiedStateProcess -State $state
        if (-not $process) {
            Remove-Item -LiteralPath $statePath -Force
            Write-Host 'Removed stale Rig Worker llama-server state; no matching process was running.'
            exit 0
        }

        Stop-Process -Id $process.Id
        try {
            Wait-Process -Id $process.Id -Timeout 15 -ErrorAction Stop
        }
        catch {
            if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
                Stop-Process -Id $process.Id -Force
                Wait-Process -Id $process.Id -Timeout 5 -ErrorAction SilentlyContinue
            }
        }

        if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
            throw "Rig Worker llama-server process $($process.Id) did not stop."
        }

        $stopReceipt = [ordered]@{
            schema_version = 1
            pid = $process.Id
            stopped_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
            server_path = $state.server_path
            donor_commit_sha = $state.donor_commit_sha
        }
        $stopReceipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runtimePath 'last-stop.json') -Encoding utf8
        Remove-Item -LiteralPath $statePath -Force
        Write-Host "Stopped Rig Worker llama-server PID $($process.Id)."
        exit 0
    }

    'Start' {
        New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null

        $existing = Read-State
        if ($existing) {
            $existingProcess = Get-VerifiedStateProcess -State $existing
            if ($existingProcess) {
                throw "Rig Worker llama-server is already running as PID $($existingProcess.Id)."
            }
            Remove-Item -LiteralPath $statePath -Force
        }

        if (-not $ModelPath) {
            throw 'Start requires -ModelPath pointing to an existing local GGUF model.'
        }
        $resolvedModel = [System.IO.Path]::GetFullPath($ModelPath)
        if (-not (Test-Path -LiteralPath $resolvedModel -PathType Leaf)) {
            throw "Model file does not exist: $resolvedModel"
        }
        if ([System.IO.Path]::GetExtension($resolvedModel) -ne '.gguf') {
            throw "Rig Worker Slice 1 expects a local .gguf model: $resolvedModel"
        }

        $resolvedServer = Get-ResolvedServerPath
        if (-not (Test-Path -LiteralPath $resolvedServer -PathType Leaf)) {
            throw "Qualified llama-server executable was not found: $resolvedServer"
        }

        $apiKey = [string]$env:RIG_WORKER_API_KEY
        if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey.Length -lt 24) {
            throw 'Set RIG_WORKER_API_KEY to a strong value of at least 24 characters before Start. It will not be written to disk or placed on the child command line.'
        }

        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        if ($listener) {
            throw "TCP port $Port is already listening. Choose another -Port."
        }

        $arguments = @(
            '--model', $resolvedModel,
            '--host', '127.0.0.1',
            '--port', $Port.ToString(),
            '--offline',
            '--no-webui',
            '--cors-origins', 'localhost',
            '--log-file', $logPath
        )
        if ($ContextSize -gt 0) {
            $arguments += @('--ctx-size', $ContextSize.ToString())
        }

        $oldLlamaApiKey = $env:LLAMA_API_KEY
        try {
            $env:LLAMA_API_KEY = $apiKey
            $process = Start-Process -FilePath $resolvedServer -ArgumentList $arguments -PassThru -WindowStyle Hidden
        }
        finally {
            if ($null -eq $oldLlamaApiKey) {
                Remove-Item Env:LLAMA_API_KEY -ErrorAction SilentlyContinue
            }
            else {
                $env:LLAMA_API_KEY = $oldLlamaApiKey
            }
        }

        Start-Sleep -Milliseconds 750
        $process.Refresh()
        if ($process.HasExited) {
            throw "llama-server exited immediately with code $($process.ExitCode). Review $logPath."
        }

        $modelInfo = Get-Item -LiteralPath $resolvedModel
        $serverInfo = Get-Item -LiteralPath $resolvedServer
        $state = [ordered]@{
            schema_version = 1
            target_project = 'Rig Worker'
            pid = $process.Id
            started_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
            server_path = $serverInfo.FullName
            server_sha256 = (Get-FileHash -LiteralPath $serverInfo.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            donor_commit_sha = $DonorSha
            model_path = $modelInfo.FullName
            model_size_bytes = $modelInfo.Length
            model_last_write_utc = $modelInfo.LastWriteTimeUtc.ToString('o')
            host = '127.0.0.1'
            port = $Port
            context_size = $ContextSize
            offline = $true
            web_ui = $false
            cors_origins = 'localhost'
            authentication = 'LLAMA_API_KEY inherited from RIG_WORKER_API_KEY; key intentionally omitted from state'
            log_path = $logPath
        }
        $state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statePath -Encoding utf8

        Write-Host "Started Rig Worker llama-server PID $($process.Id) on 127.0.0.1:$Port."
        Write-Host "State: $statePath"
        Write-Host "Log: $logPath"
        exit 0
    }
}
