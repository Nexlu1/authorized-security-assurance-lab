[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Plan', 'Preflight', 'InstallRuntime', 'InitMachine', 'AcquireTarget', 'VerifyContainment', 'Stop')]
    [string]$Action,

    [string]$StateDirectory = (Join-Path $env:LOCALAPPDATA 'DaybreakRedReadiness\G1Podman')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# FOSS runtime pin: podman-container-tools/podman v6.1.1.
$PodmanVersion = '6.1.1'
$PodmanReleaseCommit = '8303f2e25b675ea7f82099d615c60969aec15870'
$PodmanInstallerUrl = 'https://github.com/podman-container-tools/podman/releases/download/v6.1.1/podman-installer-windows-amd64.msi'
$PodmanInstallerSha256 = '91d0e8ea0846c0151d531c88c329bb2729387231e4d1e42306a8e3ae9d09fc8a'
$PodmanDefaultExe = Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'

# FOSS machine image source/build project: podman-container-tools/podman-machine-os (Apache-2.0).
# The exact machine runtime is recorded after initialization; no moving image is silently treated as pinned evidence.
$MachineName = 'daybreak-g1-podman'

# Controlled target pin: WebGoat v2025.3, source tag commit c3ed45a733377bc7313b93f57ff518254d81380f.
$TargetTag = 'docker.io/webgoat/webgoat:v2025.3'
$TargetSourceCommit = 'c3ed45a733377bc7313b93f57ff518254d81380f'
$TargetLockPath = Join-Path $StateDirectory 'WEBGOAT_TARGET_LOCK.json'

$NetworkName = 'daybreak-g1-internal'
$ContainerName = 'daybreak-g1-webgoat-v2025-3'
$ExpectedPorts = @(8080, 9090)
$ExpectedBindings = [ordered]@{
    '8080/tcp' = [ordered]@{ HostIp = '127.0.0.1'; HostPort = '8080' }
    '9090/tcp' = [ordered]@{ HostIp = '127.0.0.1'; HostPort = '9090' }
}

function New-StateDirectory {
    New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
}

function Get-PodmanExecutable {
    $command = Get-Command podman.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    if (Test-Path -LiteralPath $PodmanDefaultExe -PathType Leaf) {
        return $PodmanDefaultExe
    }
    return $null
}

function Invoke-PodmanHost {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )
    $exe = Get-PodmanExecutable
    if ([string]::IsNullOrWhiteSpace($exe)) {
        throw 'Podman 6.1.1 is not installed in the current user context.'
    }
    $output = & $exe @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "podman $($Arguments -join ' ') failed with exit code $exitCode`n$text"
    }
    return [pscustomobject]@{ ExitCode = $exitCode; Output = $text }
}

function Invoke-PodmanRemote {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )
    $remoteArgs = @('--connection', $MachineName) + $Arguments
    return Invoke-PodmanHost -Arguments $remoteArgs -AllowFailure:$AllowFailure
}

function Assert-PodmanClientVersion {
    $result = Invoke-PodmanHost -Arguments @('--version')
    if ($result.Output -notmatch '^podman version ([0-9]+\.[0-9]+\.[0-9]+)') {
        throw "Could not parse Podman client version: $($result.Output)"
    }
    if ($Matches[1] -ne $PodmanVersion) {
        throw "HOLD: expected Podman client $PodmanVersion but observed $($Matches[1])."
    }
    return $Matches[1]
}

function Get-WslConfigurationEvidence {
    $path = Join-Path $env:USERPROFILE '.wslconfig'
    $result = [ordered]@{
        Path = $path
        Exists = $false
        Sha256 = $null
        NetworkingMode = $null
        HostAddressLoopback = $null
        LocalhostForwarding = $null
        Firewall = $null
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return $result
    }

    $result['Exists'] = $true
    $result['Sha256'] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    $lines = Get-Content -LiteralPath $path
    foreach ($raw in $lines) {
        $line = ([string]$raw).Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#') -or $line.StartsWith(';') -or $line.StartsWith('[')) {
            continue
        }
        $parts = $line -split '=', 2
        if ($parts.Count -ne 2) { continue }
        $key = $parts[0].Trim().ToLowerInvariant()
        $value = $parts[1].Trim().Trim('"').Trim("'").ToLowerInvariant()
        switch ($key) {
            'networkingmode' { $result['NetworkingMode'] = $value }
            'hostaddressloopback' { $result['HostAddressLoopback'] = $value }
            'localhostforwarding' { $result['LocalhostForwarding'] = $value }
            'firewall' { $result['Firewall'] = $value }
        }
    }
    return $result
}

