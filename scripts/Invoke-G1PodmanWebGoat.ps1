[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Plan', 'Preflight', 'InstallRuntime', 'InitMachine', 'AcquireTarget', 'VerifyContainment', 'Stop')]
    [string]$Action,
    [string]$StateDirectory = (Join-Path $env:LOCALAPPDATA 'DaybreakRedReadiness\G1Podman')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# FOSS runtime: podman-container-tools/podman v6.1.1 (Apache-2.0).
$PodmanVersion = '6.1.1'
$PodmanReleaseCommit = '8303f2e25b675ea7f82099d615c60969aec15870'
$PodmanInstallerUrl = 'https://github.com/podman-container-tools/podman/releases/download/v6.1.1/podman-installer-windows-amd64.msi'
$PodmanInstallerSha256 = '91d0e8ea0846c0151d531c88c329bb2729387231e4d1e42306a8e3ae9d09fc8a'
$PodmanDefaultExe = Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'

# Dedicated FOSS machine/runtime. Podman machine OS is built from the public Apache-2.0
# podman-container-tools/podman-machine-os project. The live machine state is recorded locally.
$MachineName = 'daybreak-g1-podman'

# Controlled target: WebGoat v2025.3 (GPL-2.0-or-later).
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

function Ensure-StateDirectory {
    New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
}

function Write-Receipt {
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Receipt)
    Ensure-StateDirectory
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
    $path = Join-Path $StateDirectory "G1_PODMAN_$($Receipt['action'])_$stamp.json"
    $Receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

function Get-PodmanExe {
    $cmd = Get-Command podman.exe -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }
    if (Test-Path -LiteralPath $PodmanDefaultExe -PathType Leaf) { return $PodmanDefaultExe }
    return $null
}

function Invoke-Podman {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure,
        [switch]$Remote
    )
    $exe = Get-PodmanExe
    if ([string]::IsNullOrWhiteSpace($exe)) { throw 'Podman is not installed in the current user context.' }
    $args = $Arguments
    if ($Remote) { $args = @('--connection', $MachineName) + $Arguments }
    $output = & $exe @args 2>&1
    $code = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    if (-not $AllowFailure -and $code -ne 0) {
        throw "podman $($args -join ' ') failed with exit code $code`n$text"
    }
    return [pscustomobject]@{ ExitCode = $code; Output = $text }
}

function Assert-PodmanClientVersion {
    $result = Invoke-Podman -Arguments @('--version')
    if ($result.Output -notmatch '^podman version ([0-9]+\.[0-9]+\.[0-9]+)') {
        throw "HOLD: cannot parse Podman client version: $($result.Output)"
    }
    if ($Matches[1] -ne $PodmanVersion) {
        throw "HOLD: expected Podman client $PodmanVersion, observed $($Matches[1])."
    }
    return $Matches[1]
}

function Get-WslConfigEvidence {
    $path = Join-Path $env:USERPROFILE '.wslconfig'
    $evidence = [ordered]@{
        Path = $path; Exists = $false; Sha256 = $null
        NetworkingMode = $null; HostAddressLoopback = $null
        LocalhostForwarding = $null; Firewall = $null
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $evidence }

    $evidence['Exists'] = $true
    $evidence['Sha256'] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    foreach ($raw in (Get-Content -LiteralPath $path)) {
        $line = ([string]$raw).Trim()
        if (-not $line -or $line.StartsWith('#') -or $line.StartsWith(';') -or $line.StartsWith('[')) { continue }
        $parts = $line -split '=', 2
        if ($parts.Count -ne 2) { continue }
        $key = $parts[0].Trim().ToLowerInvariant()
        $value = $parts[1].Trim().Trim('"').Trim("'").ToLowerInvariant()
        switch ($key) {
            'networkingmode' { $evidence['NetworkingMode'] = $value }
            'hostaddressloopback' { $evidence['HostAddressLoopback'] = $value }
            'localhostforwarding' { $evidence['LocalhostForwarding'] = $value }
            'firewall' { $evidence['Firewall'] = $value }
        }
    }
    return $evidence
}

