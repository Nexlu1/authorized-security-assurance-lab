[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Plan', 'Preflight', 'Acquire', 'VerifyContainment', 'Stop')]
    [string]$Action,

    [string]$EvidenceDirectory = (Join-Path $env:LOCALAPPDATA 'DaybreakRedReadiness\G1Evidence')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Image = 'webgoat/webgoat:v2025.3'
$ContainerName = 'daybreak-g1-webgoat-v2025-3'
$ExpectedBindings = [ordered]@{
    '8080/tcp' = [ordered]@{ HostIp = '127.0.0.1'; HostPort = '8080' }
    '9090/tcp' = [ordered]@{ HostIp = '127.0.0.1'; HostPort = '9090' }
}
$ExpectedPorts = @(8080, 9090)

function Invoke-Docker {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $output = & docker @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $exitCode`n$text"
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $text
    }
}

function Get-DockerServerVersion {
    $result = Invoke-Docker -Arguments @('version', '--format', '{{.Server.Version}}')
    if ([string]::IsNullOrWhiteSpace($result.Output)) {
        throw 'Docker daemon returned an empty server version.'
    }
    return $result.Output
}

function Get-ContainerIdIfPresent {
    $result = Invoke-Docker -Arguments @('ps', '-a', '--filter', "name=^/$ContainerName$", '--format', '{{.ID}}')
    return $result.Output.Trim()
}

function Get-ImageMetadata {
    $result = Invoke-Docker -Arguments @('image', 'inspect', $Image)
    $items = @($result.Output | ConvertFrom-Json)
    if ($items.Count -lt 1) {
        throw "Docker returned no metadata for $Image."
    }
    $item = $items[0]
    return [ordered]@{
        Id = [string]$item.Id
        RepoTags = @($item.RepoTags)
        RepoDigests = @($item.RepoDigests)
        Created = [string]$item.Created
        Os = [string]$item.Os
        Architecture = [string]$item.Architecture
    }
}

function Get-HostListeners {
    $rows = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in $ExpectedPorts } |
        Select-Object LocalAddress, LocalPort, OwningProcess)
    return @($rows)
}

function Assert-NoPortConflict {
    $listeners = @(Get-HostListeners)
    if ($listeners.Count -gt 0) {
        $summary = ($listeners | ForEach-Object { "$($_.LocalAddress):$($_.LocalPort) pid=$($_.OwningProcess)" }) -join '; '
        throw "Required G1 ports are already listening before WebGoat start: $summary"
    }
}

function Get-ContainerInspection {
    $result = Invoke-Docker -Arguments @('inspect', $ContainerName)
    $items = @($result.Output | ConvertFrom-Json)
    if ($items.Count -ne 1) {
        throw 'Expected exactly one container inspection result.'
    }
    return $items[0]
}

function Assert-ExactLoopbackBindings {
    param([Parameter(Mandatory = $true)]$Inspection)

    $ports = $Inspection.NetworkSettings.Ports
    foreach ($containerPort in $ExpectedBindings.Keys) {
        $expected = $ExpectedBindings[$containerPort]
        $bindings = @($ports.$containerPort)
        if ($bindings.Count -ne 1) {
            throw "Expected exactly one published binding for $containerPort; observed $($bindings.Count)."
        }
        $binding = $bindings[0]
        if ([string]$binding.HostIp -ne $expected.HostIp -or [string]$binding.HostPort -ne $expected.HostPort) {
            throw "Unsafe or unexpected Docker binding for ${containerPort}: $($binding.HostIp):$($binding.HostPort)."
        }
    }
}

function Wait-ForExpectedListeners {
    param([int]$TimeoutSeconds = 90)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $listeners = @(Get-HostListeners)
        $portsSeen = @($listeners | Select-Object -ExpandProperty LocalPort -Unique)
        if (($ExpectedPorts | Where-Object { $_ -notin $portsSeen }).Count -eq 0) {
            return $listeners
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    throw "Timed out waiting for local listeners on ports $($ExpectedPorts -join ', ')."
}

function Assert-ListenersAreLoopbackOnly {
    param([Parameter(Mandatory = $true)][object[]]$Listeners)

    foreach ($listener in $Listeners) {
        if ([string]$listener.LocalAddress -notin @('127.0.0.1', '::1')) {
            throw "Unsafe host listener observed on $($listener.LocalAddress):$($listener.LocalPort)."
        }
    }
}

function Wait-ForTcpAvailability {
    param([int]$TimeoutSeconds = 90)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $state = [ordered]@{}
    do {
        $allReady = $true
        foreach ($port in $ExpectedPorts) {
            $ready = [bool](Test-NetConnection -ComputerName '127.0.0.1' -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)
            $state[[string]$port] = $ready
            if (-not $ready) { $allReady = $false }
        }
        if ($allReady) { return $state }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    throw "Timed out waiting for TCP availability on loopback ports $($ExpectedPorts -join ', ')."
}

function Stop-ControlledContainer {
    $existing = Get-ContainerIdIfPresent
    if (-not [string]::IsNullOrWhiteSpace($existing)) {
        [void](Invoke-Docker -Arguments @('rm', '--force', $ContainerName))
    }
}

function Assert-PortsClosedAfterStop {
    param([int]$TimeoutSeconds = 30)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $listeners = @(Get-HostListeners)
        if ($listeners.Count -eq 0) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    $summary = ($listeners | ForEach-Object { "$($_.LocalAddress):$($_.LocalPort) pid=$($_.OwningProcess)" }) -join '; '
    throw "G1 ports remained open after controlled container stop: $summary"
}

function Write-Receipt {
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Receipt)

    New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
    $path = Join-Path $EvidenceDirectory "G1_WEBGOAT_CONTAINMENT_$stamp.json"
    $Receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

if ($Action -eq 'Plan') {
    [pscustomobject]@{
        Authority = 'G1 only — no vulnerability testing'
        Image = $Image
        ContainerName = $ContainerName
        UpstreamPattern = 'WebGoat v2025.3 README Docker loopback publishing'
        AcquireCommand = "docker pull $Image"
        StartCommand = "docker run --detach --rm --name $ContainerName -p 127.0.0.1:8080:8080 -p 127.0.0.1:9090:9090 $Image"
        Actions = @('Preflight', 'Acquire', 'VerifyContainment', 'Stop')
        G2 = 'CLOSED — this helper performs no scanning, lesson solving, injection, exploit validation, or other vulnerability testing'
    } | Format-List
    exit 0
}

if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found. No system changes were made.'
}

$dockerVersion = Get-DockerServerVersion

if ($Action -eq 'Stop') {
    Stop-ControlledContainer
    Assert-PortsClosedAfterStop
    Write-Output "Controlled container is absent and G1 ports are closed."
    exit 0
}

if ($Action -eq 'Preflight') {
    Assert-NoPortConflict
    $existing = Get-ContainerIdIfPresent
    if (-not [string]::IsNullOrWhiteSpace($existing)) {
        throw "Controlled container already exists ($existing). Run -Action Stop before continuing."
    }
    $receipt = [ordered]@{
        schema_version = 1
        action = 'Preflight'
        timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
        docker_server_version = $dockerVersion
        image = $Image
        container_name = $ContainerName
        port_conflicts = @()
        result = 'PASS'
        scope = 'G1 containment prerequisites only; no vulnerability testing'
    }
    $path = Write-Receipt -Receipt $receipt
    Write-Output "G1 preflight PASS. Receipt: $path"
    exit 0
}

if ($Action -eq 'Acquire') {
    $existing = Get-ContainerIdIfPresent
    if (-not [string]::IsNullOrWhiteSpace($existing)) {
        throw "Controlled container already exists ($existing). Stop it before image acquisition."
    }
    $pull = Invoke-Docker -Arguments @('pull', $Image)
    $imageMetadata = Get-ImageMetadata
    $receipt = [ordered]@{
        schema_version = 1
        action = 'Acquire'
        timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
        docker_server_version = $dockerVersion
        image = $Image
        image_metadata = $imageMetadata
        pull_output = $pull.Output
        result = 'PASS'
        scope = 'G1 image acquisition only; no target startup or vulnerability testing'
    }
    $path = Write-Receipt -Receipt $receipt
    Write-Output "G1 image acquisition PASS. Receipt: $path"
    exit 0
}

if ($Action -ne 'VerifyContainment') {
    throw "Unhandled action: $Action"
}

Assert-NoPortConflict
$existing = Get-ContainerIdIfPresent
if (-not [string]::IsNullOrWhiteSpace($existing)) {
    throw "Controlled container already exists ($existing). Run -Action Stop before VerifyContainment."
}

# Fail closed if the pinned image has not already been acquired. This action does
# not pull from the network; use -Action Acquire separately.
try {
    $imageMetadata = Get-ImageMetadata
} catch {
    throw "Pinned image $Image is not locally inspectable. Run -Action Acquire first. $($_.Exception.Message)"
}

$started = $false
$receipt = [ordered]@{
    schema_version = 1
    action = 'VerifyContainment'
    timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
    docker_server_version = $dockerVersion
    image = $Image
    image_metadata = $imageMetadata
    container_name = $ContainerName
    expected_bindings = $ExpectedBindings
    result = 'HOLD'
    scope = 'G1 startup and containment validation only; no vulnerability testing'
}

try {
    $run = Invoke-Docker -Arguments @(
        'run', '--detach', '--rm', '--name', $ContainerName,
        '--publish', '127.0.0.1:8080:8080',
        '--publish', '127.0.0.1:9090:9090',
        $Image
    )
    $containerId = $run.Output.Trim()
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw 'Docker run returned an empty container ID.'
    }
    $started = $true
    $receipt['container_id'] = $containerId

    $inspection = Get-ContainerInspection
    if (-not [bool]$inspection.State.Running) {
        throw 'Container exists but Docker does not report it as running.'
    }
    Assert-ExactLoopbackBindings -Inspection $inspection

    $listeners = @(Wait-ForExpectedListeners)
    Assert-ListenersAreLoopbackOnly -Listeners $listeners
    $tcp = Wait-ForTcpAvailability

    $receipt['observed_bindings'] = [ordered]@{
        '8080/tcp' = @($inspection.NetworkSettings.Ports.'8080/tcp')
        '9090/tcp' = @($inspection.NetworkSettings.Ports.'9090/tcp')
    }
    $receipt['host_listeners'] = @($listeners | ForEach-Object {
        [ordered]@{
            LocalAddress = [string]$_.LocalAddress
            LocalPort = [int]$_.LocalPort
            OwningProcess = [int]$_.OwningProcess
        }
    })
    $receipt['loopback_tcp_available'] = $tcp
    $receipt['result'] = 'PASS'
} catch {
    $receipt['error'] = $_.Exception.Message
    throw
} finally {
    if ($started) {
        try {
            Stop-ControlledContainer
            Assert-PortsClosedAfterStop
            $receipt['post_stop_ports_closed'] = $true
        } catch {
            $receipt['post_stop_ports_closed'] = $false
            $receipt['stop_error'] = $_.Exception.Message
            $receipt['result'] = 'HOLD'
        }
    }
    $receipt['receipt_written_utc'] = (Get-Date).ToUniversalTime().ToString('o')
    $path = Write-Receipt -Receipt $receipt
    Write-Output "G1 containment receipt: $path"
}

if ($receipt['result'] -ne 'PASS') {
    throw 'G1 containment verification did not reach PASS. Review the local receipt.'
}

Write-Output 'G1 containment verification PASS. The WebGoat container was stopped and both controlled ports closed.'