function Assert-SafeWslConfiguration {
    $config = Get-WslConfigurationEvidence
    if ($config['NetworkingMode'] -and $config['NetworkingMode'] -ne 'nat') {
        throw "HOLD: .wslconfig networkingMode=$($config['NetworkingMode']) is not the approved conservative NAT/default model."
    }
    if ($config['HostAddressLoopback'] -eq 'true') {
        throw 'HOLD: .wslconfig hostAddressLoopback=true is not permitted for the G1 containment lab.'
    }
    if ($config['LocalhostForwarding'] -eq 'false') {
        throw 'HOLD: .wslconfig localhostForwarding=false would prevent the required host-loopback qualification.'
    }
    if ($config['Firewall'] -eq 'false') {
        throw 'HOLD: .wslconfig firewall=false weakens the selected G1 containment baseline.'
    }
    return $config
}

function Get-WslEvidence {
    if ($null -eq (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        throw 'HOLD: wsl.exe is unavailable. No Windows feature will be enabled automatically.'
    }
    $status = & wsl.exe --status 2>&1
    $statusExit = $LASTEXITCODE
    if ($statusExit -ne 0) {
        throw "HOLD: WSL status failed with exit code $statusExit. No Windows feature will be changed automatically."
    }
    $version = & wsl.exe --version 2>&1
    $versionExit = $LASTEXITCODE
    if ($versionExit -ne 0) {
        throw "HOLD: WSL version query failed with exit code $versionExit."
    }
    return [ordered]@{
        StatusText = (($status | Out-String).Trim())
        VersionText = (($version | Out-String).Trim())
        Config = (Assert-SafeWslConfiguration)
    }
}

function Get-MachineList {
    $result = Invoke-PodmanHost -Arguments @('machine', 'list', '--format', 'json')
    if ([string]::IsNullOrWhiteSpace($result.Output)) { return @() }
    return @($result.Output | ConvertFrom-Json)
}

function Get-ControlledMachineListItem {
    $items = @(Get-MachineList | Where-Object { [string]$_.Name -eq $MachineName })
    if ($items.Count -gt 1) {
        throw "HOLD: multiple Podman machines named $MachineName were reported."
    }
    if ($items.Count -eq 0) { return $null }
    return $items[0]
}

function Get-ControlledMachineInspect {
    $result = Invoke-PodmanHost -Arguments @('machine', 'inspect', $MachineName) -AllowFailure
    if ($result.ExitCode -ne 0) { return $null }
    $items = @($result.Output | ConvertFrom-Json)
    if ($items.Count -ne 1) {
        throw 'HOLD: expected exactly one machine-inspect result.'
    }
    return $items[0]
}

function Assert-ControlledMachinePolicy {
    $item = Get-ControlledMachineListItem
    if ($null -eq $item) {
        throw "HOLD: controlled Podman machine $MachineName does not exist."
    }
    if ([string]$item.VMType -ne 'wsl') {
        throw "HOLD: controlled machine provider is $($item.VMType), expected wsl."
    }
    if ([bool]$item.UserModeNetworking) {
        throw 'HOLD: Podman WSL user-mode-networking is enabled; this broader WSL-wide mode is not approved for the G1 lab.'
    }
    $inspect = Get-ControlledMachineInspect
    if ($null -eq $inspect) {
        throw 'HOLD: controlled Podman machine could not be inspected.'
    }
    if ([bool]$inspect.Rootful) {
        throw 'HOLD: controlled Podman machine is rootful; G1 requires the rootless machine connection.'
    }
    return [ordered]@{
        ListItem = $item
        Inspect = $inspect
    }
}

function Assert-RemoteRuntime {
    [void](Assert-PodmanClientVersion)
    $machine = Assert-ControlledMachinePolicy
    $infoResult = Invoke-PodmanRemote -Arguments @('info', '--format', 'json')
    $info = $infoResult.Output | ConvertFrom-Json
    $serverVersion = [string]$info.version.Version
    if ([string]::IsNullOrWhiteSpace($serverVersion)) {
        throw 'HOLD: Podman server version was not present in podman info.'
    }
    if ($serverVersion -ne $PodmanVersion) {
        throw "HOLD: Podman server $serverVersion does not match pinned client/runtime $PodmanVersion."
    }
    if (-not [bool]$info.host.security.rootless) {
        throw 'HOLD: Podman server does not report rootless execution.'
    }
    return [ordered]@{
        ClientVersion = $PodmanVersion
        ServerVersion = $serverVersion
        Rootless = $true
        Machine = $machine
    }
}

function Get-HostListeners {
    return @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in $ExpectedPorts } |
        Select-Object LocalAddress, LocalPort, OwningProcess)
}