function Assert-SafeWsl {
    if ($null -eq (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        throw 'HOLD: WSL is unavailable. This helper will not enable Windows features automatically.'
    }
    $status = & wsl.exe --status 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'HOLD: WSL is not operational; no Windows feature or reboot will be initiated automatically.' }
    $version = & wsl.exe --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'HOLD: WSL version query failed.' }

    $config = Get-WslConfigEvidence
    if ($config['NetworkingMode'] -and $config['NetworkingMode'] -ne 'nat') {
        throw "HOLD: .wslconfig networkingMode=$($config['NetworkingMode']); G1 permits only default/NAT networking."
    }
    if ($config['HostAddressLoopback'] -eq 'true') { throw 'HOLD: hostAddressLoopback=true is not permitted.' }
    if ($config['LocalhostForwarding'] -eq 'false') { throw 'HOLD: localhostForwarding=false is incompatible with the G1 loopback qualification.' }
    if ($config['Firewall'] -eq 'false') { throw 'HOLD: firewall=false weakens the selected containment baseline.' }

    return [ordered]@{
        StatusText = (($status | Out-String).Trim())
        VersionText = (($version | Out-String).Trim())
        Config = $config
    }
}

function Get-MachineItem {
    $result = Invoke-Podman -Arguments @('machine', 'list', '--format', 'json')
    $all = @()
    if ($result.Output) { $all = @($result.Output | ConvertFrom-Json) }
    $matches = @($all | Where-Object { [string]$_.Name -eq $MachineName })
    if ($matches.Count -gt 1) { throw "HOLD: multiple machines named $MachineName were reported." }
    if ($matches.Count -eq 0) { return $null }
    return $matches[0]
}

function Get-MachineInspect {
    $result = Invoke-Podman -Arguments @('machine', 'inspect', $MachineName) -AllowFailure
    if ($result.ExitCode -ne 0) { return $null }
    $items = @($result.Output | ConvertFrom-Json)
    if ($items.Count -ne 1) { throw 'HOLD: expected one controlled-machine inspection result.' }
    return $items[0]
}

function Assert-MachinePolicy {
    $item = Get-MachineItem
    if ($null -eq $item) { throw "HOLD: machine $MachineName does not exist." }
    if ([string]$item.VMType -ne 'wsl') { throw "HOLD: machine provider is $($item.VMType), expected wsl." }
    if ([bool]$item.UserModeNetworking) { throw 'HOLD: WSL user-mode-networking is enabled; that WSL-wide mode is outside this G1 design.' }
    $inspect = Get-MachineInspect
    if ($null -eq $inspect) { throw 'HOLD: controlled machine cannot be inspected.' }
    if ([bool]$inspect.Rootful) { throw 'HOLD: controlled machine is rootful; G1 requires rootless.' }
    return [ordered]@{ ListItem = $item; Inspect = $inspect }
}

function Assert-RemoteRuntime {
    $client = Assert-PodmanClientVersion
    $machine = Assert-MachinePolicy
    $result = Invoke-Podman -Remote -Arguments @('info', '--format', 'json')
    $info = $result.Output | ConvertFrom-Json
    $server = [string]$info.version.Version
    if ($server -ne $PodmanVersion) { throw "HOLD: Podman server $server does not match pinned client $PodmanVersion." }
    if (-not [bool]$info.host.security.rootless) { throw 'HOLD: Podman server does not report rootless execution.' }
    return [ordered]@{ ClientVersion = $client; ServerVersion = $server; Rootless = $true; Machine = $machine }
}

function Get-Listeners {
    return @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in $ExpectedPorts } |
        Select-Object LocalAddress, LocalPort, OwningProcess)
}

function Assert-PortsFree {
    $listeners = @(Get-Listeners)
    if ($listeners.Count -gt 0) {
        $summary = ($listeners | ForEach-Object { "$($_.LocalAddress):$($_.LocalPort) pid=$($_.OwningProcess)" }) -join '; '
        throw "HOLD: G1 ports are already in use: $summary"
    }
}