function Assert-ControlledPortsFree {
    $listeners = @(Get-HostListeners)
    if ($listeners.Count -gt 0) {
        $summary = ($listeners | ForEach-Object { "$($_.LocalAddress):$($_.LocalPort) pid=$($_.OwningProcess)" }) -join '; '
        throw "HOLD: G1 ports are already in use: $summary"
    }
}

function Wait-ForLoopbackPorts {
    param([int]$TimeoutSeconds = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $ready = $true
        foreach ($port in $ExpectedPorts) {
            if (-not (Test-NetConnection -ComputerName '127.0.0.1' -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)) {
                $ready = $false
            }
        }
        if ($ready) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "HOLD: timed out waiting for WebGoat/WebWolf TCP listeners on loopback ports $($ExpectedPorts -join ', ')."
}

function Assert-WindowsListenersLoopbackOnly {
    $listeners = @(Get-HostListeners)
    foreach ($port in $ExpectedPorts) {
        $forPort = @($listeners | Where-Object { $_.LocalPort -eq $port })
        if ($forPort.Count -lt 1) {
            throw "HOLD: Windows did not report a listening socket for port $port."
        }
        foreach ($listener in $forPort) {
            if ([string]$listener.LocalAddress -notin @('127.0.0.1', '::1')) {
                throw "HOLD: non-loopback Windows listener observed: $($listener.LocalAddress):$port."
            }
        }
    }
    return $listeners
}

function Get-NonLoopbackIPv4 {
    $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -and
            $_.IPAddress -notlike '127.*' -and
            $_.IPAddress -notlike '169.254.*'
        } |
        Select-Object -ExpandProperty IPAddress -Unique)
    return $addresses
}

function Assert-NonLoopbackAddressesCannotReachPorts {
    $addresses = @(Get-NonLoopbackIPv4)
    if ($addresses.Count -eq 0) {
        throw 'HOLD: no non-loopback IPv4 address was available for negative containment validation.'
    }
    $checks = @()
    foreach ($address in $addresses) {
        foreach ($port in $ExpectedPorts) {
            $reachable = [bool](Test-NetConnection -ComputerName $address -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)
            $checks += [pscustomobject]@{ Address = $address; Port = $port; Reachable = $reachable }
            if ($reachable) {
                throw "HOLD: G1 service is reachable through non-loopback host address ${address}:$port."
            }
        }
    }
    return $checks
}

function Get-ControlledContainerId {
    $result = Invoke-PodmanRemote -Arguments @('ps', '-a', '--filter', "name=^/$ContainerName$", '--format', '{{.ID}}')
    return $result.Output.Trim()
}

function Get-ControlledNetwork {
    $result = Invoke-PodmanRemote -Arguments @('network', 'inspect', $NetworkName) -AllowFailure
    if ($result.ExitCode -ne 0) { return $null }
    $items = @($result.Output | ConvertFrom-Json)
    if ($items.Count -ne 1) { throw 'HOLD: expected exactly one controlled-network inspection result.' }
    return $items[0]
}

function Stop-ControlledWorkload {
    $containerId = Get-ControlledContainerId
    if (-not [string]::IsNullOrWhiteSpace($containerId)) {
        [void](Invoke-PodmanRemote -Arguments @('rm', '-f', '-t', '0', $ContainerName))
    }
    $network = Get-ControlledNetwork
    if ($null -ne $network) {
        [void](Invoke-PodmanRemote -Arguments @('network', 'rm', '-f', $NetworkName))
    }
}

function Assert-PortsClosed {
    param([int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $open = $false
        foreach ($port in $ExpectedPorts) {
            if (Test-NetConnection -ComputerName '127.0.0.1' -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue) {
                $open = $true
            }
        }
        if (-not $open) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw 'HOLD: one or more G1 loopback ports remained reachable after cleanup.'
}

function Read-TargetLock {
    if (-not (Test-Path -LiteralPath $TargetLockPath -PathType Leaf)) {
        throw "HOLD: target lock is missing. Run -Action AcquireTarget first."
    }
    $lock = Get-Content -LiteralPath $TargetLockPath -Raw | ConvertFrom-Json
    if ([string]$lock.tag -ne $TargetTag) { throw 'HOLD: target-lock tag mismatch.' }
    if ([string]$lock.source_commit -ne $TargetSourceCommit) { throw 'HOLD: target-lock source commit mismatch.' }
    if ([string]$lock.digest -notmatch '^docker\.io/webgoat/webgoat@sha256:[0-9a-f]{64}$') {
        throw "HOLD: target lock contains an invalid registry digest: $($lock.digest)"
    }
    return $lock
}

function Write-Receipt {
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Receipt)
    New-StateDirectory
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
    $path = Join-Path $StateDirectory "G1_PODMAN_$($Receipt['action'])_$stamp.json"
    $Receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

if ($Action -eq 'Plan') {
    [pscustomobject]@{
        Authority = 'G1 only — prerequisites, acquisition, startup and containment validation; G2 CLOSED'
        Runtime = "Podman $PodmanVersion (Apache-2.0), release commit $PodmanReleaseCommit"
        RuntimeInstaller = $PodmanInstallerUrl
        RuntimeInstallerSHA256 = $PodmanInstallerSha256
        Machine = "$MachineName / WSL / rootless / user-mode-networking disabled"
        Target = "$TargetTag / source commit $TargetSourceCommit / exact registry digest locked after pull"
        Network = "$NetworkName / Podman internal rootless bridge"
        Bindings = '127.0.0.1:8080:8080 ; 127.0.0.1:9090:9090'
        LocalState = $StateDirectory
        G2 = 'CLOSED — no HTTP crawling, scanning, lesson solving, injection, authentication bypass or exploit validation'
    } | Format-List
    exit 0
}

if ($Action -eq 'Preflight') {
    $wsl = Get-WslEvidence
    $podmanExe = Get-PodmanExecutable
    $podman = [ordered]@{ Installed = $false; Path = $podmanExe; Version = $null }
    if (-not [string]::IsNullOrWhiteSpace($podmanExe)) {
        $podman['Installed'] = $true
        $podman['Version'] = Assert-PodmanClientVersion
    }
    Assert-ControlledPortsFree
    $receipt = [ordered]@{
        schema_version = 1
        action = 'Preflight'
        timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
        wsl = $wsl
        podman = $podman
        result = 'PASS'
        scope = 'G1 prerequisite observation only; no installation, target startup or vulnerability testing'
    }
    $path = Write-Receipt -Receipt $receipt
    Write-Output "G1 Podman preflight PASS. Receipt: $path"
    exit 0
}

if ($Action -eq 'InstallRuntime') {
    [void](Get-WslEvidence)
    New-StateDirectory
    $download = Join-Path $StateDirectory 'podman-installer-windows-amd64-v6.1.1.msi'
    $log = Join-Path $StateDirectory 'podman-msi-v6.1.1.log'

    Invoke-WebRequest -UseBasicParsing -Uri $PodmanInstallerUrl -OutFile $download
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $download).Hash.ToLowerInvariant()
    if ($hash -ne $PodmanInstallerSha256) {
        throw "HOLD: Podman installer SHA-256 mismatch. Observed $hash."
    }
    $signature = Get-AuthenticodeSignature -FilePath $download
    if ([string]$signature.Status -ne 'Valid') {
        throw "HOLD: Podman MSI Authenticode status is $($signature.Status)."
    }

    $process = Start-Process -FilePath 'msiexec.exe' -Wait -PassThru -ArgumentList @(
        '/package', $download,
        '/quiet',
        '/norestart',
        '/l*v', $log,
        'MSIINSTALLPERUSER=1',
        'MACHINE_PROVIDER=wsl'
    )
    if ($process.ExitCode -notin @(0, 3010)) {
        throw "HOLD: Podman per-user MSI exited $($process.ExitCode). Review $log."
    }
    if ($process.ExitCode -eq 3010) {
        throw "HOLD: Podman installer requested a reboot. Runtime files were installed, but no reboot will be initiated automatically. Review $log."
    }

    $exe = Get-PodmanExecutable
    if ([string]::IsNullOrWhiteSpace($exe)) {
        throw 'HOLD: Podman executable was not found after the per-user install.'
    }
    $version = Assert-PodmanClientVersion
    $receipt = [ordered]@{
        schema_version = 1
        action = 'InstallRuntime'
        timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
        podman_version = $version
        podman_release_commit = $PodmanReleaseCommit
        installer_url = $PodmanInstallerUrl
        installer_sha256 = $hash
        installer_signature_status = [string]$signature.Status
        installer_signer = [string]$signature.SignerCertificate.Subject
        install_scope = 'per-user'
        provider = 'wsl'
        result = 'PASS'
        scope = 'G1 FOSS runtime prerequisite only; no target acquisition/startup or vulnerability testing'
    }
    $path = Write-Receipt -Receipt $receipt
    Write-Output "Podman $version per-user runtime install PASS. Receipt: $path"
    exit 0
}

if ($Action -eq 'InitMachine') {
    $wsl = Get-WslEvidence
    [void](Assert-PodmanClientVersion)
    $existing = Get-ControlledMachineListItem
    if ($null -eq $existing) {
        [void](Invoke-PodmanHost -Arguments @('machine', 'init', $MachineName))
    }

    $item = Get-ControlledMachineListItem
    if ($null -eq $item) { throw 'HOLD: machine init completed without the controlled machine appearing in the machine list.' }
    if ([string]$item.VMType -ne 'wsl') { throw "HOLD: machine provider is $($item.VMType), expected wsl." }
    if ([bool]$item.UserModeNetworking) { throw 'HOLD: user-mode-networking unexpectedly enabled on controlled WSL machine.' }

    if (-not [bool]$item.Running) {
        [void](Invoke-PodmanHost -Arguments @('machine', 'start', $MachineName))
    }
    $runtime = Assert-RemoteRuntime
    $receipt = [ordered]@{
        schema_version = 1
        action = 'InitMachine'
        timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
        wsl = $wsl
        runtime = $runtime
        result = 'PASS'
        scope = 'G1 dedicated rootless WSL Podman machine only; no target acquisition/startup or vulnerability testing'
    }
    $path = Write-Receipt -Receipt $receipt
    Write-Output "Dedicated G1 Podman WSL machine PASS. Receipt: $path"
    exit 0
}

if ($Action -eq 'AcquireTarget') {
    [void](Get-WslEvidence)
    $runtime = Assert-RemoteRuntime
    [void](Invoke-PodmanRemote -Arguments @('pull', $TargetTag))
    $inspectResult = Invoke-PodmanRemote -Arguments @('image', 'inspect', $TargetTag)
    $items = @($inspectResult.Output | ConvertFrom-Json)
    if ($items.Count -ne 1) { throw 'HOLD: expected exactly one WebGoat image inspection result.' }
    $image = $items[0]
    $digests = @($image.RepoDigests | Where-Object { [string]$_ -match '^docker\.io/webgoat/webgoat@sha256:[0-9a-f]{64}$' } | Select-Object -Unique)
    if ($digests.Count -ne 1) {
        throw "HOLD: expected one unambiguous docker.io WebGoat registry digest; observed $($digests.Count)."
    }

    New-StateDirectory
    $lock = [ordered]@{
        schema_version = 1
        acquired_utc = (Get-Date).ToUniversalTime().ToString('o')
        tag = $TargetTag
        source_commit = $TargetSourceCommit
        digest = [string]$digests[0]
        image_id = [string]$image.Id
        repo_tags = @($image.RepoTags)
        podman_client_version = $runtime['ClientVersion']
        podman_server_version = $runtime['ServerVersion']
        machine = $MachineName
    }
    $lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $TargetLockPath -Encoding UTF8
    $receipt = [ordered]@{
        schema_version = 1
        action = 'AcquireTarget'
        timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
        target_lock = $lock
        lock_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $TargetLockPath).Hash.ToLowerInvariant()
        result = 'PASS'
        scope = 'G1 target acquisition only; no target startup or vulnerability testing'
    }
    $path = Write-Receipt -Receipt $receipt
    Write-Output "WebGoat v2025.3 acquired and digest-locked: $($lock['digest'])"
    Write-Output "Receipt: $path"
    exit 0
}