function Wait-Loopback {
    param([int]$TimeoutSeconds = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $all = $true
        foreach ($port in $ExpectedPorts) {
            if (-not (Test-NetConnection 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)) { $all = $false }
        }
        if ($all) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw 'HOLD: timed out waiting for WebGoat/WebWolf loopback TCP availability.'
}

function Assert-ListenerPolicy {
    $listeners = @(Get-Listeners)
    foreach ($port in $ExpectedPorts) {
        $rows = @($listeners | Where-Object { $_.LocalPort -eq $port })
        if ($rows.Count -lt 1) { throw "HOLD: Windows reports no listener for $port." }
        foreach ($row in $rows) {
            if ([string]$row.LocalAddress -notin @('127.0.0.1', '::1')) {
                throw "HOLD: non-loopback listener $($row.LocalAddress):$port."
            }
        }
    }
    return $listeners
}

function Assert-NonLoopbackRejected {
    $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -and $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        Select-Object -ExpandProperty IPAddress -Unique)
    if ($addresses.Count -eq 0) { throw 'HOLD: no non-loopback IPv4 exists for negative containment validation.' }
    $checks = @()
    foreach ($address in $addresses) {
        foreach ($port in $ExpectedPorts) {
            $reachable = [bool](Test-NetConnection $address -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue)
            $checks += [pscustomobject]@{ Address = $address; Port = $port; Reachable = $reachable }
            if ($reachable) { throw "HOLD: service reachable through non-loopback ${address}:$port." }
        }
    }
    return $checks
}

function Get-ContainerId {
    return (Invoke-Podman -Remote -Arguments @('ps', '-a', '--filter', "name=^/$ContainerName$", '--format', '{{.ID}}')).Output.Trim()
}

function Get-Network {
    $result = Invoke-Podman -Remote -Arguments @('network', 'inspect', $NetworkName) -AllowFailure
    if ($result.ExitCode -ne 0) { return $null }
    $items = @($result.Output | ConvertFrom-Json)
    if ($items.Count -ne 1) { throw 'HOLD: expected one controlled-network inspection result.' }
    return $items[0]
}

function Remove-Workload {
    if (-not [string]::IsNullOrWhiteSpace((Get-ContainerId))) {
        [void](Invoke-Podman -Remote -Arguments @('rm', '-f', '-t', '0', $ContainerName))
    }
    if ($null -ne (Get-Network)) { [void](Invoke-Podman -Remote -Arguments @('network', 'rm', '-f', $NetworkName)) }
}

function Assert-PortsClosed {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        $open = $false
        foreach ($port in $ExpectedPorts) {
            if (Test-NetConnection 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue) { $open = $true }
        }
        if (-not $open) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw 'HOLD: controlled loopback ports remained reachable after cleanup.'
}

function Read-TargetLock {
    if (-not (Test-Path -LiteralPath $TargetLockPath -PathType Leaf)) { throw 'HOLD: target lock missing; run AcquireTarget.' }
    $lock = Get-Content -LiteralPath $TargetLockPath -Raw | ConvertFrom-Json
    if ([string]$lock.tag -ne $TargetTag -or [string]$lock.source_commit -ne $TargetSourceCommit) { throw 'HOLD: target-lock provenance mismatch.' }
    if ([string]$lock.manifest_digest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'HOLD: target-lock manifest digest is invalid.' }
    if ([string]$lock.reference -notmatch '^docker\.io/webgoat/webgoat@sha256:[0-9a-f]{64}$') { throw 'HOLD: target-lock digest reference is invalid.' }
    return $lock
}