if ($Action -eq 'Stop') {
    $exe = Get-PodmanExecutable
    if (-not [string]::IsNullOrWhiteSpace($exe)) {
        $item = Get-ControlledMachineListItem
        if ($null -ne $item) {
            if ([bool]$item.Running) {
                Stop-ControlledWorkload
                Assert-PortsClosed
                [void](Invoke-PodmanHost -Arguments @('machine', 'stop', $MachineName) -AllowFailure)
            }
        }
    }
    Write-Output 'Controlled G1 workload is stopped; the dedicated Podman machine was stopped when present.'
    exit 0
}

if ($Action -ne 'VerifyContainment') {
    throw "Unhandled action: $Action"
}

$wsl = Get-WslEvidence
$runtime = Assert-RemoteRuntime
$lock = Read-TargetLock
Assert-ControlledPortsFree

if (-not [string]::IsNullOrWhiteSpace((Get-ControlledContainerId))) {
    throw "HOLD: controlled container already exists. Run -Action Stop before containment verification."
}
if ($null -ne (Get-ControlledNetwork)) {
    throw "HOLD: controlled network already exists. Run -Action Stop before containment verification."
}

# Confirm the digest-locked image is still locally available and unchanged.
$imageCheck = Invoke-PodmanRemote -Arguments @('image', 'inspect', [string]$lock.digest) -AllowFailure
if ($imageCheck.ExitCode -ne 0) { throw 'HOLD: digest-locked WebGoat image is no longer locally inspectable.' }
$imageItems = @($imageCheck.Output | ConvertFrom-Json)
if ($imageItems.Count -ne 1 -or [string]$imageItems[0].Id -ne [string]$lock.image_id) {
    throw 'HOLD: digest-locked WebGoat image identity no longer matches the acquisition lock.'
}