if ($Action -eq 'Plan') {
    [pscustomobject]@{
        Authority = 'G1 only: prerequisites/acquisition/startup/containment; G2 CLOSED'
        Runtime = "Podman $PodmanVersion / $PodmanReleaseCommit / Apache-2.0"
        InstallerSHA256 = $PodmanInstallerSha256
        Machine = "$MachineName; provider=wsl; rootless; user-mode-networking=false; default connection unchanged"
        Target = "$TargetTag; source=$TargetSourceCommit; manifest digest locked after pull"
        Network = "$NetworkName; rootless --internal bridge"
        Bindings = '127.0.0.1:8080:8080 ; 127.0.0.1:9090:9090'
        State = $StateDirectory
        G2 = 'CLOSED — no HTTP crawling, scanning, lesson solving, injection, auth bypass, or exploit validation'
    } | Format-List
    exit 0
}

if ($Action -eq 'Preflight') {
    $wsl = Assert-SafeWsl
    $exe = Get-PodmanExe
    $podman = [ordered]@{ Installed = (-not [string]::IsNullOrWhiteSpace($exe)); Path = $exe; Version = $null }
    if ($podman['Installed']) { $podman['Version'] = Assert-PodmanClientVersion }
    Assert-PortsFree
    $receipt = [ordered]@{ schema_version=1; action='Preflight'; timestamp_utc=(Get-Date).ToUniversalTime().ToString('o'); wsl=$wsl; podman=$podman; result='PASS'; scope='G1 observation only' }
    Write-Output "G1 preflight PASS. Receipt: $(Write-Receipt $receipt)"
    exit 0
}

if ($Action -eq 'InstallRuntime') {
    [void](Assert-SafeWsl)
    Ensure-StateDirectory
    $msi = Join-Path $StateDirectory 'podman-installer-windows-amd64-v6.1.1.msi'
    $log = Join-Path $StateDirectory 'podman-msi-v6.1.1.log'
    Invoke-WebRequest -UseBasicParsing -Uri $PodmanInstallerUrl -OutFile $msi
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $msi).Hash.ToLowerInvariant()
    if ($hash -ne $PodmanInstallerSha256) { throw "HOLD: Podman MSI SHA mismatch: $hash" }
    $sig = Get-AuthenticodeSignature -FilePath $msi
    if ([string]$sig.Status -ne 'Valid') { throw "HOLD: Podman MSI signature status $($sig.Status)." }
    $proc = Start-Process msiexec.exe -Wait -PassThru -ArgumentList @('/package',$msi,'/quiet','/norestart','/l*v',$log,'MSIINSTALLPERUSER=1','MACHINE_PROVIDER=wsl')
    if ($proc.ExitCode -eq 3010) { throw 'HOLD: Podman install requested reboot; no reboot will be initiated automatically.' }
    if ($proc.ExitCode -ne 0) { throw "HOLD: Podman MSI exit $($proc.ExitCode); review $log." }
    $version = Assert-PodmanClientVersion
    $receipt = [ordered]@{ schema_version=1; action='InstallRuntime'; timestamp_utc=(Get-Date).ToUniversalTime().ToString('o'); version=$version; release_commit=$PodmanReleaseCommit; installer_sha256=$hash; signature=[string]$sig.Status; signer=[string]$sig.SignerCertificate.Subject; scope='per-user'; provider='wsl'; result='PASS' }
    Write-Output "Podman runtime install PASS. Receipt: $(Write-Receipt $receipt)"
    exit 0
}

if ($Action -eq 'InitMachine') {
    $wsl = Assert-SafeWsl
    [void](Assert-PodmanClientVersion)
    if ($null -eq (Get-MachineItem)) {
        [void](Invoke-Podman -Arguments @('machine','init','--provider','wsl','--rootful=false','--user-mode-networking=false','--update-connection=false','--import-native-ca=false','--tls-verify=true',$MachineName))
    }
    $item = Get-MachineItem
    if ($null -eq $item) { throw 'HOLD: controlled machine was not created.' }
    if ([string]$item.VMType -ne 'wsl' -or [bool]$item.UserModeNetworking) { throw 'HOLD: controlled machine provider/networking policy mismatch.' }
    if (-not [bool]$item.Running) { [void](Invoke-Podman -Arguments @('machine','start',$MachineName)) }
    $runtime = Assert-RemoteRuntime
    $receipt = [ordered]@{ schema_version=1; action='InitMachine'; timestamp_utc=(Get-Date).ToUniversalTime().ToString('o'); wsl=$wsl; runtime=$runtime; result='PASS'; scope='dedicated rootless WSL Podman machine only' }
    Write-Output "G1 Podman machine PASS. Receipt: $(Write-Receipt $receipt)"
    exit 0
}

if ($Action -eq 'AcquireTarget') {
    [void](Assert-SafeWsl)
    $runtime = Assert-RemoteRuntime
    [void](Invoke-Podman -Remote -Arguments @('pull',$TargetTag))
    $items = @((Invoke-Podman -Remote -Arguments @('image','inspect',$TargetTag)).Output | ConvertFrom-Json)
    if ($items.Count -ne 1) { throw 'HOLD: expected one WebGoat image inspection result.' }
    $image = $items[0]
    $manifestDigest = [string]$image.Digest
    if ($manifestDigest -notmatch '^sha256:[0-9a-f]{64}$') { throw "HOLD: invalid WebGoat manifest digest: $manifestDigest" }
    $reference = "docker.io/webgoat/webgoat@$manifestDigest"
    Ensure-StateDirectory
    $lock = [ordered]@{ schema_version=1; acquired_utc=(Get-Date).ToUniversalTime().ToString('o'); tag=$TargetTag; source_commit=$TargetSourceCommit; manifest_digest=$manifestDigest; reference=$reference; image_id=[string]$image.Id; repo_tags=@($image.RepoTags); repo_digests=@($image.RepoDigests); podman_client=$runtime['ClientVersion']; podman_server=$runtime['ServerVersion']; machine=$MachineName }
    $lock | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $TargetLockPath -Encoding UTF8
    $receipt = [ordered]@{ schema_version=1; action='AcquireTarget'; timestamp_utc=(Get-Date).ToUniversalTime().ToString('o'); target_lock=$lock; lock_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $TargetLockPath).Hash.ToLowerInvariant(); result='PASS'; scope='G1 target acquisition only' }
    Write-Output "WebGoat digest locked: $reference"
    Write-Output "Receipt: $(Write-Receipt $receipt)"
    exit 0
}

if ($Action -eq 'Stop') {
    $exe = Get-PodmanExe
    if (-not [string]::IsNullOrWhiteSpace($exe)) {
        $item = Get-MachineItem
        if ($null -ne $item -and [bool]$item.Running) {
            Remove-Workload
            Assert-PortsClosed
            [void](Invoke-Podman -Arguments @('machine','stop',$MachineName) -AllowFailure)
        }
    }
    Write-Output 'Controlled G1 workload and dedicated Podman machine are stopped when present.'
    exit 0
}

if ($Action -ne 'VerifyContainment') { throw "Unhandled action: $Action" }

$wsl = Assert-SafeWsl
$runtime = Assert-RemoteRuntime
$lock = Read-TargetLock
Assert-PortsFree
if (-not [string]::IsNullOrWhiteSpace((Get-ContainerId)) -or $null -ne (Get-Network)) { throw 'HOLD: stale controlled container/network exists; run Stop.' }

$imageItems = @((Invoke-Podman -Remote -Arguments @('image','inspect',[string]$lock.reference)).Output | ConvertFrom-Json)
if ($imageItems.Count -ne 1 -or [string]$imageItems[0].Id -ne [string]$lock.image_id -or [string]$imageItems[0].Digest -ne [string]$lock.manifest_digest) {
    throw 'HOLD: locally available WebGoat image no longer matches the digest lock.'
}

$started = $false
$networkCreated = $false
$receipt = [ordered]@{ schema_version=1; action='VerifyContainment'; timestamp_utc=(Get-Date).ToUniversalTime().ToString('o'); wsl=$wsl; runtime=$runtime; target=$lock; expected_bindings=$ExpectedBindings; result='HOLD'; scope='G1 TCP startup/containment only; no HTTP application request or vulnerability testing' }