$started = $false
$networkCreated = $false
$receipt = [ordered]@{
    schema_version = 1
    action = 'VerifyContainment'
    timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
    wsl = $wsl
    runtime = $runtime
    target = $lock
    expected_bindings = $ExpectedBindings
    result = 'HOLD'
    scope = 'G1 startup and containment validation only; no HTTP application requests or vulnerability testing'
}

try {
    [void](Invoke-PodmanRemote -Arguments @('network', 'create', '--internal', $NetworkName))
    $networkCreated = $true
    $network = Get-ControlledNetwork
    if ($null -eq $network -or -not [bool]$network.internal) {
        throw 'HOLD: controlled Podman network does not report internal=true.'
    }
    $receipt['network'] = $network

    $run = Invoke-PodmanRemote -Arguments @(
        'run', '-d',
        '--name', $ContainerName,
        '--network', $NetworkName,
        '-p', '127.0.0.1:8080:8080',
        '-p', '127.0.0.1:9090:9090',
        [string]$lock.digest
    )
    $containerId = $run.Output.Trim()
    if ([string]::IsNullOrWhiteSpace($containerId)) { throw 'HOLD: Podman run returned an empty container ID.' }
    $started = $true
    $receipt['container_id'] = $containerId

    $containerInspectResult = Invoke-PodmanRemote -Arguments @('inspect', $ContainerName)
    $containerItems = @($containerInspectResult.Output | ConvertFrom-Json)
    if ($containerItems.Count -ne 1 -or -not [bool]$containerItems[0].State.Running) {
        throw 'HOLD: controlled WebGoat container is not running after startup.'
    }
    $ports = $containerItems[0].NetworkSettings.Ports
    foreach ($containerPort in $ExpectedBindings.Keys) {
        $expected = $ExpectedBindings[$containerPort]
        $bindings = @($ports.$containerPort)
        if ($bindings.Count -ne 1) { throw "HOLD: expected one mapping for $containerPort, observed $($bindings.Count)." }
        if ([string]$bindings[0].HostIp -ne $expected['HostIp'] -or [string]$bindings[0].HostPort -ne $expected['HostPort']) {
            throw "HOLD: unexpected mapping for ${containerPort}: $($bindings[0].HostIp):$($bindings[0].HostPort)."
        }
    }

    Wait-ForLoopbackPorts
    $listeners = @(Assert-WindowsListenersLoopbackOnly)
    $negativeChecks = @(Assert-NonLoopbackAddressesCannotReachPorts)

    # Internal bridge must provide no IPv4 default route to the container.
    $routeResult = Invoke-PodmanRemote -Arguments @('exec', $ContainerName, 'cat', '/proc/net/route')
    $defaultRoute = $false
    foreach ($line in ($routeResult.Output -split "`r?`n")) {
        $parts = @($line -split '\s+' | Where-Object { $_ })
        if ($parts.Count -ge 2 -and $parts[1] -eq '00000000') { $defaultRoute = $true }
    }
    if ($defaultRoute) { throw 'HOLD: WebGoat container has an IPv4 default route on the internal network.' }

    # If an IPv6 route table exists, reject an IPv6 default route as well.
    $route6Result = Invoke-PodmanRemote -Arguments @('exec', $ContainerName, 'cat', '/proc/net/ipv6_route') -AllowFailure
    if ($route6Result.ExitCode -eq 0) {
        foreach ($line in ($route6Result.Output -split "`r?`n")) {
            $parts = @($line -split '\s+' | Where-Object { $_ })
            if ($parts.Count -ge 2 -and $parts[0] -eq ('0' * 32) -and $parts[1] -eq '00') {
                throw 'HOLD: WebGoat container has an IPv6 default route on the internal network.'
            }
        }
    }

    $receipt['windows_listeners'] = @($listeners)
    $receipt['negative_nonloopback_checks'] = @($negativeChecks)
    $receipt['container_ipv4_routes'] = $routeResult.Output
    $receipt['container_ipv6_routes'] = $route6Result.Output
    $receipt['loopback_tcp_available'] = $true
    $receipt['result'] = 'PASS'
} catch {
    $receipt['error'] = $_.Exception.Message
    throw
} finally {
    if ($started -or $networkCreated) {
        try {
            Stop-ControlledWorkload
            Assert-PortsClosed
            $receipt['post_stop_ports_closed'] = $true
        } catch {
            $receipt['post_stop_ports_closed'] = $false
            $receipt['cleanup_error'] = $_.Exception.Message
            $receipt['result'] = 'HOLD'
        }
    }
    $receipt['receipt_written_utc'] = (Get-Date).ToUniversalTime().ToString('o')
    $path = Write-Receipt -Receipt $receipt
    Write-Output "G1 Podman containment receipt: $path"
}

if ($receipt['result'] -ne 'PASS') {
    throw 'G1 Podman containment verification did not reach PASS. Review the local receipt.'
}

Write-Output 'G1 Podman containment PASS. No HTTP application request or vulnerability test was performed; container/network were removed and the controlled ports closed.'