try {
    [void](Invoke-Podman -Remote -Arguments @('network','create','--internal',$NetworkName))
    $networkCreated = $true
    $network = Get-Network
    if ($null -eq $network -or -not [bool]$network.internal) { throw 'HOLD: controlled network does not report internal=true.' }
    $receipt['network'] = $network

    $containerId = (Invoke-Podman -Remote -Arguments @('run','-d','--name',$ContainerName,'--network',$NetworkName,'-p','127.0.0.1:8080:8080','-p','127.0.0.1:9090:9090',[string]$lock.reference)).Output.Trim()
    if (-not $containerId) { throw 'HOLD: Podman returned no container ID.' }
    $started = $true
    $receipt['container_id'] = $containerId

    $ci = @((Invoke-Podman -Remote -Arguments @('inspect',$ContainerName)).Output | ConvertFrom-Json)
    if ($ci.Count -ne 1 -or -not [bool]$ci[0].State.Running) { throw 'HOLD: controlled WebGoat container is not running.' }
    foreach ($containerPort in $ExpectedBindings.Keys) {
        $expected = $ExpectedBindings[$containerPort]
        $bindings = @($ci[0].NetworkSettings.Ports.$containerPort)
        if ($bindings.Count -ne 1 -or [string]$bindings[0].HostIp -ne $expected['HostIp'] -or [string]$bindings[0].HostPort -ne $expected['HostPort']) {
            throw "HOLD: unexpected port mapping for $containerPort."
        }
    }

    Wait-Loopback
    $listeners = @(Assert-ListenerPolicy)
    $negative = @(Assert-NonLoopbackRejected)

    $route4 = (Invoke-Podman -Remote -Arguments @('exec',$ContainerName,'cat','/proc/net/route')).Output
    foreach ($line in ($route4 -split "`r?`n")) {
        $parts = @($line -split '\s+' | Where-Object { $_ })
        if ($parts.Count -ge 2 -and $parts[1] -eq '00000000') { throw 'HOLD: container has an IPv4 default route on the internal network.' }
    }
    $route6Result = Invoke-Podman -Remote -Arguments @('exec',$ContainerName,'cat','/proc/net/ipv6_route') -AllowFailure
    if ($route6Result.ExitCode -eq 0) {
        foreach ($line in ($route6Result.Output -split "`r?`n")) {
            $parts = @($line -split '\s+' | Where-Object { $_ })
            if ($parts.Count -ge 2 -and $parts[0] -eq ('0' * 32) -and $parts[1] -eq '00') { throw 'HOLD: container has an IPv6 default route on the internal network.' }
        }
    }

    $receipt['windows_listeners'] = $listeners
    $receipt['negative_nonloopback_checks'] = $negative
    $receipt['container_ipv4_routes'] = $route4
    $receipt['container_ipv6_routes'] = $route6Result.Output
    $receipt['loopback_tcp_available'] = $true
    $receipt['result'] = 'PASS'
} catch {
    $receipt['error'] = $_.Exception.Message
    throw
} finally {
    if ($started -or $networkCreated) {
        try {
            Remove-Workload
            Assert-PortsClosed
            $receipt['post_stop_ports_closed'] = $true
        } catch {
            $receipt['post_stop_ports_closed'] = $false
            $receipt['cleanup_error'] = $_.Exception.Message
            $receipt['result'] = 'HOLD'
        }
    }
    $receipt['receipt_written_utc'] = (Get-Date).ToUniversalTime().ToString('o')
    Write-Output "G1 Podman containment receipt: $(Write-Receipt $receipt)"
}

if ($receipt['result'] -ne 'PASS') { throw 'G1 Podman containment did not reach PASS.' }
Write-Output 'G1 Podman containment PASS. No HTTP application request or vulnerability test was performed; container/network were removed and controlled ports closed.'
